from __future__ import annotations

from datetime import datetime, timedelta

from config.park_and_ride import ParkAndRideLocation
from services.car_routing import CarRoute, GeoPoint, RoadEdge
from services.park_and_ride import ParkAndRideRoute, ParkAndRideWalkLeg
from services.public_transport import JourneyLeg, PublicTransportJourney
from services.route_comparison import compare_routes


def make_public_transport_journey(
    departure_at: datetime,
    minutes: int,
    transfers: int = 0,
) -> PublicTransportJourney:
    return PublicTransportJourney(
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(minutes=minutes),
        total_minutes=minutes,
        in_vehicle_minutes=minutes - 2,
        walking_minutes=2,
        transfers=transfers,
        legs=[
            JourneyLeg(
                mode="ride",
                from_name="Start",
                to_name="End",
                departure_at=departure_at,
                arrival_at=departure_at + timedelta(minutes=minutes),
                duration_minutes=minutes,
                route_name="M1",
            )
        ],
    )


def test_compare_routes_sorts_available_options_by_total_minutes() -> None:
    departure_at = datetime(2026, 5, 14, 8, 0, 0)
    parking = ParkAndRideLocation(
        parking_id="test",
        name="P+R Test",
        lat=52.0,
        lon=21.0,
        metro_station="Metro Test",
        metro_line="M1",
        metro_lat=52.0,
        metro_lon=21.0,
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
        return [make_public_transport_journey(requested_departure_at, 35)]

    def fake_park_and_ride_finder(**kwargs):
        public_transport = make_public_transport_journey(departure_at, 20)
        car_route = CarRoute(
            departure_at=departure_at,
            arrival_at=departure_at + timedelta(minutes=10),
            total_distance_m=5_000,
            total_duration_seconds=600,
            access_distance_m=0,
            egress_distance_m=0,
            segments=[],
        )
        walk = ParkAndRideWalkLeg(
            from_name="P+R Test",
            to_name="Metro Test",
            departure_at=car_route.arrival_at,
            arrival_at=car_route.arrival_at + timedelta(minutes=2),
            distance_m=120,
            duration_seconds=120,
        )
        return [
            ParkAndRideRoute(
                parking=parking,
                departure_at=departure_at,
                arrival_at=departure_at + timedelta(minutes=32),
                total_minutes=32,
                total_distance_m=5_120,
                car_route=car_route,
                walk_to_metro=walk,
                public_transport_journey=public_transport,
            )
        ]

    def fake_car_route_finder(
        road_edges,
        origin,
        destination,
        departure_at,
        traffic_profile,
    ):
        return CarRoute(
            departure_at=departure_at,
            arrival_at=departure_at + timedelta(minutes=45),
            total_distance_m=12_000,
            total_duration_seconds=2_700,
            access_distance_m=0,
            egress_distance_m=0,
            segments=[],
        )

    comparison = compare_routes(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.1,
        destination_lon=21.1,
        departure_at=departure_at,
        road_edges=[
            RoadEdge(
                edge_id="dummy",
                source="A",
                target="B",
                source_point=GeoPoint(52.0, 21.0),
                target_point=GeoPoint(52.1, 21.1),
                length_m=12_000,
            )
        ],
        car_route_finder=fake_car_route_finder,
        public_transport_finder=fake_public_transport_finder,
        park_and_ride_finder=fake_park_and_ride_finder,
    )

    assert [option.mode for option in comparison.options] == [
        "park_and_ride",
        "public_transport",
        "car",
    ]
    assert comparison.best_option is not None
    assert comparison.best_option.mode == "park_and_ride"


def test_compare_routes_marks_missing_public_transport_and_park_and_ride() -> None:
    departure_at = datetime(2026, 5, 14, 8, 0, 0)

    comparison = compare_routes(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.01,
        destination_lon=21.01,
        departure_at=departure_at,
        public_transport_finder=lambda *args, **kwargs: [],
        park_and_ride_finder=lambda **kwargs: [],
    )

    unavailable_modes = {
        option.mode
        for option in comparison.options
        if not option.available
    }

    assert "public_transport" in unavailable_modes
    assert "park_and_ride" in unavailable_modes
    assert comparison.best_option is not None
    assert comparison.best_option.mode == "car"


def test_compare_routes_loads_road_edges_from_database_when_not_provided() -> None:
    departure_at = datetime(2026, 5, 14, 8, 0, 0)
    loaded_edges = [
        RoadEdge(
            edge_id="db-edge",
            source="A",
            target="B",
            source_point=GeoPoint(52.0, 21.0),
            target_point=GeoPoint(52.1, 21.1),
            length_m=15_000,
        )
    ]
    received_edge_ids: list[str] = []

    def fake_car_route_finder(
        road_edges,
        origin,
        destination,
        departure_at,
        traffic_profile,
    ):
        received_edge_ids.extend(edge.edge_id for edge in road_edges)
        return CarRoute(
            departure_at=departure_at,
            arrival_at=departure_at + timedelta(minutes=25),
            total_distance_m=15_000,
            total_duration_seconds=1_500,
            access_distance_m=0,
            egress_distance_m=0,
            segments=[],
        )

    comparison = compare_routes(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.1,
        destination_lon=21.1,
        departure_at=departure_at,
        car_route_finder=fake_car_route_finder,
        public_transport_finder=lambda *args, **kwargs: [],
        park_and_ride_finder=lambda **kwargs: [],
        road_edges_loader=lambda engine: loaded_edges,
    )

    assert received_edge_ids == ["db-edge"]
    assert comparison.best_option is not None
    assert comparison.best_option.mode == "car"
