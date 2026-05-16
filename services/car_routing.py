from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from heapq import heappop, heappush
from math import asin, ceil, cos, radians, sin, sqrt

from config.settings import settings


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class RoadEdge:
    edge_id: str
    source: str
    target: str
    source_point: GeoPoint
    target_point: GeoPoint
    length_m: float
    max_speed_kmh: float | None = None
    road_name: str | None = None
    bidirectional: bool = True


@dataclass(frozen=True)
class TrafficProfile:
    hourly_multipliers: dict[int, float]
    default_multiplier: float = 1.0

    def multiplier_at(self, when: datetime) -> float:
        return self.hourly_multipliers.get(when.hour, self.default_multiplier)


@dataclass(frozen=True)
class CarRouteSegment:
    edge_id: str
    from_node: str
    to_node: str
    road_name: str | None
    distance_m: float
    duration_seconds: int
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float


@dataclass(frozen=True)
class CarRoute:
    departure_at: datetime
    arrival_at: datetime
    total_distance_m: float
    total_duration_seconds: int
    access_distance_m: float
    egress_distance_m: float
    segments: list[CarRouteSegment]

    @property
    def total_minutes(self) -> int:
        return ceil(self.total_duration_seconds / 60)


@dataclass(frozen=True)
class RouteGeometry:
    route: CarRoute
    path_positions: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class CandidateMove:
    edge: RoadEdge
    from_node: str
    to_node: str
    from_point: GeoPoint
    to_point: GeoPoint


def haversine_distance_m(first: GeoPoint, second: GeoPoint) -> float:
    lat1 = radians(first.lat)
    lat2 = radians(second.lat)
    delta_lat = radians(second.lat - first.lat)
    delta_lon = radians(second.lon - first.lon)

    value = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )

    return 2 * settings.earth_radius_m * asin(sqrt(value))


def walking_speed_mps() -> float:
    return settings.public_transport_walking_speed_mps


def edge_base_duration_seconds(
    edge: RoadEdge,
    speed_mps: float | None = None,
) -> float:
    if speed_mps is not None:
        return edge.length_m / speed_mps

    speed_kmh = edge.max_speed_kmh or settings.car_default_speed_kmh
    speed_mps = speed_kmh * 1000 / 3600
    return edge.length_m / speed_mps


def edge_duration_seconds(
    edge: RoadEdge,
    departure_at: datetime,
    traffic_profile: TrafficProfile | None = None,
    speed_mps: float | None = None,
) -> int:
    if speed_mps is not None:
        return ceil(edge_base_duration_seconds(edge, speed_mps=speed_mps))

    multiplier = (
        traffic_profile.multiplier_at(departure_at)
        if traffic_profile is not None
        else 1.0
    )

    return ceil(edge_base_duration_seconds(edge) * multiplier)


def estimate_direct_car_route(
    origin: GeoPoint,
    destination: GeoPoint,
    departure_at: datetime,
    traffic_profile: TrafficProfile | None = None,
    speed_mps: float | None = None,
) -> CarRoute:
    distance_m = haversine_distance_m(origin, destination)
    effective_speed_mps = (
        speed_mps
        if speed_mps is not None
        else settings.car_default_speed_kmh * 1000 / 3600
    )
    duration_seconds = ceil(distance_m / effective_speed_mps)

    if traffic_profile is not None and speed_mps is None:
        duration_seconds = ceil(
            duration_seconds * traffic_profile.multiplier_at(departure_at)
        )

    return CarRoute(
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(seconds=duration_seconds),
        total_distance_m=distance_m,
        total_duration_seconds=duration_seconds,
        access_distance_m=0,
        egress_distance_m=0,
        segments=[],
    )


def build_adjacency(edges: list[RoadEdge]) -> dict[str, list[CandidateMove]]:
    adjacency: dict[str, list[CandidateMove]] = {}

    for edge in edges:
        adjacency.setdefault(edge.source, []).append(
            CandidateMove(
                edge=edge,
                from_node=edge.source,
                to_node=edge.target,
                from_point=edge.source_point,
                to_point=edge.target_point,
            )
        )

        if edge.bidirectional:
            adjacency.setdefault(edge.target, []).append(
                CandidateMove(
                    edge=edge,
                    from_node=edge.target,
                    to_node=edge.source,
                    from_point=edge.target_point,
                    to_point=edge.source_point,
                )
            )

    return adjacency


def collect_nodes(edges: list[RoadEdge]) -> dict[str, GeoPoint]:
    nodes: dict[str, GeoPoint] = {}

    for edge in edges:
        nodes.setdefault(edge.source, edge.source_point)
        nodes.setdefault(edge.target, edge.target_point)

    return nodes


def find_nearest_node(point: GeoPoint, nodes: dict[str, GeoPoint]) -> tuple[str, float]:
    if not nodes:
        raise ValueError("Cannot find nearest node in an empty road graph.")

    node_id, node_point = min(
        nodes.items(),
        key=lambda item: haversine_distance_m(point, item[1]),
    )

    return node_id, haversine_distance_m(point, node_point)


def reconstruct_path(
    destination_node: str,
    predecessors: dict[str, tuple[str, CandidateMove]],
) -> list[CandidateMove]:
    path: list[CandidateMove] = []
    current_node = destination_node

    while current_node in predecessors:
        previous_node, move = predecessors[current_node]
        path.append(move)
        current_node = previous_node

    path.reverse()
    return path


def find_car_route(
    edges: list[RoadEdge],
    origin: GeoPoint,
    destination: GeoPoint,
    departure_at: datetime,
    traffic_profile: TrafficProfile | None = None,
    speed_mps: float | None = None,
) -> CarRoute | None:
    if not edges:
        return None

    nodes = collect_nodes(edges)
    origin_node, access_distance_m = find_nearest_node(origin, nodes)
    destination_node, egress_distance_m = find_nearest_node(destination, nodes)

    if origin_node == destination_node:
        direct_distance_m = haversine_distance_m(origin, destination)
        if speed_mps is not None:
            duration_seconds = ceil(direct_distance_m / speed_mps)
        else:
            duration_seconds = ceil(
                direct_distance_m / (settings.car_default_speed_kmh * 1000 / 3600)
            )

        return CarRoute(
            departure_at=departure_at,
            arrival_at=departure_at + timedelta(seconds=duration_seconds),
            total_distance_m=direct_distance_m,
            total_duration_seconds=duration_seconds,
            access_distance_m=access_distance_m,
            egress_distance_m=egress_distance_m,
            segments=[],
        )

    adjacency = build_adjacency(edges)
    best_duration_by_node: dict[str, int] = {origin_node: 0}
    predecessors: dict[str, tuple[str, CandidateMove]] = {}
    queue: list[tuple[int, str]] = [(0, origin_node)]

    while queue:
        current_duration_seconds, current_node = heappop(queue)

        if current_duration_seconds > best_duration_by_node[current_node]:
            continue

        if current_node == destination_node:
            break

        for move in adjacency.get(current_node, []):
            edge_departure_at = departure_at + timedelta(
                seconds=current_duration_seconds
            )
            move_duration_seconds = edge_duration_seconds(
                move.edge,
                edge_departure_at,
                traffic_profile,
                speed_mps=speed_mps,
            )
            candidate_duration_seconds = (
                current_duration_seconds + move_duration_seconds
            )

            if candidate_duration_seconds >= best_duration_by_node.get(
                move.to_node,
                10**18,
            ):
                continue

            best_duration_by_node[move.to_node] = candidate_duration_seconds
            predecessors[move.to_node] = (current_node, move)
            heappush(queue, (candidate_duration_seconds, move.to_node))

    if destination_node not in best_duration_by_node:
        return None

    path = reconstruct_path(destination_node, predecessors)
    segments: list[CarRouteSegment] = []
    elapsed_seconds = 0

    for move in path:
        duration_seconds = edge_duration_seconds(
            move.edge,
            departure_at + timedelta(seconds=elapsed_seconds),
            traffic_profile,
            speed_mps=speed_mps,
        )
        elapsed_seconds += duration_seconds
        segments.append(
            CarRouteSegment(
                edge_id=move.edge.edge_id,
                from_node=move.from_node,
                to_node=move.to_node,
                road_name=move.edge.road_name,
                distance_m=move.edge.length_m,
                duration_seconds=duration_seconds,
                from_lat=move.from_point.lat,
                from_lon=move.from_point.lon,
                to_lat=move.to_point.lat,
                to_lon=move.to_point.lon,
            )
        )

    network_distance_m = sum(segment.distance_m for segment in segments)
    total_distance_m = access_distance_m + network_distance_m + egress_distance_m
    total_duration_seconds = best_duration_by_node[destination_node]
    if speed_mps is not None:
        total_duration_seconds += ceil(access_distance_m / speed_mps)
        total_duration_seconds += ceil(egress_distance_m / speed_mps)

    return CarRoute(
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(seconds=total_duration_seconds),
        total_distance_m=total_distance_m,
        total_duration_seconds=total_duration_seconds,
        access_distance_m=access_distance_m,
        egress_distance_m=egress_distance_m,
        segments=segments,
    )


def path_positions_from_route(
    origin: GeoPoint,
    destination: GeoPoint,
    route: CarRoute,
) -> tuple[tuple[float, float], ...]:
    if not route.segments:
        return (
            (origin.lat, origin.lon),
            (destination.lat, destination.lon),
        )

    positions: list[tuple[float, float]] = [(origin.lat, origin.lon)]

    for segment in route.segments:
        from_point = (segment.from_lat, segment.from_lon)
        to_point = (segment.to_lat, segment.to_lon)
        if positions[-1] != from_point:
            positions.append(from_point)
        if positions[-1] != to_point:
            positions.append(to_point)

    if positions[-1] != (destination.lat, destination.lon):
        positions.append((destination.lat, destination.lon))

    return tuple(positions)


def resolve_route(
    origin: GeoPoint,
    destination: GeoPoint,
    departure_at: datetime,
    road_edges: list[RoadEdge] | None,
    *,
    speed_mps: float | None = None,
    traffic_profile: TrafficProfile | None = None,
    allow_direct_fallback: bool = True,
) -> RouteGeometry | None:
    if road_edges:
        routed = find_car_route(
            edges=road_edges,
            origin=origin,
            destination=destination,
            departure_at=departure_at,
            traffic_profile=traffic_profile,
            speed_mps=speed_mps,
        )
        if routed is not None:
            return RouteGeometry(
                route=routed,
                path_positions=path_positions_from_route(
                    origin, destination, routed
                ),
            )
        if not allow_direct_fallback:
            return None
    elif not allow_direct_fallback:
        return None

    direct = estimate_direct_car_route(
        origin=origin,
        destination=destination,
        departure_at=departure_at,
        traffic_profile=traffic_profile,
        speed_mps=speed_mps,
    )
    return RouteGeometry(
        route=direct,
        path_positions=path_positions_from_route(origin, destination, direct),
    )
