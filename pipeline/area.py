"""The demo area: households (OSM building footprints), the drive network, and the 3DEP elevation grid."""
import json
import random
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox

# Bear Creek, west Houston (Addicks Reservoir backflow, Harvey 2017): dense homes + 21 georeferenced response images.
DEMO_BBOX = (-95.66, 29.835, -95.62, 29.865)  # (west, south, east, north)
N_HOUSEHOLDS = 150
SEED = 7
HOUSE_TYPES = {"house", "residential", "detached", "semidetached_house", "yes"}


OVERPASS_MIRRORS = ["https://maps.mail.ru/osm/tools/overpass/api", "https://overpass-api.de/api",
                    "https://overpass.kumi.systems/api", "https://overpass.private.coffee/api"]
ox.settings.http_user_agent = "Swift flood-response hackathon (UTSA datathon)"
ox.settings.requests_timeout = 300


def _with_mirrors(fetch):
    """Overpass mirrors refuse or rate-limit unpredictably; try each in turn."""
    error = None
    for url in OVERPASS_MIRRORS:
        ox.settings.overpass_url = url
        try:
            return fetch()
        except Exception as exc:  # noqa: BLE001 - any mirror failure means try the next one
            error = exc
            print(f"overpass mirror failed ({url}): {str(exc)[:120]}")
    raise error


@dataclass
class Area:
    bbox: tuple[float, float, float, float]
    households: gpd.GeoDataFrame  # id, address, height_m, geometry (footprint polygon), lon, lat
    graph: nx.MultiDiGraph
    dem: np.ndarray  # metres, row 0 = north
    dem_lons: np.ndarray
    dem_lats: np.ndarray


def _street_name(value) -> str:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) and value else "Unnamed Rd"


def _fetch_buildings(bbox) -> gpd.GeoDataFrame:
    """Building outlines (closed ways only) via a lean Overpass query; osmnx's own query stalls overloaded mirrors."""
    import httpx
    from shapely.geometry import Polygon

    west, south, east, north = bbox
    query = f'[out:json][timeout:250];way["building"]({south},{west},{north},{east});out geom tags;'
    error = None
    for url in OVERPASS_MIRRORS:
        try:
            response = httpx.post(f"{url}/interpreter", data={"data": query}, timeout=280,
                                  headers={"User-Agent": ox.settings.http_user_agent})
            response.raise_for_status()
            elements = response.json()["elements"]
            break
        except Exception as exc:  # noqa: BLE001 - any mirror failure means try the next one
            error = exc
            print(f"overpass mirror failed ({url}): {str(exc)[:120]}")
    else:
        raise error
    rows, shapes = [], []
    for element in elements:
        points = [(p["lon"], p["lat"]) for p in element.get("geometry", [])]
        if len(points) >= 4 and points[0] == points[-1]:
            rows.append(element.get("tags", {}))
            shapes.append(Polygon(points))
    return gpd.GeoDataFrame(rows, geometry=shapes, crs=4326)


def _households(bbox, graph: nx.MultiDiGraph) -> gpd.GeoDataFrame:
    buildings = _fetch_buildings(bbox)
    houses = buildings[buildings["building"].isin(HOUSE_TYPES)]
    houses = (houses if len(houses) >= N_HOUSEHOLDS else buildings).sample(
        n=min(N_HOUSEHOLDS, len(buildings)), random_state=SEED).reset_index(drop=True)
    rng = random.Random(SEED)
    edges = ox.graph_to_gdfs(graph, nodes=False)
    centroids = houses.geometry.centroid
    nearest = edges.iloc[edges.sindex.nearest(centroids, return_all=False)[1]]
    addresses = []
    for (_, house), street in zip(houses.iterrows(), nearest["name"].tolist()):
        number, road = house.get("addr:housenumber"), house.get("addr:street")
        if isinstance(number, str) and isinstance(road, str):
            addresses.append(f"{number} {road}")
        else:
            addresses.append(f"{rng.randrange(10, 199) * 10 + rng.choice([0, 2, 4, 6, 8])} {_street_name(street)}")
    levels = houses.get("building:levels")
    heights = [float(lv) * 3.2 if isinstance(lv, str) and lv.replace(".", "").isdigit() else rng.uniform(5.5, 8.5)
               for lv in (levels if levels is not None else [None] * len(houses))]
    return gpd.GeoDataFrame({
        "id": [f"h{i + 1:03d}" for i in range(len(houses))],
        "address": addresses,
        "height_m": [round(h, 1) for h in heights],
        "lon": centroids.x.round(6).to_numpy(),
        "lat": centroids.y.round(6).to_numpy(),
    }, geometry=houses.geometry.to_numpy(), crs=4326)


def load_area(bbox: tuple[float, float, float, float], cache: Path) -> Area:
    """Fetch (or read from cache) households, drive graph and DEM for the bbox."""
    import py3dep

    cache.mkdir(parents=True, exist_ok=True)
    graph_path, houses_path, dem_path = cache / "drive.graphml", cache / "households.geojson", cache / "dem.npz"
    if graph_path.exists():
        graph = ox.load_graphml(graph_path)
    else:
        graph = _with_mirrors(lambda: ox.graph.graph_from_bbox(bbox=bbox, network_type="drive"))
        ox.save_graphml(graph, graph_path)
    if houses_path.exists():
        households = gpd.read_file(houses_path)
    else:
        households = _households(bbox, graph)
        houses_path.write_text(households.to_json())
    if dem_path.exists():
        saved = np.load(dem_path)
        dem, lons, lats = saved["dem"], saved["lons"], saved["lats"]
    else:
        grid = py3dep.get_dem(bbox, 10)
        if grid.rio.crs is not None and grid.rio.crs.to_epsg() != 4326:  # 3DEP returns a projected (metre) grid
            grid = grid.rio.reproject("EPSG:4326")
        grid = grid.where(grid > -1000)  # drop nodata fill from the reprojection edges
        dem = grid.values.astype("float32")
        dem = np.where(np.isnan(dem), np.nanmedian(dem), dem)
        lons, lats = grid["x"].values, grid["y"].values
        if lats[0] < lats[-1]:  # make row 0 the northern edge
            dem, lats = dem[::-1], lats[::-1]
        np.savez_compressed(dem_path, dem=dem, lons=lons, lats=lats)
    return Area(bbox=bbox, households=households, graph=graph, dem=dem, dem_lons=lons, dem_lats=lats)


def dem_index(area: Area, lon: float, lat: float) -> tuple[int, int]:
    col = int(np.clip(np.searchsorted(area.dem_lons, lon), 0, len(area.dem_lons) - 1))
    row = int(np.clip(np.searchsorted(-area.dem_lats, -lat), 0, len(area.dem_lats) - 1))
    return row, col


def dem_bounds(area: Area) -> list[list[float]]:
    return [[float(area.dem_lons.min()), float(area.dem_lats.min())], [float(area.dem_lons.max()), float(area.dem_lats.max())]]


def write_households(area: Area, depths, path: Path) -> None:
    joined = area.households.merge(depths, on="id")
    features = json.loads(joined[["id", "address", "height_m", "water_arrival_min", "depth_ft_peak", "geometry"]].to_json())
    for feature in features["features"]:
        feature.pop("id", None)
        props = feature["properties"]
        if props["water_arrival_min"] != props["water_arrival_min"]:  # NaN -> never floods
            props["water_arrival_min"] = None
    path.write_text(json.dumps(features))
