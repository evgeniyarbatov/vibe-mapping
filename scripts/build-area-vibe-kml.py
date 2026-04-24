import argparse
import csv
import json
from pathlib import Path
from xml.etree import ElementTree as ET


KML_NS = "http://www.opengis.net/kml/2.2"
REQUIRED_COLUMNS = {"cell_id", "cell_boundary", "vibe", "label"}
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
        raise ValueError(f"Cell {cell_id}: unsupported geometry type in cell_boundary: {geometry_type}")

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


def ring_signed_area(ring):
    area = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        area += x1 * y2 - x2 * y1
    return area * 0.5


def ring_centroid(ring):
    signed_area = ring_signed_area(ring)
    if abs(signed_area) < 1e-12:
        lon = sum(point[0] for point in ring) / len(ring)
        lat = sum(point[1] for point in ring) / len(ring)
        return lon, lat

    factor = 1.0 / (6.0 * signed_area)
    cx = 0.0
    cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return cx * factor, cy * factor


def polygon_centroid(polygons):
    weighted_lon = 0.0
    weighted_lat = 0.0
    total_weight = 0.0
    all_points = []

    for polygon in polygons:
        outer = polygon["outer"]
        all_points.extend(outer)

        area = abs(ring_signed_area(outer))
        lon, lat = ring_centroid(outer)
        if area > 1e-12:
            weighted_lon += lon * area
            weighted_lat += lat * area
            total_weight += area

    if total_weight > 1e-12:
        return weighted_lon / total_weight, weighted_lat / total_weight

    if not all_points:
        return 0.0, 0.0
    lon = sum(point[0] for point in all_points) / len(all_points)
    lat = sum(point[1] for point in all_points) / len(all_points)
    return lon, lat


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


def read_area_vibe_rows(input_csv_path):
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
            centroid_lon, centroid_lat = polygon_centroid(polygons)
            rows.append(
                {
                    "cell_id": cell_id,
                    "vibe": vibe,
                    "label": label,
                    "polygons": polygons,
                    "centroid": (centroid_lon, centroid_lat),
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
            "label_style_id": f"label-label-{label}",
            "line_color": rgb_to_kml_color(rgb, "ff"),
            "fill_color": rgb_to_kml_color(rgb, "88"),
            "label_color": rgb_to_kml_color(rgb, "ff"),
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

        label_style = ET.SubElement(document, f"{{{KML_NS}}}Style", id=style["label_style_id"])
        labels = ET.SubElement(label_style, f"{{{KML_NS}}}LabelStyle")
        ET.SubElement(labels, f"{{{KML_NS}}}color").text = style["label_color"]
        ET.SubElement(labels, f"{{{KML_NS}}}scale").text = "1.0"
        icons = ET.SubElement(label_style, f"{{{KML_NS}}}IconStyle")
        ET.SubElement(icons, f"{{{KML_NS}}}scale").text = "0.0"


def add_area_placemark(document, row, style):
    area = ET.SubElement(document, f"{{{KML_NS}}}Placemark")
    ET.SubElement(area, f"{{{KML_NS}}}name").text = f"{row['vibe']} ({row['cell_id']})"
    ET.SubElement(area, f"{{{KML_NS}}}description").text = (
        f"Area {row['cell_id']} | vibe: {row['vibe']} | label: {row['label']}"
    )
    ET.SubElement(area, f"{{{KML_NS}}}styleUrl").text = f"#{style['area_style_id']}"

    polygons = row["polygons"]
    if len(polygons) == 1:
        add_polygon(area, polygons[0])
        return

    multi_geometry = ET.SubElement(area, f"{{{KML_NS}}}MultiGeometry")
    for polygon in polygons:
        add_polygon(multi_geometry, polygon)


def add_label_placemark(document, row, style):
    label = ET.SubElement(document, f"{{{KML_NS}}}Placemark")
    ET.SubElement(label, f"{{{KML_NS}}}name").text = row["vibe"]
    ET.SubElement(label, f"{{{KML_NS}}}description").text = (
        f"Label for area {row['cell_id']} | label: {row['label']}"
    )
    ET.SubElement(label, f"{{{KML_NS}}}styleUrl").text = f"#{style['label_style_id']}"

    point = ET.SubElement(label, f"{{{KML_NS}}}Point")
    centroid_lon, centroid_lat = row["centroid"]
    ET.SubElement(point, f"{{{KML_NS}}}coordinates").text = f"{centroid_lon:.8f},{centroid_lat:.8f},0"


def build_area_vibe_kml(input_csv_path, output_kml_path):
    rows = read_area_vibe_rows(input_csv_path)
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
        add_label_placemark(document, row, style)

    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", help="Input CSV with columns: cell_id, cell_boundary, vibe, label")
    parser.add_argument("output_kml", help="Output KML path")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_area_vibe_kml(args.input_csv, args.output_kml)
