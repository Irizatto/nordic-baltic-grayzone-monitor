"""Geographic helpers for later risk-signal calculations."""
from math import asin, atan2, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two latitude/longitude points."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * asin(sqrt(a))


def point_to_linestring_distance_km(lat: float, lon: float, coordinates: list[list[float]]) -> float:
    """Return an approximate minimum distance from a point to GeoJSON [lon, lat] line coordinates."""
    if len(coordinates) < 2:
        raise ValueError("A LineString requires at least two coordinates.")
    reference_lat = radians(lat)
    px, py = radians(lon) * cos(reference_lat), radians(lat)
    best = float("inf")
    for start, end in zip(coordinates, coordinates[1:]):
        ax, ay = radians(start[0]) * cos(reference_lat), radians(start[1])
        bx, by = radians(end[0]) * cos(reference_lat), radians(end[1])
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        fraction = 0 if length_sq == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        nearest_lon = (ax + fraction * dx) / cos(reference_lat)
        nearest_lat = ay + fraction * dy
        best = min(best, haversine_km(lat, lon, nearest_lat * 180 / 3.141592653589793, nearest_lon * 180 / 3.141592653589793))
    return best


def point_in_bbox(lat: float, lon: float, lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> bool:
    """Return whether a point lies inside an inclusive latitude/longitude bounding box."""
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
