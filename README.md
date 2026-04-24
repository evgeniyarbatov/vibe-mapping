# Vibe Mapping

What is the vibe of a place based on OSM map? Experiment to understand subjective experience from map data.

`scripts/get-points.py` exports area features to CSV with full geometry in a `geometry` column (GeoJSON `Polygon` or `LineString`) plus tag columns:
`amenity`, `shop`, `tourism`, `leisure`, `natural`, `landuse`, `building`, `highway`, `water`, `historic`, `cultural`.
