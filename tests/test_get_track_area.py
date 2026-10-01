import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path

import h3


def load_track_area_module() -> types.ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "get-track-area.py"
    spec = importlib.util.spec_from_file_location("get_track_area", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


track_area = load_track_area_module()

GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
 <trk><trkseg>
  <trkpt lat="10.7700" lon="106.6900"><ele>7.8</ele></trkpt>
  <trkpt lat="10.7750" lon="106.6950"><ele>7.9</ele></trkpt>
 </trkseg><trkseg>
  <trkpt lat="10.7800" lon="106.7000"><ele>8.0</ele></trkpt>
 </trkseg></trk>
</gpx>
"""


class GetTrackAreaTests(unittest.TestCase):
    def test_read_track_points_spans_all_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            gpx_path = Path(temp_dir) / "run.gpx"
            gpx_path.write_text(GPX, encoding="utf-8")
            points = track_area.read_track_points(str(gpx_path))

        self.assertEqual(points, [(10.77, 106.69), (10.775, 106.695), (10.78, 106.7)])

    def test_read_track_points_rejects_empty_gpx(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            gpx_path = Path(temp_dir) / "empty.gpx"
            gpx_path.write_text('<gpx xmlns="http://www.topografix.com/GPX/1/1"/>')
            with self.assertRaises(ValueError):
                track_area.read_track_points(str(gpx_path))

    def test_track_cells_fill_gaps_between_distant_points(self) -> None:
        points = [(10.77, 106.69), (10.78, 106.70)]
        cells = track_area.track_cells(points, resolution=9)

        start = h3.latlng_to_cell(*points[0], 9)
        end = h3.latlng_to_cell(*points[1], 9)
        self.assertEqual(set(cells), set(h3.grid_path_cells(start, end)))
        self.assertGreater(len(cells), 2)

    def test_buffered_bbox_contains_track_with_margin(self) -> None:
        points = [(10.77, 106.69), (10.78, 106.70)]
        min_lat, min_lon, max_lat, max_lon = track_area.buffered_bbox(points, buffer_m=1000)

        self.assertAlmostEqual(10.77 - min_lat, 1000 / 111_320, places=6)
        self.assertGreater(106.69 - min_lon, 1000 / 111_320)
        self.assertGreater(max_lat, 10.78)
        self.assertGreater(max_lon, 106.70)

    def test_build_track_area_writes_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gpx_path = root / "run.gpx"
            gpx_path.write_text(GPX, encoding="utf-8")

            track_area.build_track_area(
                str(gpx_path),
                str(root / "area.poly"),
                str(root / "cells.json"),
                str(root / "track.geojson"),
                resolution=9,
            )

            poly_lines = (root / "area.poly").read_text().splitlines()
            cells = json.loads((root / "cells.json").read_text())
            track = json.loads((root / "track.geojson").read_text())

        self.assertEqual(poly_lines[:2], ["track", "1"])
        self.assertEqual(poly_lines[-2:], ["END", "END"])
        self.assertEqual(poly_lines[2], poly_lines[-3])
        self.assertIn(h3.latlng_to_cell(10.775, 106.695, 9), cells)
        self.assertEqual(track["type"], "LineString")
        self.assertEqual(track["coordinates"][0], [106.69, 10.77])


if __name__ == "__main__":
    unittest.main()
