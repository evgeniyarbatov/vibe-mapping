import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_normalizer_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "normalize-area-points.py"
    spec = importlib.util.spec_from_file_location("normalize_area_points", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


normalizer = load_normalizer_module()


class NormalizeAreaPointsTests(unittest.TestCase):
    def test_parse_type_field_accepts_json_object(self):
        parsed = normalizer.parse_type_field('{"Amenity":"School","building":"yes"}')
        self.assertEqual(parsed, {"amenity": "school", "building": "yes"})

    def test_parse_type_field_handles_invalid_json(self):
        self.assertEqual(normalizer.parse_type_field("{bad"), {})
        self.assertEqual(normalizer.parse_type_field("[]"), {})
        self.assertEqual(normalizer.parse_type_field(""), {})

    def test_classify_category_covers_requested_categories(self):
        self.assertEqual(
            normalizer.classify_category({"amenity": "cafe"}, "Street Cafe"),
            normalizer.FOOD_AND_CAFE,
        )
        self.assertEqual(
            normalizer.classify_category({"amenity": "pub"}, "Late Bar"),
            normalizer.NIGHTLIFE,
        )
        self.assertEqual(
            normalizer.classify_category({"tourism": "hotel"}, "Basic Hotel"),
            normalizer.TOURIST_LODGING,
        )
        self.assertEqual(
            normalizer.classify_category({"tourism": "hotel"}, "Luxury Resort Hotel"),
            normalizer.LUXURY_HIGH_END,
        )
        self.assertEqual(
            normalizer.classify_category({"landuse": "industrial"}, "Industrial Zone"),
            normalizer.INDUSTRIAL_LOGISTICS,
        )
        self.assertEqual(
            normalizer.classify_category({"amenity": "school"}, "Primary School"),
            normalizer.CIVIC_INSTITUTIONAL,
        )
        self.assertEqual(
            normalizer.classify_category({"building": "temple"}, "Temple"),
            normalizer.RELIGIOUS_HISTORIC,
        )
        self.assertEqual(
            normalizer.classify_category({"amenity": "bank"}, "Bank"),
            normalizer.LOCAL_SERVICES,
        )
        self.assertEqual(
            normalizer.classify_category({"landuse": "commercial"}, "Market Block"),
            normalizer.WALKABLE_COMMERCIAL,
        )
        self.assertEqual(
            normalizer.classify_category({"leisure": "park"}, "City Park"),
            normalizer.NATURE_QUIET,
        )
        self.assertEqual(
            normalizer.classify_category({"natural": "water", "water": "lake"}, "Lake"),
            normalizer.SCENIC_WATER_FOREST,
        )
        self.assertEqual(
            normalizer.classify_category({"highway": "residential"}, "Lane"),
            normalizer.FAMILY_RESIDENTIAL,
        )
        self.assertEqual(
            normalizer.classify_category({"highway": "primary"}, "Main Road"),
            normalizer.ROAD_HEAVY,
        )

    def test_normalize_csv_outputs_name_geometry_category_and_type(self):
        rows = [
            {
                "name": "Neighborhood Road",
                "geometry": '{"type":"LineString","coordinates":[[105.0,20.0],[105.1,20.1]]}',
                "type": '{"highway":"residential"}',
            },
            {
                "name": "Big Factory",
                "geometry": '{"type":"Polygon","coordinates":[[[105.0,20.0],[105.1,20.0],[105.1,20.1],[105.0,20.0]]]}',
                "type": '{"landuse":"industrial"}',
            },
            {
                "name": "Lake View",
                "geometry": '{"type":"Polygon","coordinates":[[[105.0,20.0],[105.1,20.0],[105.1,20.1],[105.0,20.0]]]}',
                "type": '{"natural":"water","water":"lake"}',
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.csv"
            output_path = Path(temp_dir) / "normalized.csv"

            with open(source_path, "w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(
                    source,
                    fieldnames=["name", "geometry", "type"],
                )
                writer.writeheader()
                writer.writerows(rows)

            normalizer.normalize_csv(str(source_path), str(output_path))

            with open(output_path, newline="", encoding="utf-8") as output:
                normalized_rows = list(csv.DictReader(output))

        self.assertEqual(list(normalized_rows[0].keys()), ["name", "geometry", "category", "type"])
        self.assertEqual(
            [row["category"] for row in normalized_rows],
            [
                normalizer.FAMILY_RESIDENTIAL,
                normalizer.INDUSTRIAL_LOGISTICS,
                normalizer.SCENIC_WATER_FOREST,
            ],
        )
        self.assertEqual(
            [row["type"] for row in normalized_rows],
            [
                '{"highway":"residential"}',
                '{"landuse":"industrial"}',
                '{"natural":"water","water":"lake"}',
            ],
        )


if __name__ == "__main__":
    unittest.main()
