import math
from collections.abc import Iterable, Sequence
from decimal import Decimal

EARTH_RADIUS_KM: float = 6371.0088


def haversine_km(
    lat1: float | Decimal,
    lng1: float | Decimal,
    lat2: float | Decimal,
    lng2: float | Decimal,
) -> float:
    """Calculate the great-circle distance between two points on Earth in kilometers."""
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lng2) - float(lng1))

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


def route_distance_km(points: Iterable[Sequence[float | Decimal]]) -> int:
    """Calculate total route distance across consecutive points in kilometers."""
    it = iter(points)
    try:
        prev = next(it)
    except StopIteration:
        return 0

    total_km = 0.0
    count = 1
    for curr in it:
        total_km += haversine_km(prev[0], prev[1], curr[0], curr[1])
        prev = curr
        count += 1

    if count < 2:
        return 0

    return round(total_km)
