import argparse
import csv
import json
from pathlib import Path
from xml.etree import ElementTree as ET

KML_NS = "http://www.opengis.net/kml/2.2"
REQUIRED_COLUMNS = {"cell_id", "cell_boundary", "vibe", "label"}
AREA_CELLS_REQUIRED_COLUMNS = {"cell_id", "cell_features", "scores"}
DEFAULT_AREA_CELLS_CSV = "osm/area-cells.csv"
VALID_LABELS = {"positive", "mixed", "negative"}

LABEL_COLORS = {
    "positive": "2E8B57",
    "mixed": "E9C46A",
    "negative": "C1121F",
}


def sanitize_vibe(vibe):
    cleaned = " ".join(str(vibe or "").split()).strip()
    if cleaned:
        return cleaned
    return "Unclassified vibe"


def normalize_label(label):
    cleaned = str(label or "").strip().lower()
    if cleaned in VALID_LABELS:
        return cleaned
    return "mixed"


def rgb_to_kml_color(rgb_hex, alpha):
    rgb = rgb_hex.strip().lstrip("#")
    if len(rgb) != 6:
        raise ValueError(f"Expected 6-char RGB color, got: {rgb_hex}")
    red = rgb[0:2]
    green = rgb[2:4]
    blue = rgb[4:6]
    return f"{alpha}{blue}{green}{red}"


def parse_json_object(cell_id, column_name, raw_value):
    try:
        payload = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cell {cell_id}: invalid JSON in {column_name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Cell {cell_id}: expected JSON object in {column_name}")
    return payload


def normalize_position(cell_id, position):
    if not isinstance(position, list) or len(position) < 2:
        raise ValueError(f"Cell {cell_id}: invalid coordinate pair in cell_boundary")
    try:
        lon = float(position[0])
        lat = float(position[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Cell {cell_id}: non-numeric coordinate in cell_boundary") from exc
    return lon, lat


def ensure_closed_ring(cell_id, ring):
    if not ring:
        raise ValueError(f"Cell {cell_id}: empty ring in cell_boundary")

    closed_ring = list(ring)
    if closed_ring[0] != closed_ring[-1]:
        closed_ring.append(closed_ring[0])

    if len(closed_ring) < 4:
        raise ValueError(f"Cell {cell_id}: ring must contain at least 4 coordinates")
    return closed_ring


def parse_ring(cell_id, raw_ring):
    if not isinstance(raw_ring, list):
        raise ValueError(f"Cell {cell_id}: ring is not an array")
    normalized = [normalize_position(cell_id, position) for position in raw_ring]
    return ensure_closed_ring(cell_id, normalized)


def parse_polygons(cell_id, raw_boundary):
    try:
        boundary = json.loads(raw_boundary)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cell {cell_id}: invalid JSON in cell_boundary: {exc}") from exc

    if not isinstance(boundary, dict):
        raise ValueError(f"Cell {cell_id}: cell_boundary must be a GeoJSON object")

    geometry_type = boundary.get("type")
    coordinates = boundary.get("coordinates")
    if geometry_type == "Polygon":
        raw_polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        raw_polygons = coordinates
    else:
        raise ValueError(
            f"Cell {cell_id}: unsupported geometry type in cell_boundary: {geometry_type}"
        )

    if not isinstance(raw_polygons, list) or not raw_polygons:
        raise ValueError(f"Cell {cell_id}: missing polygon coordinates in cell_boundary")

    polygons = []
    for polygon in raw_polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError(f"Cell {cell_id}: polygon has no rings in cell_boundary")
        outer = parse_ring(cell_id, polygon[0])
        inners = [parse_ring(cell_id, ring) for ring in polygon[1:]]
        polygons.append({"outer": outer, "inners": inners})
    return polygons


def format_coords(ring):
    return " ".join(f"{lon:.8f},{lat:.8f},0" for lon, lat in ring)


def add_polygon(parent, polygon):
    polygon_element = ET.SubElement(parent, f"{{{KML_NS}}}Polygon")
    ET.SubElement(polygon_element, f"{{{KML_NS}}}tessellate").text = "1"

    outer_boundary = ET.SubElement(polygon_element, f"{{{KML_NS}}}outerBoundaryIs")
    outer_ring = ET.SubElement(outer_boundary, f"{{{KML_NS}}}LinearRing")
    ET.SubElement(outer_ring, f"{{{KML_NS}}}coordinates").text = format_coords(polygon["outer"])

    for inner in polygon["inners"]:
        inner_boundary = ET.SubElement(polygon_element, f"{{{KML_NS}}}innerBoundaryIs")
        inner_ring = ET.SubElement(inner_boundary, f"{{{KML_NS}}}LinearRing")
        ET.SubElement(inner_ring, f"{{{KML_NS}}}coordinates").text = format_coords(inner)


def read_area_cells_details(area_cells_csv_path):
    with open(area_cells_csv_path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing = AREA_CELLS_REQUIRED_COLUMNS.difference(set(reader.fieldnames or []))
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing required columns in area cells CSV: {missing_list}")

        details = {}
        for row in reader:
            cell_id = row["cell_id"]
            details[cell_id] = {
                "cell_features": parse_json_object(cell_id, "cell_features", row["cell_features"]),
                "scores": parse_json_object(cell_id, "scores", row["scores"]),
            }
    return details


def read_area_vibe_rows(input_csv_path, cell_details):
    rows = []
    with open(input_csv_path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS.difference(set(reader.fieldnames or []))
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing required columns: {missing_list}")

        for row in reader:
            cell_id = row["cell_id"]
            vibe = sanitize_vibe(row["vibe"])
            label = normalize_label(row.get("label"))
            polygons = parse_polygons(cell_id, row["cell_boundary"])
            details = cell_details.get(cell_id, {"cell_features": {}, "scores": {}})
            rows.append(
                {
                    "cell_id": cell_id,
                    "vibe": vibe,
                    "label": label,
                    "polygons": polygons,
                    "cell_features": details["cell_features"],
                    "scores": details["scores"],
                }
            )
    return rows


def build_label_styles(rows):
    labels_present = {row["label"] for row in rows}
    styles = {}
    for label in ["positive", "mixed", "negative"]:
        if label not in labels_present:
            continue
        rgb = LABEL_COLORS[label]
        styles[label] = {
            "area_style_id": f"area-label-{label}",
            "line_color": rgb_to_kml_color(rgb, "ff"),
            "fill_color": rgb_to_kml_color(rgb, "88"),
        }
    return styles


def add_styles(document, styles):
    for style in styles.values():
        area_style = ET.SubElement(document, f"{{{KML_NS}}}Style", id=style["area_style_id"])
        line_style = ET.SubElement(area_style, f"{{{KML_NS}}}LineStyle")
        ET.SubElement(line_style, f"{{{KML_NS}}}color").text = style["line_color"]
        ET.SubElement(line_style, f"{{{KML_NS}}}width").text = "1.2"
        poly_style = ET.SubElement(area_style, f"{{{KML_NS}}}PolyStyle")
        ET.SubElement(poly_style, f"{{{KML_NS}}}color").text = style["fill_color"]
        ET.SubElement(poly_style, f"{{{KML_NS}}}fill").text = "1"
        ET.SubElement(poly_style, f"{{{KML_NS}}}outline").text = "1"


def build_description(row):
    cell_features = json.dumps(row["cell_features"], indent=2, sort_keys=True)
    scores = json.dumps(row["scores"], indent=2, sort_keys=True)
    return (
        f"Area {row['cell_id']}\n"
        f"Vibe: {row['vibe']}\n"
        f"Label: {row['label']}\n\n"
        f"Cell Features:\n{cell_features}\n\n"
        f"Scores:\n{scores}"
    )


def add_area_placemark(document, row, style):
    area = ET.SubElement(document, f"{{{KML_NS}}}Placemark")
    ET.SubElement(area, f"{{{KML_NS}}}name").text = f"{row['vibe']} ({row['cell_id']})"
    ET.SubElement(area, f"{{{KML_NS}}}description").text = build_description(row)
    ET.SubElement(area, f"{{{KML_NS}}}styleUrl").text = f"#{style['area_style_id']}"

    polygons = row["polygons"]
    if len(polygons) == 1:
        add_polygon(area, polygons[0])
        return

    multi_geometry = ET.SubElement(area, f"{{{KML_NS}}}MultiGeometry")
    for polygon in polygons:
        add_polygon(multi_geometry, polygon)


def build_area_vibe_kml(
    input_csv_path, output_kml_path, area_cells_csv_path=DEFAULT_AREA_CELLS_CSV
):
    cell_details = read_area_cells_details(area_cells_csv_path)
    rows = read_area_vibe_rows(input_csv_path, cell_details)
    styles = build_label_styles(rows)

    output_path = Path(output_kml_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ET.register_namespace("", KML_NS)
    root = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(root, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = "area-vibe"

    add_styles(document, styles)
    for row in rows:
        style = styles[row["label"]]
        add_area_placemark(document, row, style)

    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_csv", help="Input CSV with columns: cell_id, cell_boundary, vibe, label"
    )
    parser.add_argument("output_kml", help="Output KML path")
    parser.add_argument(
        "--area-cells-csv",
        default=DEFAULT_AREA_CELLS_CSV,
        help=f"Area cells CSV with cell_features and scores (default: {DEFAULT_AREA_CELLS_CSV})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_area_vibe_kml(args.input_csv, args.output_kml, args.area_cells_csv)
