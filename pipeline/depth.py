"""Flood depth: HAND-lite (height above the local low point) against a rising water level, on the GB10 GPU.

depth_ft(t) = max(0, rise_ft(t) - hand_ft), with hand_ft = (dem - local 1 km minimum) in feet.
All time steps are computed as one (time x grid) array op."""
import csv
import math
import statistics
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from pipeline.area import Area, dem_bounds, dem_index
from pipeline.xp import BACKEND, ndimage, to_numpy, xp

PEAK_RISE_FT = 12.0
END_MIN = 360
STAGE_STEP_MIN = 30
ARRIVAL_DEPTH_FT = 0.5
WINDOW_PX = 101  # 1 km at 10 m resolution


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


def rise_curve(source: str = "replay") -> list[tuple[int, float]]:
    """Water-level rise (ft) per minute: a logistic storm curve reaching PEAK_RISE_FT by END_MIN."""
    if source != "replay":
        raise NotImplementedError("live source: rise comes from NWPS/USGS gauge forecasts")
    raw = [1 / (1 + math.exp(-(t - 150) / 35)) for t in range(END_MIN + 1)]
    low, high = raw[0], raw[-1]
    return [(t, round(PEAK_RISE_FT * (v - low) / (high - low), 3)) for t, v in enumerate(raw)]


def hand_ft(area: Area):
    dem = xp.asarray(area.dem, dtype=xp.float32)
    return (dem - ndimage.minimum_filter(dem, size=WINDOW_PX)) * 3.281


def household_depths(area: Area, curve: list[tuple[int, float]]) -> pd.DataFrame:
    hand = to_numpy(hand_ft(area))
    rises = np.array([r for _, r in curve])
    rows = []
    for house in area.households.itertuples():
        h = float(hand[dem_index(area, house.lon, house.lat)])
        flooded = np.nonzero(rises - h > ARRIVAL_DEPTH_FT)[0]
        rows.append({"id": house.id, "hand_ft": round(h, 2),
                     "water_arrival_min": int(curve[flooded[0]][0]) if len(flooded) else None,
                     "depth_ft_peak": round(max(0.0, PEAK_RISE_FT - h), 2)})
    return pd.DataFrame(rows)


def depth_stack(area: Area, rises: list[float]):
    """(stages, rows, cols) depth in feet, computed in one shot on the GPU when available."""
    return xp.clip(xp.asarray(rises, dtype=xp.float32)[:, None, None] - hand_ft(area)[None], 0, None)


def write_depth_stages(area: Area, curve: list[tuple[int, float]], out: Path) -> list[dict]:
    times = list(range(0, END_MIN + 1, STAGE_STEP_MIN))
    stack = to_numpy(depth_stack(area, [curve[t][1] for t in times]))
    bounds = dem_bounds(area)
    stages = []
    for t, depth in zip(times, stack):
        alpha = np.clip(depth / 6.0, 0, 1) * 210  # 6 ft and deeper = most opaque
        rgba = np.zeros(depth.shape + (4,), dtype=np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = 30, 120, 255
        rgba[..., 3] = np.where(depth > 0.05, alpha, 0).astype(np.uint8)
        name = f"depth_{t:03d}.png"
        Image.fromarray(rgba, "RGBA").save(out / name)
        stages.append({"t_min": t, "png": name, "bounds": bounds})
    print(f"depth stages: {len(stages)} computed with {BACKEND}")
    return stages
