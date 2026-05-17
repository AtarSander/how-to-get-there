from __future__ import annotations

from datetime import datetime, timedelta

from services.car_routing import GeoPoint, RoadEdge
from services.route_comparison import compare_routes
from services.traffic_profiles import (
    hourly_multipliers_from_volumes,
    traffic_profile_from_hourly_volumes,
)
from services.zdm_apr import parse_zdm_apr_feature


def test_hourly_multipliers_from_volumes_uses_hourly_apr_intensity() -> None:
    multipliers = hourly_multipliers_from_volumes({
        hour: 100.0
        for hour in range(24)
    } | {8: 220.0})

    assert multipliers[2] == 1.0
    assert 1.2 < multipliers[8] < 1.25


def test_parse_zdm_apr_feature_extracts_two_direction_hourly_profiles() -> None:
    feature = {
        "attributes": {
            "ObjectId": 10,
            "NR": 1306,
            "Ulica": "Chelmzynska",
            "Odcinek_lokalizacji": "Gwarkow - Strazacka",
            "Lat": 52.2632,
            "Long": 21.1233,
            "Nazwa_dzielnicy": "Rembertow",
            "Kordon_lub_ekran": "KZ",
            "G7_1": 267,
            "G7_2": 287,
        },
        "geometry": {"x": 21.1233, "y": 52.2632},
    }

    point, profiles = parse_zdm_apr_feature(feature, source_year=2023)

    assert point.source_object_id == 10
    assert point.point_number == 1306
    assert point.lat == 52.2632
    assert point.lon == 21.1233
    assert len(profiles) == 48
    assert next(
        profile
        for profile in profiles
        if profile.direction == 1 and profile.hour == 7
    ).volume == 267
    assert next(
        profile
        for profile in profiles
        if profile.direction == 2 and profile.hour == 7
    ).volume == 287


def test_traffic_profile_from_hourly_volumes_keeps_directional_profiles() -> None:
    profile = traffic_profile_from_hourly_volumes(
        {hour: 100.0 for hour in range(24)} | {8: 180.0},
        directional_hourly_volumes={
            1: {hour: 100.0 for hour in range(24)} | {8: 180.0},
            2: {hour: 100.0 for hour in range(24)} | {8: 120.0},
        },
    )

    assert profile is not None
    assert profile.directional_hourly_multipliers is not None
    assert profile.directional_hourly_multipliers[1][8] > (
        profile.directional_hourly_multipliers[2][8]
    )


def test_compare_routes_uses_database_traffic_profile_when_available(monkeypatch) -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    received_multiplier: list[float] = []

    def fake_load_zdm_apr_traffic_profile(_engine):
        from services.car_routing import TrafficProfile

        return TrafficProfile(hourly_multipliers={8: 1.75})

    def fake_car_route_finder(
        road_edges,
        origin,
        destination,
        departure_at,
        traffic_profile,
    ):
        received_multiplier.append(traffic_profile.multiplier_at(departure_at))
        from services.car_routing import CarRoute

        return CarRoute(
            departure_at=departure_at,
            arrival_at=departure_at + timedelta(minutes=20),
            total_distance_m=1_000,
            total_duration_seconds=1_200,
            access_distance_m=0,
            egress_distance_m=0,
            segments=[],
        )

    monkeypatch.setattr(
        "services.route_comparison.load_zdm_apr_traffic_profile",
        fake_load_zdm_apr_traffic_profile,
    )

    compare_routes(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.01,
        destination_lon=21.01,
        departure_at=departure_at,
        road_edges=[
            RoadEdge(
                edge_id="edge",
                source="A",
                target="B",
                source_point=GeoPoint(52.0, 21.0),
                target_point=GeoPoint(52.01, 21.01),
                length_m=1_000,
                max_speed_kmh=50,
            )
        ],
        car_route_finder=fake_car_route_finder,
        public_transport_finder=lambda *args, **kwargs: [],
        park_and_ride_finder=lambda **kwargs: [],
    )

    assert received_multiplier == [1.75]
