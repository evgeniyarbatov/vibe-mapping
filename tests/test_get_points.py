import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_get_points_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "get-points.py"
    spec = importlib.util.spec_from_file_location("get_points", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


get_points = load_get_points_module()


class GetPointsTests(unittest.TestCase):
    def test_has_requested_category_tag(self):
        self.assertTrue(get_points.has_requested_category_tag({"amenity": "school"}))
        self.assertTrue(get_points.has_requested_category_tag({"historic": "monument"}))
        self.assertFalse(get_points.has_requested_category_tag({"religion": "buddhist"}))

    def test_legacy_tag_logic_is_preserved(self):
        self.assertTrue(get_points.is_interesting_tag({"religion": "buddhist"}))
        self.assertTrue(get_points.is_interesting_tag({"boundary": "national_park"}))

    def test_geometry_to_geojson_polygon_and_linestring(self):
        polygon_nodes = [
            (10.0, 20.0),
            (10.0, 21.0),
            (11.0, 21.0),
            (10.0, 20.0),
        ]
        line_nodes = [(10.0, 20.0), (10.5, 20.5), (11.0, 21.0)]

        polygon = json.loads(get_points.geometry_to_geojson(polygon_nodes))
        line = json.loads(get_points.geometry_to_geojson(line_nodes))

        self.assertEqual(polygon["type"], "Polygon")
        self.assertEqual(polygon["coordinates"][0][0], [20.0, 10.0])
        self.assertEqual(line["type"], "LineString")
        self.assertEqual(line["coordinates"][0], [20.0, 10.0])

    def test_write_csv_outputs_geometry_and_category_columns(self):
        ways = [
            [
                "City Park",
                [(10.0, 20.0), (10.0, 21.0), (11.0, 21.0), (10.0, 20.0)],
                "https://en.wikipedia.org/wiki/City_park",
                {"leisure": "park", "tourism": "attraction"},
            ],
            [
                "Main Street",
                [(10.0, 20.0), (10.5, 20.5), (11.0, 21.0)],
                "",
                {"highway": "residential"},
            ],
        ]

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".csv") as tmp_file:
            get_points.write_csv(ways, tmp_file.name)
            tmp_file.seek(0)
            rows = list(csv.DictReader(tmp_file))

        self.assertEqual(len(rows), 2)
        self.assertIn("geometry", rows[0])
        self.assertNotIn("lat", rows[0])
        self.assertNotIn("lon", rows[0])

        rows_by_name = {row["name"]: row for row in rows}
        park_geom = json.loads(rows_by_name["City Park"]["geometry"])
        road_geom = json.loads(rows_by_name["Main Street"]["geometry"])

        self.assertEqual(park_geom["type"], "Polygon")
        self.assertEqual(road_geom["type"], "LineString")
        self.assertEqual(rows_by_name["City Park"]["leisure"], "park")
        self.assertEqual(rows_by_name["City Park"]["tourism"], "attraction")
        self.assertEqual(rows_by_name["Main Street"]["highway"], "residential")


if __name__ == "__main__":
    unittest.main()
