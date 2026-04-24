# Vibe Mapping

What is the vibe of a place based on OSM map? Experiment to understand subjective experience from map data.

`scripts/get-points.py` exports area features to CSV with full geometry in a `geometry` column (GeoJSON `Polygon` or `LineString`) and a compact `type` JSON column containing matched tag details from:
`amenity`, `shop`, `tourism`, `leisure`, `natural`, `landuse`, `building`, `highway`, `water`, `historic`, `cultural`.

`scripts/normalize-area-points.py` reads `osm/area-points.csv` and outputs `osm/area-points-normalized.csv` with exactly:
`name`, `geometry`, `category`.
Use `make points-normalized` to run it.

`scripts/build-area-cells.py` reads `osm/area-points-normalized.csv`, assigns each feature to an H3 cell, aggregates per-cell features, computes vibe scores, and writes:
`data/area-cells.csv` with columns `cell_id`, `cell_features`, `scores`, `cell_boundary`.
Use `make area-cells` to run it.

`scripts/build-area-vibe.py` reads `osm/area-cells.csv`, calls local Ollama (`mistral-nemo` by default), and writes:
`osm/area-vibe.csv` with columns `cell_id`, `cell_boundary`, `vibe`.
Use `make area-vibe` to run it.
