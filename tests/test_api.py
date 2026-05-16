from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from api.app import create_app
from services.car_routing import CarRoute, GeoPoint
from services.route_comparison import (
    RouteComparison,
    RouteOption,
    option_from_car_route,
)


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_routes_compare_validation(client) -> None:
    response = client.post("/api/routes/compare", json={})
    assert response.status_code == 400
    assert "error" in response.get_json()


@patch("api.routes.compare_routes")
@patch("api.routes.get_engine")
def test_routes_compare_success(mock_get_engine, mock_compare, client) -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    car_route = CarRoute(
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(minutes=20),
        total_distance_m=8_000,
        total_duration_seconds=1_200,
        access_distance_m=100,
        egress_distance_m=150,
        segments=[],
    )
    comparison = RouteComparison(
        origin=GeoPoint(52.23, 21.01),
        destination=GeoPoint(52.25, 21.05),
        departure_at=departure_at,
        options=[option_from_car_route(car_route, departure_at)],
    )
    mock_compare.return_value = comparison

    response = client.post(
        "/api/routes/compare",
        json={
            "origin_lat": 52.23,
            "origin_lon": 21.01,
            "destination_lat": 52.25,
            "destination_lon": 21.05,
            "departure_at": departure_at.isoformat(),
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["origin"] == {"lat": 52.23, "lon": 21.01}
    assert len(payload["options"]) == 1
    assert payload["best_option"]["mode"] == "car"
    mock_get_engine.assert_called_once()
    mock_compare.assert_called_once()
