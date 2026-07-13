import csv
import json
import sys

FOOD_AND_CAFE = "Food & café"
NIGHTLIFE = "Nightlife"
TOURIST_LODGING = "Tourist lodging"
LOCAL_SERVICES = "Local services"
LUXURY_HIGH_END = "Luxury / high-end"
NATURE_QUIET = "Nature / quiet"
INDUSTRIAL_LOGISTICS = "Industrial / logistics"
CIVIC_INSTITUTIONAL = "Civic / institutional"
RELIGIOUS_HISTORIC = "Religious / historic"
FAMILY_RESIDENTIAL = "Family / residential"
ROAD_HEAVY = "Road-heavy / car-oriented"
WALKABLE_COMMERCIAL = "Walkable commercial"
SCENIC_WATER_FOREST = "Scenic / water / forest"


ALL_CATEGORIES = {
    FOOD_AND_CAFE,
    NIGHTLIFE,
    TOURIST_LODGING,
    LOCAL_SERVICES,
    LUXURY_HIGH_END,
    NATURE_QUIET,
    INDUSTRIAL_LOGISTICS,
    CIVIC_INSTITUTIONAL,
    RELIGIOUS_HISTORIC,
    FAMILY_RESIDENTIAL,
    ROAD_HEAVY,
    WALKABLE_COMMERCIAL,
    SCENIC_WATER_FOREST,
}

FOOD_AMENITIES = {
    "restaurant",
    "cafe",
    "fast_food",
    "food_court",
    "ice_cream",
    "biergarten",
    "bbq",
}
FOOD_SHOPS = {
    "bakery",
    "coffee",
    "confectionery",
    "deli",
    "pastry",
    "tea",
    "wine",
}

NIGHTLIFE_AMENITIES = {"bar", "pub", "nightclub", "stripclub", "casino"}
NIGHTLIFE_LEISURE = {"adult_gaming_centre", "dance"}

LODGING_TOURISM = {
    "hotel",
    "guest_house",
    "hostel",
    "motel",
    "apartment",
    "resort",
    "chalet",
    "camp_site",
    "caravan_site",
}
LUXURY_NAME_TERMS = {"luxury", "resort", "golf", "country club", "boutique"}

CIVIC_AMENITIES = {
    "school",
    "hospital",
    "university",
    "college",
    "kindergarten",
    "police",
    "courthouse",
    "library",
    "townhall",
    "community_centre",
    "prison",
    "theatre",
    "arts_centre",
}
CIVIC_BUILDINGS = {"school", "hospital", "university", "public", "civic"}

RELIGIOUS_AMENITIES = {"place_of_worship"}
RELIGIOUS_BUILDINGS = {
    "temple",
    "church",
    "cathedral",
    "mosque",
    "shrine",
    "synagogue",
    "monastery",
}
RELIGIOUS_LANDUSE = {"religious", "cemetery"}
HISTORIC_TOURISM = {"museum", "memorial", "monument"}

INDUSTRIAL_LANDUSE = {"industrial", "harbour", "port", "railway"}
INDUSTRIAL_BUILDINGS = {"industrial", "warehouse", "factory"}

LOCAL_SERVICE_AMENITIES = {
    "bank",
    "atm",
    "post_office",
    "social_facility",
    "pharmacy",
    "doctors",
    "clinic",
    "dentist",
    "veterinary",
    "bus_station",
    "fuel",
    "car_wash",
    "bureau_de_change",
    "charging_station",
}
WALKABLE_AMENITIES = {"marketplace"}

SCENIC_NATURAL = {
    "water",
    "coastline",
    "beach",
    "wood",
    "wetland",
    "bay",
    "cliff",
    "peak",
    "sand",
    "heath",
    "scrub",
}
SCENIC_WATER = {
    "lake",
    "river",
    "canal",
    "reservoir",
    "pond",
    "stream",
    "basin",
}
SCENIC_TOURISM = {"viewpoint"}

QUIET_LEISURE = {"park", "garden", "nature_reserve"}
QUIET_LANDUSE = {"recreation_ground", "grass", "farmyard"}

RESIDENTIAL_BUILDINGS = {"house", "residential", "apartments", "dormitory"}
RESIDENTIAL_HIGHWAYS = {"residential", "living_street"}

ROAD_HEAVY_HIGHWAYS = {
    "service",
    "tertiary",
    "secondary",
    "primary",
    "trunk",
    "unclassified",
    "construction",
    "services",
    "track",
    "motorway",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
}


def parse_type_field(type_field):
    if not type_field:
        return {}

    try:
        parsed = json.loads(type_field)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    normalized = {}
    for key, value in parsed.items():
        if value is None:
            continue
        normalized[str(key).lower()] = str(value).lower()

    return normalized


def has_name_term(name_lower, terms):
    return any(term in name_lower for term in terms)


def classify_category(tags, name):
    amenity = tags.get("amenity", "")
    tourism = tags.get("tourism", "")
    leisure = tags.get("leisure", "")
    natural = tags.get("natural", "")
    water = tags.get("water", "")
    landuse = tags.get("landuse", "")
    building = tags.get("building", "")
    highway = tags.get("highway", "")
    historic = tags.get("historic", "")
    shop = tags.get("shop", "")
    name_lower = (name or "").lower()

    if (
        leisure == "golf_course"
        or has_name_term(name_lower, LUXURY_NAME_TERMS)
        or (tourism in LODGING_TOURISM and has_name_term(name_lower, {"luxury", "resort"}))
    ):
        return LUXURY_HIGH_END

    if tourism in LODGING_TOURISM:
        return TOURIST_LODGING

    if amenity in NIGHTLIFE_AMENITIES or leisure in NIGHTLIFE_LEISURE:
        return NIGHTLIFE

    if amenity in FOOD_AMENITIES or shop in FOOD_SHOPS:
        return FOOD_AND_CAFE

    if (
        amenity in RELIGIOUS_AMENITIES
        or building in RELIGIOUS_BUILDINGS
        or landuse in RELIGIOUS_LANDUSE
        or bool(historic)
        or tourism in HISTORIC_TOURISM
    ):
        return RELIGIOUS_HISTORIC

    if landuse in INDUSTRIAL_LANDUSE or building in INDUSTRIAL_BUILDINGS:
        return INDUSTRIAL_LOGISTICS

    if (
        amenity in CIVIC_AMENITIES
        or building in CIVIC_BUILDINGS
        or landuse == "military"
        or has_name_term(name_lower, {"ubnd", "office", "ministry", "department", "city hall"})
    ):
        return CIVIC_INSTITUTIONAL

    if landuse == "commercial" or amenity in WALKABLE_AMENITIES or bool(shop):
        return WALKABLE_COMMERCIAL

    if amenity in LOCAL_SERVICE_AMENITIES:
        return LOCAL_SERVICES

    if natural in SCENIC_NATURAL or water in SCENIC_WATER or tourism in SCENIC_TOURISM:
        return SCENIC_WATER_FOREST

    if leisure in QUIET_LEISURE or landuse in QUIET_LANDUSE:
        return NATURE_QUIET

    if building in RESIDENTIAL_BUILDINGS or highway in RESIDENTIAL_HIGHWAYS:
        return FAMILY_RESIDENTIAL

    if highway in ROAD_HEAVY_HIGHWAYS or amenity == "parking":
        return ROAD_HEAVY

    if building == "yes":
        return LOCAL_SERVICES

    return LOCAL_SERVICES


def normalize_rows(rows):
    for row in rows:
        tags = parse_type_field(row.get("type", ""))
        category = classify_category(tags, row.get("name", ""))
        if category not in ALL_CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")
        yield {
            "name": row.get("name", ""),
            "geometry": row.get("geometry", ""),
            "category": category,
            "type": row.get("type", ""),
        }


def normalize_csv(input_csv_path, output_csv_path):
    with open(input_csv_path, newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        normalized_rows = list(normalize_rows(reader))

    with open(output_csv_path, "w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["name", "geometry", "category", "type"])
        writer.writeheader()
        writer.writerows(normalized_rows)


def main(*args):
    input_csv_path = args[0] if len(args) > 0 else "osm/area-points.csv"
    output_csv_path = args[1] if len(args) > 1 else "osm/area-points-normalized.csv"
    normalize_csv(input_csv_path, output_csv_path)


if __name__ == "__main__":
    main(*sys.argv[1:])
