from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from config.settings import settings
from database.queries import RoadEdgeRecord, fetch_road_edges
from services.car_routing import (
    CarRoute,
    GeoPoint,
    RoadEdge,
    TrafficProfile,
    estimate_direct_car_route,
    find_car_route,
)
from services.park_and_ride import ParkAndRideRoute, find_park_and_ride_routes
from services.public_transport import (
    PublicTransportJourney,
    find_public_transport_connections,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any

CarRouteFinder = Callable[
    [list[RoadEdge], GeoPoint, GeoPoint, datetime, TrafficProfile | None],
    CarRoute | None,
]
PublicTransportFinder = Callable[
    [Engine, float, float, float, float, datetime],
    list[PublicTransportJourney],
]
ParkAndRideFinder = Callable[..., list[ParkAndRideRoute]]
RoadEdgesLoader = Callable[[Engine], list[RoadEdge]]


@dataclass(frozen=True)
class RouteOption:
    mode: str
    label: str
    available: bool
    departure_at: datetime
    arrival_at: datetime | None
    total_minutes: int | None
    total_distance_m: float | None
    transfers: int | None
    details: CarRoute | PublicTransportJourney | ParkAndRideRoute | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RouteComparison:
    origin: GeoPoint
    destination: GeoPoint
    departure_at: datetime
    options: list[RouteOption]

    @property
    def best_option(self) -> RouteOption | None:
        available_options = [option for option in self.options if option.available]
        if not available_options:
            return None

        return min(
            available_options,
            key=lambda option: (
                option.total_minutes if option.total_minutes is not None else 10**9,
                option.transfers if option.transfers is not None else 10**9,
            ),
        )


def build_unavailable_option(
    mode: str,
    label: str,
    departure_at: datetime,
    reason: str,
) -> RouteOption:
    return RouteOption(
        mode=mode,
        label=label,
        available=False,
        departure_at=departure_at,
        arrival_at=None,
        total_minutes=None,
        total_distance_m=None,
        transfers=None,
        details=None,
        reason=reason,
    )


def option_from_car_route(route: CarRoute, departure_at: datetime) -> RouteOption:
    return RouteOption(
        mode="car",
        label="Samochod",
        available=True,
        departure_at=departure_at,
        arrival_at=route.arrival_at,
        total_minutes=route.total_minutes,
        total_distance_m=route.total_distance_m,
        transfers=0,
        details=route,
    )


def option_from_public_transport(
    journey: PublicTransportJourney,
    departure_at: datetime,
) -> RouteOption:
    return RouteOption(
        mode="public_transport",
        label="Komunikacja miejska",
        available=True,
        departure_at=departure_at,
        arrival_at=journey.arrival_at,
        total_minutes=journey.total_minutes,
        total_distance_m=None,
        transfers=journey.transfers,
        details=journey,
    )


def option_from_park_and_ride(
    route: ParkAndRideRoute,
    departure_at: datetime,
) -> RouteOption:
    return RouteOption(
        mode="park_and_ride",
        label=f"Park & Ride: {route.parking.name}",
        available=True,
        departure_at=departure_at,
        arrival_at=route.arrival_at,
        total_minutes=route.total_minutes,
        total_distance_m=route.total_distance_m,
        transfers=route.public_transport_journey.transfers + 1,
        details=route,
    )


def road_edge_from_record(record: RoadEdgeRecord) -> RoadEdge:
    return RoadEdge(
        edge_id=record.edge_id,
        source=record.source,
        target=record.target,
        source_point=GeoPoint(record.source_lat, record.source_lon),
        target_point=GeoPoint(record.target_lat, record.target_lon),
        length_m=record.length_m,
        max_speed_kmh=record.max_speed_kmh,
        road_name=record.road_name,
        bidirectional=not record.oneway,
    )


def load_road_edges_from_database(engine: Engine) -> list[RoadEdge]:
    records = fetch_road_edges(engine, limit=settings.car_road_edges_limit)
    return [road_edge_from_record(record) for record in records]


def resolve_road_edges(
    engine: Engine,
    road_edges: list[RoadEdge] | None,
    road_edges_loader: RoadEdgesLoader | None,
) -> list[RoadEdge] | None:
    if road_edges is not None:
        return road_edges

    if not settings.car_use_database_edges or road_edges_loader is None:
        return None

    try:
        loaded_edges = road_edges_loader(engine)
    except Exception:
        return None

    return loaded_edges or None


def compare_routes(
    engine: Engine,
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    departure_at: datetime,
    road_edges: list[RoadEdge] | None = None,
    traffic_profile: TrafficProfile | None = None,
    car_route_finder: CarRouteFinder = find_car_route,
    public_transport_finder: PublicTransportFinder = find_public_transport_connections,
    park_and_ride_finder: ParkAndRideFinder = find_park_and_ride_routes,
    road_edges_loader: RoadEdgesLoader | None = load_road_edges_from_database,
) -> RouteComparison:
    origin = GeoPoint(origin_lat, origin_lon)
    destination = GeoPoint(destination_lat, destination_lon)
    options: list[RouteOption] = []
    resolved_road_edges = resolve_road_edges(
        engine=engine,
        road_edges=road_edges,
        road_edges_loader=road_edges_loader,
    )

    car_route = (
        car_route_finder(
            resolved_road_edges,
            origin,
            destination,
            departure_at,
            traffic_profile,
        )
        if resolved_road_edges
        else estimate_direct_car_route(
            origin=origin,
            destination=destination,
            departure_at=departure_at,
            traffic_profile=traffic_profile,
        )
    )
    if car_route is None:
        options.append(
            build_unavailable_option(
                mode="car",
                label="Samochod",
                departure_at=departure_at,
                reason="Nie znaleziono trasy samochodowej.",
            )
        )
    else:
        options.append(option_from_car_route(car_route, departure_at))

    public_transport_journeys = public_transport_finder(
        engine,
        origin_lat,
        origin_lon,
        destination_lat,
        destination_lon,
        departure_at,
        limit=1,
        road_edges=resolved_road_edges,
    )
    if public_transport_journeys:
        options.append(
            option_from_public_transport(public_transport_journeys[0], departure_at)
        )
    else:
        options.append(
            build_unavailable_option(
                mode="public_transport",
                label="Komunikacja miejska",
                departure_at=departure_at,
                reason="Nie znaleziono polaczenia komunikacja miejska.",
            )
        )

    park_and_ride_routes = park_and_ride_finder(
        engine=engine,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        departure_at=departure_at,
        road_edges=resolved_road_edges,
        traffic_profile=traffic_profile,
        public_transport_finder=public_transport_finder,
    )
    if park_and_ride_routes:
        options.append(option_from_park_and_ride(park_and_ride_routes[0], departure_at))
    else:
        options.append(
            build_unavailable_option(
                mode="park_and_ride",
                label="Park & Ride",
                departure_at=departure_at,
                reason="Nie znaleziono trasy Park & Ride.",
            )
        )

    options.sort(
        key=lambda option: (
            not option.available,
            option.total_minutes if option.total_minutes is not None else 10**9,
            option.transfers if option.transfers is not None else 10**9,
        )
    )

    return RouteComparison(
        origin=origin,
        destination=destination,
        departure_at=departure_at,
        options=options,
    )
