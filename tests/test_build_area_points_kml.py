import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def load_kml_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build-area-points-kml.py"
    spec = importlib.util.spec_from_file_location("build_area_points_kml", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


kml_builder = load_kml_module()


class BuildAreaPointsKmlTests(unittest.TestCase):
    def write_csv(self, path, fieldnames, rows):
        with path.open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_build_area_points_kml_writes_category_styled_placemarks(self):
        rows = [
            {
                "name": "Residential Street",
                "geometry": '{"type":"LineString","coordinates":[[105.0,20.0],[105.1,20.1]]}',
                "category": "Family / residential",
            },
            {
                "name": "Lakefront Park",
                "geometry": '{"type":"Polygon","coordinates":[[[106.0,21.0],[106.2,21.0],[106.2,21.2],[106.0,21.2],[106.0,21.0]]]}',
                "category": "Scenic / water / forest",
            },
            {
                "name": "Prototype Place",
                "geometry": '{"type":"Point","coordinates":[106.5,21.5]}',
                "category": "Experimental category",
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-points-normalized.csv"
            output_path = Path(temp_dir) / "area-points.kml"
            self.write_csv(input_path, ["name", "geometry", "category"], rows)

            kml_builder.build_area_points_kml(str(input_path), str(output_path))

            tree = ET.parse(output_path)
            placemarks = tree.findall(".//kml:Placemark", namespaces=KML_NS)
            styles = tree.findall(".//kml:Style", namespaces=KML_NS)
            lines = tree.findall(".//kml:LineString", namespaces=KML_NS)
            polygons = tree.findall(".//kml:Polygon", namespaces=KML_NS)
            points = tree.findall(".//kml:Point", namespaces=KML_NS)

            self.assertEqual(len(placemarks), 3)
            self.assertEqual(len(styles), 3)
            self.assertEqual(len(lines), 1)
            self.assertEqual(len(polygons), 1)
            self.assertEqual(len(points), 1)

            style_urls = [
                placemark.find("kml:styleUrl", namespaces=KML_NS).text for placemark in placemarks
            ]
            self.assertIn("#category-family-residential", style_urls)
            self.assertIn("#category-scenic-water-forest", style_urls)
            self.assertIn("#category-experimental-category", style_urls)

            experimental_style = tree.find(
                './/kml:Style[@id="category-experimental-category"]/kml:LineStyle/kml:color',
                namespaces=KML_NS,
            ).text
            expected_rgb = kml_builder.color_for_category("Experimental category")
            self.assertEqual(experimental_style, kml_builder.rgb_to_kml_color(expected_rgb, "ff"))

    def test_build_area_points_kml_rejects_missing_required_column(self):
        rows = [
            {
                "name": "Broken Row",
                "geometry": '{"type":"Point","coordinates":[106.0,20.0]}',
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-points-normalized.csv"
            output_path = Path(temp_dir) / "area-points.kml"
            self.write_csv(input_path, ["name", "geometry"], rows)

            with self.assertRaisesRegex(ValueError, "Missing required columns: category"):
                kml_builder.build_area_points_kml(str(input_path), str(output_path))

    def test_build_area_points_kml_rejects_invalid_geometry_json(self):
        rows = [
            {
                "name": "Broken Geometry",
                "geometry": "{bad-json}",
                "category": "Family / residential",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-points-normalized.csv"
            output_path = Path(temp_dir) / "area-points.kml"
            self.write_csv(input_path, ["name", "geometry", "category"], rows)

            with self.assertRaisesRegex(ValueError, "invalid JSON in geometry"):
                kml_builder.build_area_points_kml(str(input_path), str(output_path))

    def test_build_area_points_kml_rejects_unsupported_geometry_type(self):
        rows = [
            {
                "name": "Unsupported",
                "geometry": '{"type":"GeometryCollection","geometries":[]}',
                "category": "Family / residential",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-points-normalized.csv"
            output_path = Path(temp_dir) / "area-points.kml"
            self.write_csv(input_path, ["name", "geometry", "category"], rows)

            with self.assertRaisesRegex(ValueError, "unsupported geometry type"):
                kml_builder.build_area_points_kml(str(input_path), str(output_path))


if __name__ == "__main__":
    unittest.main()
