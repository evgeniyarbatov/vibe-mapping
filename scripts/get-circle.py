import sys

from geopy.distance import geodesic

NUMBER_OF_POINTS = 32


def generate_circle_poly(
    lat,
    lon,
    radius_km,
    filename,
):
    points = []
    for i in range(NUMBER_OF_POINTS):
        bearing = 360 * i / NUMBER_OF_POINTS

        destination = geodesic(kilometers=float(radius_km)).destination((lat, lon), bearing)
        point_lon, point_lat = destination.longitude, destination.latitude
        points.append((point_lon, point_lat))

    with open(filename, "w") as f:
        f.write("circle\n")
        for lon_p, lat_p in points:
            f.write(f"   {lon_p:.6f}   {lat_p:.6f}\n")
        f.write(f"   {points[0][0]:.6f}   {points[0][1]:.6f}\n")
        f.write("END\n")


def main(
    start_lat,
    start_lon,
    radius_km,
    polygon_filename,
):
    generate_circle_poly(
        start_lat,
        start_lon,
        radius_km,
        polygon_filename,
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
