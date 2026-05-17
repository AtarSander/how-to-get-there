from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from database.queries import ConnectionSegment, DirectConnectionCandidate, NearbyStop
from services.car_routing import GeoPoint
from services.public_transport import (
    attach_gtfs_seconds_to_display_day,
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


def test_attach_gtfs_seconds_wraps_extended_hours_onto_display_day() -> None:
    display_day_start = datetime(2026, 5, 19, 0, 0, 0)
    attached = attach_gtfs_seconds_to_display_day(
        display_day_start,
        24 * 3600 + 41 * 60,
    )
    assert attached == datetime(2026, 5, 19, 0, 41, 0)


def test_build_journey_total_minutes_ignores_extra_24h_in_gtfs_times() -> None:
    requested = datetime(2026, 5, 19, 0, 22, 0)
    segment = ConnectionSegment(
        trip_id="trip-1",
        route_id="route-1",
        route_short_name="N62",
        trip_headsign="Test",
        from_stop_id="a",
        from_stop_name="Start",
        to_stop_id="b",
        to_stop_name="End",
        departure_time="24:30:00",
        arrival_time="24:41:00",
        from_lat=52.23,
        from_lon=21.01,
        to_lat=52.25,
        to_lon=21.03,
        from_stop_sequence=1,
        to_stop_sequence=2,
        from_shape_dist_traveled=None,
        to_shape_dist_traveled=None,
    )

    with patch(
        "services.public_transport.build_walk_leg",
        side_effect=lambda **kwargs: type(
            "Leg",
            (),
            {
                "departure_at": kwargs["departure_at"],
                "arrival_at": kwargs["departure_at"] + timedelta(minutes=6),
                "duration_minutes": 6,
            },
        )(),
    ):
        journey = build_journey_from_segments(
            requested_departure_at=requested,
            origin_point=GeoPoint(52.229, 21.004),
            destination_point=GeoPoint(52.272, 21.045),
            origin_stop=NearbyStop("a", "Start", 52.229, 21.004, 100),
            destination_stop=NearbyStop("b", "End", 52.272, 21.045, 80),
            segments=[segment],
            include_geometry=False,
        )

    assert journey is not None
    assert journey.total_minutes < 60


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


@patch("services.public_transport.resolve_ride_path_positions", return_value=None)
@patch("services.public_transport.fetch_reachable_connection_segments")
@patch("services.public_transport.fetch_active_service_ids")
@patch("services.public_transport.fetch_nearest_stops")
def test_find_public_transport_connections_ranks_by_final_arrival_after_walk(
    mocked_fetch_nearest_stops: Mock,
    mocked_fetch_active_service_ids: Mock,
    mocked_fetch_reachable_connection_segments: Mock,
    _mocked_resolve_ride_path_positions: Mock,
) -> None:
    requested_departure = datetime(2026, 5, 2, 8, 0, 0)

    mocked_fetch_nearest_stops.side_effect = [
        [
            NearbyStop("A", "Origin Stop", 52.0, 21.0, 0.0),
        ],
        [
            NearbyStop("FAR", "Far Destination", 52.02, 21.02, 2_600.0),
            NearbyStop("NEAR", "Near Destination", 52.0, 21.0101, 10.0),
        ],
    ]
    mocked_fetch_active_service_ids.return_value = {"weekday"}
    mocked_fetch_reachable_connection_segments.side_effect = [
        [
            ConnectionSegment(
                trip_id="trip-far",
                route_id="route-far",
                route_short_name="F",
                trip_headsign="Far",
                from_stop_id="A",
                from_stop_name="Origin Stop",
                to_stop_id="FAR",
                to_stop_name="Far Destination",
                departure_time="08:02:00",
                arrival_time="08:10:00",
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.02,
                to_lon=21.02,
            ),
            ConnectionSegment(
                trip_id="trip-near",
                route_id="route-near",
                route_short_name="N",
                trip_headsign="Near",
                from_stop_id="A",
                from_stop_name="Origin Stop",
                to_stop_id="NEAR",
                to_stop_name="Near Destination",
                departure_time="08:03:00",
                arrival_time="08:13:00",
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.0,
                to_lon=21.0101,
            ),
        ],
        [],
        [],
    ]

    journeys = find_public_transport_connections(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.0,
        destination_lon=21.01,
        requested_departure_at=requested_departure,
        limit=1,
    )

    assert len(journeys) == 1
    assert journeys[0].legs[1].to_name == "Near Destination"
    _mocked_resolve_ride_path_positions.assert_called_once()


@patch("services.public_transport.resolve_ride_path_positions", return_value=None)
@patch("services.public_transport.fetch_reachable_connection_segments")
@patch("services.public_transport.fetch_active_service_ids")
@patch("services.public_transport.fetch_nearest_stops")
def test_find_public_transport_connections_can_finish_with_walk_from_reached_stop(
    mocked_fetch_nearest_stops: Mock,
    mocked_fetch_active_service_ids: Mock,
    mocked_fetch_reachable_connection_segments: Mock,
    _mocked_resolve_ride_path_positions: Mock,
) -> None:
    requested_departure = datetime(2026, 5, 2, 8, 0, 0)

    mocked_fetch_nearest_stops.side_effect = [
        [
            NearbyStop("A", "Origin Stop", 52.0, 21.0, 0.0),
        ],
        [
            NearbyStop("D", "Formal Destination Stop", 52.0, 21.01, 0.0),
        ],
    ]
    mocked_fetch_active_service_ids.return_value = {"weekday"}
    mocked_fetch_reachable_connection_segments.side_effect = [
        [
            ConnectionSegment(
                trip_id="trip-walkable",
                route_id="route-walkable",
                route_short_name="W",
                trip_headsign="Walkable",
                from_stop_id="A",
                from_stop_name="Origin Stop",
                to_stop_id="C",
                to_stop_name="Walkable Stop",
                departure_time="08:02:00",
                arrival_time="08:10:00",
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.0,
                to_lon=21.009,
            ),
            ConnectionSegment(
                trip_id="trip-formal",
                route_id="route-formal",
                route_short_name="F",
                trip_headsign="Formal",
                from_stop_id="A",
                from_stop_name="Origin Stop",
                to_stop_id="D",
                to_stop_name="Formal Destination Stop",
                departure_time="08:02:00",
                arrival_time="08:25:00",
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.0,
                to_lon=21.01,
            ),
        ],
        [],
    ]

    journeys = find_public_transport_connections(
        engine=object(),
        origin_lat=52.0,
        origin_lon=21.0,
        destination_lat=52.0,
        destination_lon=21.01,
        requested_departure_at=requested_departure,
        limit=1,
    )

    assert len(journeys) == 1
    assert journeys[0].legs[1].to_name == "Walkable Stop"
    assert journeys[0].legs[-1].from_name == "Walkable Stop"
    assert journeys[0].arrival_at < datetime(2026, 5, 2, 8, 25, 0)
    _mocked_resolve_ride_path_positions.assert_called_once()


@patch("services.public_transport.resolve_ride_path_positions")
def test_build_journey_from_segments_can_skip_ride_geometry(
    mocked_resolve_ride_path_positions: Mock,
) -> None:
    requested_departure = datetime(2026, 5, 2, 8, 0, 0)

    journey = build_journey_from_segments(
        requested_departure_at=requested_departure,
        origin_point=GeoPoint(52.0, 21.0),
        destination_point=GeoPoint(52.01, 21.01),
        origin_stop=NearbyStop("A", "Start", 52.0, 21.0, 0.0),
        destination_stop=NearbyStop("B", "End", 52.01, 21.01, 0.0),
        segments=[
            ConnectionSegment(
                trip_id="trip-1",
                route_id="route-1",
                route_short_name="116",
                trip_headsign="Centrum",
                from_stop_id="A",
                from_stop_name="Start",
                to_stop_id="B",
                to_stop_name="End",
                departure_time="08:05:00",
                arrival_time="08:10:00",
                from_stop_sequence=1,
                to_stop_sequence=2,
                from_lat=52.0,
                from_lon=21.0,
                to_lat=52.01,
                to_lon=21.01,
            )
        ],
        include_geometry=False,
    )

    assert journey is not None
    assert journey.legs[1].path_positions is None
    mocked_resolve_ride_path_positions.assert_not_called()
