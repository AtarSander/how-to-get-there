from __future__ import annotations

from datetime import datetime

from services.car_routing import (
    GeoPoint,
    RoadEdge,
    find_car_route,
    path_positions_from_route,
    resolve_route,
    walking_speed_mps,
)


def make_walk_edge(
    edge_id: str,
    source: str,
    target: str,
    source_point: GeoPoint,
    target_point: GeoPoint,
    length_m: float,
) -> RoadEdge:
    return RoadEdge(
        edge_id=edge_id,
        source=source,
        target=target,
        source_point=source_point,
        target_point=target_point,
        length_m=length_m,
        bidirectional=True,
    )


def test_find_car_route_uses_walking_speed() -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    edges = [
        make_walk_edge(
            "a-b",
            "a",
            "b",
            GeoPoint(52.0, 21.0),
            GeoPoint(52.001, 21.0),
            140.0,
        ),
        make_walk_edge(
            "b-c",
            "b",
            "c",
            GeoPoint(52.001, 21.0),
            GeoPoint(52.002, 21.0),
            140.0,
        ),
    ]

    route = find_car_route(
        edges=edges,
        origin=GeoPoint(52.0, 21.0),
        destination=GeoPoint(52.002, 21.0),
        departure_at=departure_at,
        speed_mps=walking_speed_mps(),
    )

    assert route is not None
    assert route.total_duration_seconds == 200
    assert len(route.segments) == 2


def test_resolve_route_falls_back_to_direct_line_without_edges() -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    origin = GeoPoint(52.0, 21.0)
    destination = GeoPoint(52.01, 21.01)

    result = resolve_route(
        origin=origin,
        destination=destination,
        departure_at=departure_at,
        road_edges=None,
        speed_mps=walking_speed_mps(),
        allow_direct_fallback=True,
    )

    assert result is not None
    assert result.route.total_distance_m > 0
    assert result.path_positions[0] == (origin.lat, origin.lon)
    assert result.path_positions[-1] == (destination.lat, destination.lon)


def test_path_positions_from_route_follows_segments() -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    route = find_car_route(
        edges=[
            make_walk_edge(
                "a-b",
                "a",
                "b",
                GeoPoint(52.0, 21.0),
                GeoPoint(52.001, 21.0),
                140.0,
            )
        ],
        origin=GeoPoint(52.0, 21.0),
        destination=GeoPoint(52.001, 21.0),
        departure_at=departure_at,
        speed_mps=walking_speed_mps(),
    )
    assert route is not None

    positions = path_positions_from_route(
        GeoPoint(52.0, 21.0),
        GeoPoint(52.001, 21.0),
        route,
    )

    assert len(positions) >= 2
    assert walking_speed_mps() == 1.4
