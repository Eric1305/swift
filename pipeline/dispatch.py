"""Rescue queue, depth-aware vehicle routes and door-knock clusters from the call records."""
import json
import math
import time
from collections.abc import Callable
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, mapping

from agent.script import Record
from pipeline.schedule import build_timeline

NO_ARRIVAL_MIN = 360.0
BOARD_MIN = 10.0
CLUSTER_M = 300.0
VEHICLES = {  # kind: (depth limit ft, mph)
    "hwv": (3.0, 25.0),
    "boat": (math.inf, 8.0),
    "neighbor_truck": (3.0, 25.0),
    "neighbor_boat": (math.inf, 8.0),
}
LonLat = tuple[float, float]


def _lookup(depths: pd.DataFrame) -> dict[str, tuple[float | None, float]]:
    out = {}
    for row in depths.itertuples():
        arrival = pd.to_numeric(row.water_arrival_min, errors="coerce")
        out[str(row.id)] = (None if pd.isna(arrival) else float(arrival), float(row.depth_ft_peak or 0.0))
    return out


def _arrival(lookup: dict, hid: str) -> float:
    arrival = lookup.get(hid, (None, 0.0))[0]
    return NO_ARRIVAL_MIN if arrival is None else arrival


def rank(records: list[Record], depths: pd.DataFrame) -> list[dict]:
    lookup = _lookup(depths)
    ranked = []
    for rec in records:
        if rec.status != "needs_help":
            continue
        arrival, peak = lookup.get(rec.id, (None, 0.0))
        score = (100 * bool(rec.cant_leave_alone) + 50 * bool(rec.water_inside) + 10 * peak
                 - 0.1 * (NO_ARRIVAL_MIN if arrival is None else arrival))
        reasons = []
        needs = [p.get("need") or p.get("who") for p in rec.cant_leave_alone]
        if needs := [n for n in needs if n]:
            reasons.append(", ".join(dict.fromkeys(needs)))
        if rec.water_inside:
            reasons.append("water inside")
        if peak > 0:
            reasons.append(f"{peak:.1f} ft peak")
        reasons.append(f"water in ~{arrival:.0f} min" if arrival is not None else "no flooding forecast")
        ranked.append({"household_id": rec.id, "score": round(score, 1), "reasons": reasons})
    return sorted(ranked, key=lambda r: (-r["score"], r["household_id"]))


def _nearest_node(graph: nx.MultiDiGraph, lonlat: LonLat):
    nodes = list(graph.nodes)
    xy = np.array([(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in nodes], dtype=float)
    lat0 = math.radians(lonlat[1])
    d = ((xy[:, 0] - lonlat[0]) * math.cos(lat0)) ** 2 + (xy[:, 1] - lonlat[1]) ** 2
    return nodes[int(np.argmin(d))]


def _edge_length(graph, u, v) -> float:
    return min(float(d.get("length", 0.0)) for d in graph.get_edge_data(u, v).values())


def routes(graph: nx.MultiDiGraph, ranked: list[dict], records: list[Record], depths: pd.DataFrame,
           households_lonlat: dict[str, LonLat], staging: LonLat,
           edge_depth_ft: Callable[[object, object, dict, float], float],
           known_at: dict[str, float] | None = None) -> list[dict]:
    """Greedy: each request (rank order) goes to the vehicle that reaches it first. A vehicle departs when
    it is free and the request is known (`known_at`, default 0), and avoids edges deeper than its limit."""
    known_at = known_at or {}
    nearest = {hid: _nearest_node(graph, ll) for hid, ll in households_lonlat.items()}
    staging_node = _nearest_node(graph, staging)
    fleet = [{"id": f"hwv-{i}", "kind": "hwv", "node": staging_node, "free": 0.0} for i in (1, 2)]
    fleet.append({"id": "boat-1", "kind": "boat", "node": staging_node, "free": 0.0})
    for rec in records:
        if rec.status == "can_help" and (rec.can_help.boat or rec.can_help.truck) and rec.id in nearest:
            kind = "neighbor_boat" if rec.can_help.boat else "neighbor_truck"
            fleet.append({"id": f"nbr-{rec.id}", "kind": kind, "node": nearest[rec.id], "free": known_at.get(rec.id, 0.0)})

    def passable(limit: float, t: float):
        if math.isinf(limit):
            return graph
        return nx.subgraph_view(graph, filter_edge=lambda u, v, k: edge_depth_ft(u, v, graph[u][v][k], t) <= limit)

    out = []
    for req in ranked:
        hid = req["household_id"]
        if hid not in nearest:
            continue
        best = None
        for vehicle in fleet:
            limit, mph = VEHICLES[vehicle["kind"]]
            depart = max(vehicle["free"], known_at.get(hid, 0.0))
            try:
                meters, path = nx.single_source_dijkstra(passable(limit, depart), vehicle["node"], nearest[hid], weight="length")
            except nx.NetworkXNoPath:
                continue
            arrive = depart + meters / (mph * 1609.34 / 60)
            if best is None or arrive < best[0]:
                best = (arrive, depart, vehicle, path, mph)
        if best is None:
            continue
        arrive, depart, vehicle, path, mph = best
        stamps, t = [depart], depart
        for u, v in zip(path, path[1:]):
            t += _edge_length(graph, u, v) / (mph * 1609.34 / 60)
            stamps.append(t)
        path = path + [path[-1]]  # dwell while boarding
        stamps.append(arrive + BOARD_MIN)
        out.append({"vehicle_id": vehicle["id"], "vehicle": vehicle["kind"], "to_household_id": hid,
                    "path": [[round(graph.nodes[n]["x"], 6), round(graph.nodes[n]["y"], 6)] for n in path],
                    "timestamps": [round(s, 2) for s in stamps]})
        vehicle["free"], vehicle["node"] = arrive + BOARD_MIN, nearest[hid]
    return out


def haversine_m(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def doorknock(no_answer_lonlat: dict[str, LonLat], t_min: float) -> dict:
    """Group no-answer households within CLUSTER_M of each other (single linkage) into hull polygons."""
    ids = sorted(no_answer_lonlat)
    parent = {i: i for i in ids}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if haversine_m(no_answer_lonlat[a], no_answer_lonlat[b]) <= CLUSTER_M:
                parent[root(a)] = root(b)
    clusters: dict[str, list[str]] = {}
    for i in ids:
        clusters.setdefault(root(i), []).append(i)
    features = []
    for members in clusters.values():
        hull = MultiPoint([no_answer_lonlat[m] for m in members]).convex_hull.buffer(0.0004, quad_segs=4)
        features.append({"type": "Feature", "geometry": mapping(hull),
                         "properties": {"t_min": round(t_min, 2), "household_ids": members}})
    return {"type": "FeatureCollection", "features": features}


def _queue(timeline: list[dict], records: dict[str, Record], depths: pd.DataFrame, min_gap: float = 3.0) -> list[dict]:
    snapshots, known, last = [], [], None
    completes = [e for e in timeline if e["event"] == "complete" and e.get("status") == "needs_help"]
    for i, event in enumerate(completes):
        known.append(records[event["household_id"]])
        is_last = i == len(completes) - 1
        if not is_last and completes[i + 1]["t_min"] == event["t_min"]:
            continue
        if last is not None and event["t_min"] - last < min_gap and not is_last:
            continue
        ranked = rank(known, depths)
        if snapshots and snapshots[-1]["t_min"] == event["t_min"]:
            snapshots.pop()
        snapshots.append({"t_min": event["t_min"], "ranked": ranked})
        last = event["t_min"]
    return snapshots


def build_dispatch(source: str, out: Path, cache: Path, depths: pd.DataFrame) -> None:
    from pipeline.area import DEMO_BBOX, dem_index, load_area
    from pipeline.baseline import compare, monte_carlo
    from pipeline.depth import hand_ft, rise_curve
    from pipeline.xp import BACKEND, to_numpy

    depths = depths.assign(id=depths["id"].astype(str))
    records = {r.id: r for r in (Record.model_validate_json(p.read_text()) for p in sorted((out / "records").glob("*.json")))}
    answers_path = out / "answers.json"
    answers = json.loads(answers_path.read_text()) if answers_path.exists() else {}
    answers = {hid: answers.get(hid, rec.status != "no_answer") for hid, rec in records.items()}
    statuses = {hid: rec.status for hid, rec in records.items()}
    called = depths[depths["id"].isin(records)]

    timeline = build_timeline(called, answers, statuses=statuses)
    (out / "timeline.json").write_text(json.dumps(timeline, indent=1) + "\n")
    known_at = {e["household_id"]: e["t_min"] for e in timeline if e["event"] == "complete"}
    (out / "queue.json").write_text(json.dumps(_queue(timeline, records, called), indent=1) + "\n")

    area = load_area(DEMO_BBOX, cache)
    graph = area.graph
    hand = to_numpy(hand_ft(area))
    rises = [r for _, r in rise_curve(source)]
    edge_hand = {}
    for u, v in graph.edges():
        lon = (graph.nodes[u]["x"] + graph.nodes[v]["x"]) / 2
        lat = (graph.nodes[u]["y"] + graph.nodes[v]["y"]) / 2
        edge_hand[(u, v)] = float(hand[dem_index(area, lon, lat)])

    def edge_depth_ft(u, v, data, t: float) -> float:
        return max(0.0, rises[int(min(max(t, 0), len(rises) - 1))] - edge_hand[(u, v)])

    lonlat = {str(h.id): (float(h.lon), float(h.lat)) for h in area.households.itertuples()}
    meta = json.loads((out / "meta.json").read_text())
    ranked = rank(list(records.values()), called)
    trips = routes(graph, ranked, list(records.values()), called, lonlat, tuple(meta["staging"]), edge_depth_ft, known_at)
    (out / "routes.json").write_text(json.dumps(trips) + "\n")

    no_answer = [e for e in timeline if e["event"] == "no_answer"]
    knock = doorknock({e["household_id"]: lonlat[e["household_id"]] for e in no_answer if e["household_id"] in lonlat},
                      max((e["t_min"] for e in no_answer), default=0.0))
    (out / "doorknock.geojson").write_text(json.dumps(knock) + "\n")

    staging_node = _nearest_node(graph, tuple(meta["staging"]))
    node_of = {hid: _nearest_node(graph, ll) for hid, ll in lonlat.items()}
    lengths: dict = {}

    def travel_min(src: str | None, dst: str) -> float:
        a = staging_node if src is None else node_of[src]
        if a not in lengths:
            lengths[a] = nx.single_source_dijkstra_path_length(graph, a, weight="length")
        return lengths[a].get(node_of[dst], math.inf) / (VEHICLES["hwv"][1] * 1609.34 / 60)

    results_path = out / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    results.update(compare(called, list(records.values()), travel_min, known_at=known_at))
    started = time.perf_counter()
    results["mc"] = monte_carlo(called, list(records.values()))
    results_path.write_text(json.dumps(results, indent=2) + "\n")
    print(f"timeline {len(timeline)} events, {len(ranked)} need help, {len(trips)} routes, "
          f"{len(knock['features'])} door-knock clusters; baseline {results['baseline_pct']}% vs swift "
          f"{results['swift_pct']}%; monte carlo {results['mc']['n']} nights in "
          f"{time.perf_counter() - started:.2f}s on {BACKEND}")
