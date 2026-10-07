from decimal import Decimal

from apps.loads.distance import haversine_km, route_distance_km


def test_haversine_tashkent_to_samarkand() -> None:
    """Tashkent to Samarkand great-circle distance is approx 270 km."""
    tashkent = (41.2995, 69.2401)
    samarkand = (39.6542, 66.9597)
    dist = haversine_km(tashkent[0], tashkent[1], samarkand[0], samarkand[1])
    assert 265.0 <= dist <= 275.0

    route_dist = route_distance_km([tashkent, samarkand])
    assert 265 <= route_dist <= 275


def test_identical_points() -> None:
    """Distance between identical points is zero."""
    point = (41.2995, 69.2401)
    assert haversine_km(point[0], point[1], point[0], point[1]) == 0.0
    assert route_distance_km([point, point]) == 0


def test_three_point_route_sum_of_legs() -> None:
    """Three-point route distance equals sum of individual legs."""
    tashkent = (41.2995, 69.2401)
    samarkand = (39.6542, 66.9597)
    bukhara = (39.7747, 64.4286)

    leg1 = haversine_km(tashkent[0], tashkent[1], samarkand[0], samarkand[1])
    leg2 = haversine_km(samarkand[0], samarkand[1], bukhara[0], bukhara[1])
    expected = round(leg1 + leg2)

    assert route_distance_km([tashkent, samarkand, bukhara]) == expected


def test_decimal_inputs() -> None:
    """Decimal coordinate inputs are supported."""
    tashkent = (Decimal("41.2995"), Decimal("69.2401"))
    samarkand = (Decimal("39.6542"), Decimal("66.9597"))

    dist = haversine_km(tashkent[0], tashkent[1], samarkand[0], samarkand[1])
    assert isinstance(dist, float)
    assert 265.0 <= dist <= 275.0

    route_dist = route_distance_km([tashkent, samarkand])
    assert isinstance(route_dist, int)
    assert 265 <= route_dist <= 275


def test_empty_or_single_point() -> None:
    """Routes with fewer than two points return 0."""
    point = (41.2995, 69.2401)
    assert route_distance_km([]) == 0
    assert route_distance_km([point]) == 0
    assert route_distance_km(iter([])) == 0
    assert route_distance_km(iter([point])) == 0
