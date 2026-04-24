import sys
import osmium
import pandas as pd
from haversine import haversine

# --- WIKIPEDIA EXTRACTION ---


def get_wikipedia_url(tags):
    """Get Wikipedia or Wikidata URL from OSM tags."""
    # Check if POI has a wikipedia tag
    if "wikipedia" in tags:
        wiki_tag = tags["wikipedia"]
        if ":" in wiki_tag:
            lang, title = wiki_tag.split(":", 1)
            return f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"

    # Check for wikidata tag
    if "wikidata" in tags:
        wikidata_id = tags["wikidata"]
        return f"https://www.wikidata.org/wiki/{wikidata_id}"

    return None


# --- OSM HANDLER ---


class WayHandler(osmium.SimpleHandler):
    def __init__(self):
        osmium.SimpleHandler.__init__(self)
        self.ways = []

    # --- CATEGORY CHECKS ---

    def is_temple(self, tags):
        return (
            tags.get("landuse") == "religious"
            or tags.get("building") == "temple"
            or tags.get("amenity") in {"place_of_worship"}
            or tags.get("religion") is not None
        )

    def is_park(self, tags):
        return (
            tags.get("leisure") in {"park", "garden", "nature_reserve"}
            or tags.get("landuse") in {"recreation_ground", "grass"}
            or tags.get("boundary") == "national_park"
        )

    def is_lake(self, tags):
        return tags.get("water") in {"lake", "pond", "reservoir"} or (
            tags.get("natural") == "water"
            and tags.get("water") in {"lake", "pond", "reservoir"}
        )

    def is_tourist_attraction(self, tags):
        return tags.get("tourism") == "attraction"

    def is_museum(self, tags):
        return tags.get("tourism") == "museum"

    def is_cultural_site(self, tags):
        return (
            tags.get("tourism")
            in {
                "museum",
                "gallery",
                "artwork",
                "attraction",
                "viewpoint",
                "information",
            }
            or tags.get("historic")
            in {"monument", "memorial", "archaeological_site", "castle", "ruins"}
            or tags.get("amenity") in {"theatre", "arts_centre", "cinema"}
        )

    def is_interesting_tag(self, tags):
        return (
            self.is_temple(tags)
            or self.is_park(tags)
            or self.is_lake(tags)
            or self.is_tourist_attraction(tags)
            or self.is_cultural_site(tags)
        )

    # --- HELPERS ---

    def get_name(self, tags):
        return tags.get("name:en", tags.get("name", "Unknown"))

    # --- MAIN WAY PROCESSING ---

    def way(self, w):
        if not self.is_interesting_tag(w.tags):
            return

        way_nodes = []
        for n in w.nodes:
            try:
                way_nodes.append((float(n.lat), float(n.lon)))
            except Exception:
                continue

        if not way_nodes:
            return

        name = self.get_name(w.tags)
        wiki_url = get_wikipedia_url(w.tags)
        self.ways.append([name, way_nodes, wiki_url])


# --- UTILITIES ---


def get_point(start, way_border):
    distances = [haversine(start, (float(lat), float(lon))) for lat, lon in way_border]
    min_dist_index = distances.index(min(distances))
    return way_border[min_dist_index]


def write_csv(start_lat, start_lon, ways, filename):
    df = pd.DataFrame(ways, columns=["name", "way_border", "wikipedia_url"])
    df = df[df["name"] != "Unknown"]
    df = df.drop_duplicates(subset="name", keep=False)

    df["way_border"] = df["way_border"].apply(
        lambda x: [(float(lat), float(lon)) for lat, lon in x]
    )
    df[["lat", "lon"]] = df["way_border"].apply(
        lambda way: pd.Series(get_point((float(start_lat), float(start_lon)), way))
    )

    df[["name", "lat", "lon", "wikipedia_url"]].to_csv(filename, index=False)


def main(start_lat, start_lon, osm_file, filename):
    handler = WayHandler()
    handler.apply_file(osm_file, locations=True)
    write_csv(start_lat, start_lon, handler.ways, filename)


if __name__ == "__main__":
    main(*sys.argv[1:])