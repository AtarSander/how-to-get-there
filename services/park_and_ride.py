from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import TYPE_CHECKING, Any, Callable

from config.park_and_ride import PARK_AND_RIDE_LOCATIONS, ParkAndRideLocation
from config.settings import settings
from services.car_routing import (
    CarRoute,
    GeoPoint,
    RoadEdge,
    TrafficProfile,
    estimate_direct_car_route,
    find_car_route,
    haversine_distance_m,
    resolve_route,
    walking_speed_mps,
)
from services.public_transport import (
    JourneyLeg,
    PublicTransportJourney,
    find_public_transport_connections,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any

PublicTransportFinder = Callable[
    [Engine, float, float, float, float, datetime],
    list[PublicTransportJourney],
]


@dataclass(frozen=True)
class ParkAndRideWalkLeg:
    from_name: str
    to_name: str
    departure_at: datetime
    arrival_at: datetime
    distance_m: float
    duration_seconds: int
    path_positions: tuple[tuple[float, float], ...] | None = None

    @property
    def duration_minutes(self) -> int:
        return ceil(self.duration_seconds / 60)


@dataclass(frozen=True)
class ParkAndRideRoute:
    parking: ParkAndRideLocation
    departure_at: datetime
    arrival_at: datetime
    total_minutes: int
    total_distance_m: float
    car_route: CarRoute
    walk_to_metro: ParkAndRideWalkLeg
    public_transport_journey: PublicTransportJourney

    @property
    def public_transport_legs(self) -> list[JourneyLeg]:
        return self.public_transport_journey.legs


def build_walk_to_metro_leg(
    parking: ParkAndRideLocation,
    departure_at: datetime,
    road_edges: list[RoadEdge] | None = None,
) -> ParkAndRideWalkLeg:
    parking_point = GeoPoint(parking.lat, parking.lon)
    metro_point = GeoPoint(parking.metro_lat, parking.metro_lon)
    walk_result = resolve_route(
        origin=parking_point,
        destination=metro_point,
        departure_at=departure_at,
        road_edges=road_edges,
        speed_mps=walking_speed_mps(),
        allow_direct_fallback=True,
    )
    assert walk_result is not None

    return ParkAndRideWalkLeg(
        from_name=parking.name,
        to_name=parking.metro_station,
        departure_at=departure_at,
        arrival_at=walk_result.route.arrival_at,
        distance_m=walk_result.route.total_distance_m,
        duration_seconds=walk_result.route.total_duration_seconds,
        path_positions=walk_result.path_positions,
    )


def rank_candidate_parkings(
    origin: GeoPoint,
    parkings: list[ParkAndRideLocation],
    limit: int,
) -> list[ParkAndRideLocation]:
    return sorted(
        parkings,
        key=lambda parking: haversine_distance_m(
            origin,
            GeoPoint(parking.lat, parking.lon),
        ),
    )[:limit]


def find_park_and_ride_routes(
    engine: Engine,
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    departure_at: datetime,
    road_edges: list[RoadEdge] | None = None,
    traffic_profile: TrafficProfile | None = None,
    parkings: list[ParkAndRideLocation] | None = None,
    candidate_limit: int | None = None,
    limit: int | None = None,
    public_transport_finder: PublicTransportFinder = find_public_transport_connections,
) -> list[ParkAndRideRoute]:
    origin = GeoPoint(origin_lat, origin_lon)
    destination = GeoPoint(destination_lat, destination_lon)
    candidate_limit = candidate_limit or settings.park_and_ride_candidate_limit
    limit = limit or settings.park_and_ride_result_limit
    parkings = parkings or PARK_AND_RIDE_LOCATIONS

    candidates = rank_candidate_parkings(origin, parkings, candidate_limit)
    routes: list[ParkAndRideRoute] = []

    for parking in candidates:
        parking_point = GeoPoint(parking.lat, parking.lon)
        car_route = (
            find_car_route(
                edges=road_edges,
                origin=origin,
                destination=parking_point,
                departure_at=departure_at,
                traffic_profile=traffic_profile,
            )
            if road_edges
            else estimate_direct_car_route(
                origin=origin,
                destination=parking_point,
                departure_at=departure_at,
                traffic_profile=traffic_profile,
            )
        )

        if car_route is None:
            continue

        walk_to_metro = build_walk_to_metro_leg(
            parking,
            car_route.arrival_at,
            road_edges=road_edges,
        )
        metro_departure_at = walk_to_metro.arrival_at + timedelta(
            seconds=settings.park_and_ride_min_transfer_seconds
        )
        public_transport_journeys = public_transport_finder(
            engine,
            parking.metro_lat,
            parking.metro_lon,
            destination.lat,
            destination.lon,
            metro_departure_at,
            road_edges=road_edges,
        )

        for public_transport_journey in public_transport_journeys:
            arrival_at = public_transport_journey.arrival_at
            total_seconds = ceil((arrival_at - departure_at).total_seconds())

            routes.append(
                ParkAndRideRoute(
                    parking=parking,
                    departure_at=departure_at,
                    arrival_at=arrival_at,
                    total_minutes=ceil(total_seconds / 60),
                    total_distance_m=(
                        car_route.total_distance_m + walk_to_metro.distance_m
                    ),
                    car_route=car_route,
                    walk_to_metro=walk_to_metro,
                    public_transport_journey=public_transport_journey,
                )
            )

    routes.sort(
        key=lambda route: (
            route.arrival_at,
            route.public_transport_journey.transfers,
            route.total_minutes,
        )
    )
    return routes[:limit]
