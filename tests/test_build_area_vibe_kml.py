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

    def test_build_area_vibe_kml_writes_area_and_label_placemarks(self):
        rows = [
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

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(input_path, ["cell_id", "cell_boundary", "vibe", "label"], rows)

            kml_builder.build_area_vibe_kml(str(input_path), str(output_path))

            tree = ET.parse(output_path)
            placemarks = tree.findall(".//kml:Placemark", namespaces=KML_NS)
            self.assertEqual(len(placemarks), 6)

            area_placemarks = [
                placemark
                for placemark in placemarks
                if placemark.find("kml:Polygon", namespaces=KML_NS) is not None
            ]
            label_placemarks = [
                placemark
                for placemark in placemarks
                if placemark.find("kml:Point", namespaces=KML_NS) is not None
            ]

            self.assertEqual(len(area_placemarks), 3)
            self.assertEqual(len(label_placemarks), 3)

            area_style_urls = [
                placemark.find("kml:styleUrl", namespaces=KML_NS).text for placemark in area_placemarks
            ]
            self.assertEqual(len(set(area_style_urls)), 2)
            self.assertIn("#area-label-positive", area_style_urls)
            self.assertIn("#area-label-negative", area_style_urls)

            first_label_name = label_placemarks[0].find("kml:name", namespaces=KML_NS).text
            self.assertIn(
                first_label_name,
                {"Quiet Industrial", "Harsh Road Corridor", "Calm Residential Pocket"},
            )

            first_label_coords = label_placemarks[0].find(
                ".//kml:coordinates", namespaces=KML_NS
            ).text
            self.assertRegex(first_label_coords, r"^\d+\.\d+,\d+\.\d+,0$")

    def test_build_area_vibe_kml_defaults_invalid_label_to_mixed(self):
        rows = [
            {
                "cell_id": "cell-a",
                "cell_boundary": '{"type":"Polygon","coordinates":[[[105.0,20.0],[105.2,20.0],[105.2,20.2],[105.0,20.2],[105.0,20.0]]]}',
                "vibe": "Uncertain vibe",
                "label": "unknown",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(input_path, ["cell_id", "cell_boundary", "vibe", "label"], rows)

            kml_builder.build_area_vibe_kml(str(input_path), str(output_path))
            tree = ET.parse(output_path)

            area_style_url = tree.find(
                ".//kml:Placemark/kml:styleUrl", namespaces=KML_NS
            ).text
            self.assertEqual(area_style_url, "#area-label-mixed")

    def test_build_area_vibe_kml_rejects_missing_required_column(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
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

            with self.assertRaisesRegex(ValueError, "Missing required columns: label"):
                kml_builder.build_area_vibe_kml(str(input_path), str(output_path))

    def test_build_area_vibe_kml_rejects_invalid_boundary_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-vibe.csv"
            output_path = Path(temp_dir) / "area-vibe.kml"
            self.write_csv(
                input_path,
                ["cell_id", "cell_boundary", "vibe", "label"],
                [
                    {
                        "cell_id": "cell-a",
                        "cell_boundary": "{bad-json}",
                        "vibe": "Quiet",
                        "label": "mixed",
                    }
                ],
            )

            with self.assertRaisesRegex(ValueError, "invalid JSON in cell_boundary"):
                kml_builder.build_area_vibe_kml(str(input_path), str(output_path))


if __name__ == "__main__":
    unittest.main()
