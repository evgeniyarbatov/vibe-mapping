import sys

from geopy.distance import geodesic

NUMBER_OF_POINTS = 32


def generate_circle_poly(
    lat: float,
    lon: float,
    radius_km: float,
    filename: str,
) -> None:
    points = []
    for i in range(NUMBER_OF_POINTS):
        bearing = 360 * i / NUMBER_OF_POINTS

        destination = geodesic(kilometers=radius_km).destination((lat, lon), bearing)
        point_lon, point_lat = destination.longitude, destination.latitude
        points.append((point_lon, point_lat))

    with open(filename, "w") as f:
        f.write("circle\n")
        for lon_p, lat_p in points:
            f.write(f"   {lon_p:.6f}   {lat_p:.6f}\n")
        f.write(f"   {points[0][0]:.6f}   {points[0][1]:.6f}\n")
        f.write("END\n")


def main(
    start_lat: str,
    start_lon: str,
    radius_km: str,
    polygon_filename: str,
) -> None:
    generate_circle_poly(
        float(start_lat),
        float(start_lon),
        float(radius_km),
        polygon_filename,
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
