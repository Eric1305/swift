import numpy as np
import pandas as pd

from pipeline.depth import (END_MIN, REPLAY_END, REPLAY_START, depth_grid, forecast_trend, observed_curve,
                            pool_at, pool_readings)
from pipeline.schedule import call_order


def test_only_ground_connected_to_the_pool_floods():
    ground = np.array([[100.0, 101.0, 110.0, 102.0],
                       [100.0, 101.0, 110.0, 102.0]])
    depth = depth_grid(ground, 105.0)
    assert depth[0, 0] == 5.0 and depth[0, 1] == 4.0
    assert depth[0, 3] == 0.0  # below the pool but cut off by the 110 ft ridge
    assert depth[0, 2] == 0.0


def test_observed_curve_replays_the_gauge():
    readings = pool_readings()
    curve = observed_curve(readings)
    assert len(curve) == END_MIN + 1
    assert curve[0][1] == round(pool_at(readings, REPLAY_START), 3)
    assert curve[-1][1] == round(pool_at(readings, REPLAY_END), 3) == max(level for _, level in curve)
    assert all(b >= a for (_, a), (_, b) in zip(curve, curve[1:]))  # the pool only rises Aug 27-30


def test_forecast_uses_only_readings_before_the_trigger():
    readings = pool_readings()
    before = [(when, level) for when, level in readings if when <= REPLAY_START]
    altered = before + [(when, level + 50) for when, level in readings[len(before):]]
    assert forecast_trend(altered) == forecast_trend(readings)


def test_call_order_uses_forecast_then_ground():
    depths = pd.DataFrame({"id": ["a", "b", "c", "d"], "ground_ft": [104.0, 102.0, 103.0, 101.0],
                           "water_arrival_min": [10, None, 30, 5],  # observed: never used for the order
                           "forecast_arrival_min": [120, 100, 110, 100]})
    assert call_order(depths) == ["d", "b", "c", "a"]
