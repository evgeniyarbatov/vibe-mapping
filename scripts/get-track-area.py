import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path
from xml.etree import ElementTree as ET

import h3

METERS_PER_DEGREE_LAT = 111_320.0
BUFFER_EDGE_LENGTHS = 2

Point = tuple[float, float]


def read_track_points(gpx_path: str) -> list[Point]:
    root = ET.parse(gpx_path).getroot()  # noqa: S314
    points = [
        (float(trkpt.attrib["lat"]), float(trkpt.attrib["lon"]))
        for trkpt in root.iterfind(".//{*}trkpt")
    ]
    if not points:
        raise ValueError(f"No track points in {gpx_path}")
    return points


def track_cells(points: Sequence[Point], resolution: int) -> list[str]:
    cells: list[str] = []
    for lat, lon in points:
        cell = h3.latlng_to_cell(lat, lon, resolution)
        if not cells:
            cells.append(cell)
        elif cell != cells[-1]:
            cells.extend(h3.grid_path_cells(cells[-1], cell)[1:])
    return sorted(set(cells))


def buffered_bbox(points: Sequence[Point], buffer_m: float) -> tuple[float, float, float, float]:
    lats = [lat for lat, _ in points]
    lons = [lon for _, lon in points]
    max_abs_lat = max(abs(lat) for lat in lats)
    d_lat = buffer_m / METERS_PER_DEGREE_LAT
    d_lon = buffer_m / (METERS_PER_DEGREE_LAT * math.cos(math.radians(max_abs_lat)))
    return min(lats) - d_lat, min(lons) - d_lon, max(lats) + d_lat, max(lons) + d_lon


def write_poly(bbox: tuple[float, float, float, float], filename: str) -> None:
    min_lat, min_lon, max_lat, max_lon = bbox
    corners = [
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
        (min_lon, min_lat),
    ]
    with open(filename, "w") as f:
        f.write("track\n1\n")
        for lon, lat in corners:
            f.write(f"   {lon:.6f}   {lat:.6f}\n")
        f.write("END\nEND\n")


def write_track_geojson(points: Sequence[Point], filename: str) -> None:
    geometry = {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in points]}
    Path(filename).write_text(json.dumps(geometry), encoding="utf-8")


def build_track_area(
    gpx_path: str,
    output_poly: str,
    output_cells_json: str,
    output_track_geojson: str,
    resolution: int,
) -> None:
    points = read_track_points(gpx_path)
    buffer_m = BUFFER_EDGE_LENGTHS * h3.average_hexagon_edge_length(resolution, unit="m")
    write_poly(buffered_bbox(points, buffer_m), output_poly)
    Path(output_cells_json).write_text(
        json.dumps(track_cells(points, resolution)), encoding="utf-8"
    )
    write_track_geojson(points, output_track_geojson)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("gpx", help="Input GPX file")
    parser.add_argument("output_poly", help="Output .poly (buffered track bbox) for osmconvert")
    parser.add_argument("output_cells_json", help="Output JSON list of H3 cells on the track")
    parser.add_argument("output_track_geojson", help="Output GeoJSON LineString of the track")
    parser.add_argument("--resolution", type=int, default=9, help="H3 resolution (default: 9)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_track_area(
        args.gpx,
        args.output_poly,
        args.output_cells_json,
        args.output_track_geojson,
        args.resolution,
    )
