import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def load_kml_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build-area-vibe-kml.py"
    spec = importlib.util.spec_from_file_location("build_area_vibe_kml", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


kml_builder = load_kml_module()


class BuildAreaVibeKmlTests(unittest.TestCase):
    def write_csv(self, path, fieldnames, rows):
        with path.open("w", newline="", encoding="utf-8") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def write_area_cells_csv(self, path, rows):
        self.write_csv(path, ["cell_id", "cell_features", "scores"], rows)

    def test_build_area_vibe_kml_writes_area_placemarks_with_details(self):
        vibe_rows = [
            {
                "cell_id": "cell-a",
                "cell_boundary": '{"type":"Polygon","coordinates":[[[105.0,20.0],[105.2,20.0],[105.2,20.2],[105.0,20.2],[105.0,20.0]]]}',
                "vibe": "Quiet Industrial",
                "label": "positive",
            },
            {
                "cell_id": "cell-b",
                "cell_boundary": '{"type":"Polygon","coordinates":[[[106.0,21.0],[106.2,21.0],[106.2,21.2],[106.0,21.2],[106.0,21.0]]]}',
                "vibe": "Harsh Road Corridor",
                "label": "negative",
            },
            {
                "cell_id": "cell-c",
                "cell_boundary": '{"type":"Polygon","coordinates":[[[106.5,21.5],[106.7,21.5],[106.7,21.7],[106.5,21.7],[106.5,21.5]]]}',
                "vibe": "Calm Residential Pocket",
                "label": "positive",
            },
        ]
        area_cell_rows = [
            {
                "cell_id": "cell-a",
                "cell_features": '{"poi_total": 9, "intersection_count": 3}',
                "scores": '{"walkable": 0.7, "car_oriented": 0.1}',
            },
            {
                "cell_id": "cell-b",
                "cell_features": '{"poi_total": 2, "intersection_count": 0}',
                "scores": '{"walkable": 0.1, "car_oriented": 0.9}',
            },
            {
                "cell_id": "cell-c",
                "cell_features": '{"poi_total": 5, "intersection_count": 1}',
                "scores": '{"walkable": 0.4, "car_oriented": 0.3}',
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            area_cells_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(input_path, ["cell_id", "cell_boundary", "vibe", "label"], vibe_rows)
            self.write_area_cells_csv(area_cells_path, area_cell_rows)

            kml_builder.build_area_vibe_kml(str(input_path), str(output_path), str(area_cells_path))

            tree = ET.parse(output_path)
            placemarks = tree.findall(".//kml:Placemark", namespaces=KML_NS)
            points = tree.findall(".//kml:Point", namespaces=KML_NS)
            self.assertEqual(len(placemarks), 3)
            self.assertEqual(len(points), 0)

            area_placemarks = [
                placemark
                for placemark in placemarks
                if placemark.find("kml:Polygon", namespaces=KML_NS) is not None
            ]
            self.assertEqual(len(area_placemarks), 3)

            area_style_urls = [
                placemark.find("kml:styleUrl", namespaces=KML_NS).text for placemark in area_placemarks
            ]
            self.assertEqual(len(set(area_style_urls)), 2)
            self.assertIn("#area-label-positive", area_style_urls)
            self.assertIn("#area-label-negative", area_style_urls)

            cell_a_description = next(
                placemark.find("kml:description", namespaces=KML_NS).text
                for placemark in placemarks
                if placemark.find("kml:name", namespaces=KML_NS).text == "Quiet Industrial (cell-a)"
            )
            self.assertIn("Area cell-a", cell_a_description)
            self.assertIn("Cell Features:", cell_a_description)
            self.assertIn('"intersection_count": 3', cell_a_description)
            self.assertIn("Scores:", cell_a_description)
            self.assertIn('"walkable": 0.7', cell_a_description)

    def test_build_area_vibe_kml_defaults_invalid_label_to_mixed(self):
        vibe_rows = [
            {
                "cell_id": "cell-a",
                "cell_boundary": '{"type":"Polygon","coordinates":[[[105.0,20.0],[105.2,20.0],[105.2,20.2],[105.0,20.2],[105.0,20.0]]]}',
                "vibe": "Uncertain vibe",
                "label": "unknown",
            }
        ]
        area_cell_rows = [
            {
                "cell_id": "cell-a",
                "cell_features": '{"poi_total": 1}',
                "scores": '{"walkable": 0.2}',
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            area_cells_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(input_path, ["cell_id", "cell_boundary", "vibe", "label"], vibe_rows)
            self.write_area_cells_csv(area_cells_path, area_cell_rows)

            kml_builder.build_area_vibe_kml(str(input_path), str(output_path), str(area_cells_path))
            tree = ET.parse(output_path)

            area_style_url = tree.find(".//kml:Placemark/kml:styleUrl", namespaces=KML_NS).text
            self.assertEqual(area_style_url, "#area-label-mixed")

    def test_build_area_vibe_kml_rejects_missing_required_column(self):
        area_cell_rows = [
            {
                "cell_id": "cell-a",
                "cell_features": '{"poi_total": 1}',
                "scores": '{"walkable": 0.2}',
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            area_cells_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(
                input_path,
                ["cell_id", "cell_boundary", "vibe"],
                [
                    {
                        "cell_id": "cell-a",
                        "cell_boundary": '{"type":"Polygon","coordinates":[[[105.0,20.0],[105.1,20.0],[105.1,20.1],[105.0,20.0]]]}',
                        "vibe": "Quiet streets",
                    }
                ],
            )
            self.write_area_cells_csv(area_cells_path, area_cell_rows)

            with self.assertRaisesRegex(ValueError, "Missing required columns: label"):
                kml_builder.build_area_vibe_kml(str(input_path), str(output_path), str(area_cells_path))

    def test_build_area_vibe_kml_rejects_invalid_boundary_json(self):
        vibe_rows = [
            {
                "cell_id": "cell-a",
                "cell_boundary": "{bad-json}",
                "vibe": "Quiet",
                "label": "mixed",
            }
        ]
        area_cell_rows = [
            {
                "cell_id": "cell-a",
                "cell_features": '{"poi_total": 1}',
                "scores": '{"walkable": 0.2}',
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            area_cells_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(input_path, ["cell_id", "cell_boundary", "vibe", "label"], vibe_rows)
            self.write_area_cells_csv(area_cells_path, area_cell_rows)

            with self.assertRaisesRegex(ValueError, "invalid JSON in cell_boundary"):
                kml_builder.build_area_vibe_kml(str(input_path), str(output_path), str(area_cells_path))

    def test_build_area_vibe_kml_uses_empty_details_when_area_cell_missing(self):
        vibe_rows = [
            {
                "cell_id": "cell-a",
                "cell_boundary": '{"type":"Polygon","coordinates":[[[105.0,20.0],[105.2,20.0],[105.2,20.2],[105.0,20.2],[105.0,20.0]]]}',
                "vibe": "Unknown details",
                "label": "mixed",
            }
        ]
        area_cell_rows = [
            {
                "cell_id": "other-cell",
                "cell_features": '{"poi_total": 4}',
                "scores": '{"walkable": 0.5}',
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            area_cells_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(input_path, ["cell_id", "cell_boundary", "vibe", "label"], vibe_rows)
            self.write_area_cells_csv(area_cells_path, area_cell_rows)

            kml_builder.build_area_vibe_kml(str(input_path), str(output_path), str(area_cells_path))
            tree = ET.parse(output_path)
            description = tree.find(".//kml:Placemark/kml:description", namespaces=KML_NS).text
            self.assertIn("Cell Features:\n{}", description)
            self.assertIn("Scores:\n{}", description)


if __name__ == "__main__":
    unittest.main()
