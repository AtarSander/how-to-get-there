from __future__ import annotations

from datetime import datetime, timedelta

from api.serialization import serialize_route_comparison
from services.car_routing import CarRoute, GeoPoint
from services.route_comparison import RouteComparison, option_from_car_route


def test_serialize_route_comparison_includes_best_option() -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    car_route = CarRoute(
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(minutes=15),
        total_distance_m=5_000,
        total_duration_seconds=900,
        access_distance_m=0,
        egress_distance_m=0,
        segments=[],
    )
    comparison = RouteComparison(
        origin=GeoPoint(52.0, 21.0),
        destination=GeoPoint(52.1, 21.1),
        departure_at=departure_at,
        options=[option_from_car_route(car_route, departure_at)],
    )

    payload = serialize_route_comparison(comparison)

    assert payload["best_option"]["mode"] == "car"
    assert payload["options"][0]["details"]["car"]["total_minutes"] == 15
