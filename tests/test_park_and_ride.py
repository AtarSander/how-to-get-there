from __future__ import annotations

from datetime import datetime, timedelta

from config.park_and_ride import ParkAndRideLocation
from services.car_routing import CarRoute, GeoPoint
from services.park_and_ride import (
    build_walk_to_metro_leg,
    find_park_and_ride_routes,
    rank_candidate_parkings,
)
from services.public_transport import JourneyLeg, PublicTransportJourney


def test_rank_candidate_parkings_sorts_by_distance() -> None:
    origin = GeoPoint(52.29, 20.93)
    farther = ParkAndRideLocation(
        parking_id="far",
        name="Far",
        lat=52.10,
        lon=21.10,
        metro_station="Far Metro",
        metro_line="M1",
        metro_lat=52.10,
        metro_lon=21.10,
    )
    closer = ParkAndRideLocation(
        parking_id="near",
        name="Near",
        lat=52.291,
        lon=20.931,
        metro_station="Near Metro",
        metro_line="M1",
        metro_lat=52.291,
        metro_lon=20.931,
    )

    ranked = rank_candidate_parkings(origin, [farther, closer], limit=1)

    assert ranked == [closer]


def test_build_walk_to_metro_leg_uses_parking_and_station_coordinates() -> None:
    departure_at = datetime(2026, 5, 14, 8, 0, 0)
    parking = ParkAndRideLocation(
        parking_id="test",
        name="P+R Test",
        lat=52.0,
        lon=21.0,
        metro_station="Metro Test",
        metro_line="M1",
        metro_lat=52.0,
        metro_lon=21.001,
    )

    leg = build_walk_to_metro_leg(parking, departure_at)

    assert leg.from_name == "P+R Test"
    assert leg.to_name == "Metro Test"
    assert leg.distance_m > 60
    assert leg.arrival_at > departure_at


def test_find_park_and_ride_routes_combines_car_walk_and_public_transport() -> None:
    departure_at = datetime(2026, 5, 14, 8, 0, 0)
    parking = ParkAndRideLocation(
        parking_id="test",
        name="P+R Test",
        lat=52.0,
        lon=21.01,
        metro_station="Metro Test",
        metro_line="M1",
        metro_lat=52.0,
        metro_lon=21.011,
    )

    def fake_public_transport_finder(
        engine,
        origin_lat,
        origin_lon,
        destination_lat,
        destination_lon,
        requested_departure_at,
        **kwargs,
    ):
        return [
            PublicTransportJourney(
                departure_at=requested_departure_at,
                arrival_at=requested_departure_at + timedelta(minutes=20),
                total_minutes=20,
                in_vehicle_minutes=17,
                walking_minutes=3,
                transfers=0,
                legs=[
                    JourneyLeg(
                        mode="ride",
                        from_name="Metro Test",
                        to_name="Destination",
                        departure_at=requested_departure_at,
                        arrival_at=requested_departure_at + timedelta(minutes=20),
                        duration_minutes=20,
                        route_name="M1",
                    )
                ],
            )
        ]

    routes = find_park_and_ride_routes(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.1,
        destination_lon=21.1,
        departure_at=departure_at,
        parkings=[parking],
        candidate_limit=1,
        limit=1,
        public_transport_finder=fake_public_transport_finder,
    )

    assert len(routes) == 1
    assert routes[0].parking == parking
    assert isinstance(routes[0].car_route, CarRoute)
    assert routes[0].walk_to_metro.to_name == "Metro Test"
    assert routes[0].public_transport_journey.legs[0].route_name == "M1"
    assert routes[0].arrival_at > departure_at + timedelta(minutes=20)


def test_find_park_and_ride_routes_prefers_closer_parking_before_fastest_arrival() -> None:
    departure_at = datetime(2026, 5, 14, 8, 0, 0)
    near_parking = ParkAndRideLocation(
        parking_id="near",
        name="P+R Near",
        lat=52.001,
        lon=21.0,
        metro_station="Metro Near",
        metro_line="M1",
        metro_lat=52.001,
        metro_lon=21.0,
    )
    far_parking = ParkAndRideLocation(
        parking_id="wilanowska-like",
        name="P+R Far",
        lat=52.1,
        lon=21.0,
        metro_station="Metro Far",
        metro_line="M1",
        metro_lat=52.1,
        metro_lon=21.0,
    )
    public_transport_origins: list[tuple[float, float]] = []

    def fake_public_transport_finder(
        engine,
        origin_lat,
        origin_lon,
        destination_lat,
        destination_lon,
        requested_departure_at,
        **kwargs,
    ):
        public_transport_origins.append((origin_lat, origin_lon))
        is_far_parking = origin_lat == far_parking.metro_lat
        duration_minutes = 1 if is_far_parking else 60
        to_name = "Destination from Far" if is_far_parking else "Destination from Near"

        return [
            PublicTransportJourney(
                departure_at=requested_departure_at,
                arrival_at=requested_departure_at + timedelta(minutes=duration_minutes),
                total_minutes=duration_minutes,
                in_vehicle_minutes=duration_minutes,
                walking_minutes=0,
                transfers=0,
                legs=[
                    JourneyLeg(
                        mode="ride",
                        from_name="Metro",
                        to_name=to_name,
                        departure_at=requested_departure_at,
                        arrival_at=(
                            requested_departure_at
                            + timedelta(minutes=duration_minutes)
                        ),
                        duration_minutes=duration_minutes,
                        route_name="M1",
                    )
                ],
            )
        ]

    routes = find_park_and_ride_routes(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.2,
        destination_lon=21.0,
        departure_at=departure_at,
        parkings=[near_parking, far_parking],
        candidate_limit=2,
        limit=1,
        public_transport_finder=fake_public_transport_finder,
    )

    assert len(routes) == 1
    assert routes[0].parking == near_parking
    assert public_transport_origins == [
        (near_parking.metro_lat, near_parking.metro_lon)
    ]
    assert routes[0].public_transport_journey.legs[0].to_name == (
        "Destination from Near"
    )
