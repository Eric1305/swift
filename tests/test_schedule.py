import pandas as pd

from pipeline.schedule import build_timeline


def _depths(arrivals: dict) -> pd.DataFrame:
    return pd.DataFrame({"id": list(arrivals), "hand_ft": 1.0, "water_arrival_min": list(arrivals.values()),
                         "depth_ft_peak": 2.0})


def test_no_answer_retries_then_marks():
    depths = _depths({"h001": 40, "h002": 90})
    timeline = build_timeline(depths, {"h001": False, "h002": True})
    mine = [e for e in timeline if e["household_id"] == "h001"]
    t = mine[0]["t_min"]
    assert [(e["event"], e["t_min"] - t) for e in mine[:3]] == [("call_start", 0), ("retry", 2), ("retry", 5)]
    assert mine[-1]["event"] == "no_answer" and mine[-1]["status"] == "no_answer"
    assert mine[-1]["t_min"] > t + 5 and len(mine) == 4


def test_call_order_follows_arrival():
    arrivals = {f"h{i:03d}": a for i, a in enumerate([200, 35, None, 120, 80, 15, 300, 60, 90, None, 45, 150])}
    answers = {hid: i % 3 != 0 for i, hid in enumerate(arrivals)}
    parallel = 3
    timeline = build_timeline(_depths(arrivals), answers, parallel=parallel)
    starts = [e for e in timeline if e["event"] == "call_start"]
    assert starts[0]["household_id"] == "h005"
    assert [e["t_min"] for e in timeline] == sorted(e["t_min"] for e in timeline)
    active = 0
    for e in timeline:
        if e["event"] == "call_start":
            active += 1
        elif e["event"] in ("complete", "no_answer"):
            active -= 1
        assert active <= parallel
    assert active == 0
