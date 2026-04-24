VENV_PATH := .venv

PYTHON := $(VENV_PATH)/bin/python
PIP := $(VENV_PATH)/bin/pip
REQUIREMENTS := requirements.txt

OSM_URL = https://download.geofabrik.de/asia/vietnam-latest.osm.pbf
COUNTRY_OSM_FILE = $$(basename $(OSM_URL))

RADIUS_KM = 30
H3_RESOLUTION = 7

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
AREA_VIBE_KML = osm/area-vibe.kml
OLLAMA_MODEL = mistral-nemo
OLLAMA_URL = http://127.0.0.1:11434

venv:
	@python3 -m venv $(VENV_PATH)

install: venv
	@$(PIP) install --disable-pip-version-check -q --upgrade pip
	@$(PIP) install --disable-pip-version-check -q -r $(REQUIREMENTS)

country:
	if [ ! -f $(OSM_DIR)/$(COUNTRY_OSM_FILE) ]; then \
		wget $(OSM_URL) -P $(OSM_DIR); \
	fi

circle:
	@$(PYTHON) scripts/get-circle.py \
	$(START_LAT) \
	$(START_LON) \
	$(RADIUS_KM) \
	$(CIRCLE);

area: circle
	@osmconvert $(OSM_DIR)/$(COUNTRY_OSM_FILE) -B=$(CIRCLE) -o=$(OSM_DIR)/foot/area.osm.pbf
	@osmconvert $(OSM_DIR)/$(COUNTRY_OSM_FILE) -B=$(CIRCLE) -o=$(OSM_DIR)/bicycle/area.osm.pbf
	@osmium cat --overwrite $(OSM_DIR)/foot/area.osm.pbf -o $(OSM_DIR)/area.osm

points:
	@$(PYTHON) scripts/get-points.py \
	$(START_LAT) \
	$(START_LON) \
	$(OSM_DIR)/area.osm \
	$(POINTS);

points-normalized:
	@$(PYTHON) scripts/normalize-area-points.py \
	$(POINTS) \
	$(POINTS_NORMALIZED);

area-cells:
	@$(PYTHON) scripts/build-area-cells.py \
	--resolution $(H3_RESOLUTION) \
	$(POINTS_NORMALIZED) \
	$(AREA_CELLS);

area-vibe:
	@$(PYTHON) scripts/build-area-vibe.py \
	--model $(OLLAMA_MODEL) \
	--ollama-url $(OLLAMA_URL) \
	$(AREA_CELLS) \
	$(AREA_VIBE);

area-vibe-kml:
	@$(PYTHON) scripts/build-area-vibe-kml.py \
	$(AREA_VIBE) \
	$(AREA_VIBE_KML);
