# Uses uv (https://docs.astral.sh/uv) for dependency management — uv sync creates/updates .venv; run commands via uv run, no manual activation.

OSM_URL = https://download.geofabrik.de/asia/vietnam-latest.osm.pbf
include $(HOME)/gitRepo/dotfiles/make/osm-country.mk

RADIUS_KM = 5
H3_RESOLUTION = 8

# Hai Tien
START_LAT = 19.843303820107394
START_LON = 105.93544337695647

# Times City
# START_LAT = 20.9948665623132
# START_LON = 105.86777883150903

OSM_DIR = osm

CIRCLE = osm/circle.poly
POINTS = osm/area-points.csv
POINTS_NORMALIZED = osm/area-points-normalized.csv
AREA_CELLS = osm/area-cells.csv
AREA_VIBE = osm/area-vibe.csv
AREA_POINTS_KML = osm/area-points.kml
AREA_VIBE_KML = osm/area-vibe.kml
OLLAMA_MODEL = mistral-nemo
OLLAMA_URL = http://127.0.0.1:11434

.PHONY: help install test country circle area points points-normalized area-points-kml area-cells area-vibe area-vibe-kml lock

install:
	@uv sync

test: install
	@uv run python -m unittest discover -s tests -p 'test_*.py'

circle: install
	@uv run python scripts/get-circle.py \
	$(START_LAT) \
	$(START_LON) \
	$(RADIUS_KM) \
	$(CIRCLE);

area: circle
	@osmconvert $(OSM_DIR)/$(COUNTRY_OSM_FILE) \
		-B=$(CIRCLE) \
		--complete-ways \
		--complete-multipolygons \
		-o=$(OSM_DIR)/area.osm.pbf
	@osmium cat --overwrite $(OSM_DIR)/area.osm.pbf -o $(OSM_DIR)/area.osm

points: install area
	@uv run python scripts/get-points.py \
	$(START_LAT) \
	$(START_LON) \
	$(OSM_DIR)/area.osm \
	$(POINTS);

points-normalized: install points
	@uv run python scripts/normalize-area-points.py \
	$(POINTS) \
	$(POINTS_NORMALIZED);

area-points-kml: install points-normalized
	@uv run python scripts/build-area-points-kml.py \
	$(POINTS_NORMALIZED) \
	$(AREA_POINTS_KML);

area-cells: install points-normalized
	@uv run python scripts/build-area-cells.py \
	--resolution $(H3_RESOLUTION) \
	--center-lat $(START_LAT) \
	--center-lon $(START_LON) \
	--radius-km $(RADIUS_KM) \
	$(POINTS_NORMALIZED) \
	$(AREA_CELLS);

area-vibe: install
	@uv run python scripts/build-area-vibe.py \
	--model $(OLLAMA_MODEL) \
	--ollama-url $(OLLAMA_URL) \
	$(AREA_CELLS) \
	$(AREA_VIBE);

area-vibe-kml: install
	@uv run python scripts/build-area-vibe-kml.py \
	$(AREA_VIBE) \
	$(AREA_VIBE_KML);

lock:
	@uv lock

help:
	@echo "install           - uv sync"
	@echo "test              - run unit tests"
	@echo "circle            - generate search circle polygon"
	@echo "area              - extract OSM area"
	@echo "points            - extract points from area"
	@echo "points-normalized - normalize area points"
	@echo "area-points-kml   - build KML from points"
	@echo "area-cells        - build H3 cells from points"
	@echo "area-vibe         - classify area vibe via ollama"
	@echo "area-vibe-kml     - build KML from vibe cells"
	@echo "lock              - uv lock"
