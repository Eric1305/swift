"""Flood depth: the observed Addicks Reservoir pool replayed over the 3DEP ground, on the GB10 GPU when available.

Bear Creek floods when the Addicks pool backs into it, and a reservoir pool is close to flat, so
depth_ft(t) = pool_ft(t) - ground_ft wherever that ground is connected to the main body of water.
The pool is USGS gauge 08073000's daily mean (ft NAVD88, the same datum as 3DEP), published in real time.

Two views of the same water:
  observed  - what the gauge recorded, Aug 27 00:00 to the Aug 30 peak, compressed into END_MIN replay minutes.
              It drives the map and every "did help arrive before the water" score.
  forecast  - what Swift could know at the trigger (replay minute 0): the gauge's readings up to then and
              their rise rate, giving each home an ETA. It drives the call order and the rescue ranking. Because the
              pool is flat and rising, that order is simply lowest ground first; the rate only sets the ETAs."""
import csv
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from pipeline.area import Area, dem_bounds, dem_index
from pipeline.xp import BACKEND, ndimage, to_numpy, xp

GAUGE = "USGS 08073000 Addicks Reservoir near Addicks, TX"
POOL_CSV = Path(__file__).resolve().parent / "data" / "addicks_pool_2017.csv"
CDT = timezone(timedelta(hours=-5))
REPLAY_START = datetime(2017, 8, 27, 0, 0, tzinfo=CDT)  # trigger
REPLAY_END = datetime(2017, 8, 30, 12, 0, tzinfo=CDT)   # observed peak (daily means are placed at noon)
END_MIN = 360
TIME_SCALE = (REPLAY_END - REPLAY_START).total_seconds() / 60 / END_MIN  # real minutes per replay minute
STAGE_STEP_MIN = 30
ARRIVAL_DEPTH_FT = 0.5
EIGHT_WAY = np.ones((3, 3), dtype=bool)


def harvey_rain_mm(metadata_csv: Path, bbox) -> float:
    """Median 3-day rainfall before the response images inside the bbox (the dataset's own Harvey record)."""
    values = []
    if metadata_csv.exists():
        with open(metadata_csv, newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    lon, lat = float(row["longitude"]), float(row["latitude"])
                    rain = float(row["preceding_3d_precipitation_mm"])
                except (KeyError, ValueError):
                    continue
                if row.get("image_role") == "response" and bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]:
                    values.append(rain)
    return statistics.median(values) if values else 754.0


def pool_readings(path: Path = POOL_CSV) -> list[tuple[datetime, float]]:
    """Daily mean pool elevations, each placed at local noon of its day."""
    with open(path, newline="") as handle:
        return [(datetime.combine(date.fromisoformat(r["date"]), datetime.min.time(), CDT) + timedelta(hours=12),
                 float(r["pool_ft_navd88"])) for r in csv.DictReader(handle)]


def pool_at(readings: list[tuple[datetime, float]], when: datetime) -> float:
    """Linear interpolation between readings (missing days are bridged)."""
    xs = [w.timestamp() for w, _ in readings]
    return float(np.interp(when.timestamp(), xs, [v for _, v in readings]))


def real_time(t_min: float) -> datetime:
    return REPLAY_START + timedelta(minutes=t_min * TIME_SCALE)


def observed_curve(readings=None) -> list[tuple[int, float]]:
    """Pool elevation (ft NAVD88) for every replay minute."""
    readings = readings or pool_readings()
    return [(t, round(pool_at(readings, real_time(t)), 3)) for t in range(END_MIN + 1)]


def forecast_trend(readings=None) -> tuple[float, float]:
    """(pool ft at the trigger, ft per replay minute): all Swift knows about the water. Uses only the last two
    daily readings published before the trigger, carried forward to it at their slope."""
    readings = readings or pool_readings()
    (t0, a), (t1, b) = [r for r in readings if r[0] <= REPLAY_START][-2:]
    per_real_min = (b - a) / ((t1 - t0).total_seconds() / 60)
    now = b + per_real_min * (REPLAY_START - t1).total_seconds() / 60
    return now, per_real_min * TIME_SCALE


def forecast_arrivals(ground: pd.Series, readings=None) -> pd.Series:
    """Replay minute each home's ground + ARRIVAL_DEPTH_FT is reached if the trigger-time trend holds."""
    now, rate = forecast_trend(readings)
    return ((ground + ARRIVAL_DEPTH_FT - now) / rate).clip(lower=0).round(0)


def ground_ft(area: Area):
    return xp.asarray(area.dem, dtype=xp.float32) * 3.281


def depth_grid(ground, level: float):
    """Depth (ft) at one pool level: only ground below the pool and connected to its lowest cell is wet."""
    wet = ground < level
    labels, _ = ndimage.label(wet, structure=xp.asarray(EIGHT_WAY))
    main = labels.ravel()[int(xp.argmin(ground))]
    return xp.where((labels == main) & wet, level - ground, 0.0)


def household_depths(area: Area, curve: list[tuple[int, float]]) -> pd.DataFrame:
    """Per house: ground elevation, observed first minute with >= ARRIVAL_DEPTH_FT of water and depth at the
    end, and the trigger-time forecast arrival."""
    ground = ground_ft(area)
    cells = [dem_index(area, h.lon, h.lat) for h in area.households.itertuples()]
    rows_idx, cols_idx = xp.asarray([r for r, _ in cells]), xp.asarray([c for _, c in cells])
    arrival = [None] * len(cells)
    depth = np.zeros(len(cells))
    last_level = None
    for t, level in curve:
        if level == last_level:
            continue
        last_level = level
        depth = to_numpy(depth_grid(ground, level)[rows_idx, cols_idx])
        for i in np.nonzero(depth >= ARRIVAL_DEPTH_FT)[0]:
            if arrival[i] is None:
                arrival[i] = t
    g = to_numpy(ground[rows_idx, cols_idx])
    out = pd.DataFrame({"id": area.households["id"].tolist(), "ground_ft": np.round(g, 2),
                        "water_arrival_min": arrival, "depth_ft_peak": np.round(depth, 2)})
    out["forecast_arrival_min"] = forecast_arrivals(out["ground_ft"])
    return out


def edge_depths(area: Area, lonlats: list[tuple[float, float]], curve: list[tuple[int, float]]) -> np.ndarray:
    """(minutes, points) depth in feet at each point for every minute of the curve (for depth-aware routing)."""
    ground = ground_ft(area)
    cells = [dem_index(area, lon, lat) for lon, lat in lonlats]
    rows_idx, cols_idx = xp.asarray([r for r, _ in cells]), xp.asarray([c for _, c in cells])
    out, cache = np.zeros((len(curve), len(cells)), dtype=np.float32), {}
    for t, level in curve:
        if level not in cache:
            cache[level] = to_numpy(depth_grid(ground, level)[rows_idx, cols_idx])
        out[t] = cache[level]
    return out


def write_depth_stages(area: Area, curve: list[tuple[int, float]], out: Path) -> list[dict]:
    times = list(range(0, END_MIN + 1, STAGE_STEP_MIN))
    ground = ground_ft(area)
    bounds = dem_bounds(area)
    stages = []
    from scipy.ndimage import gaussian_filter

    # Three-stop ramp: shallow cyan -> mid blue -> deep navy, so depth reads as hue, not just opacity.
    stops = np.array([[150, 214, 252], [64, 140, 232], [20, 62, 160]], dtype=float)
    for t in times:
        depth = gaussian_filter(to_numpy(depth_grid(ground, curve[t][1])), sigma=1.5)  # soften DEM noise
        k = np.clip(depth / 6.0, 0, 1)
        lo = np.clip(k * 2, 0, 1)[..., None]
        hi = np.clip(k * 2 - 1, 0, 1)[..., None]
        rgb = np.where(k[..., None] < 0.5, stops[0] * (1 - lo) + stops[1] * lo, stops[1] * (1 - hi) + stops[2] * hi)
        rgba = np.zeros(depth.shape + (4,), dtype=np.uint8)
        rgba[..., :3] = rgb.astype(np.uint8)
        wet = depth > 0.3
        rgba[..., 3] = np.where(wet, 165 + 70 * k, 0).astype(np.uint8)
        name = f"depth_{t:03d}.png"
        Image.fromarray(rgba, "RGBA").save(out / name)
        stages.append({"t_min": t, "png": name, "bounds": bounds})
    print(f"depth stages: {len(stages)} computed with {BACKEND}")
    return stages
