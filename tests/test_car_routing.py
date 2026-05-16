from __future__ import annotations

from datetime import datetime

from services.car_routing import (
    GeoPoint,
    RoadEdge,
    TrafficProfile,
    edge_duration_seconds,
    find_car_route,
    haversine_distance_m,
)


def test_haversine_distance_is_reasonable_for_warsaw_points() -> None:
    palace_of_culture = GeoPoint(52.2318, 21.0061)
    metro_centrum = GeoPoint(52.2298, 21.0118)

    distance_m = haversine_distance_m(palace_of_culture, metro_centrum)

    assert 400 <= distance_m <= 500


def test_edge_duration_uses_hourly_traffic_multiplier() -> None:
    edge = RoadEdge(
        edge_id="edge-1",
        source="A",
        target="B",
        source_point=GeoPoint(52.0, 21.0),
        target_point=GeoPoint(52.0, 21.01),
        length_m=1_000,
        max_speed_kmh=60,
    )
    profile = TrafficProfile(hourly_multipliers={8: 1.5})

    duration_seconds = edge_duration_seconds(
        edge,
        datetime(2026, 5, 13, 8, 0, 0),
        profile,
    )

    assert duration_seconds == 90


def test_edge_duration_uses_directional_traffic_multiplier() -> None:
    center = GeoPoint(52.0, 21.0)
    toward_center = RoadEdge(
        edge_id="toward",
        source="A",
        target="B",
        source_point=GeoPoint(52.0, 21.02),
        target_point=GeoPoint(52.0, 21.01),
        length_m=1_000,
        max_speed_kmh=60,
    )
    away_from_center = RoadEdge(
        edge_id="away",
        source="B",
        target="A",
        source_point=GeoPoint(52.0, 21.01),
        target_point=GeoPoint(52.0, 21.02),
        length_m=1_000,
        max_speed_kmh=60,
    )
    profile = TrafficProfile(
        hourly_multipliers={8: 1.1},
        directional_hourly_multipliers={
            1: {8: 2.0},
            2: {8: 1.25},
        },
        center=center,
    )

    assert edge_duration_seconds(
        toward_center,
        datetime(2026, 5, 13, 8, 0, 0),
        profile,
    ) == 120
    assert edge_duration_seconds(
        away_from_center,
        datetime(2026, 5, 13, 8, 0, 0),
        profile,
    ) == 75


def test_find_car_route_chooses_fastest_path_not_shortest_path() -> None:
    edges = [
        RoadEdge(
            edge_id="slow-short",
            source="A",
            target="C",
            source_point=GeoPoint(52.0, 21.0),
            target_point=GeoPoint(52.0, 21.02),
            length_m=1_000,
            max_speed_kmh=20,
            road_name="short local road",
            bidirectional=False,
        ),
        RoadEdge(
            edge_id="fast-1",
            source="A",
            target="B",
            source_point=GeoPoint(52.0, 21.0),
            target_point=GeoPoint(52.01, 21.01),
            length_m=900,
            max_speed_kmh=60,
            road_name="arterial road",
            bidirectional=False,
        ),
        RoadEdge(
            edge_id="fast-2",
            source="B",
            target="C",
            source_point=GeoPoint(52.01, 21.01),
            target_point=GeoPoint(52.0, 21.02),
            length_m=900,
            max_speed_kmh=60,
            road_name="arterial road",
            bidirectional=False,
        ),
    ]

    route = find_car_route(
        edges=edges,
        origin=GeoPoint(52.0, 21.0),
        destination=GeoPoint(52.0, 21.02),
        departure_at=datetime(2026, 5, 13, 10, 0, 0),
    )

    assert route is not None
    assert [segment.edge_id for segment in route.segments] == ["fast-1", "fast-2"]
    assert route.total_duration_seconds == 108


def test_find_car_route_respects_one_way_edges() -> None:
    edges = [
        RoadEdge(
            edge_id="one-way",
            source="A",
            target="B",
            source_point=GeoPoint(52.0, 21.0),
            target_point=GeoPoint(52.0, 21.01),
            length_m=1_000,
            max_speed_kmh=50,
            bidirectional=False,
        )
    ]

    route = find_car_route(
        edges=edges,
        origin=GeoPoint(52.0, 21.01),
        destination=GeoPoint(52.0, 21.0),
        departure_at=datetime(2026, 5, 13, 10, 0, 0),
    )

    assert route is None
