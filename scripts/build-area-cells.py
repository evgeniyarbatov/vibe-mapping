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

DEDICATED_FOOTWAY_HIGHWAYS = {
    "footway",
    "pedestrian",
    "steps",
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
    "biển",
    "vịnh",
    "sông",
}

WATER_NATURAL_VALUES = {
    "water",
    "coastline",
    "beach",
}

WATER_TAG_VALUES = {
    "lake",
    "river",
    "canal",
    "reservoir",
    "pond",
    "stream",
    "basin",
    "lagoon",
    "bay",
    "sea",
}

COASTLINE_BAND_WIDTH_M = 300.0


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


def _h3_grid_path_cells(start_cell, end_cell):
    if hasattr(h3, "grid_path_cells"):
        return list(h3.grid_path_cells(start_cell, end_cell))
    return list(h3.h3_line(start_cell, end_cell))


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


def parse_type_field(type_field):
    if not type_field:
        return {}

    try:
        parsed = json.loads(type_field)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    normalized = {}
    for key, value in parsed.items():
        if value is None:
            continue
        normalized[str(key).lower()] = str(value).lower()
    return normalized


def _ring_without_duplicate_endpoint(ring):
    if not ring:
        return []
    if ring[0] == ring[-1]:
        return ring[:-1]
    return list(ring)


def _ring_to_latlng(ring):
    return [(float(lat), float(lon)) for lon, lat in _ring_without_duplicate_endpoint(ring)]


def _rings_from_geometry(geometry):
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])

    polygons = []
    if geom_type == "Polygon":
        if coords:
            polygons.append(coords)
        return polygons

    if geom_type == "MultiPolygon":
        for polygon in coords:
            if polygon:
                polygons.append(polygon)
        return polygons

    return polygons


def _polygon_total_area_m2(polygon_rings):
    if not polygon_rings:
        return 0.0

    outer_area = polygon_area_m2(polygon_rings[0])
    holes_area = sum(polygon_area_m2(ring) for ring in polygon_rings[1:])
    return max(outer_area - holes_area, 0.0)


def _project_lonlat_to_xy(lon, lat, origin_lon_r, origin_lat_r):
    lon_r = math.radians(lon)
    lat_r = math.radians(lat)
    x = EARTH_RADIUS_M * (lon_r - origin_lon_r) * math.cos(origin_lat_r)
    y = EARTH_RADIUS_M * (lat_r - origin_lat_r)
    return x, y


def _ring_lonlat_to_xy(ring, origin_lon_r, origin_lat_r):
    return [
        _project_lonlat_to_xy(float(lon), float(lat), origin_lon_r, origin_lat_r)
        for lon, lat in _ring_without_duplicate_endpoint(ring)
    ]


def _polygon_signed_area_xy(points):
    if len(points) < 3:
        return 0.0
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + [points[0]]):
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _is_inside_half_plane(point, edge_start, edge_end, orientation):
    x, y = point
    x1, y1 = edge_start
    x2, y2 = edge_end
    cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
    return cross * orientation >= -1e-9


def _line_intersection(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if math.isclose(denominator, 0.0, abs_tol=1e-12):
        return p2

    determinant_1 = x1 * y2 - y1 * x2
    determinant_2 = x3 * y4 - y3 * x4
    px = (determinant_1 * (x3 - x4) - (x1 - x2) * determinant_2) / denominator
    py = (determinant_1 * (y3 - y4) - (y1 - y2) * determinant_2) / denominator
    return px, py


def _clip_polygon_with_convex(subject_polygon, clip_polygon):
    if len(subject_polygon) < 3 or len(clip_polygon) < 3:
        return []

    output = list(subject_polygon)
    orientation = 1.0 if _polygon_signed_area_xy(clip_polygon) >= 0.0 else -1.0

    for edge_start, edge_end in zip(clip_polygon, clip_polygon[1:] + [clip_polygon[0]]):
        input_points = output
        output = []
        if not input_points:
            break

        prev_point = input_points[-1]
        prev_inside = _is_inside_half_plane(prev_point, edge_start, edge_end, orientation)

        for curr_point in input_points:
            curr_inside = _is_inside_half_plane(curr_point, edge_start, edge_end, orientation)
            if curr_inside:
                if not prev_inside:
                    output.append(_line_intersection(prev_point, curr_point, edge_start, edge_end))
                output.append(curr_point)
            elif prev_inside:
                output.append(_line_intersection(prev_point, curr_point, edge_start, edge_end))

            prev_point = curr_point
            prev_inside = curr_inside

    return output


def _clipped_ring_area_m2(subject_ring_lonlat, clip_ring_lonlat, origin_lon_r, origin_lat_r):
    subject_xy = _ring_lonlat_to_xy(subject_ring_lonlat, origin_lon_r, origin_lat_r)
    clip_xy = _ring_lonlat_to_xy(clip_ring_lonlat, origin_lon_r, origin_lat_r)
    clipped_xy = _clip_polygon_with_convex(subject_xy, clip_xy)
    return abs(_polygon_signed_area_xy(clipped_xy))


def _h3_cells_overlapping_polygon(polygon_rings, resolution):
    outer = _ring_to_latlng(polygon_rings[0]) if polygon_rings else []
    holes = [_ring_to_latlng(ring) for ring in polygon_rings[1:]]
    if len(outer) < 3:
        return set()

    polygon = h3.LatLngPoly(outer, *holes)
    if hasattr(h3, "h3shape_to_cells_experimental"):
        return set(h3.h3shape_to_cells_experimental(polygon, resolution, contain="overlap"))
    if hasattr(h3, "polygon_to_cells_experimental"):
        return set(h3.polygon_to_cells_experimental(polygon, resolution, contain="overlap"))
    if hasattr(h3, "h3shape_to_cells"):
        return set(h3.h3shape_to_cells(polygon, resolution))
    return set(h3.polygon_to_cells(polygon, resolution))


def distribute_polygon_area_across_cells(geometry, resolution):
    allocations = defaultdict(float)
    for polygon_rings in _rings_from_geometry(geometry):
        polygon_area = _polygon_total_area_m2(polygon_rings)
        if polygon_area <= 0.0:
            continue

        outer_ring = polygon_rings[0]
        outer_lons = [pt[0] for pt in _ring_without_duplicate_endpoint(outer_ring)]
        outer_lats = [pt[1] for pt in _ring_without_duplicate_endpoint(outer_ring)]
        if not outer_lons or not outer_lats:
            continue

        origin_lon_r = math.radians(sum(outer_lons) / len(outer_lons))
        origin_lat_r = math.radians(sum(outer_lats) / len(outer_lats))

        overlapping_cells = _h3_cells_overlapping_polygon(polygon_rings, resolution)
        if not overlapping_cells:
            centroid = geometry_centroid_lonlat({"type": "Polygon", "coordinates": polygon_rings})
            if centroid is not None:
                lon, lat = centroid
                allocations[_h3_latlng_to_cell(lat, lon, resolution)] += polygon_area
            continue

        intersection_areas = {}
        for cell_id in overlapping_cells:
            hex_ring = [[lng, lat] for lat, lng in _h3_cell_to_boundary(cell_id)]
            if hex_ring and hex_ring[0] != hex_ring[-1]:
                hex_ring.append(hex_ring[0])

            overlap_area = _clipped_ring_area_m2(
                polygon_rings[0], hex_ring, origin_lon_r, origin_lat_r
            )
            if overlap_area > 0.0:
                for hole_ring in polygon_rings[1:]:
                    overlap_area -= _clipped_ring_area_m2(
                        hole_ring, hex_ring, origin_lon_r, origin_lat_r
                    )
                overlap_area = max(overlap_area, 0.0)

            if overlap_area > 0.0:
                intersection_areas[cell_id] = overlap_area

        covered_area = sum(intersection_areas.values())
        if covered_area <= 0.0:
            centroid = geometry_centroid_lonlat({"type": "Polygon", "coordinates": polygon_rings})
            if centroid is not None:
                lon, lat = centroid
                allocations[_h3_latlng_to_cell(lat, lon, resolution)] += polygon_area
            continue

        scale = polygon_area / covered_area
        for cell_id, area_m2 in intersection_areas.items():
            allocations[cell_id] += area_m2 * scale

    return dict(allocations)


def linestring_length_m(coords):
    if len(coords) < 2:
        return 0.0

    length = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        length += haversine_m(lat1, lon1, lat2, lon2)
    return length


def distribute_linestring_length_across_cells(coords, resolution):
    if len(coords) < 2:
        return {}

    allocations = defaultdict(float)
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        segment_length = haversine_m(lat1, lon1, lat2, lon2)
        if segment_length <= 0.0:
            continue

        start_cell = _h3_latlng_to_cell(lat1, lon1, resolution)
        end_cell = _h3_latlng_to_cell(lat2, lon2, resolution)
        try:
            path_cells = _h3_grid_path_cells(start_cell, end_cell)
        except Exception:
            path_cells = [start_cell] if start_cell == end_cell else [start_cell, end_cell]

        if not path_cells:
            continue
        per_cell_length = segment_length / len(path_cells)
        for cell_id in path_cells:
            allocations[cell_id] += per_cell_length

    return dict(allocations)


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

    if geom_type == "MultiPolygon":
        rings = _rings_from_geometry(geometry)
        if not rings:
            return None

        weighted_lon = 0.0
        weighted_lat = 0.0
        total_area = 0.0
        for polygon_rings in rings:
            ring = polygon_rings[0] if polygon_rings else []
            if not ring:
                continue
            area = _polygon_total_area_m2(polygon_rings)
            if area <= 0:
                continue
            lon = sum(pt[0] for pt in ring) / len(ring)
            lat = sum(pt[1] for pt in ring) / len(ring)
            weighted_lon += lon * area
            weighted_lat += lat * area
            total_area += area

        if total_area > 0:
            return weighted_lon / total_area, weighted_lat / total_area

    return None


def is_water_name(name):
    lowered = (name or "").lower()
    return any(term in lowered for term in WATER_NAME_TERMS)


def is_water_feature(name, tags):
    water = tags.get("water", "")
    natural = tags.get("natural", "")
    waterway = tags.get("waterway", "")
    landuse = tags.get("landuse", "")

    if water in WATER_TAG_VALUES:
        return True
    if natural in WATER_NATURAL_VALUES:
        return True
    if waterway in WATER_TAG_VALUES:
        return True
    if landuse in {"reservoir", "basin"}:
        return True
    return is_water_name(name)


def is_coastline_like_feature(tags):
    return tags.get("natural", "") in {"coastline", "beach"}


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


def update_land_texture(cell, category, name, tags, area):
    if area <= 0.0:
        return

    if category == NATURE_QUIET:
        cell["green_area_m2"] += area

    if category == SCENIC_WATER_FOREST:
        if is_water_feature(name, tags):
            cell["water_area_m2"] += area
        else:
            cell["green_area_m2"] += area

    if category == FAMILY_RESIDENTIAL:
        cell["residential_area_m2"] += area

    if category == INDUSTRIAL_LOGISTICS:
        cell["industrial_area_m2"] += area

    if category in BUILT_ENV_CATEGORIES:
        cell["building_area_m2"] += area


def update_water_from_lines(cells, category, name, tags, geometry, resolution):
    if geometry.get("type") != "LineString":
        return
    if category != SCENIC_WATER_FOREST:
        return
    if not is_water_feature(name, tags):
        return
    if not is_coastline_like_feature(tags):
        return

    coords = geometry.get("coordinates", [])
    if len(coords) < 2:
        return

    length_allocations = distribute_linestring_length_across_cells(coords, resolution)
    for cell_id, length_m in length_allocations.items():
        if length_m <= 0.0:
            continue
        cells[cell_id]["water_area_m2"] += length_m * COASTLINE_BAND_WIDTH_M


def endpoint_key(lon, lat, precision=6):
    return f"{round(lon, precision):.{precision}f},{round(lat, precision):.{precision}f}"


def is_dedicated_footway(tags):
    return tags.get("highway", "") in DEDICATED_FOOTWAY_HIGHWAYS


def update_streets(cell, category, geometry, tags):
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

    if is_dedicated_footway(tags):
        cell["footway_length_m"] += length


def compute_intersection_count(cell):
    counts = cell["_road_endpoint_counts"]
    return sum(1 for value in counts.values() if value >= 2)


def add_derived_fields(cell, cell_area_m2):
    cell_area_km2 = cell_area_m2 / 1_000_000.0 if cell_area_m2 > 0 else 0.0
    intersection_count = compute_intersection_count(cell)

    poi_total = cell["poi_total"]
    road_length = cell["road_length_m"]

    if cell_area_m2 > 0:
        cell["water_area_m2"] = min(cell["water_area_m2"], cell_area_m2)

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
            tags = parse_type_field(row.get("type", ""))

            cell = cells[cell_id]
            update_poi_mix(cell, category, name)
            update_streets(cell, category, geometry, tags)
            update_water_from_lines(cells, category, name, tags, geometry, resolution)

            area_allocations = distribute_polygon_area_across_cells(geometry, resolution)
            for area_cell_id, area in area_allocations.items():
                update_land_texture(cells[area_cell_id], category, name, tags, area)

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
