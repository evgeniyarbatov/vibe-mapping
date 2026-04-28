import json
import sys

import osmium
import pandas as pd

REQUESTED_TAG_KEYS = (
    "amenity",
    "shop",
    "tourism",
    "leisure",
    "natural",
    "landuse",
    "building",
    "highway",
    "water",
    "historic",
    "cultural",
)


def tags_to_dict(tags):
    tag_map = {}
    if hasattr(tags, "items"):
        for key, value in tags.items():
            tag_map[str(key)] = str(value)
        return tag_map

    for tag in tags:
        tag_map[str(tag.k)] = str(tag.v)
    return tag_map


def is_temple(tags):
    return (
        tags.get("landuse") == "religious"
        or tags.get("building") == "temple"
        or tags.get("amenity") in {"place_of_worship"}
        or tags.get("religion") is not None
    )


def is_park(tags):
    return (
        tags.get("leisure") in {"park", "garden", "nature_reserve"}
        or tags.get("landuse") in {"recreation_ground", "grass"}
        or tags.get("boundary") == "national_park"
    )


def is_lake(tags):
    return tags.get("water") in {"lake", "pond", "reservoir"} or (
        tags.get("natural") == "water" and tags.get("water") in {"lake", "pond", "reservoir"}
    )


def is_tourist_attraction(tags):
    return tags.get("tourism") == "attraction"


def is_cultural_site(tags):
    return (
        tags.get("tourism")
        in {"museum", "gallery", "artwork", "attraction", "viewpoint", "information"}
        or tags.get("historic") in {"monument", "memorial", "archaeological_site", "castle", "ruins"}
        or tags.get("amenity") in {"theatre", "arts_centre", "cinema"}
        or tags.get("cultural") is not None
    )


def has_requested_category_tag(tags):
    return any(tags.get(key) is not None for key in REQUESTED_TAG_KEYS)


def is_interesting_tag(tags):
    return (
        has_requested_category_tag(tags)
        or is_temple(tags)
        or is_park(tags)
        or is_lake(tags)
        or is_tourist_attraction(tags)
        or is_cultural_site(tags)
    )


def get_name(tags):
    return tags.get("name:en", tags.get("name", "Unknown"))


def geometry_to_geojson(way_nodes):
    coordinates = [[float(lon), float(lat)] for lat, lon in way_nodes]
    is_polygon = len(coordinates) >= 4 and coordinates[0] == coordinates[-1]

    if is_polygon:
        geometry = {"type": "Polygon", "coordinates": [coordinates]}
    else:
        geometry = {"type": "LineString", "coordinates": coordinates}

    return json.dumps(geometry, separators=(",", ":"))


def type_details_to_json(type_details):
    return json.dumps(type_details, separators=(",", ":"), sort_keys=True)


def extract_type_details(tags):
    return {key: tags[key] for key in REQUESTED_TAG_KEYS if tags.get(key) is not None}


# --- OSM HANDLER ---


class WayHandler(osmium.SimpleHandler):
    def __init__(self):
        osmium.SimpleHandler.__init__(self)
        self.ways = []

    def way(self, w):
        tag_map = tags_to_dict(w.tags)
        if not is_interesting_tag(tag_map):
            return

        way_nodes = []
        for n in w.nodes:
            try:
                way_nodes.append((float(n.lat), float(n.lon)))
            except Exception:
                continue

        if len(way_nodes) < 2:
            return

        name = get_name(tag_map)
        type_details = extract_type_details(tag_map)
        self.ways.append([name, way_nodes, type_details])


# --- UTILITIES ---


def write_csv(ways, filename):
    df = pd.DataFrame(ways, columns=["name", "way_nodes", "type_details"])
    # Keep unnamed areas (name == "Unknown") but continue removing ambiguous
    # duplicates among named places.
    unnamed_mask = df["name"] == "Unknown"
    named = df[~unnamed_mask].drop_duplicates(subset="name", keep=False)
    unnamed = df[unnamed_mask]
    df = pd.concat([named, unnamed], ignore_index=True)

    output_columns = ["name", "geometry", "type"]
    if df.empty:
        pd.DataFrame(columns=output_columns).to_csv(filename, index=False)
        return

    df["geometry"] = df["way_nodes"].apply(geometry_to_geojson)
    df["type"] = df["type_details"].apply(type_details_to_json)

    df[output_columns].to_csv(filename, index=False)


def main(start_lat, start_lon, osm_file, filename):
    del start_lat
    del start_lon
    handler = WayHandler()
    handler.apply_file(osm_file, locations=True)
    write_csv(handler.ways, filename)


if __name__ == "__main__":
    main(*sys.argv[1:])
