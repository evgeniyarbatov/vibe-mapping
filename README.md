# Vibe Mapping

`vibe-mapping` is an OSM-driven pipeline that turns raw map features into:
- structured per-cell urban signals,
- LLM-generated "walking vibe" summaries,
- and a color-coded KML output for map viewing.

## Example

Google My Maps - [link](https://www.google.com/maps/d/u/0/edit?mid=1pV5Zj1CWguzwJkHu4UJhqCfgidr1cCg&usp=sharing)

<img src="https://github.com/user-attachments/assets/5bdef217-d802-46d8-97a8-c362296c53d0" width="400" />

## Quick Start

```bash
make tools      # osmium CLI via Homebrew (if missing)
make country    # one-time: country .osm.pbf
ollama serve    # in another terminal; model mistral-nemo must be pulled
make run GPX=~/path/to/run.gpx   # GPX mode
make run                         # circle mode around START_LAT/START_LON
```

Open `area-vibe.kml` from the run directory (see below) in Google My Maps or Google Earth.

## How the Pipeline Works

Two modes share every stage except the first, and differ only in *which area* is clipped and *which cells* are kept:

- **GPX mode** (`GPX=<file>`) — area is the run's bounding box plus a buffer; only H3 cells the route passes through survive. Meant for ground-truthing: run somewhere, then compare the map's vibe with what you saw.
- **Circle mode** (default) — area is a `RADIUS_KM` circle around `START_LAT`/`START_LON`; cells whose center lies inside the circle survive. Meant for exploring an area you have no track for.

Stages, each writing a file that is the contract for the next:

1. **Clip polygon** — `get-track-area.py` (GPX) or `get-circle.py` (circle) writes `area.poly`. GPX mode also writes `track-cells.json` (the on-route cells) and `track.geojson` (the route).
2. **OSM clip** — `osmium extract` cuts the country extract to `area.osm`, keeping complete ways and multipolygons that cross the boundary.
3. **Feature extraction** — `get-points.py` keeps "interesting" OSM ways (amenities, shops, tourism, leisure, landuse, natural, highways, …) with their geometry and a filtered tag subset.
4. **Normalization** — `normalize-area-points.py` maps raw tags to one of 13 vibe categories (food, nightlife, green, road-heavy, …).
5. **Cell aggregation** — `build-area-cells.py` buckets features into H3 cells, computes per-cell metrics (POI mix, green/water/building area, road vs footway length, intersections, diversity), applies the mode's cell filter, then normalizes metrics into 0–1 scores (`busy`, `walkable`, `green_quiet`, `car_oriented`, …) relative to the other kept cells.
6. **Vibe generation** — `build-area-vibe.py` sends each cell's metrics and scores to a local Ollama model, which returns a one-line walking vibe and a `positive`/`mixed`/`negative` label.
7. **Rendering** — `build-area-vibe-kml.py` draws cells colored by label (with metrics in each description) and, in GPX mode, the route on top; `build-area-points-kml.py` separately renders the categorized features.

Because scores are normalized across the kept cells, a cell's score is relative to the rest of the same run, not absolute.

## Data Flow

Outputs below are relative to the run directory `$(DATA_DIR)/<run>/` — `<run>` is the GPX file name in GPX mode, `circle` otherwise; see [Makefile Pipeline](#makefile-pipeline).

| Stage | Producer | Output | Main columns / format |
| --- | --- | --- | --- |
| Clip polygon (GPX) | `scripts/get-track-area.py` | `area.poly`, `track-cells.json`, `track.geojson` | buffered track bbox; H3 cells on the route; route LineString |
| Clip polygon (circle) | `scripts/get-circle.py` | `area.poly` | OSM polygon file for clipping |
| Area OSM clip | `make area` (`osmium extract`) | `area.osm` | OSM XML |
| Raw points | `scripts/get-points.py` | `area-points.csv` | `name`, `geometry`, `type` |
| Normalized points | `scripts/normalize-area-points.py` | `area-points-normalized.csv` | `name`, `geometry`, `category`, `type` |
| Category KML map | `scripts/build-area-points-kml.py` | `area-points.kml` | KML features styled by `category` |
| Cell features + scores | `scripts/build-area-cells.py` | `area-cells.csv` | `cell_id`, `cell_features` (JSON), `scores` (JSON), `cell_boundary` (GeoJSON Polygon JSON) |
| Vibe text + label | `scripts/build-area-vibe.py` | `area-vibe.csv` | `cell_id`, `cell_boundary`, `vibe`, `label` |
| KML map | `scripts/build-area-vibe-kml.py` | `area-vibe.kml` | KML polygons styled by `label`, plus the route in GPX mode |

## Script Reference

### `scripts/get-track-area.py`
Reads all `trkpt`s from a GPX file and writes:
- a `.poly` rectangle around the track, buffered by two H3 edge lengths so edge cells get complete features;
- a JSON list of H3 cells the route passes through (consecutive points joined with `grid_path_cells`, so fast stretches leave no gaps);
- the route as a GeoJSON `LineString`.

Usage:
```bash
python scripts/get-track-area.py --resolution 9 <gpx> <output_poly> <output_cells_json> <output_track_geojson>
```

### `scripts/get-circle.py`
Builds a 32-point geodesic circle polygon around `START_LAT` / `START_LON` and writes `.poly` format for `osmium extract`.

Usage:
```bash
python scripts/get-circle.py <lat> <lon> <radius_km> <output_poly>
```

### `scripts/get-points.py`
Parses OSM ways with `osmium`, keeps relevant features (amenity/shop/tourism/leisure/natural/etc.), and exports compact rows.

- Geometry output: GeoJSON `Polygon` or `LineString` in the `geometry` column.
- Tag payload: filtered tag subset in `type` JSON.
- Name handling: prefers `name:en`, then `name`; drops unknown names and duplicate names.

Usage:
```bash
python scripts/get-points.py <input_osm> <output_csv>
```

### `scripts/normalize-area-points.py`
Maps raw OSM `type` JSON to a fixed category set used by downstream scoring.

Output schema is always:
- `name`
- `geometry`
- `category`
- `type` (original filtered tag JSON, preserved for downstream feature logic)

Categories:
- `Food & café`
- `Nightlife`
- `Tourist lodging`
- `Local services`
- `Luxury / high-end`
- `Nature / quiet`
- `Industrial / logistics`
- `Civic / institutional`
- `Religious / historic`
- `Family / residential`
- `Road-heavy / car-oriented`
- `Walkable commercial`
- `Scenic / water / forest`

Usage:
```bash
python scripts/normalize-area-points.py [input_csv] [output_csv]
```

### `scripts/build-area-cells.py`
Converts normalized features into H3 cells, computes per-cell aggregates, then derives normalized vibe scores.

Feature engineering includes:
- POI mix (`food_count`, `hotel_count`, `culture_count`, `parking_count`, etc.)
- Land texture (`green_area_m2`, `water_area_m2`, `building_area_m2`, etc.)
- Street structure (`road_length_m`, `major_road_length_m`, `footway_length_m`, intersections)
  - `footway_length_m` counts only dedicated pedestrian highways (`highway=footway|pedestrian|steps`)
- Derived metrics (`poi_density`, `walkability_proxy`, `car_orientation`, `diversity`, etc.)

Polygon land areas are distributed across all overlapping H3 cells using polygon-cell overlap area (instead of assigning full polygon area to a single centroid cell).
Water-vs-green detection for `Scenic / water / forest` now uses OSM tags from `type` first (with name-term fallback), including coastal tags like `natural=coastline` and `natural=beach`, which correctly handles unnamed sea-adjacent polygons.
Coastline `LineString` features additionally contribute a coastal-water proxy area (length distributed across touched H3 cells times a fixed coastal band width), so sea-adjacent cells without explicit water polygons do not remain at zero `water_area_m2`.

Scores include:
- `busy`, `touristy`, `foodie`, `nightlife`, `green_quiet`,
- `residential`, `industrial`, `walkable`, `car_oriented`.

Usage:
```bash
python scripts/build-area-cells.py \
  --resolution 9 \
  --center-lat <start_lat> \
  --center-lon <start_lon> \
  --radius-km <radius_km> \
  <input_csv> <output_csv>
```

Optional cell filters (mutually exclusive):
- `--center-lat`/`--center-lon`/`--radius-km` together keep cells whose H3 center is within `radius_km` of the center.
- `--track-cells <json>` keeps only cells listed in the JSON (from `get-track-area.py`).

### `scripts/build-area-vibe.py`
Reads `area-cells.csv`, sends `cell_features` and `scores` to local Ollama chat API, and writes per-cell vibe text.

- Default model: `mistral-nemo`
- Default Ollama URL: `http://127.0.0.1:11434`
- Output label is normalized to one of: `positive`, `mixed`, `negative`
- Writes rows incrementally so completed rows remain if a later cell fails

Usage:
```bash
python scripts/build-area-vibe.py \
  --model mistral-nemo \
  --ollama-url http://127.0.0.1:11434 \
  <input_csv> <output_csv>
```

### `scripts/build-area-vibe-kml.py`
Builds KML polygons from `area-vibe.csv`, enriches descriptions with `cell_features`/`scores` from `area-cells.csv`, and applies label-based styles.

Label colors:
- `positive`: green
- `mixed`: yellow
- `negative`: red

Usage:
```bash
python scripts/build-area-vibe-kml.py \
  <area_vibe_csv> <output_kml> \
  --area-cells-csv area-cells.csv \
  [--track-geojson track.geojson]
```

`--track-geojson` draws the run as a blue line on top of the cells.

### `scripts/build-area-points-kml.py`
Builds KML from `area-points-normalized.csv` and applies category-based colors so each feature category is visually distinct.

- Supports GeoJSON `Point`, `LineString`, `Polygon`, `MultiPoint`, `MultiLineString`, and `MultiPolygon`.
- Uses fixed colors for known normalized categories and deterministic fallback colors for unexpected category values.

Usage:
```bash
python scripts/build-area-points-kml.py \
  area-points-normalized.csv \
  area-points.kml
```

## Makefile Pipeline

`H3_RESOLUTION` defaults to 9 in GPX mode (~175 m cells, block-level) and 8 in circle mode (~460 m cells).

Generated data is written outside the repo, under `DATA_DIR` (default `~/Documents/data/vibe-mapping/`). The country extract lives in `$(DATA_DIR)/osm/`; each run's artifacts go to `$(DATA_DIR)/<gpx-name>/` or `$(DATA_DIR)/circle/`. Override with `DATA_ROOT=`, `DATA_DIR=`, or `RUN_NAME=`.

Main targets:
- `make install`: `uv sync`
- `make tools`: install the `osmium` CLI via Homebrew if missing
- `make test`: run all tests in `tests/`
- `make country`: download country `.osm.pbf` (Geofabrik URL in `Makefile`)
- `make area-poly`: build the clip polygon (and track cells/route in GPX mode)
- `make area`: clip country extract to `area.osm`
- `make points`: build `area-points.csv`
- `make points-normalized`: build normalized CSV
- `make area-points-kml`: build category-colored feature KML
- `make area-cells`: build H3 cell features + scores
- `make area-vibe`: build LLM vibe CSV
- `make area-vibe-kml`: build KML
- `make run`: full pipeline (see [Quick Start](#quick-start))

## Dependencies

Python packages (see `pyproject.toml`):
- `geopy`
- `osmium`
- `pandas`
- `h3`

System tools:
- `uv` — Python environment (`make install`)
- `osmium` CLI — installed by `make tools` (Homebrew)
- local `ollama` server with `mistral-nemo` — vibe generation stage
