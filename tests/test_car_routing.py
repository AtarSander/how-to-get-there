from __future__ import annotations

from datetime import datetime

from config.settings import settings
from services.car_routing import (
    GeoPoint,
    RoadEdge,
    TrafficProfile,
    edge_duration_seconds,
    find_car_route,
    haversine_distance_m,
    path_positions_from_route,
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


def test_edge_duration_caps_urban_road_speed_by_highway_type() -> None:
    edge = RoadEdge(
        edge_id="urban-secondary",
        source="A",
        target="B",
        source_point=GeoPoint(52.0, 21.0),
        target_point=GeoPoint(52.0, 21.01),
        length_m=1_000,
        max_speed_kmh=50,
        highway="secondary",
    )

    assert edge_duration_seconds(edge, datetime(2026, 5, 13, 10, 0, 0)) == 80


def test_edge_duration_parses_list_like_highway_values() -> None:
    edge = RoadEdge(
        edge_id="mixed-urban",
        source="A",
        target="B",
        source_point=GeoPoint(52.0, 21.0),
        target_point=GeoPoint(52.0, 21.01),
        length_m=1_000,
        max_speed_kmh=50,
        highway="['secondary', 'residential']",
    )

    assert edge_duration_seconds(edge, datetime(2026, 5, 13, 10, 0, 0)) == 129


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
    assert route.total_duration_seconds == 108 + settings.car_right_turn_penalty_seconds


def test_find_car_route_adds_car_access_and_egress_time() -> None:
    route = find_car_route(
        edges=[
            RoadEdge(
                edge_id="a-b",
                source="A",
                target="B",
                source_point=GeoPoint(52.0, 21.0),
                target_point=GeoPoint(52.0, 21.01),
                length_m=1_000,
                max_speed_kmh=60,
                bidirectional=False,
            )
        ],
        origin=GeoPoint(52.0, 20.999),
        destination=GeoPoint(52.0, 21.011),
        departure_at=datetime(2026, 5, 13, 10, 0, 0),
    )

    assert route is not None
    assert route.access_distance_m > 60
    assert route.egress_distance_m > 60
    assert route.total_duration_seconds > route.segments[0].duration_seconds


def test_find_car_route_penalizes_signalized_intersection_turns() -> None:
    departure_at = datetime(2026, 5, 13, 10, 0, 0)
    common = {
        "max_speed_kmh": 60,
        "bidirectional": False,
    }
    edges = [
        RoadEdge(
            edge_id="entry",
            source="A",
            target="B",
            source_point=GeoPoint(52.0, 21.0),
            target_point=GeoPoint(52.001, 21.0),
            length_m=600,
            target_highway="traffic_signals",
            target_street_count=4,
            **common,
        ),
        RoadEdge(
            edge_id="left",
            source="B",
            target="C",
            source_point=GeoPoint(52.001, 21.0),
            target_point=GeoPoint(52.001, 20.999),
            length_m=600,
            source_highway="traffic_signals",
            source_street_count=4,
            **common,
        ),
    ]

    route = find_car_route(
        edges=edges,
        origin=GeoPoint(52.0, 21.0),
        destination=GeoPoint(52.001, 20.999),
        departure_at=departure_at,
    )

    assert route is not None
    base_duration = sum(edge_duration_seconds(edge, departure_at) for edge in edges)
    assert route.total_duration_seconds == (
        base_duration
        + settings.car_traffic_signal_penalty_seconds
        + settings.car_left_turn_penalty_seconds
    )
    assert route.segments[1].duration_seconds > edge_duration_seconds(
        edges[1],
        departure_at,
    )


def test_path_positions_from_route_uses_full_edge_geometry() -> None:
    origin = GeoPoint(52.0, 21.0)
    destination = GeoPoint(52.0, 21.02)
    route = find_car_route(
        edges=[
            RoadEdge(
                edge_id="curved",
                source="A",
                target="B",
                source_point=origin,
                target_point=destination,
                length_m=1_500,
                max_speed_kmh=50,
                bidirectional=False,
                geometry_positions=(
                    (52.0, 21.0),
                    (52.001, 21.01),
                    (52.0, 21.02),
                ),
            )
        ],
        origin=origin,
        destination=destination,
        departure_at=datetime(2026, 5, 13, 10, 0, 0),
    )

    assert route is not None
    assert route.segments[0].path_positions == (
        (52.0, 21.0),
        (52.001, 21.01),
        (52.0, 21.02),
    )
    assert path_positions_from_route(origin, destination, route) == (
        (52.0, 21.0),
        (52.001, 21.01),
        (52.0, 21.02),
    )


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
