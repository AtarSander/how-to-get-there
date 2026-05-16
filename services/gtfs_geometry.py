from __future__ import annotations

from typing import TYPE_CHECKING, Any

from services.car_routing import GeoPoint, haversine_distance_m

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any


def slice_polyline_by_shape_distance(
    points: tuple[tuple[float, float], ...],
    dist_from: float,
    dist_to: float,
) -> tuple[tuple[float, float], ...]:
    if len(points) < 2 or dist_from >= dist_to:
        return points[:1] if points else ()

    cumulative_distances = [0.0]
    for index in range(1, len(points)):
        previous = GeoPoint(points[index - 1][0], points[index - 1][1])
        current = GeoPoint(points[index][0], points[index][1])
        cumulative_distances.append(
            cumulative_distances[-1] + haversine_distance_m(previous, current)
        )

    start_index = 0
    for index, distance in enumerate(cumulative_distances):
        if distance >= dist_from:
            start_index = max(0, index - 1)
            break

    end_index = len(points) - 1
    for index in range(len(cumulative_distances) - 1, -1, -1):
        if cumulative_distances[index] <= dist_to:
            end_index = index
            break

    if start_index > end_index:
        return (points[start_index],)

    return points[start_index : end_index + 1]


def resolve_ride_path_positions(
    engine: Engine | None,
    trip_id: str,
    from_stop_sequence: int,
    to_stop_sequence: int,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    from_shape_dist_traveled: float | None,
    to_shape_dist_traveled: float | None,
) -> tuple[tuple[float, float], ...] | None:
    if engine is None:
        return None

    from database.queries import (
        fetch_shape_points,
        fetch_stop_chain_positions,
        fetch_trip_shape_id,
    )

    shape_id = fetch_trip_shape_id(engine, trip_id)
    if (
        shape_id
        and from_shape_dist_traveled is not None
        and to_shape_dist_traveled is not None
        and from_shape_dist_traveled < to_shape_dist_traveled
    ):
        shape_points = fetch_shape_points(engine, shape_id)
        if len(shape_points) >= 2:
            sliced = slice_polyline_by_shape_distance(
                shape_points,
                from_shape_dist_traveled,
                to_shape_dist_traveled,
            )
            if len(sliced) >= 2:
                return _ensure_endpoints(
                    sliced,
                    from_lat,
                    from_lon,
                    to_lat,
                    to_lon,
                )

    stop_chain = fetch_stop_chain_positions(
        engine,
        trip_id=trip_id,
        from_stop_sequence=from_stop_sequence,
        to_stop_sequence=to_stop_sequence,
    )
    if len(stop_chain) >= 2:
        return stop_chain

    return ((from_lat, from_lon), (to_lat, to_lon))


def _ensure_endpoints(
    positions: tuple[tuple[float, float], ...],
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
) -> tuple[tuple[float, float], ...]:
    result: list[tuple[float, float]] = list(positions)
    start = (from_lat, from_lon)
    end = (to_lat, to_lon)

    if result[0] != start:
        result.insert(0, start)
    if result[-1] != end:
        result.append(end)

    return tuple(result)
