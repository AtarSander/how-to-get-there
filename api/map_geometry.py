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


def line_kind_from_journey_leg(leg: Any) -> str:
    return "walk" if leg.mode == "walk" else "transit"


def build_line_from_car_route(
    origin: GeoPoint,
    destination: GeoPoint,
    car_route: CarRoute,
) -> list[list[float]]:
    if not car_route.segments:
        return [
            _point(origin.lat, origin.lon),
            _point(destination.lat, destination.lon),
        ]

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
) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []

    for leg in journey.legs:
        if leg.path_positions:
            positions = [_point(lat, lon) for lat, lon in leg.path_positions]
            lines.append({
                "kind": line_kind_from_journey_leg(leg),
                "positions": positions,
            })
            continue
        if (
            leg.from_lat is None
            or leg.from_lon is None
            or leg.to_lat is None
            or leg.to_lon is None
        ):
            continue
        lines.append(
            {
                "kind": line_kind_from_journey_leg(leg),
                "positions": [
                    _point(leg.from_lat, leg.from_lon),
                    _point(leg.to_lat, leg.to_lon),
                ],
            }
        )

    if not lines:
        lines.append({
            "kind": "transit",
            "positions": [
                _point(origin.lat, origin.lon),
                _point(destination.lat, destination.lon),
            ],
        })

    return lines


def _append_unique_marker(
    markers: list[dict[str, Any]],
    seen: set[tuple[str, float, float]],
    *,
    kind: str,
    label: str,
    lat: float,
    lon: float,
) -> None:
    key = (label, round(lat, 6), round(lon, 6))
    if key in seen:
        return

    seen.add(key)
    markers.append(
        {
            "kind": kind,
            "label": label,
            "lat": lat,
            "lon": lon,
        }
    )


def build_stop_markers_from_public_transport(
    journey: PublicTransportJourney,
    seen: set[tuple[str, float, float]] | None = None,
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    seen_markers = seen if seen is not None else set()

    for leg in journey.legs:
        if leg.mode != "ride":
            continue
        if leg.from_lat is not None and leg.from_lon is not None:
            _append_unique_marker(
                markers,
                seen_markers,
                kind="transit_stop",
                label=leg.from_name,
                lat=leg.from_lat,
                lon=leg.from_lon,
            )
        if leg.to_lat is not None and leg.to_lon is not None:
            _append_unique_marker(
                markers,
                seen_markers,
                kind="transit_stop",
                label=leg.to_name,
                lat=leg.to_lat,
                lon=leg.to_lon,
            )

    return markers


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
                    "positions": build_line_from_car_route(
                        origin, destination, car_route
                    ),
                }
            ],
            "markers": [],
        }

    if option.mode == "public_transport":
        journey = option.details
        return {
            "lines": build_lines_from_public_transport(
                origin,
                destination,
                journey,
            ),
            "markers": build_stop_markers_from_public_transport(journey),
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
                "positions": (
                    [
                        _point(lat, lon)
                        for lat, lon in route.walk_to_metro.path_positions
                    ]
                    if route.walk_to_metro.path_positions
                    else [
                        _point(parking.lat, parking.lon),
                        _point(parking.metro_lat, parking.metro_lon),
                    ]
                ),
            },
        ]
        lines.extend(
            build_lines_from_public_transport(
                GeoPoint(parking.metro_lat, parking.metro_lon),
                destination,
                route.public_transport_journey,
            )
        )
        seen_markers: set[tuple[str, float, float]] = set()
        markers = [
            {
                "kind": "parking",
                "label": parking.name,
                "lat": parking.lat,
                "lon": parking.lon,
            }
        ]
        _append_unique_marker(
            markers,
            seen_markers,
            kind="transit_stop",
            label=parking.metro_station,
            lat=parking.metro_lat,
            lon=parking.metro_lon,
        )
        markers.extend(
            build_stop_markers_from_public_transport(
                route.public_transport_journey,
                seen_markers,
            )
        )
        return {
            "lines": lines,
            "markers": markers,
        }

    return None
