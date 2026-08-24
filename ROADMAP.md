# Roadmap

A staged OSM pipeline that clips an area, extracts and categorizes map features, aggregates them into H3 cells, generates LLM "walking vibe" text per cell (via local Ollama), and renders the result as color-coded KML.

## Near-term

- Fix the stale `requirements.txt` references in the README (see TODO.md) now that the repo runs on `uv`.
- Add CI to run the existing test suite on push.
- The pipeline is currently single-area/single-run (`DATA_DIR` per invocation) — a natural next step given the design is already staged around H3 cells is comparing or merging vibe maps across multiple areas/cities.
