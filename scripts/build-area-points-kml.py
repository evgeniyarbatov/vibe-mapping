import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET


KML_NS = "http://www.opengis.net/kml/2.2"
REQUIRED_COLUMNS = {"name", "geometry", "category"}
DEFAULT_INPUT_CSV = "osm/area-points-normalized.csv"
DEFAULT_OUTPUT_KML = "osm/area-points.kml"

CATEGORY_COLORS = {
    "Food & café": "F4A261",
    "Nightlife": "D62828",
    "Tourist lodging": "2A9D8F",
    "Local services": "457B9D",
    "Luxury / high-end": "B08968",
    "Nature / quiet": "588157",
    "Industrial / logistics": "6C757D",
    "Civic / institutional": "1D3557",
    "Religious / historic": "9C6644",
    "Family / residential": "8AB17D",
    "Road-heavy / car-oriented": "E63946",
    "Walkable commercial": "FFB703",
    "Scenic / water / forest": "219EBC",
}


def rgb_to_kml_color(rgb_hex, alpha):
    rgb = rgb_hex.strip().lstrip("#")
    if len(rgb) != 6:
        raise ValueError(f"Expected 6-char RGB color, got: {rgb_hex}")
    return f"{alpha}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


def deterministic_category_color(category):
    digest = hashlib.md5(category.encode("utf-8")).hexdigest()
    return digest[:6].upper()


def color_for_category(category):
    return CATEGORY_COLORS.get(category, deterministic_category_color(category))


def sanitize_category(raw_value):
    cleaned = " ".join(str(raw_value or "").split()).strip()
    if cleaned:
        return cleaned
    return "Uncategorized"


def style_id_for_category(category):
    slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
    if not slug:
        slug = "uncategorized"
    return f"category-{slug}"


def parse_position(row_number, raw_position):
    if not isinstance(raw_position, list) or len(raw_position) < 2:
        raise ValueError(f"Row {row_number}: invalid coordinate pair")
    try:
        lon = float(raw_position[0])
        lat = float(raw_position[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Row {row_number}: non-numeric coordinate value") from exc
    return lon, lat


def parse_line_coordinates(row_number, raw_coordinates):
    if not isinstance(raw_coordinates, list) or len(raw_coordinates) < 2:
        raise ValueError(f"Row {row_number}: LineString requires at least 2 coordinates")
    return [parse_position(row_number, position) for position in raw_coordinates]


def parse_ring_coordinates(row_number, raw_ring):
    if not isinstance(raw_ring, list) or not raw_ring:
        raise ValueError(f"Row {row_number}: Polygon ring must contain coordinates")
    ring = [parse_position(row_number, position) for position in raw_ring]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    if len(ring) < 4:
        raise ValueError(f"Row {row_number}: Polygon ring must contain at least 4 coordinates")
    return ring


def parse_polygon_coordinates(row_number, raw_polygon):
    if not isinstance(raw_polygon, list) or not raw_polygon:
        raise ValueError(f"Row {row_number}: Polygon requires at least one ring")
    outer_ring = parse_ring_coordinates(row_number, raw_polygon[0])
    inner_rings = [parse_ring_coordinates(row_number, ring) for ring in raw_polygon[1:]]
    return {"outer": outer_ring, "inners": inner_rings}


def format_coordinates(coordinates):
    return " ".join(f"{lon:.8f},{lat:.8f},0" for lon, lat in coordinates)


def add_point(parent, point):
    point_element = ET.SubElement(parent, f"{{{KML_NS}}}Point")
    ET.SubElement(point_element, f"{{{KML_NS}}}coordinates").text = f"{point[0]:.8f},{point[1]:.8f},0"


def add_linestring(parent, coordinates):
    line_element = ET.SubElement(parent, f"{{{KML_NS}}}LineString")
    ET.SubElement(line_element, f"{{{KML_NS}}}tessellate").text = "1"
    ET.SubElement(line_element, f"{{{KML_NS}}}coordinates").text = format_coordinates(coordinates)


def add_polygon(parent, polygon):
    polygon_element = ET.SubElement(parent, f"{{{KML_NS}}}Polygon")
    ET.SubElement(polygon_element, f"{{{KML_NS}}}tessellate").text = "1"

    outer_boundary = ET.SubElement(polygon_element, f"{{{KML_NS}}}outerBoundaryIs")
    outer_ring = ET.SubElement(outer_boundary, f"{{{KML_NS}}}LinearRing")
    ET.SubElement(outer_ring, f"{{{KML_NS}}}coordinates").text = format_coordinates(polygon["outer"])

    for inner in polygon["inners"]:
        inner_boundary = ET.SubElement(polygon_element, f"{{{KML_NS}}}innerBoundaryIs")
        inner_ring = ET.SubElement(inner_boundary, f"{{{KML_NS}}}LinearRing")
        ET.SubElement(inner_ring, f"{{{KML_NS}}}coordinates").text = format_coordinates(inner)


def add_geometry(parent, row_number, geometry):
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "Point":
        add_point(parent, parse_position(row_number, coordinates))
        return
    if geometry_type == "LineString":
        add_linestring(parent, parse_line_coordinates(row_number, coordinates))
        return
    if geometry_type == "Polygon":
        add_polygon(parent, parse_polygon_coordinates(row_number, coordinates))
        return
    if geometry_type == "MultiPoint":
        multi = ET.SubElement(parent, f"{{{KML_NS}}}MultiGeometry")
        for point in coordinates or []:
            add_point(multi, parse_position(row_number, point))
        return
    if geometry_type == "MultiLineString":
        multi = ET.SubElement(parent, f"{{{KML_NS}}}MultiGeometry")
        for line in coordinates or []:
            add_linestring(multi, parse_line_coordinates(row_number, line))
        return
    if geometry_type == "MultiPolygon":
        multi = ET.SubElement(parent, f"{{{KML_NS}}}MultiGeometry")
        for polygon in coordinates or []:
            add_polygon(multi, parse_polygon_coordinates(row_number, polygon))
        return

    raise ValueError(f"Row {row_number}: unsupported geometry type: {geometry_type}")


def read_rows(input_csv_path):
    rows = []
    with open(input_csv_path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS.difference(set(reader.fieldnames or []))
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing required columns: {missing_list}")

        for row_number, row in enumerate(reader, start=2):
            try:
                geometry = json.loads(row["geometry"])
            except json.JSONDecodeError as exc:
                raise ValueError(f"Row {row_number}: invalid JSON in geometry: {exc}") from exc
            if not isinstance(geometry, dict):
                raise ValueError(f"Row {row_number}: geometry must be a GeoJSON object")

            name = " ".join(str(row.get("name") or "").split()).strip()
            if not name:
                name = f"Unnamed feature {row_number - 1}"

            category = sanitize_category(row.get("category"))
            rows.append({"name": name, "category": category, "geometry": geometry, "row_number": row_number})
    return rows


def build_styles(rows):
    categories = []
    seen = set()
    for row in rows:
        category = row["category"]
        if category in seen:
            continue
        seen.add(category)
        categories.append(category)

    used_style_ids = set()
    styles = {}
    for category in categories:
        base_style_id = style_id_for_category(category)
        style_id = base_style_id
        if style_id in used_style_ids:
            suffix = hashlib.md5(category.encode("utf-8")).hexdigest()[:8]
            style_id = f"{base_style_id}-{suffix}"
        used_style_ids.add(style_id)
        styles[category] = {
            "style_id": style_id,
            "line_color": rgb_to_kml_color(color_for_category(category), "ff"),
            "fill_color": rgb_to_kml_color(color_for_category(category), "66"),
        }
    return styles


def add_styles(document, styles):
    for style in styles.values():
        style_element = ET.SubElement(document, f"{{{KML_NS}}}Style", id=style["style_id"])
        line_style = ET.SubElement(style_element, f"{{{KML_NS}}}LineStyle")
        ET.SubElement(line_style, f"{{{KML_NS}}}color").text = style["line_color"]
        ET.SubElement(line_style, f"{{{KML_NS}}}width").text = "1.6"
        poly_style = ET.SubElement(style_element, f"{{{KML_NS}}}PolyStyle")
        ET.SubElement(poly_style, f"{{{KML_NS}}}color").text = style["fill_color"]
        ET.SubElement(poly_style, f"{{{KML_NS}}}fill").text = "1"
        ET.SubElement(poly_style, f"{{{KML_NS}}}outline").text = "1"


def add_placemark(document, row, style):
    placemark = ET.SubElement(document, f"{{{KML_NS}}}Placemark")
    ET.SubElement(placemark, f"{{{KML_NS}}}name").text = row["name"]
    ET.SubElement(placemark, f"{{{KML_NS}}}description").text = f"Category: {row['category']}"
    ET.SubElement(placemark, f"{{{KML_NS}}}styleUrl").text = f"#{style['style_id']}"
    add_geometry(placemark, row["row_number"], row["geometry"])


def build_area_points_kml(input_csv_path, output_kml_path):
    rows = read_rows(input_csv_path)
    styles = build_styles(rows)

    output_path = Path(output_kml_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ET.register_namespace("", KML_NS)
    root = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(root, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = "area-points"

    add_styles(document, styles)
    for row in rows:
        add_placemark(document, row, styles[row["category"]])

    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_csv",
        nargs="?",
        default=DEFAULT_INPUT_CSV,
        help=f"Input CSV with columns: name, geometry, category (default: {DEFAULT_INPUT_CSV})",
    )
    parser.add_argument(
        "output_kml",
        nargs="?",
        default=DEFAULT_OUTPUT_KML,
        help=f"Output KML path (default: {DEFAULT_OUTPUT_KML})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_area_points_kml(args.input_csv, args.output_kml)
