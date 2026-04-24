# Vibe Mapping

`vibe-mapping` is an OSM-driven pipeline that turns raw map features into:
- structured per-cell urban signals,
- LLM-generated "walking vibe" summaries,
- and a color-coded KML output for map viewing.

## Overall Design

The system is intentionally staged. Each stage writes an artifact that becomes the contract for the next stage.

1. Area extraction: clip a country OSM dataset to a circular area around a start point.
2. Feature extraction: scan OSM ways and keep "interesting" map objects with geometry and selected tags.
3. Category normalization: map raw OSM tags into a fixed vibe taxonomy.
4. Cell aggregation: bucket features into H3 cells and compute engineered metrics and normalized scores.
5. Vibe generation: call Ollama to convert numeric signals into short human-readable vibe text + sentiment label.
6. Visualization: convert normalized features and vibe cells into styled KML layers.

## Data Flow

| Stage | Producer | Output | Main columns / format |
| --- | --- | --- | --- |
| Circle polygon | `scripts/get-circle.py` | `osm/circle.poly` | OSM polygon file for clipping |
| Area OSM clip | `make area` (`osmconvert` + `osmium`) | `osm/area.osm` | OSM XML |
| Raw points | `scripts/get-points.py` | `osm/area-points.csv` | `name`, `geometry`, `wikipedia_url`, `type` |
| Normalized points | `scripts/normalize-area-points.py` | `osm/area-points-normalized.csv` | `name`, `geometry`, `category` |
| Category KML map | `scripts/build-area-points-kml.py` | `osm/area-points.kml` | KML features styled by `category` |
| Cell features + scores | `scripts/build-area-cells.py` | `osm/area-cells.csv` | `cell_id`, `cell_features` (JSON), `scores` (JSON), `cell_boundary` (GeoJSON Polygon JSON) |
| Vibe text + label | `scripts/build-area-vibe.py` | `osm/area-vibe.csv` | `cell_id`, `cell_boundary`, `vibe`, `label` |
| KML map | `scripts/build-area-vibe-kml.py` | `osm/area-vibe.kml` | KML polygons styled by `label` |

## Script Reference

### `scripts/get-circle.py`
Builds a 32-point geodesic circle polygon around `START_LAT` / `START_LON` and writes `.poly` format for `osmconvert`.

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
python scripts/get-points.py <start_lat> <start_lon> <input_osm> <output_csv>
```

Note: `start_lat` and `start_lon` are currently accepted for interface compatibility but not used internally.

### `scripts/normalize-area-points.py`
Maps raw OSM `type` JSON to a fixed category set used by downstream scoring.

Output schema is always:
- `name`
- `geometry`
- `category`

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
- Derived metrics (`poi_density`, `walkability_proxy`, `car_orientation`, `diversity`, etc.)

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

The center/radius flags are optional, but when provided together, only cells whose H3 cell center is within `radius_km` from the given center are kept.

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
  --area-cells-csv osm/area-cells.csv
```

### `scripts/build-area-points-kml.py`
Builds KML from `area-points-normalized.csv` and applies category-based colors so each feature category is visually distinct.

- Supports GeoJSON `Point`, `LineString`, `Polygon`, `MultiPoint`, `MultiLineString`, and `MultiPolygon`.
- Uses fixed colors for known normalized categories and deterministic fallback colors for unexpected category values.

Usage:
```bash
python scripts/build-area-points-kml.py \
  osm/area-points-normalized.csv \
  osm/area-points.kml
```

## Makefile Pipeline

Main targets:
- `make install`: create `.venv` and install `requirements.txt`
- `make country`: download country `.osm.pbf` (Geofabrik URL in `Makefile`)
- `make circle`: generate `osm/circle.poly`
- `make area`: clip country extract to `osm/area.osm`
- `make points`: build `osm/area-points.csv`
- `make points-normalized`: build normalized CSV
- `make area-points-kml`: build category-colored feature KML
- `make area-cells`: build H3 cell features + scores
- `make area-vibe`: build LLM vibe CSV
- `make area-vibe-kml`: build KML

Recommended run order:
```bash
make install
make country
make area
make points-normalized
make area-points-kml
make area-cells
make area-vibe
make area-vibe-kml
```

## Dependencies

Python packages (see `requirements.txt`):
- `geopy`
- `osmium`
- `pandas`
- `h3`

System tools used by Make targets:
- `wget`
- `osmconvert`
- `osmium` CLI
- local `ollama` server (for vibe generation stage)
