import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import h3


FOOD_AND_CAFE = "Food & café"
NIGHTLIFE = "Nightlife"
TOURIST_LODGING = "Tourist lodging"
LOCAL_SERVICES = "Local services"
LUXURY_HIGH_END = "Luxury / high-end"
NATURE_QUIET = "Nature / quiet"
INDUSTRIAL_LOGISTICS = "Industrial / logistics"
CIVIC_INSTITUTIONAL = "Civic / institutional"
RELIGIOUS_HISTORIC = "Religious / historic"
FAMILY_RESIDENTIAL = "Family / residential"
ROAD_HEAVY = "Road-heavy / car-oriented"
WALKABLE_COMMERCIAL = "Walkable commercial"
SCENIC_WATER_FOREST = "Scenic / water / forest"

EARTH_RADIUS_M = 6_371_008.8

BUILT_ENV_CATEGORIES = {
    FAMILY_RESIDENTIAL,
    INDUSTRIAL_LOGISTICS,
    CIVIC_INSTITUTIONAL,
    LOCAL_SERVICES,
    TOURIST_LODGING,
    LUXURY_HIGH_END,
    RELIGIOUS_HISTORIC,
    WALKABLE_COMMERCIAL,
}

ROAD_CATEGORIES = {
    ROAD_HEAVY,
    FAMILY_RESIDENTIAL,
    WALKABLE_COMMERCIAL,
    LOCAL_SERVICES,
}

FOOTWAY_LIKE_CATEGORIES = {
    WALKABLE_COMMERCIAL,
    FAMILY_RESIDENTIAL,
}

WATER_NAME_TERMS = {
    "lake",
    "river",
    "sea",
    "ocean",
    "bay",
    "reservoir",
    "pond",
    "canal",
    "stream",
    "hồ",
    "sông",
}


def _h3_latlng_to_cell(lat, lng, resolution):
    if hasattr(h3, "latlng_to_cell"):
        return h3.latlng_to_cell(lat, lng, resolution)
    return h3.geo_to_h3(lat, lng, resolution)


def _h3_cell_to_boundary(cell_id):
    if hasattr(h3, "cell_to_boundary"):
        points = h3.cell_to_boundary(cell_id)
        return [(float(lat), float(lng)) for lat, lng in points]
    points = h3.h3_to_geo_boundary(cell_id, geo_json=False)
    return [(float(lat), float(lng)) for lat, lng in points]


def _h3_cell_area_m2(cell_id):
    if hasattr(h3, "cell_area"):
        return float(h3.cell_area(cell_id, unit="m^2"))
    return float(h3.cell_area(cell_id, unit="m2"))


def _h3_cell_to_latlng(cell_id):
    if hasattr(h3, "cell_to_latlng"):
        lat, lng = h3.cell_to_latlng(cell_id)
        return float(lat), float(lng)
    lat, lng = h3.h3_to_geo(cell_id)
    return float(lat), float(lng)


def haversine_m(lat1, lon1, lat2, lon2):
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def polygon_area_m2(ring):
    if len(ring) < 3:
        return 0.0

    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    origin_lon = math.radians(sum(lons) / len(lons))
    origin_lat = math.radians(sum(lats) / len(lats))

    projected = []
    for lon, lat in ring:
        lon_r = math.radians(lon)
        lat_r = math.radians(lat)
        x = EARTH_RADIUS_M * (lon_r - origin_lon) * math.cos(origin_lat)
        y = EARTH_RADIUS_M * (lat_r - origin_lat)
        projected.append((x, y))

    if projected[0] != projected[-1]:
        projected.append(projected[0])

    area = 0.0
    for (x1, y1), (x2, y2) in zip(projected, projected[1:]):
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def linestring_length_m(coords):
    if len(coords) < 2:
        return 0.0

    length = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        length += haversine_m(lat1, lon1, lat2, lon2)
    return length


def geometry_centroid_lonlat(geometry):
    coords = geometry.get("coordinates", [])
    geom_type = geometry.get("type")

    if geom_type == "Polygon":
        ring = coords[0] if coords else []
        if not ring:
            return None
        lon = sum(pt[0] for pt in ring) / len(ring)
        lat = sum(pt[1] for pt in ring) / len(ring)
        return lon, lat

    if geom_type == "LineString":
        if not coords:
            return None
        lon = sum(pt[0] for pt in coords) / len(coords)
        lat = sum(pt[1] for pt in coords) / len(coords)
        return lon, lat

    return None


def is_water_name(name):
    lowered = (name or "").lower()
    return any(term in lowered for term in WATER_NAME_TERMS)


def init_cell_aggregate():
    return {
        "poi_total": 0,
        "food_count": 0,
        "cafe_count": 0,
        "bar_count": 0,
        "hotel_count": 0,
        "shop_count": 0,
        "service_count": 0,
        "culture_count": 0,
        "parking_count": 0,
        "green_area_m2": 0.0,
        "water_area_m2": 0.0,
        "residential_area_m2": 0.0,
        "industrial_area_m2": 0.0,
        "building_area_m2": 0.0,
        "road_length_m": 0.0,
        "major_road_length_m": 0.0,
        "footway_length_m": 0.0,
        "_road_endpoint_counts": Counter(),
    }


def update_poi_mix(cell, category, name):
    lowered_name = (name or "").lower()
    cell["poi_total"] += 1

    if category == FOOD_AND_CAFE:
        cell["food_count"] += 1
    if category == FOOD_AND_CAFE and ("cafe" in lowered_name or "coffee" in lowered_name):
        cell["cafe_count"] += 1
    if category == NIGHTLIFE or any(term in lowered_name for term in {"bar", "pub", "club"}):
        cell["bar_count"] += 1
    if category in {TOURIST_LODGING, LUXURY_HIGH_END} or any(
        term in lowered_name for term in {"hotel", "hostel", "guest house", "resort", "motel"}
    ):
        cell["hotel_count"] += 1
    if category == WALKABLE_COMMERCIAL or any(
        term in lowered_name for term in {"shop", "market", "mall", "store"}
    ):
        cell["shop_count"] += 1
    if category in {LOCAL_SERVICES, CIVIC_INSTITUTIONAL}:
        cell["service_count"] += 1
    if category in {RELIGIOUS_HISTORIC, CIVIC_INSTITUTIONAL, SCENIC_WATER_FOREST}:
        cell["culture_count"] += 1
    if "parking" in lowered_name or "car park" in lowered_name:
        cell["parking_count"] += 1


def update_land_texture(cell, category, name, geometry):
    if geometry.get("type") != "Polygon":
        return

    ring = geometry.get("coordinates", [[]])[0]
    area = polygon_area_m2(ring)
    if area <= 0.0:
        return

    if category == NATURE_QUIET:
        cell["green_area_m2"] += area

    if category == SCENIC_WATER_FOREST:
        if is_water_name(name):
            cell["water_area_m2"] += area
        else:
            cell["green_area_m2"] += area

    if category == FAMILY_RESIDENTIAL:
        cell["residential_area_m2"] += area

    if category == INDUSTRIAL_LOGISTICS:
        cell["industrial_area_m2"] += area

    if category in BUILT_ENV_CATEGORIES:
        cell["building_area_m2"] += area


def endpoint_key(lon, lat, precision=6):
    return f"{round(lon, precision):.{precision}f},{round(lat, precision):.{precision}f}"


def update_streets(cell, category, geometry):
    if geometry.get("type") != "LineString":
        return

    coords = geometry.get("coordinates", [])
    if len(coords) < 2:
        return

    length = linestring_length_m(coords)
    if category in ROAD_CATEGORIES:
        cell["road_length_m"] += length
        start_lon, start_lat = coords[0]
        end_lon, end_lat = coords[-1]
        cell["_road_endpoint_counts"][endpoint_key(start_lon, start_lat)] += 1
        cell["_road_endpoint_counts"][endpoint_key(end_lon, end_lat)] += 1

    if category == ROAD_HEAVY:
        cell["major_road_length_m"] += length

    if category in FOOTWAY_LIKE_CATEGORIES:
        cell["footway_length_m"] += length


def compute_intersection_count(cell):
    counts = cell["_road_endpoint_counts"]
    return sum(1 for value in counts.values() if value >= 2)


def add_derived_fields(cell, cell_area_m2):
    cell_area_km2 = cell_area_m2 / 1_000_000.0 if cell_area_m2 > 0 else 0.0
    intersection_count = compute_intersection_count(cell)

    poi_total = cell["poi_total"]
    road_length = cell["road_length_m"]

    cell["intersection_count"] = intersection_count
    cell["poi_density"] = poi_total / cell_area_km2 if cell_area_km2 > 0 else 0.0
    cell["food_share"] = cell["food_count"] / max(poi_total, 1)
    cell["green_share"] = cell["green_area_m2"] / cell_area_m2 if cell_area_m2 > 0 else 0.0
    cell["building_coverage"] = (
        cell["building_area_m2"] / cell_area_m2 if cell_area_m2 > 0 else 0.0
    )
    cell["walkability_proxy"] = intersection_count + cell["footway_length_m"] / 100.0
    cell["car_orientation"] = cell["major_road_length_m"] / max(road_length, 1.0)

    diversity_fields = (
        "food_count",
        "cafe_count",
        "bar_count",
        "hotel_count",
        "shop_count",
        "service_count",
        "culture_count",
    )
    cell["diversity"] = sum(1 for field in diversity_fields if cell[field] > 0)

    del cell["_road_endpoint_counts"]


def round_floats(payload, digits=6):
    rounded = {}
    for key, value in payload.items():
        if isinstance(value, float):
            rounded[key] = round(value, digits)
        else:
            rounded[key] = value
    return rounded


def minmax_normalizers(cells, fields):
    field_values = {field: [cells[cell_id][field] for cell_id in cells] for field in fields}
    minima = {field: min(values) for field, values in field_values.items()}
    maxima = {field: max(values) for field, values in field_values.items()}

    def norm(field, value):
        minimum = minima[field]
        maximum = maxima[field]
        if math.isclose(minimum, maximum):
            return 0.0
        return (value - minimum) / (maximum - minimum)

    return norm


def compute_scores(cells):
    if not cells:
        return {}

    norm_fields = [
        "poi_density",
        "intersection_count",
        "hotel_count",
        "culture_count",
        "food_count",
        "cafe_count",
        "bar_count",
        "green_share",
        "major_road_length_m",
        "residential_area_m2",
        "industrial_area_m2",
        "footway_length_m",
        "parking_count",
    ]
    norm = minmax_normalizers(cells, norm_fields)

    scores = {}
    for cell_id, features in cells.items():
        scores[cell_id] = {
            "busy": norm("poi_density", features["poi_density"])
            + norm("intersection_count", features["intersection_count"]),
            "touristy": norm("hotel_count", features["hotel_count"])
            + norm("culture_count", features["culture_count"]),
            "foodie": norm("food_count", features["food_count"])
            + norm("cafe_count", features["cafe_count"]),
            "nightlife": norm("bar_count", features["bar_count"]),
            "green_quiet": norm("green_share", features["green_share"])
            - norm("major_road_length_m", features["major_road_length_m"]),
            "residential": norm("residential_area_m2", features["residential_area_m2"]),
            "industrial": norm("industrial_area_m2", features["industrial_area_m2"]),
            "walkable": norm("intersection_count", features["intersection_count"])
            + norm("footway_length_m", features["footway_length_m"])
            - norm("major_road_length_m", features["major_road_length_m"]),
            "car_oriented": norm("major_road_length_m", features["major_road_length_m"])
            + norm("parking_count", features["parking_count"]),
        }
        scores[cell_id] = round_floats(scores[cell_id])

    return scores


def cell_boundary_geojson(cell_id):
    boundary = _h3_cell_to_boundary(cell_id)
    coordinates = [[lng, lat] for lat, lng in boundary]
    if coordinates and coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])
    return {"type": "Polygon", "coordinates": [coordinates]}


def aggregate_cells(input_csv_path, resolution):
    cells = defaultdict(init_cell_aggregate)

    with open(input_csv_path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        required = {"name", "geometry", "category"}
        missing = required.difference(set(reader.fieldnames or []))
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing required columns: {missing_list}")

        for row in reader:
            geometry = json.loads(row["geometry"])
            centroid = geometry_centroid_lonlat(geometry)
            if centroid is None:
                continue

            lon, lat = centroid
            cell_id = _h3_latlng_to_cell(lat, lon, resolution)
            category = row["category"]
            name = row["name"]

            cell = cells[cell_id]
            update_poi_mix(cell, category, name)
            update_land_texture(cell, category, name, geometry)
            update_streets(cell, category, geometry)

    for cell_id, cell in cells.items():
        area_m2 = _h3_cell_area_m2(cell_id)
        add_derived_fields(cell, area_m2)
        cells[cell_id] = round_floats(cell)

    return cells


def filter_cells_by_center_radius(cells, center_lat, center_lon, radius_km):
    if center_lat is None or center_lon is None or radius_km is None:
        return dict(cells)

    radius_m = radius_km * 1000.0
    filtered_cells = {}
    for cell_id, features in cells.items():
        cell_lat, cell_lon = _h3_cell_to_latlng(cell_id)
        if haversine_m(center_lat, center_lon, cell_lat, cell_lon) <= radius_m:
            filtered_cells[cell_id] = features
    return filtered_cells


def write_cells_csv(output_csv_path, cells, scores):
    output_path = Path(output_csv_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["cell_id", "cell_features", "scores", "cell_boundary"]
    with output_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()

        for cell_id in sorted(cells):
            writer.writerow(
                {
                    "cell_id": cell_id,
                    "cell_features": json.dumps(cells[cell_id], sort_keys=True),
                    "scores": json.dumps(scores[cell_id], sort_keys=True),
                    "cell_boundary": json.dumps(cell_boundary_geojson(cell_id), separators=(",", ":")),
                }
            )


def build_area_cells(
    input_csv_path,
    output_csv_path,
    resolution,
    center_lat=None,
    center_lon=None,
    radius_km=None,
):
    cells = aggregate_cells(input_csv_path, resolution)
    cells = filter_cells_by_center_radius(cells, center_lat, center_lon, radius_km)
    if not cells:
        write_cells_csv(output_csv_path, cells, {})
        return
    scores = compute_scores(cells)
    write_cells_csv(output_csv_path, cells, scores)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", help="Normalized POI CSV (name,geometry,category)")
    parser.add_argument("output_csv", help="Output CSV with cell features and scores")
    parser.add_argument("--resolution", type=int, default=9, help="H3 resolution (default: 9)")
    parser.add_argument("--center-lat", type=float, help="Center latitude for optional radius filter")
    parser.add_argument("--center-lon", type=float, help="Center longitude for optional radius filter")
    parser.add_argument("--radius-km", type=float, help="Max distance from center (km) for cell center")

    args = parser.parse_args()
    radius_filter_args = [args.center_lat is not None, args.center_lon is not None, args.radius_km is not None]
    if any(radius_filter_args) and not all(radius_filter_args):
        parser.error("--center-lat, --center-lon, and --radius-km must be provided together")
    if args.radius_km is not None and args.radius_km < 0:
        parser.error("--radius-km must be non-negative")
    return args


if __name__ == "__main__":
    args = parse_args()
    build_area_cells(
        args.input_csv,
        args.output_csv,
        args.resolution,
        center_lat=args.center_lat,
        center_lon=args.center_lon,
        radius_km=args.radius_km,
    )
