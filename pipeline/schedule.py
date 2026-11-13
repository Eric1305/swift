"""Call schedule: dial every household in order of predicted water arrival, `parallel` lines at once.

A no-answer household keeps its line through both retries (rings at t, t+2, t+5) and is marked
`no_answer` once the last ring times out, RING_MIN after the final retry."""
import heapq
import math

import pandas as pd

RETRY_OFFSETS = (2.0, 5.0)
RING_MIN = 1.0


def call_order(depths: pd.DataFrame) -> list[str]:
    """Household ids by ascending water arrival; never-flooding households last."""
    arrival = pd.to_numeric(depths["water_arrival_min"], errors="coerce").fillna(math.inf)
    order = pd.DataFrame({"id": depths["id"].astype(str), "arrival": arrival}).sort_values(["arrival", "id"], kind="stable")
    return order["id"].tolist()


def build_timeline(depths: pd.DataFrame, answers: dict[str, bool], parallel: int = 20, call_min: float = 3.0,
                   statuses: dict[str, str] | None = None) -> list[dict]:
    statuses = statuses or {}
    lines = [0.0] * parallel
    heapq.heapify(lines)
    events = []
    for seq, hid in enumerate(call_order(depths)):
        t = heapq.heappop(lines)
        events.append((t, seq, 0, {"t_min": round(t, 2), "household_id": hid, "event": "call_start"}))
        if answers.get(hid, True):
            end = t + call_min
            events.append((end, seq, 3, {"t_min": round(end, 2), "household_id": hid, "event": "complete",
                                         "status": statuses.get(hid, "safe")}))
        else:
            for i, offset in enumerate(RETRY_OFFSETS, start=1):
                events.append((t + offset, seq, i, {"t_min": round(t + offset, 2), "household_id": hid, "event": "retry"}))
            end = t + RETRY_OFFSETS[-1] + RING_MIN
            events.append((end, seq, 3, {"t_min": round(end, 2), "household_id": hid, "event": "no_answer",
                                         "status": "no_answer"}))
        heapq.heappush(lines, end)
    # at equal times, finished calls come before new ones so a line is never double-counted
    events.sort(key=lambda e: (e[0], e[2] == 0, e[1], e[2]))
    return [e[3] for e in events]
