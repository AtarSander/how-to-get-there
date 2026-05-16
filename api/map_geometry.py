from __future__ import annotations

from typing import Any

from services.car_routing import CarRoute, GeoPoint
from services.park_and_ride import ParkAndRideRoute
from services.public_transport import PublicTransportJourney
from services.route_comparison import RouteOption


def _point(lat: float, lon: float) -> list[float]:
    return [lat, lon]


def _append_unique(positions: list[list[float]], lat: float, lon: float) -> None:
    point = _point(lat, lon)
    if not positions or positions[-1] != point:
        positions.append(point)


def build_line_from_car_route(
    origin: GeoPoint,
    destination: GeoPoint,
    car_route: CarRoute,
) -> list[list[float]]:
    if not car_route.segments:
        return [_point(origin.lat, origin.lon), _point(destination.lat, destination.lon)]

    positions: list[list[float]] = []
    _append_unique(positions, origin.lat, origin.lon)

    for segment in car_route.segments:
        _append_unique(positions, segment.from_lat, segment.from_lon)
        _append_unique(positions, segment.to_lat, segment.to_lon)

    _append_unique(positions, destination.lat, destination.lon)
    return positions


def build_lines_from_public_transport(
    origin: GeoPoint,
    destination: GeoPoint,
    journey: PublicTransportJourney,
) -> list[list[list[float]]]:
    lines: list[list[list[float]]] = []

    for leg in journey.legs:
        if leg.from_lat is None or leg.from_lon is None or leg.to_lat is None or leg.to_lon is None:
            continue
        lines.append(
            [
                _point(leg.from_lat, leg.from_lon),
                _point(leg.to_lat, leg.to_lon),
            ]
        )

    if not lines:
        lines.append([_point(origin.lat, origin.lon), _point(destination.lat, destination.lon)])

    return lines


def build_option_map(
    option: RouteOption,
    origin: GeoPoint,
    destination: GeoPoint,
) -> dict[str, Any] | None:
    if not option.available or option.details is None:
        return None

    if option.mode == "car":
        car_route = option.details
        return {
            "lines": [
                {
                    "kind": "car",
                    "positions": build_line_from_car_route(origin, destination, car_route),
                }
            ],
            "markers": [],
        }

    if option.mode == "public_transport":
        journey = option.details
        return {
            "lines": [
                {
                    "kind": "transit",
                    "positions": positions,
                }
                for positions in build_lines_from_public_transport(
                    origin,
                    destination,
                    journey,
                )
            ],
            "markers": [],
        }

    if option.mode == "park_and_ride":
        route: ParkAndRideRoute = option.details
        parking = route.parking
        lines = [
            {
                "kind": "car",
                "positions": build_line_from_car_route(
                    origin,
                    GeoPoint(parking.lat, parking.lon),
                    route.car_route,
                ),
            },
            {
                "kind": "walk",
                "positions": [
                    _point(parking.lat, parking.lon),
                    _point(parking.metro_lat, parking.metro_lon),
                ],
            },
        ]
        lines.extend(
            {
                "kind": "transit",
                "positions": positions,
            }
            for positions in build_lines_from_public_transport(
                GeoPoint(parking.metro_lat, parking.metro_lon),
                destination,
                route.public_transport_journey,
            )
        )
        return {
            "lines": lines,
            "markers": [
                {
                    "kind": "parking",
                    "label": parking.name,
                    "lat": parking.lat,
                    "lon": parking.lon,
                }
            ],
        }

    return None
