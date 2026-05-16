from __future__ import annotations

from datetime import datetime
from typing import Any

from services.car_routing import CarRoute, CarRouteSegment, GeoPoint
from services.park_and_ride import ParkAndRideRoute, ParkAndRideWalkLeg
from services.public_transport import JourneyLeg, PublicTransportJourney
from api.map_geometry import build_option_map
from services.route_comparison import RouteComparison, RouteOption


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_geo_point(point: GeoPoint) -> dict[str, float]:
    return {"lat": point.lat, "lon": point.lon}


def serialize_car_segment(segment: CarRouteSegment) -> dict[str, Any]:
    return {
        "edge_id": segment.edge_id,
        "from_node": segment.from_node,
        "to_node": segment.to_node,
        "road_name": segment.road_name,
        "distance_m": segment.distance_m,
        "duration_seconds": segment.duration_seconds,
        "from_lat": segment.from_lat,
        "from_lon": segment.from_lon,
        "to_lat": segment.to_lat,
        "to_lon": segment.to_lon,
    }


def serialize_car_route(route: CarRoute) -> dict[str, Any]:
    return {
        "departure_at": _dt(route.departure_at),
        "arrival_at": _dt(route.arrival_at),
        "total_distance_m": route.total_distance_m,
        "total_duration_seconds": route.total_duration_seconds,
        "total_minutes": route.total_minutes,
        "access_distance_m": route.access_distance_m,
        "egress_distance_m": route.egress_distance_m,
        "segments": [serialize_car_segment(segment) for segment in route.segments],
    }


def serialize_journey_leg(leg: JourneyLeg) -> dict[str, Any]:
    return {
        "mode": leg.mode,
        "from_name": leg.from_name,
        "to_name": leg.to_name,
        "departure_at": _dt(leg.departure_at),
        "arrival_at": _dt(leg.arrival_at),
        "duration_minutes": leg.duration_minutes,
        "route_name": leg.route_name,
        "trip_headsign": leg.trip_headsign,
        "from_lat": leg.from_lat,
        "from_lon": leg.from_lon,
        "to_lat": leg.to_lat,
        "to_lon": leg.to_lon,
    }


def serialize_public_transport_journey(
    journey: PublicTransportJourney,
) -> dict[str, Any]:
    return {
        "departure_at": _dt(journey.departure_at),
        "arrival_at": _dt(journey.arrival_at),
        "total_minutes": journey.total_minutes,
        "in_vehicle_minutes": journey.in_vehicle_minutes,
        "walking_minutes": journey.walking_minutes,
        "transfers": journey.transfers,
        "legs": [serialize_journey_leg(leg) for leg in journey.legs],
    }


def serialize_walk_leg(leg: ParkAndRideWalkLeg) -> dict[str, Any]:
    return {
        "from_name": leg.from_name,
        "to_name": leg.to_name,
        "departure_at": _dt(leg.departure_at),
        "arrival_at": _dt(leg.arrival_at),
        "distance_m": leg.distance_m,
        "duration_seconds": leg.duration_seconds,
        "duration_minutes": leg.duration_minutes,
    }


def serialize_park_and_ride_route(route: ParkAndRideRoute) -> dict[str, Any]:
    parking = route.parking
    return {
        "parking": {
            "parking_id": parking.parking_id,
            "name": parking.name,
            "lat": parking.lat,
            "lon": parking.lon,
            "metro_station": parking.metro_station,
            "metro_line": parking.metro_line,
            "metro_lat": parking.metro_lat,
            "metro_lon": parking.metro_lon,
        },
        "departure_at": _dt(route.departure_at),
        "arrival_at": _dt(route.arrival_at),
        "total_minutes": route.total_minutes,
        "total_distance_m": route.total_distance_m,
        "car_route": serialize_car_route(route.car_route),
        "walk_to_metro": serialize_walk_leg(route.walk_to_metro),
        "public_transport": serialize_public_transport_journey(
            route.public_transport_journey
        ),
    }


def serialize_option_details(option: RouteOption) -> dict[str, Any] | None:
    details = option.details
    if details is None:
        return None
    if option.mode == "car":
        return {"car": serialize_car_route(details)}
    if option.mode == "public_transport":
        return {"public_transport": serialize_public_transport_journey(details)}
    if option.mode == "park_and_ride":
        return {"park_and_ride": serialize_park_and_ride_route(details)}
    return None


def serialize_route_option(
    option: RouteOption,
    origin: GeoPoint,
    destination: GeoPoint,
) -> dict[str, Any]:
    return {
        "mode": option.mode,
        "label": option.label,
        "available": option.available,
        "departure_at": _dt(option.departure_at),
        "arrival_at": _dt(option.arrival_at),
        "total_minutes": option.total_minutes,
        "total_distance_m": option.total_distance_m,
        "transfers": option.transfers,
        "reason": option.reason,
        "details": serialize_option_details(option),
        "map": build_option_map(option, origin, destination),
    }


def serialize_route_comparison(comparison: RouteComparison) -> dict[str, Any]:
    best = comparison.best_option
    return {
        "origin": serialize_geo_point(comparison.origin),
        "destination": serialize_geo_point(comparison.destination),
        "departure_at": _dt(comparison.departure_at),
        "options": [
            serialize_route_option(option, comparison.origin, comparison.destination)
            for option in comparison.options
        ],
        "best_option": (
            serialize_route_option(best, comparison.origin, comparison.destination)
            if best is not None
            else None
        ),
    }
