"""Swift vs. the 911 baseline: share of needs-help households picked up before water arrives.

Baseline: only some needs-help households get through to 911, each `lead_min` before its water arrives;
first come, first served. Swift: every needs-help household is known when its call completes; served in rank
order. Both use the same fleet: the earliest-free vehicle takes the next request and continues from that house."""
import math
import random
import time
from collections.abc import Callable

import numpy as np
import pandas as pd

from agent.script import Record
from pipeline.dispatch import BOARD_MIN, NO_ARRIVAL_MIN, _arrival, _lookup, rank
from pipeline.schedule import build_timeline
from pipeline.xp import to_numpy, xp

FLEET = 3  # 2 high-water vehicles + 1 boat
REACH_RATE = 0.55
LEAD_MIN = 20.0


def _serve(requests: list[tuple], travel_min: Callable[[str | None, str], float], fleet: int) -> int:
    """requests: (hid, known_t, deadline, priority). Returns how many are picked up by their deadline."""
    vehicles = [[0.0, None] for _ in range(fleet)]  # [free_at, at_household]
    pending, picked = list(requests), 0
    while pending:
        vehicle = min(vehicles, key=lambda v: v[0])
        t = max(vehicle[0], min(r[1] for r in pending))
        req = min((r for r in pending if r[1] <= t), key=lambda r: r[3])
        pending.remove(req)
        arrive = t + travel_min(vehicle[1], req[0])
        picked += arrive <= req[2]
        vehicle[0], vehicle[1] = (arrive + BOARD_MIN, req[0]) if math.isfinite(arrive) else (vehicle[0], vehicle[1])
    return picked


def compare(depths: pd.DataFrame, records: list[Record], travel_min: Callable[[str | None, str], float],
            known_at: dict[str, float] | None = None, fleet: int = FLEET, reach_rate: float = REACH_RATE,
            lead_min: float = LEAD_MIN, seed: int = 7) -> dict:
    """travel_min(from_household_id or None for staging, to_household_id) -> minutes."""
    lookup = _lookup(depths)
    needs = [r for r in records if r.status == "needs_help"]
    if not needs:
        return {"baseline_pct": 0.0, "swift_pct": 0.0}
    if known_at is None:
        answers = {r.id: r.status != "no_answer" for r in records}
        timeline = build_timeline(depths, answers, statuses={r.id: r.status for r in records})
        known_at = {e["household_id"]: e["t_min"] for e in timeline if e["event"] == "complete"}
    rng = random.Random(seed)
    deadline = {r.id: _arrival(lookup, r.id) for r in needs}
    reached = [r.id for r in needs if rng.random() < reach_rate]
    base = [(hid, max(0.0, deadline[hid] - lead_min), deadline[hid], max(0.0, deadline[hid] - lead_min)) for hid in reached]
    order = {item["household_id"]: i for i, item in enumerate(rank(needs, depths))}
    swift = [(r.id, known_at.get(r.id, 0.0), deadline[r.id], order[r.id]) for r in needs]
    pct = lambda n: round(100 * n / len(needs), 1)  # noqa: E731
    return {"baseline_pct": pct(_serve(base, travel_min, fleet)), "swift_pct": pct(_serve(swift, travel_min, fleet))}


def monte_carlo(depths: pd.DataFrame, records: list[Record], n: int = 1000, travel_min: float = 8.0,
                parallel: int = 20, call_min: float = 3.0, seed: int = 7) -> dict:
    """Baseline vs. Swift over `n` randomized flood nights, all nights at once as (n,) / (n, households) arrays.

    Per night: peak rise U(8, 16) ft scales arrival times by 12/peak (higher peak, earlier water); no-answer rate
    U(5%, 30%) hides households from Swift; fleet U{2..5}; 911 reach rate U(30%, 70%). Each pickup takes
    travel U(0.5, 1.5) x `travel_min` plus boarding. Requests are walked once in a fixed order (baseline: by
    deadline, which is its 911 order; Swift: rank order) and each goes to that night's earliest-free vehicle,
    so the loop is over households while every operation is vectorized across nights."""
    started = time.perf_counter()
    lookup = _lookup(depths)
    needs = [r for r in records if r.status == "needs_help"]
    if not needs:
        return {"median_baseline": 0.0, "median_swift": 0.0, "p10": 0.0, "p90": 0.0, "n": n, "seconds": 0.0}
    timeline = build_timeline(depths, {}, parallel=parallel, call_min=call_min)
    complete = {e["household_id"]: e["t_min"] for e in timeline if e["event"] == "complete"}
    ranked = [item["household_id"] for item in rank(needs, depths)]
    m = len(ranked)
    rng = np.random.default_rng(seed)
    peak = xp.asarray(rng.uniform(8, 16, n))
    no_answer = xp.asarray(rng.uniform(0.05, 0.30, n))
    fleet = xp.asarray(rng.integers(2, 6, n))
    reach = xp.asarray(rng.uniform(0.30, 0.70, n))
    draw_known, draw_reach = xp.asarray(rng.random((n, m))), xp.asarray(rng.random((n, m)))
    travel = xp.asarray(rng.uniform(0.5, 1.5, (n, m)) * travel_min)

    arrivals = [lookup.get(h, (None, 0.0))[0] for h in ranked]
    base_arrival = xp.asarray([math.nan if a is None else a for a in arrivals], dtype=xp.float64)
    deadline = xp.where(xp.isnan(base_arrival)[None], NO_ARRIVAL_MIN,
                        xp.minimum(NO_ARRIVAL_MIN, base_arrival[None] * (12.0 / peak)[:, None]))
    called_at = xp.asarray([complete.get(h, 0.0) for h in ranked], dtype=xp.float64)[None]
    swift_known = xp.where(draw_known >= no_answer[:, None], called_at, xp.inf)
    base_known = xp.where(draw_reach < reach[:, None], xp.maximum(0.0, deadline - LEAD_MIN), xp.inf)

    def serve(known, order) -> object:
        free = xp.where(xp.arange(5)[None] < fleet[:, None], 0.0, xp.inf)
        rows = xp.arange(n)
        picked = xp.zeros(n)
        for j in order:
            active = xp.isfinite(known[:, j])
            v = xp.argmin(free, axis=1)
            arrive = xp.maximum(free[rows, v], known[:, j]) + travel[:, j]
            picked += active & (arrive <= deadline[:, j])
            free[rows, v] = xp.where(active, arrive + BOARD_MIN, free[rows, v])
        return 100 * picked / m

    base_order = np.argsort(to_numpy(base_arrival), kind="stable")  # NaN (never floods) last
    base_pct, swift_pct = to_numpy(serve(base_known, base_order)), to_numpy(serve(swift_known, range(m)))
    return {"median_baseline": round(float(np.median(base_pct)), 1), "median_swift": round(float(np.median(swift_pct)), 1),
            "p10": round(float(np.percentile(swift_pct, 10)), 1), "p90": round(float(np.percentile(swift_pct, 90)), 1),
            "n": n, "seconds": round(time.perf_counter() - started, 3)}
