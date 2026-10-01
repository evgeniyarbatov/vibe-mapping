# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An OSM-driven pipeline that clips an area (around a GPX run, or a circle around a start point), extracts and categorizes map features, aggregates them into H3 cells with engineered "vibe" scores, generates human-readable walking-vibe summaries via a local Ollama LLM, and renders everything as color-coded KML for map viewing.

## Key files

- `scripts/get-track-area.py` — GPX mode: clip polygon, on-route H3 cells, route GeoJSON
- `scripts/get-circle.py` — circle mode: search-area circle polygon
- `scripts/get-points.py` — extracts raw OSM features (amenity/shop/tourism/leisure/natural/etc.) from the clipped area
- `scripts/normalize-area-points.py` — maps raw OSM tags to a fixed vibe taxonomy
- `scripts/build-area-cells.py` — buckets points into H3 cells, computes engineered metrics and normalized scores
- `scripts/build-area-vibe.py` — calls Ollama to turn cell scores into vibe text + sentiment label
- `scripts/build-area-points-kml.py` / `scripts/build-area-vibe-kml.py` — render KML layers
- See README.md "Script Reference" and "Data Flow" for full per-stage schemas.

## How to run

- `make tools` — installs the `osmium` CLI via Homebrew if missing (the only system OSM tool)
- `make country` — one-time download of the country OSM PBF (needs `evgeniyarbatov/dotfiles` helper, or fetch manually per the Makefile's error message)
- `make run GPX=<file>` (GPX mode) or `make run` (circle mode) — entry point: `area -> points-normalized -> area-points-kml -> area-cells -> area-vibe -> area-vibe-kml`
- `make test` — run all tests in `tests/`
- Requires a local `ollama` server running (default `http://127.0.0.1:11434`, model `mistral-nemo`) for the `area-vibe` stage.

## Conventions / gotchas

- Each pipeline stage writes a CSV/KML artifact that is the contract for the next stage; stages after `area-cells` (`area-vibe`, `area-vibe-kml`) don't declare Make prerequisites on the earlier stage, so run them in order.
- Circle mode uses `START_LAT`/`START_LON`/`RADIUS_KM` from the Makefile; `H3_RESOLUTION` defaults to 9 in GPX mode, 8 in circle mode.
- `.poly` files must have the full osmium format (name line, ring id line, coords, `END`, `END`); `osmium extract` rejects the short form.
- Generated data goes to `$(DATA_DIR)` (default `~/Documents/data/vibe-mapping/`), outside the repo: country PBF in `osm/`, per-run artifacts in `<gpx-name>/` or `circle/`.
