from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from heapq import heappop, heappush
from itertools import count
from math import asin, atan2, ceil, cos, degrees, radians, sin, sqrt

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
    highway: str | None = None
    source_street_count: int | None = None
    target_street_count: int | None = None
    source_highway: str | None = None
    target_highway: str | None = None
    geometry_positions: tuple[tuple[float, float], ...] | None = None


@dataclass(frozen=True)
class TrafficProfile:
    hourly_multipliers: dict[int, float]
    default_multiplier: float = 1.0
    directional_hourly_multipliers: dict[int, dict[int, float]] | None = None
    center: GeoPoint | None = None

    def multiplier_at(self, when: datetime, edge: RoadEdge | None = None) -> float:
        if (
            edge is not None
            and self.directional_hourly_multipliers is not None
            and self.center is not None
        ):
            direction = edge_direction_toward_center(edge, self.center)
            directional_multipliers = self.directional_hourly_multipliers.get(
                direction,
                {},
            )
            return directional_multipliers.get(when.hour, self.default_multiplier)

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
    path_positions: tuple[tuple[float, float], ...] | None = None


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


SearchStateKey = tuple[str, str | None]


URBAN_HIGHWAY_SPEED_CAPS_KMH: dict[str, float] = {
    "motorway": 80.0,
    "motorway_link": 45.0,
    "trunk": 55.0,
    "trunk_link": 38.0,
    "primary": 50.0,
    "primary_link": 35.0,
    "secondary": 45.0,
    "secondary_link": 32.0,
    "tertiary": 38.0,
    "tertiary_link": 28.0,
    "unclassified": 30.0,
    "residential": 28.0,
    "living_street": 12.0,
    "service": 22.0,
}


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


def bearing_degrees(first: GeoPoint, second: GeoPoint) -> float:
    lat1 = radians(first.lat)
    lat2 = radians(second.lat)
    delta_lon = radians(second.lon - first.lon)

    x = sin(delta_lon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(delta_lon)
    return (degrees(atan2(x, y)) + 360) % 360


def edge_direction_toward_center(edge: RoadEdge, center: GeoPoint) -> int:
    source_distance = haversine_distance_m(edge.source_point, center)
    target_distance = haversine_distance_m(edge.target_point, center)
    return 1 if target_distance <= source_distance else 2


def walking_speed_mps() -> float:
    return settings.public_transport_walking_speed_mps


def car_access_egress_speed_mps() -> float:
    return settings.car_access_egress_speed_kmh * 1000 / 3600


def estimate_access_egress_seconds(
    distance_m: float,
    speed_mps: float | None = None,
) -> int:
    if distance_m <= 0:
        return 0

    effective_speed_mps = speed_mps or car_access_egress_speed_mps()
    return ceil(distance_m / effective_speed_mps)


def edge_highway_values(edge: RoadEdge) -> tuple[str, ...]:
    if not edge.highway:
        return ()

    normalized = (
        edge.highway.replace("[", "")
        .replace("]", "")
        .replace("'", "")
        .replace('"', "")
        .replace(",", ";")
    )
    return tuple(
        value.strip()
        for value in normalized.split(";")
        if value.strip()
    )


def urban_speed_cap_kmh(edge: RoadEdge) -> float | None:
    caps = [
        URBAN_HIGHWAY_SPEED_CAPS_KMH[value]
        for value in edge_highway_values(edge)
        if value in URBAN_HIGHWAY_SPEED_CAPS_KMH
    ]
    if not caps:
        return None

    return min(caps)


def effective_car_speed_kmh(edge: RoadEdge) -> float:
    posted_speed_kmh = edge.max_speed_kmh or settings.car_default_speed_kmh
    speed_cap_kmh = urban_speed_cap_kmh(edge)
    if speed_cap_kmh is None:
        return posted_speed_kmh

    return min(posted_speed_kmh, speed_cap_kmh)


def edge_base_duration_seconds(
    edge: RoadEdge,
    speed_mps: float | None = None,
) -> float:
    if speed_mps is not None:
        return edge.length_m / speed_mps

    speed_kmh = effective_car_speed_kmh(edge)
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
        traffic_profile.multiplier_at(departure_at, edge=edge)
        if traffic_profile is not None
        else 1.0
    )

    return ceil(edge_base_duration_seconds(edge) * multiplier)


def move_state_id(move: CandidateMove) -> str:
    return f"{move.edge.edge_id}:{move.from_node}:{move.to_node}"


def move_geometry_positions(
    move: CandidateMove,
) -> tuple[tuple[float, float], ...]:
    positions = move.edge.geometry_positions
    if positions:
        if move.from_node == move.edge.source:
            return positions
        return tuple(reversed(positions))

    return (
        (move.from_point.lat, move.from_point.lon),
        (move.to_point.lat, move.to_point.lon),
    )


def node_highway_from_move(move: CandidateMove) -> str | None:
    if move.from_node == move.edge.source:
        return move.edge.source_highway
    return move.edge.target_highway


def node_street_count_from_move(move: CandidateMove) -> int | None:
    if move.from_node == move.edge.source:
        return move.edge.source_street_count
    return move.edge.target_street_count


def intersection_penalty_seconds(move: CandidateMove) -> int:
    if node_highway_from_move(move) == "traffic_signals":
        return settings.car_traffic_signal_penalty_seconds

    street_count = node_street_count_from_move(move)
    if street_count is not None and street_count >= 3:
        return settings.car_intersection_penalty_seconds

    return 0


def turn_penalty_seconds(
    previous_move: CandidateMove | None,
    next_move: CandidateMove,
) -> int:
    if previous_move is None:
        return 0

    previous_bearing = bearing_degrees(previous_move.from_point, previous_move.to_point)
    next_bearing = bearing_degrees(next_move.from_point, next_move.to_point)
    angle_delta = (next_bearing - previous_bearing + 540) % 360 - 180
    abs_angle_delta = abs(angle_delta)

    if abs_angle_delta < settings.car_minor_turn_angle_degrees:
        return 0
    if abs_angle_delta >= settings.car_u_turn_angle_degrees:
        return settings.car_u_turn_penalty_seconds
    if angle_delta > 0:
        return settings.car_right_turn_penalty_seconds

    return settings.car_left_turn_penalty_seconds


def transition_penalty_seconds(
    previous_move: CandidateMove | None,
    next_move: CandidateMove,
    speed_mps: float | None = None,
) -> int:
    if speed_mps is not None or previous_move is None:
        return 0

    turn_penalty = turn_penalty_seconds(
        previous_move,
        next_move,
    )
    if node_highway_from_move(next_move) == "traffic_signals":
        return settings.car_traffic_signal_penalty_seconds + turn_penalty

    intersection_penalty = (
        intersection_penalty_seconds(next_move) if turn_penalty > 0 else 0
    )

    return intersection_penalty + turn_penalty


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
    destination_state: SearchStateKey,
    predecessors: dict[SearchStateKey, tuple[SearchStateKey, CandidateMove]],
) -> list[CandidateMove]:
    path: list[CandidateMove] = []
    current_state = destination_state

    while current_state in predecessors:
        previous_state, move = predecessors[current_state]
        path.append(move)
        current_state = previous_state

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
    access_duration_seconds = estimate_access_egress_seconds(
        access_distance_m,
        speed_mps=speed_mps,
    )
    egress_duration_seconds = estimate_access_egress_seconds(
        egress_distance_m,
        speed_mps=speed_mps,
    )

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
    initial_state: SearchStateKey = (origin_node, None)
    best_duration_by_state: dict[SearchStateKey, int] = {
        initial_state: access_duration_seconds
    }
    predecessors: dict[SearchStateKey, tuple[SearchStateKey, CandidateMove]] = {}
    queue_counter = count()
    queue: list[tuple[int, int, SearchStateKey]] = [
        (access_duration_seconds, next(queue_counter), initial_state)
    ]
    destination_state: SearchStateKey | None = None

    while queue:
        current_duration_seconds, _index, current_state = heappop(queue)
        current_node, _incoming_move_id = current_state

        if current_duration_seconds > best_duration_by_state[current_state]:
            continue

        if current_node == destination_node:
            destination_state = current_state
            break

        previous_move = (
            predecessors[current_state][1] if current_state in predecessors else None
        )
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
            penalty_seconds = transition_penalty_seconds(
                previous_move,
                move,
                speed_mps=speed_mps,
            )
            candidate_duration_seconds = (
                current_duration_seconds + move_duration_seconds + penalty_seconds
            )
            next_state: SearchStateKey = (
                move.to_node,
                move_state_id(move),
            )

            if candidate_duration_seconds >= best_duration_by_state.get(
                next_state,
                10**18,
            ):
                continue

            best_duration_by_state[next_state] = candidate_duration_seconds
            predecessors[next_state] = (current_state, move)
            heappush(
                queue,
                (
                    candidate_duration_seconds,
                    next(queue_counter),
                    next_state,
                ),
            )

    if destination_state is None:
        return None

    path = reconstruct_path(destination_state, predecessors)
    segments: list[CarRouteSegment] = []
    elapsed_seconds = access_duration_seconds
    previous_move: CandidateMove | None = None

    for move in path:
        duration_seconds = edge_duration_seconds(
            move.edge,
            departure_at + timedelta(seconds=elapsed_seconds),
            traffic_profile,
            speed_mps=speed_mps,
        )
        penalty_seconds = transition_penalty_seconds(
            previous_move,
            move,
            speed_mps=speed_mps,
        )
        segment_duration_seconds = duration_seconds + penalty_seconds
        elapsed_seconds += segment_duration_seconds
        positions = move_geometry_positions(move)
        segments.append(
            CarRouteSegment(
                edge_id=move.edge.edge_id,
                from_node=move.from_node,
                to_node=move.to_node,
                road_name=move.edge.road_name,
                distance_m=move.edge.length_m,
                duration_seconds=segment_duration_seconds,
                from_lat=move.from_point.lat,
                from_lon=move.from_point.lon,
                to_lat=move.to_point.lat,
                to_lon=move.to_point.lon,
                path_positions=positions,
            )
        )
        previous_move = move

    network_distance_m = sum(segment.distance_m for segment in segments)
    total_distance_m = access_distance_m + network_distance_m + egress_distance_m
    total_duration_seconds = (
        best_duration_by_state[destination_state] + egress_duration_seconds
    )

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
        segment_positions = segment.path_positions or (
            (segment.from_lat, segment.from_lon),
            (segment.to_lat, segment.to_lon),
        )
        for point in segment_positions:
            if positions[-1] != point:
                positions.append(point)

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
