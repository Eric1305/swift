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
from pipeline.depth import END_MIN, harvey_rain_mm, household_depths, rise_curve, write_depth_stages

CACHE = Path(__file__).resolve().parent / "cache"
DATA_DIR = Path(os.environ.get("SWIFT_DATA_DIR", Path.home() / "Texas_Flood_Student_Data"))


def build_base(source: str, out: Path) -> None:
    area = load_area(DEMO_BBOX, CACHE)
    curve = rise_curve(source)
    depths = household_depths(area, curve)
    depths.to_csv(CACHE / "depths.csv", index=False)
    stages = write_depth_stages(area, curve, out)
    write_households(area, depths, out / "households.geojson")

    houses = area.households.merge(depths, on="id")
    west, south, east, north = DEMO_BBOX
    center = ((west + east) / 2, (south + north) / 2)
    flooding = houses.dropna(subset=["water_arrival_min"])
    median_arrival = flooding["water_arrival_min"].median()
    candidates = flooding[(flooding["water_arrival_min"] - median_arrival).abs() <= 30]
    distance = (candidates["lon"] - center[0]) ** 2 + (candidates["lat"] - center[1]) ** 2
    demo_id = candidates.loc[distance.idxmin(), "id"] if len(candidates) else houses.iloc[0]["id"]
    highest = houses.loc[houses["hand_ft"].idxmax()]

    meta = {
        "demo_household_id": demo_id,
        "center": [round(center[0], 5), round(center[1], 5)],
        "zoom": 14.3, "pitch": 50, "bearing": -20,
        "timeline": {"start_iso": "2017-08-27T00:00:00-05:00", "end_min": END_MIN, "step_min": 1},
        "staging": [float(highest["lon"]), float(highest["lat"])],
        "hub": [round(west + 0.004, 5), round(north - 0.004, 5)],
        "rain_3d_mm": harvey_rain_mm(DATA_DIR / "image_metadata.csv", DEMO_BBOX),
        "depth_stages": stages,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    arrivals = depths["water_arrival_min"]
    print(f"{len(depths)} households: {arrivals.notna().sum()} flood (arrival min {arrivals.min()}, "
          f"median {arrivals.median()}, max {arrivals.max()}), {arrivals.isna().sum()} stay dry; demo house {demo_id}")


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
