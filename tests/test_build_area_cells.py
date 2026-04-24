import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_builder_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build-area-cells.py"
    spec = importlib.util.spec_from_file_location("build_area_cells", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


builder = load_builder_module()


class BuildAreaCellsTests(unittest.TestCase):
    def test_build_area_cells_writes_expected_columns(self):
        rows = [
            {
                "name": "Downtown Cafe",
                "geometry": json.dumps(
                    {
                        "type": "LineString",
                        "coordinates": [[105.0, 20.0], [105.0005, 20.0005]],
                    }
                ),
                "category": builder.FOOD_AND_CAFE,
            },
            {
                "name": "Local Road",
                "geometry": json.dumps(
                    {
                        "type": "LineString",
                        "coordinates": [[105.0, 20.0], [105.0005, 20.0005]],
                    }
                ),
                "category": builder.ROAD_HEAVY,
            },
            {
                "name": "Central Park",
                "geometry": json.dumps(
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [105.0001, 20.0001],
                                [105.0005, 20.0001],
                                [105.0005, 20.0005],
                                [105.0001, 20.0005],
                                [105.0001, 20.0001],
                            ]
                        ],
                    }
                ),
                "category": builder.NATURE_QUIET,
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.csv"
            output_path = Path(temp_dir) / "area-cells.csv"

            with input_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(source, fieldnames=["name", "geometry", "category"])
                writer.writeheader()
                writer.writerows(rows)

            builder.build_area_cells(str(input_path), str(output_path), resolution=9)

            with output_path.open(newline="", encoding="utf-8") as output:
                result_rows = list(csv.DictReader(output))

        self.assertEqual(list(result_rows[0].keys()), ["cell_id", "cell_features", "scores", "cell_boundary"])
        self.assertGreaterEqual(len(result_rows), 1)

        features = json.loads(result_rows[0]["cell_features"])
        scores = json.loads(result_rows[0]["scores"])
        boundary = json.loads(result_rows[0]["cell_boundary"])

        self.assertIn("poi_total", features)
        self.assertIn("walkability_proxy", features)
        self.assertIn("car_oriented", scores)
        self.assertEqual(boundary["type"], "Polygon")

    def test_aggregate_cells_computes_intersection_and_derived_metrics(self):
        rows = [
            {
                "name": "Main Road A",
                "geometry": json.dumps(
                    {
                        "type": "LineString",
                        "coordinates": [[105.0, 20.0], [105.001, 20.0]],
                    }
                ),
                "category": builder.ROAD_HEAVY,
            },
            {
                "name": "Main Road B",
                "geometry": json.dumps(
                    {
                        "type": "LineString",
                        "coordinates": [[105.0, 20.0], [105.0, 20.001]],
                    }
                ),
                "category": builder.FAMILY_RESIDENTIAL,
            },
            {
                "name": "Parking Plaza",
                "geometry": json.dumps(
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [105.0001, 20.0001],
                                [105.0002, 20.0001],
                                [105.0002, 20.0002],
                                [105.0001, 20.0002],
                                [105.0001, 20.0001],
                            ]
                        ],
                    }
                ),
                "category": builder.LOCAL_SERVICES,
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.csv"
            with input_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(source, fieldnames=["name", "geometry", "category"])
                writer.writeheader()
                writer.writerows(rows)

            cells = builder.aggregate_cells(str(input_path), resolution=9)

        self.assertEqual(len(cells), 1)
        features = next(iter(cells.values()))
        self.assertGreaterEqual(features["intersection_count"], 1)
        self.assertGreater(features["road_length_m"], 0)
        self.assertGreater(features["footway_length_m"], 0)
        self.assertEqual(
            round(features["walkability_proxy"], 6),
            round(features["intersection_count"] + features["footway_length_m"] / 100.0, 6),
        )
        self.assertEqual(features["parking_count"], 1)

    def test_compute_scores_returns_zero_for_flat_dimensions(self):
        cells = {
            "a": {
                "poi_density": 10.0,
                "intersection_count": 4,
                "hotel_count": 1,
                "culture_count": 2,
                "food_count": 3,
                "cafe_count": 1,
                "bar_count": 0,
                "green_share": 0.2,
                "major_road_length_m": 100.0,
                "residential_area_m2": 10.0,
                "industrial_area_m2": 1.0,
                "footway_length_m": 30.0,
                "parking_count": 0,
            },
            "b": {
                "poi_density": 10.0,
                "intersection_count": 4,
                "hotel_count": 1,
                "culture_count": 2,
                "food_count": 3,
                "cafe_count": 1,
                "bar_count": 0,
                "green_share": 0.2,
                "major_road_length_m": 100.0,
                "residential_area_m2": 10.0,
                "industrial_area_m2": 1.0,
                "footway_length_m": 30.0,
                "parking_count": 0,
            },
        }

        scores = builder.compute_scores(cells)
        self.assertEqual(scores["a"], scores["b"])
        self.assertTrue(all(value == 0.0 for value in scores["a"].values()))

    def test_build_area_cells_handles_empty_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.csv"
            output_path = Path(temp_dir) / "output.csv"

            with input_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(source, fieldnames=["name", "geometry", "category"])
                writer.writeheader()

            builder.build_area_cells(str(input_path), str(output_path), resolution=9)

            with output_path.open(newline="", encoding="utf-8") as output:
                result_rows = list(csv.DictReader(output))

        self.assertEqual(result_rows, [])

    def test_build_area_cells_filters_cells_by_center_radius(self):
        rows = [
            {
                "name": "Near cafe",
                "geometry": json.dumps(
                    {
                        "type": "LineString",
                        "coordinates": [[105.0, 20.0], [105.001, 20.001]],
                    }
                ),
                "category": builder.FOOD_AND_CAFE,
            },
            {
                "name": "Far road",
                "geometry": json.dumps(
                    {
                        "type": "LineString",
                        "coordinates": [[105.1, 20.1], [105.101, 20.101]],
                    }
                ),
                "category": builder.ROAD_HEAVY,
            },
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.csv"
            output_path = Path(temp_dir) / "output.csv"

            with input_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(source, fieldnames=["name", "geometry", "category"])
                writer.writeheader()
                writer.writerows(rows)

            unfiltered_cells = builder.aggregate_cells(str(input_path), resolution=9)
            self.assertGreaterEqual(len(unfiltered_cells), 2)

            builder.build_area_cells(
                str(input_path),
                str(output_path),
                resolution=9,
                center_lat=20.0,
                center_lon=105.0,
                radius_km=1.0,
            )

            with output_path.open(newline="", encoding="utf-8") as output:
                result_rows = list(csv.DictReader(output))

        self.assertGreaterEqual(len(result_rows), 1)
        self.assertLess(len(result_rows), len(unfiltered_cells))

        for row in result_rows:
            cell_lat, cell_lon = builder._h3_cell_to_latlng(row["cell_id"])
            distance_km = builder.haversine_m(20.0, 105.0, cell_lat, cell_lon) / 1000.0
            self.assertLessEqual(distance_km, 1.0)


if __name__ == "__main__":
    unittest.main()
