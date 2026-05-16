from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from database.queries import ConnectionSegment, DirectConnectionCandidate, NearbyStop
from services.car_routing import GeoPoint
from services.public_transport import (
    build_journey_from_candidate,
    build_journey_from_segments,
    find_public_transport_connections,
    format_gtfs_time,
    parse_gtfs_time,
)


def test_parse_gtfs_time_supports_hours_above_24() -> None:
    assert parse_gtfs_time("26:15:00") == timedelta(hours=26, minutes=15)


def test_format_gtfs_time_serializes_timedelta() -> None:
    assert format_gtfs_time(timedelta(hours=5, minutes=7, seconds=9)) == "05:07:09"


def test_build_journey_skips_unreachable_departure() -> None:
    requested_departure = datetime(2026, 5, 2, 8, 0, 0)

    journey = build_journey_from_candidate(
        requested_departure_at=requested_departure,
        origin_point=GeoPoint(52.0, 21.0),
        destination_point=GeoPoint(52.01, 21.01),
        origin_stop=NearbyStop("A", "Start", 52.008, 21.0, 900.0),
        destination_stop=NearbyStop("B", "End", 52.01, 21.01, 50.0),
        candidate=DirectConnectionCandidate(
            trip_id="trip-1",
            route_id="route-1",
            route_short_name="M1",
            trip_headsign="Centrum",
            origin_stop_id="A",
            origin_stop_name="Start",
            destination_stop_id="B",
            destination_stop_name="End",
            departure_time="08:05:00",
            arrival_time="08:20:00",
            stop_count=4,
        ),
    )

    assert journey is None


def test_build_journey_from_segments_counts_transfers() -> None:
    requested_departure = datetime(2026, 5, 2, 8, 0, 0)

    journey = build_journey_from_segments(
        requested_departure_at=requested_departure,
        origin_point=GeoPoint(52.0, 21.0),
        destination_point=GeoPoint(52.03, 21.03),
        origin_stop=NearbyStop("A", "Start", 52.0, 21.0, 80.0),
        destination_stop=NearbyStop("D", "End", 52.03, 21.03, 60.0),
        segments=[
            ConnectionSegment(
                trip_id="trip-1",
                route_id="route-1",
                route_short_name="116",
                trip_headsign="Dworzec Centralny",
                from_stop_id="A",
                from_stop_name="Start",
                to_stop_id="B",
                to_stop_name="Transfer",
                departure_time="08:05:00",
                arrival_time="08:10:00",
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.01,
                to_lon=21.01,
            ),
            ConnectionSegment(
                trip_id="trip-1",
                route_id="route-1",
                route_short_name="116",
                trip_headsign="Dworzec Centralny",
                from_stop_id="B",
                from_stop_name="Transfer",
                to_stop_id="C",
                to_stop_name="Transfer 2",
                departure_time="08:10:00",
                arrival_time="08:16:00",
                from_stop_sequence=2,
                to_stop_sequence=3,
                from_lat=52.01,
                from_lon=21.01,
                to_lat=52.02,
                to_lon=21.02,
            ),
            ConnectionSegment(
                trip_id="trip-2",
                route_id="route-2",
                route_short_name="M1",
                trip_headsign="Mloci ny",
                from_stop_id="C",
                from_stop_name="Transfer 2",
                to_stop_id="D",
                to_stop_name="End",
                departure_time="08:20:00",
                arrival_time="08:28:00",
                from_stop_sequence=10,
                to_stop_sequence=11,
                from_lat=52.02,
                from_lon=21.02,
                to_lat=52.03,
                to_lon=21.03,
            ),
        ],
    )

    assert journey is not None
    assert journey.transfers == 1
    assert journey.legs[1].route_name == "116"
    assert journey.legs[2].route_name == "M1"


@patch("services.public_transport.resolve_ride_path_positions", return_value=None)
@patch("services.public_transport.fetch_reachable_connection_segments")
@patch("services.public_transport.fetch_active_service_ids")
@patch("services.public_transport.fetch_nearest_stops")
def test_find_public_transport_connections_supports_transfer_paths(
    mocked_fetch_nearest_stops: Mock,
    mocked_fetch_active_service_ids: Mock,
    mocked_fetch_reachable_connection_segments: Mock,
    _mocked_resolve_ride_path_positions: Mock,
) -> None:
    requested_departure = datetime(2026, 5, 2, 8, 0, 0)

    mocked_fetch_nearest_stops.side_effect = [
        [
            NearbyStop("A", "Metro Politechnika", 52.001, 21.0, 120.0),
        ],
        [
            NearbyStop("D", "Ratusz Arsenal", 52.1, 21.1, 180.0),
        ],
    ]
    mocked_fetch_active_service_ids.return_value = {"weekday"}
    mocked_fetch_reachable_connection_segments.side_effect = [
        [
            ConnectionSegment(
                trip_id="trip-1",
                route_id="route-1",
                route_short_name="116",
                trip_headsign="Centrum",
                from_stop_id="A",
                from_stop_name="Metro Politechnika",
                to_stop_id="B",
                to_stop_name="Swietokrzyska",
                departure_time="08:05:00",
                arrival_time="08:10:00",
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.01,
                to_lon=21.01,
            ),
        ],
        [
            ConnectionSegment(
                trip_id="trip-2",
                route_id="route-2",
                route_short_name="M1",
                trip_headsign="Mloci ny",
                from_stop_id="B",
                from_stop_name="Swietokrzyska",
                to_stop_id="D",
                to_stop_name="Ratusz Arsenal",
                departure_time="08:13:00",
                arrival_time="08:17:00",
                from_stop_sequence=10,
                to_stop_sequence=11,
                from_lat=52.01,
                from_lon=21.01,
                to_lat=52.02,
                to_lon=21.02,
            ),
        ],
        [],
    ]

    journeys = find_public_transport_connections(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.1,
        destination_lon=21.1,
        requested_departure_at=requested_departure,
    )

    assert len(journeys) == 1
    assert journeys[0].transfers == 1
    assert [leg.mode for leg in journeys[0].legs] == ["walk", "ride", "ride", "walk"]
    assert journeys[0].legs[1].route_name == "116"
    assert journeys[0].legs[2].route_name == "M1"
