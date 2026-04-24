import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_vibe_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build-area-vibe.py"
    spec = importlib.util.spec_from_file_location("build_area_vibe", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


vibe_builder = load_vibe_module()


class FakeOllamaClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, model, messages, response_format):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "response_format": response_format,
            }
        )
        return {"message": {"content": self.content}}


class BuildAreaVibeTests(unittest.TestCase):
    def test_extract_vibe_prefers_json_vibe_field(self):
        self.assertEqual(
            vibe_builder.extract_vibe('{"vibe":"Lively walkable market streets"}'),
            "Lively walkable market streets",
        )

    def test_extract_vibe_accepts_plain_text_fallback(self):
        self.assertEqual(
            vibe_builder.extract_vibe("  Scenic and quiet  \nsecondary line"),
            "Scenic and quiet",
        )

    def test_classify_cell_vibe_uses_ollama_response_content(self):
        client = FakeOllamaClient('{"vibe":"Calm residential roads"}')

        vibe = vibe_builder.classify_cell_vibe(
            client,
            "mistral-nemo",
            {"poi_total": 2, "intersection_count": 1},
            {"walkable": 0.2, "car_oriented": 0.4},
        )

        self.assertEqual(vibe, "Calm residential roads")
        self.assertEqual(client.calls[0]["model"], "mistral-nemo")
        self.assertEqual(client.calls[0]["response_format"], "json")
        user_message = client.calls[0]["messages"][1]["content"]
        self.assertIn("cell_features=", user_message)
        self.assertIn("scores=", user_message)

    def test_build_area_vibe_writes_expected_columns(self):
        input_rows = [
            {
                "cell_id": "abc",
                "cell_features": '{"poi_total": 3, "intersection_count": 1}',
                "scores": '{"walkable": 0.4, "car_oriented": 0.1}',
                "cell_boundary": '{"type":"Polygon","coordinates":[[[105,20],[105.1,20],[105.1,20.1],[105,20]]]}',
            },
            {
                "cell_id": "def",
                "cell_features": '{"poi_total": 1, "intersection_count": 0}',
                "scores": '{"walkable": 0.0, "car_oriented": 0.6}',
                "cell_boundary": '{"type":"Polygon","coordinates":[[[106,21],[106.1,21],[106.1,21.1],[106,21]]]}',
            },
        ]

        captured = []

        def classify(cell_features, scores):
            captured.append((cell_features, scores))
            return "Balanced local services"

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.csv"

            with input_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(
                    source,
                    fieldnames=["cell_id", "cell_features", "scores", "cell_boundary"],
                )
                writer.writeheader()
                writer.writerows(input_rows)

            vibe_builder.build_area_vibe(str(input_path), str(output_path), classify)

            with output_path.open(newline="", encoding="utf-8") as output:
                result_rows = list(csv.DictReader(output))

        self.assertEqual(
            list(result_rows[0].keys()),
            ["cell_id", "cell_boundary", "vibe"],
        )
        self.assertEqual(result_rows[0]["cell_id"], "abc")
        self.assertEqual(result_rows[1]["cell_id"], "def")
        self.assertEqual(result_rows[0]["vibe"], "Balanced local services")
        self.assertEqual(captured[0][0]["poi_total"], 3)
        self.assertEqual(captured[1][1]["car_oriented"], 0.6)

    def test_build_area_vibe_rejects_missing_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.csv"

            with input_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(source, fieldnames=["cell_id", "cell_features", "cell_boundary"])
                writer.writeheader()
                writer.writerow(
                    {
                        "cell_id": "abc",
                        "cell_features": '{"poi_total": 1}',
                        "cell_boundary": "{}",
                    }
                )

            with self.assertRaisesRegex(ValueError, "Missing required columns: scores"):
                vibe_builder.build_area_vibe(str(input_path), str(output_path), lambda *_: "N/A")

    def test_parse_json_column_rejects_invalid_json(self):
        with self.assertRaisesRegex(ValueError, "invalid JSON in cell_features"):
            vibe_builder.parse_json_column("abc", "cell_features", "{not-json}")

    def test_build_area_vibe_persists_completed_rows_on_late_failure(self):
        input_rows = [
            {
                "cell_id": "abc",
                "cell_features": '{"poi_total": 3}',
                "scores": '{"walkable": 0.4}',
                "cell_boundary": '{"type":"Polygon","coordinates":[[[105,20],[105.1,20],[105.1,20.1],[105,20]]]}',
            },
            {
                "cell_id": "def",
                "cell_features": '{"poi_total": 1}',
                "scores": '{"walkable": 0.1}',
                "cell_boundary": '{"type":"Polygon","coordinates":[[[106,21],[106.1,21],[106.1,21.1],[106,21]]]}',
            },
        ]

        call_count = 0

        def classify(_cell_features, _scores):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("ollama request failed")
            return "First-row vibe"

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "area-cells.csv"
            output_path = Path(temp_dir) / "area-vibe.csv"

            with input_path.open("w", newline="", encoding="utf-8") as source:
                writer = csv.DictWriter(
                    source,
                    fieldnames=["cell_id", "cell_features", "scores", "cell_boundary"],
                )
                writer.writeheader()
                writer.writerows(input_rows)

            with self.assertRaisesRegex(RuntimeError, "ollama request failed"):
                vibe_builder.build_area_vibe(str(input_path), str(output_path), classify)

            with output_path.open(newline="", encoding="utf-8") as output:
                result_rows = list(csv.DictReader(output))

        self.assertEqual(len(result_rows), 1)
        self.assertEqual(result_rows[0]["cell_id"], "abc")
        self.assertEqual(result_rows[0]["vibe"], "First-row vibe")


if __name__ == "__main__":
    unittest.main()
