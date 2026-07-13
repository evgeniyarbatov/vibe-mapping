import argparse
import csv
import json
from pathlib import Path
from urllib import error, request

DEFAULT_MODEL = "mistral-nemo"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_RETRIES = 2

REQUIRED_COLUMNS = {"cell_id", "cell_boundary", "cell_features", "scores"}

SYSTEM_PROMPT = """You are an urban walking experience interpreter.

RULES:
- Every word must trace to a provided feature or score. Invent nothing.
- Treat zero/near-zero values as absence — silence, not omission.
- Translate scores into felt experience (e.g. high walkable = purposeful movement; zero green_share = no visual relief).

SCORE THRESHOLDS:
- busy > 0.8 → overwhelming; > 1.2 → sensory overload + traffic noise implied
- car_oriented > 0.6 + major_road → pedestrian feels exposed
- industrial > 0.7 → functional bulk, noise/fumes implied
- green_quiet < 0 → green exists but offers no relief (penalize "peaceful" language)
- green_share > 0.15 → visible softness, shade, visual breathing room
- water_proximity or water features → openness, reflective quality, edge-walking feel
- walkable > 0.7 + car_oriented > 0.6 → contested, not comfortable
- poi_density > 500 → destination-rich but potentially overwhelming
- touristy > 0.5 + culture_count > 50 → outsider-facing, landmark-heavy
- residential > 0.7 + busy > 1.0 → lived-in but relentless

INTERACTIONS:
- high walkable + high car_oriented = mixed (infrastructure present, comfort compromised)
- high busy + industrial = mixed-to-negative regardless of poi_density
- green_share > 0 + green_quiet < 0 = greenery without peace
- water + low busy + high walkable = calming edge; water + high car_oriented = scenery without access

OUTPUT: Strict JSON only — {"vibe": "...", "label": "positive|mixed|negative"}
vibe: 8–20 words. One concrete sensory or spatial observation grounded in the data."""

USER_PROMPT_TEMPLATE = """Generate a walking vibe grounded ONLY in the data below.

KEY FEATURES:
- footway_length_m / road_length_m → dedicated walking vs shared road space
- green_share → visual softness, shade, relief from hard surfaces
- water_* features → openness, edge quality, reflective space
- building_coverage → enclosure and urban density
- car_orientation → traffic exposure, pedestrian comfort
- walkable score → overall pedestrian signal
- poi_density / poi_total → encounter density per step
- nightlife / foodie / touristy → activation and destination-pull
- residential → warmth vs anonymity
- diversity → mixed-use texture vs mono-function

cell_features={cell_features}
scores={scores}

Return ONLY: {{"vibe":"...","label":"positive|mixed|negative"}}"""

VALID_LABELS = {"positive", "mixed", "negative"}


class OllamaClient:
    def __init__(self, base_url, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, retries=DEFAULT_RETRIES):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def chat(self, model, messages, response_format="json"):
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if response_format:
            payload["format"] = response_format

        url = f"{self.base_url}/api/chat"
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = request.Request(url, data=body, headers=headers, method="POST")

        last_error = None
        for _ in range(self.retries + 1):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")
                return json.loads(raw_body)
            except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc

        raise RuntimeError(f"Failed to query Ollama at {url}: {last_error}")


def sanitize_vibe(vibe):
    cleaned = " ".join(str(vibe or "").split())
    cleaned = cleaned.strip("`\"' ")
    if cleaned.endswith("."):
        cleaned = cleaned[:-1].strip()
    if not cleaned:
        return "Unclassified vibe"
    return cleaned[:240]


def normalize_label(label):
    cleaned = str(label or "").strip().lower()
    if cleaned in VALID_LABELS:
        return cleaned

    if cleaned in {"good", "pleasant", "upbeat", "vibrant", "safe", "lively"}:
        return "positive"
    if cleaned in {"bad", "harsh", "unpleasant", "unsafe", "bleak"}:
        return "negative"

    return "mixed"


def extract_vibe_and_label(content):
    text = str(content or "").strip()
    if not text:
        return "Unclassified vibe", "mixed"

    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            vibe = sanitize_vibe(payload.get("vibe", payload.get("description", "")))
            label = normalize_label(payload.get("label"))
            return vibe, label
    except json.JSONDecodeError:
        pass

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return sanitize_vibe(first_line), "mixed"


def build_prompt(cell_features, scores):
    return USER_PROMPT_TEMPLATE.format(
        cell_features=json.dumps(cell_features, sort_keys=True),
        scores=json.dumps(scores, sort_keys=True),
    )


def classify_cell_vibe(ollama_client, model, cell_features, scores):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(cell_features, scores)},
    ]
    response = ollama_client.chat(model=model, messages=messages, response_format="json")
    content = (response.get("message") or {}).get("content", "")
    return extract_vibe_and_label(content)


def parse_json_column(cell_id, column_name, raw_json):
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cell {cell_id}: invalid JSON in {column_name}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Cell {cell_id}: expected JSON object in {column_name}")
    return parsed


def normalize_classification_result(result):
    if isinstance(result, dict):
        return sanitize_vibe(result.get("vibe")), normalize_label(result.get("label"))
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        return sanitize_vibe(result[0]), normalize_label(result[1])
    return sanitize_vibe(result), "mixed"


def build_area_vibe(input_csv_path, output_csv_path, classify_vibe_fn):
    output_path = Path(output_csv_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with (
        open(input_csv_path, newline="", encoding="utf-8") as source,
        output_path.open("w", newline="", encoding="utf-8") as target,
    ):
        writer = csv.DictWriter(target, fieldnames=["cell_id", "cell_boundary", "vibe", "label"])
        writer.writeheader()
        target.flush()
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS.difference(set(reader.fieldnames or []))
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing required columns: {missing_list}")

        for row in reader:
            cell_id = row["cell_id"]
            cell_boundary = row["cell_boundary"]
            cell_features = parse_json_column(cell_id, "cell_features", row["cell_features"])
            scores = parse_json_column(cell_id, "scores", row["scores"])

            vibe_result = classify_vibe_fn(cell_features, scores)
            vibe, label = normalize_classification_result(vibe_result)
            writer.writerow(
                {
                    "cell_id": cell_id,
                    "cell_boundary": cell_boundary,
                    "vibe": vibe,
                    "label": label,
                }
            )
            target.flush()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", help="Input area cells CSV with cell_features and scores")
    parser.add_argument("output_csv", help="Output CSV with cell_id,cell_boundary,vibe,label")
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"Retries after the first failed request (default: {DEFAULT_RETRIES})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    client = OllamaClient(args.ollama_url, timeout_seconds=args.timeout, retries=args.retries)
    build_area_vibe(
        args.input_csv,
        args.output_csv,
        lambda cell_features, scores: classify_cell_vibe(
            client, args.model, cell_features, scores
        ),
    )
