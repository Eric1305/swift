"""Build the dashboard fixtures.

  python -m pipeline.build --source replay --stage base --out web/public/data      # area, depth, households
  python -m pipeline.build --source replay --stage dispatch --out web/public/data  # needs records/ from agent.simulate
"""
import argparse
import json
import os
from pathlib import Path

import pandas as pd

from pipeline.area import DEMO_BBOX, load_area, write_households
from pipeline.depth import (END_MIN, GAUGE, REPLAY_START, TIME_SCALE, forecast_trend, harvey_rain_mm, household_depths,
                            observed_curve, write_depth_stages)

CACHE = Path(__file__).resolve().parent / "cache"
DATA_DIR = Path(os.environ.get("SWIFT_DATA_DIR", Path.home() / "Texas_Flood_Student_Data"))


def build_base(source: str, out: Path) -> None:
    area = load_area(DEMO_BBOX, CACHE)
    if source != "replay":
        raise NotImplementedError("live source: the pool comes from the gauge's real-time feed and USACE projections")
    curve = observed_curve()
    depths = household_depths(area, curve)
    depths.to_csv(CACHE / "depths.csv", index=False)
    stages = write_depth_stages(area, curve, out)
    write_households(area, depths, out / "households.geojson")

    houses = area.households.merge(depths, on="id")
    now, rate = forecast_trend()
    west, south, east, north = DEMO_BBOX
    center = ((west + east) / 2, (south + north) / 2)
    flooding = houses.dropna(subset=["water_arrival_min"])
    median_arrival = flooding["water_arrival_min"].median()
    candidates = flooding[(flooding["water_arrival_min"] - median_arrival).abs() <= 30]
    distance = (candidates["lon"] - center[0]) ** 2 + (candidates["lat"] - center[1]) ** 2
    demo_id = candidates.loc[distance.idxmin(), "id"] if len(candidates) else houses.iloc[0]["id"]
    if (out / "meta.json").exists():  # keep the live-call house stable across rebuilds
        demo_id = json.loads((out / "meta.json").read_text()).get("demo_household_id", demo_id)
    highest = houses.loc[houses["ground_ft"].idxmax()]

    meta = {
        "demo_household_id": demo_id,
        "center": [round(center[0], 5), round(center[1], 5)],
        "zoom": 14.3, "pitch": 50, "bearing": -20,
        "timeline": {"start_iso": REPLAY_START.isoformat(), "end_min": END_MIN, "step_min": 1,
                     "time_scale": TIME_SCALE},
        "staging": [float(highest["lon"]), float(highest["lat"])],
        "hub": [round(west + 0.004, 5), round(north - 0.004, 5)],
        "rain_3d_mm": harvey_rain_mm(DATA_DIR / "image_metadata.csv", DEMO_BBOX),
        "gauge": {"name": GAUGE, "pool_ft_at_trigger": round(now, 2), "rise_ft_per_day": round(rate * 1440 / TIME_SCALE, 1),
                  "pool_ft_peak": max(level for _, level in curve)},
        "depth_stages": stages,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    arrivals = depths["water_arrival_min"]
    print(f"{len(depths)} households: {arrivals.notna().sum()} flood (arrival min {arrivals.min()}, "
          f"median {arrivals.median()}, max {arrivals.max()}), {arrivals.isna().sum()} stay dry; demo house {demo_id}")
    flooded = depths.dropna(subset=["water_arrival_min"])
    agreement = flooded["forecast_arrival_min"].corr(flooded["water_arrival_min"], method="spearman")
    print(f"trigger: pool {now:.1f} ft rising {rate * 1440 / TIME_SCALE:.1f} ft/day; forecast ETAs "
          f"{depths['forecast_arrival_min'].min():.0f}-{depths['forecast_arrival_min'].max():.0f} min; "
          f"rank agreement with observed arrival {agreement:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="replay", choices=["replay", "live"])
    parser.add_argument("--stage", default="base", choices=["base", "dispatch"])
    parser.add_argument("--out", type=Path, default=Path("web/public/data"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.stage == "base":
        build_base(args.source, args.out)
    else:
        from pipeline.dispatch import build_dispatch

        build_dispatch(args.source, args.out, CACHE, pd.read_csv(CACHE / "depths.csv"))


if __name__ == "__main__":
    main()
