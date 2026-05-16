from __future__ import annotations

from datetime import datetime, timedelta

from api.map_geometry import build_option_map
from config.park_and_ride import ParkAndRideLocation
from services.car_routing import CarRoute, GeoPoint
from services.park_and_ride import ParkAndRideRoute, ParkAndRideWalkLeg
from services.public_transport import JourneyLeg, PublicTransportJourney
from services.route_comparison import (
    option_from_park_and_ride,
    option_from_public_transport,
)


def test_public_transport_map_separates_walk_and_transit_lines_with_stop_markers() -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    journey = PublicTransportJourney(
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(minutes=20),
        total_minutes=20,
        in_vehicle_minutes=14,
        walking_minutes=6,
        transfers=0,
        legs=[
            JourneyLeg(
                mode="walk",
                from_name="origin",
                to_name="Stop A",
                departure_at=departure_at,
                arrival_at=departure_at + timedelta(minutes=3),
                duration_minutes=3,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.001,
                to_lon=21.001,
            ),
            JourneyLeg(
                mode="ride",
                from_name="Stop A",
                to_name="Stop B",
                departure_at=departure_at + timedelta(minutes=3),
                arrival_at=departure_at + timedelta(minutes=17),
                duration_minutes=14,
                route_name="M1",
                from_lat=52.001,
                from_lon=21.001,
                to_lat=52.01,
                to_lon=21.01,
            ),
            JourneyLeg(
                mode="walk",
                from_name="Stop B",
                to_name="destination",
                departure_at=departure_at + timedelta(minutes=17),
                arrival_at=departure_at + timedelta(minutes=20),
                duration_minutes=3,
                from_lat=52.01,
                from_lon=21.01,
                to_lat=52.011,
                to_lon=21.011,
            ),
        ],
    )

    route_map = build_option_map(
        option_from_public_transport(journey, departure_at),
        GeoPoint(52.0, 21.0),
        GeoPoint(52.011, 21.011),
    )

    assert route_map is not None
    assert [line["kind"] for line in route_map["lines"]] == [
        "walk",
        "transit",
        "walk",
    ]
    assert {
        (marker["kind"], marker["label"])
        for marker in route_map["markers"]
    } == {
        ("transit_stop", "Stop A"),
        ("transit_stop", "Stop B"),
    }


def test_park_and_ride_map_marks_parking_and_transit_stops() -> None:
    departure_at = datetime(2026, 5, 16, 8, 0, 0)
    parking = ParkAndRideLocation(
        parking_id="test",
        name="P+R Test",
        lat=52.0,
        lon=21.0,
        metro_station="Metro Test",
        metro_line="M1",
        metro_lat=52.002,
        metro_lon=21.002,
    )
    car_route = CarRoute(
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(minutes=5),
        total_distance_m=1_000,
        total_duration_seconds=300,
        access_distance_m=0,
        egress_distance_m=0,
        segments=[],
    )
    walk_to_metro = ParkAndRideWalkLeg(
        from_name=parking.name,
        to_name=parking.metro_station,
        departure_at=car_route.arrival_at,
        arrival_at=car_route.arrival_at + timedelta(minutes=2),
        distance_m=150,
        duration_seconds=120,
        path_positions=((52.0, 21.0), (52.002, 21.002)),
    )
    public_transport = PublicTransportJourney(
        departure_at=walk_to_metro.arrival_at,
        arrival_at=walk_to_metro.arrival_at + timedelta(minutes=12),
        total_minutes=12,
        in_vehicle_minutes=12,
        walking_minutes=0,
        transfers=0,
        legs=[
            JourneyLeg(
                mode="ride",
                from_name=parking.metro_station,
                to_name="Stop B",
                departure_at=walk_to_metro.arrival_at,
                arrival_at=walk_to_metro.arrival_at + timedelta(minutes=12),
                duration_minutes=12,
                route_name="M1",
                from_lat=parking.metro_lat,
                from_lon=parking.metro_lon,
                to_lat=52.01,
                to_lon=21.01,
            )
        ],
    )
    route = ParkAndRideRoute(
        parking=parking,
        departure_at=departure_at,
        arrival_at=public_transport.arrival_at,
        total_minutes=19,
        total_distance_m=1_150,
        car_route=car_route,
        walk_to_metro=walk_to_metro,
        public_transport_journey=public_transport,
    )

    route_map = build_option_map(
        option_from_park_and_ride(route, departure_at),
        GeoPoint(51.999, 20.999),
        GeoPoint(52.011, 21.011),
    )

    assert route_map is not None
    assert [line["kind"] for line in route_map["lines"]] == [
        "car",
        "walk",
        "transit",
    ]
    assert {
        (marker["kind"], marker["label"])
        for marker in route_map["markers"]
    } == {
        ("parking", "P+R Test"),
        ("transit_stop", "Metro Test"),
        ("transit_stop", "Stop B"),
    }
