# Uses uv (https://docs.astral.sh/uv) for dependency management — uv sync creates/updates .venv; run commands via uv run, no manual activation.

DATA_ROOT ?= $(HOME)/Documents/data
REPO_NAME := $(notdir $(CURDIR))
DATA_DIR  ?= $(DATA_ROOT)/$(REPO_NAME)

OSM_URL = https://download.geofabrik.de/asia/vietnam-latest.osm.pbf

DOTFILES_MK := $(HOME)/gitRepo/dotfiles/make/osm-country.mk

# Set before including DOTFILES_MK, which only does OSM_DIR ?=.
OSM_DIR := $(DATA_DIR)/osm

.PHONY: country osm-country-fetch

ifneq ($(wildcard $(DOTFILES_MK)),)
include $(DOTFILES_MK)
else
COUNTRY_OSM_FILE ?= $(notdir $(OSM_URL))

country osm-country-fetch:
	@echo "error: '$@' needs evgeniyarbatov/dotfiles (private helper); not found at $(DOTFILES_MK)." >&2
	@echo "Fetch manually: download $(OSM_URL) into $(OSM_DIR)/$(COUNTRY_OSM_FILE), then retry." >&2
	@exit 1
endif

RADIUS_KM = 5

# GPX mode: `make run GPX=path/to/run.gpx`; otherwise circle mode around START_LAT/START_LON.
ifdef GPX
RUN_NAME ?= $(basename $(notdir $(GPX)))
H3_RESOLUTION ?= 9
else
RUN_NAME ?= circle
H3_RESOLUTION ?= 8
endif
RUN_DIR := $(DATA_DIR)/$(RUN_NAME)

# Hai Tien
START_LAT = 19.843303820107394
START_LON = 105.93544337695647

# Times City
# START_LAT = 20.9948665623132
# START_LON = 105.86777883150903

AREA_POLY = $(RUN_DIR)/area.poly
TRACK_CELLS = $(RUN_DIR)/track-cells.json
TRACK_GEOJSON = $(RUN_DIR)/track.geojson
POINTS = $(RUN_DIR)/area-points.csv
POINTS_NORMALIZED = $(RUN_DIR)/area-points-normalized.csv
AREA_CELLS = $(RUN_DIR)/area-cells.csv
AREA_VIBE = $(RUN_DIR)/area-vibe.csv
AREA_POINTS_KML = $(RUN_DIR)/area-points.kml
AREA_VIBE_KML = $(RUN_DIR)/area-vibe.kml

ifdef GPX
CELL_FILTER_ARGS = --track-cells $(TRACK_CELLS)
VIBE_KML_ARGS = --track-geojson $(TRACK_GEOJSON)
else
CELL_FILTER_ARGS = --center-lat $(START_LAT) --center-lon $(START_LON) --radius-km $(RADIUS_KM)
VIBE_KML_ARGS =
endif
OLLAMA_MODEL = mistral-nemo
OLLAMA_URL = http://127.0.0.1:11434

.PHONY: help install tools test country area-poly area points points-normalized area-points-kml area-cells area-vibe area-vibe-kml run lock

install:
	@uv sync

tools:
	@command -v osmium >/dev/null || brew install osmium-tool

test: install
	@uv run python -m unittest discover -s tests -p 'test_*.py'

area-poly: install
	@mkdir -p $(RUN_DIR)
ifdef GPX
	@uv run python scripts/get-track-area.py \
	--resolution $(H3_RESOLUTION) \
	$(GPX) \
	$(AREA_POLY) \
	$(TRACK_CELLS) \
	$(TRACK_GEOJSON);
else
	@uv run python scripts/get-circle.py \
	$(START_LAT) \
	$(START_LON) \
	$(RADIUS_KM) \
	$(AREA_POLY);
endif

area: tools area-poly
	@osmium extract $(OSM_DIR)/$(COUNTRY_OSM_FILE) \
		--polygon $(AREA_POLY) \
		--strategy smart \
		--overwrite \
		-o $(RUN_DIR)/area.osm

points: install area
	@uv run python scripts/get-points.py \
	$(RUN_DIR)/area.osm \
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
	$(CELL_FILTER_ARGS) \
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
	--area-cells-csv $(AREA_CELLS) \
	$(VIBE_KML_ARGS) \
	$(AREA_VIBE) \
	$(AREA_VIBE_KML);

lock:
	@uv lock

# Entry point: full pipeline (assumes `make country` was already run once); add GPX=<file> for GPX mode.
# area -> points-normalized -> area-points-kml -> area-cells -> area-vibe -> area-vibe-kml.
run: area points-normalized area-points-kml area-cells area-vibe area-vibe-kml
	@echo "Run complete."

help:
	@echo "install           - uv sync"
	@echo "tools             - install osmium CLI via Homebrew if missing"
	@echo "test              - run unit tests"
	@echo "area-poly         - clip polygon: GPX track bbox (GPX=<file>) or circle around START_LAT/LON"
	@echo "area              - extract OSM area"
	@echo "points            - extract points from area"
	@echo "points-normalized - normalize area points"
	@echo "area-points-kml   - build KML from points"
	@echo "area-cells        - build H3 cells from points"
	@echo "area-vibe         - classify area vibe via ollama"
	@echo "area-vibe-kml     - build KML from vibe cells"
	@echo "run               - entry point: full pipeline (after one-time 'make country'); GPX=<file> for GPX mode"
	@echo "lock              - uv lock"
