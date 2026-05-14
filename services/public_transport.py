from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import TYPE_CHECKING, Any

from config.settings import settings
from database.queries import (
    ConnectionSegment,
    DirectConnectionCandidate,
    NearbyStop,
    fetch_active_service_ids,
    fetch_direct_connection_candidates,
    fetch_nearest_stops,
    fetch_reachable_connection_segments,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any


@dataclass(frozen=True)
class JourneyLeg:
    mode: str
    from_name: str
    to_name: str
    departure_at: datetime
    arrival_at: datetime
    duration_minutes: int
    route_name: str | None = None
    trip_headsign: str | None = None


@dataclass(frozen=True)
class PublicTransportJourney:
    departure_at: datetime
    arrival_at: datetime
    total_minutes: int
    in_vehicle_minutes: int
    walking_minutes: int
    transfers: int
    legs: list[JourneyLeg]


@dataclass(frozen=True)
class SearchState:
    kind: str
    stop_id: str
    boardings: int
    trip_id: str | None = None


@dataclass(frozen=True)
class StateTransition:
    previous_state: SearchState | None
    segment: ConnectionSegment | None


def parse_gtfs_time(value: str) -> timedelta:
    hours_str, minutes_str, seconds_str = value.split(":")
    return timedelta(
        hours=int(hours_str),
        minutes=int(minutes_str),
        seconds=int(seconds_str),
    )


def format_gtfs_time(value: timedelta) -> str:
    total_seconds = int(value.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def estimate_walking_seconds(
    distance_m: float,
    walking_speed_mps: float | None = None,
) -> int:
    if distance_m <= 0:
        return 0

    speed_mps = walking_speed_mps or settings.public_transport_walking_speed_mps
    return ceil(distance_m / speed_mps)


def build_journey_from_candidate(
    requested_departure_at: datetime,
    origin_stop: NearbyStop,
    destination_stop: NearbyStop,
    candidate: DirectConnectionCandidate,
) -> PublicTransportJourney | None:
    request_offset = requested_departure_at - requested_departure_at.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    departure_offset = parse_gtfs_time(candidate.departure_time)
    arrival_offset = parse_gtfs_time(candidate.arrival_time)

    access_walk_seconds = estimate_walking_seconds(origin_stop.distance_m)
    egress_walk_seconds = estimate_walking_seconds(destination_stop.distance_m)

    if request_offset + timedelta(seconds=access_walk_seconds) > departure_offset:
        return None

    service_day_start = requested_departure_at.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    vehicle_departure_at = service_day_start + departure_offset
    vehicle_arrival_at = service_day_start + arrival_offset
    final_arrival_at = vehicle_arrival_at + timedelta(seconds=egress_walk_seconds)

    in_vehicle_minutes = ceil(
        (vehicle_arrival_at - vehicle_departure_at).total_seconds() / 60
    )
    walking_minutes = ceil((access_walk_seconds + egress_walk_seconds) / 60)
    total_minutes = ceil(
        (final_arrival_at - requested_departure_at).total_seconds() / 60
    )

    route_name = candidate.route_short_name or candidate.route_id

    return PublicTransportJourney(
        departure_at=requested_departure_at,
        arrival_at=final_arrival_at,
        total_minutes=total_minutes,
        in_vehicle_minutes=in_vehicle_minutes,
        walking_minutes=walking_minutes,
        transfers=0,
        legs=[
            JourneyLeg(
                mode="walk",
                from_name="origin",
                to_name=origin_stop.stop_name,
                departure_at=requested_departure_at,
                arrival_at=requested_departure_at
                + timedelta(seconds=access_walk_seconds),
                duration_minutes=ceil(access_walk_seconds / 60),
            ),
            JourneyLeg(
                mode="ride",
                from_name=origin_stop.stop_name,
                to_name=destination_stop.stop_name,
                departure_at=vehicle_departure_at,
                arrival_at=vehicle_arrival_at,
                duration_minutes=in_vehicle_minutes,
                route_name=route_name,
                trip_headsign=candidate.trip_headsign,
            ),
            JourneyLeg(
                mode="walk",
                from_name=destination_stop.stop_name,
                to_name="destination",
                departure_at=vehicle_arrival_at,
                arrival_at=final_arrival_at,
                duration_minutes=ceil(egress_walk_seconds / 60),
            ),
        ],
    )


def relax_state(
    best_arrivals: dict[SearchState, timedelta],
    predecessors: dict[SearchState, StateTransition],
    state: SearchState,
    arrival_time: timedelta,
    previous_state: SearchState | None,
    segment: ConnectionSegment | None,
) -> bool:
    best_known = best_arrivals.get(state)
    if best_known is not None and best_known <= arrival_time:
        return False

    best_arrivals[state] = arrival_time
    predecessors[state] = StateTransition(
        previous_state=previous_state,
        segment=segment,
    )
    return True


def reconstruct_segments(
    final_state: SearchState,
    predecessors: dict[SearchState, StateTransition],
) -> list[ConnectionSegment]:
    segments: list[ConnectionSegment] = []
    current_state = final_state

    while current_state in predecessors:
        transition = predecessors[current_state]
        if transition.segment is not None:
            segments.append(transition.segment)

        if transition.previous_state is None:
            break

        current_state = transition.previous_state

    segments.reverse()
    return segments


def timedelta_to_seconds(value: timedelta) -> int:
    return int(value.total_seconds())


def process_segments_for_boarding_round(
    segments: list[ConnectionSegment],
    boardings: int,
    best_arrivals: dict[SearchState, timedelta],
    predecessors: dict[SearchState, StateTransition],
    transfer_buffer_seconds: int,
) -> None:
    for segment in segments:
        departure_offset = parse_gtfs_time(segment.departure_time)
        arrival_offset = parse_gtfs_time(segment.arrival_time)

        offboard_state = SearchState(
            kind="offboard",
            stop_id=segment.from_stop_id,
            boardings=boardings - 1,
        )
        if offboard_state in best_arrivals:
            ready_to_board = best_arrivals[offboard_state] + timedelta(
                seconds=transfer_buffer_seconds if boardings > 1 else 0
            )
            if ready_to_board <= departure_offset:
                onboard_state = SearchState(
                    kind="onboard",
                    stop_id=segment.to_stop_id,
                    boardings=boardings,
                    trip_id=segment.trip_id,
                )
                if relax_state(
                    best_arrivals=best_arrivals,
                    predecessors=predecessors,
                    state=onboard_state,
                    arrival_time=arrival_offset,
                    previous_state=offboard_state,
                    segment=segment,
                ):
                    relax_state(
                        best_arrivals=best_arrivals,
                        predecessors=predecessors,
                        state=SearchState(
                            kind="offboard",
                            stop_id=segment.to_stop_id,
                            boardings=boardings,
                        ),
                        arrival_time=arrival_offset,
                        previous_state=onboard_state,
                        segment=None,
                    )

        ongoing_ride_state = SearchState(
            kind="onboard",
            stop_id=segment.from_stop_id,
            boardings=boardings,
            trip_id=segment.trip_id,
        )
        if (
            ongoing_ride_state in best_arrivals
            and best_arrivals[ongoing_ride_state] <= departure_offset
        ):
            onboard_state = SearchState(
                kind="onboard",
                stop_id=segment.to_stop_id,
                boardings=boardings,
                trip_id=segment.trip_id,
            )
            if relax_state(
                best_arrivals=best_arrivals,
                predecessors=predecessors,
                state=onboard_state,
                arrival_time=arrival_offset,
                previous_state=ongoing_ride_state,
                segment=segment,
            ):
                relax_state(
                    best_arrivals=best_arrivals,
                    predecessors=predecessors,
                    state=SearchState(
                        kind="offboard",
                        stop_id=segment.to_stop_id,
                        boardings=boardings,
                    ),
                    arrival_time=arrival_offset,
                    previous_state=onboard_state,
                    segment=None,
                )


def compress_segments_into_rides(
    segments: list[ConnectionSegment],
) -> list[ConnectionSegment]:
    if not segments:
        return []

    rides: list[ConnectionSegment] = [segments[0]]

    for segment in segments[1:]:
        last_ride = rides[-1]
        if (
            segment.trip_id == last_ride.trip_id
            and segment.from_stop_id == last_ride.to_stop_id
            and segment.from_stop_sequence >= last_ride.to_stop_sequence
        ):
            rides[-1] = ConnectionSegment(
                trip_id=last_ride.trip_id,
                route_id=last_ride.route_id,
                route_short_name=last_ride.route_short_name,
                trip_headsign=last_ride.trip_headsign,
                from_stop_id=last_ride.from_stop_id,
                from_stop_name=last_ride.from_stop_name,
                to_stop_id=segment.to_stop_id,
                to_stop_name=segment.to_stop_name,
                departure_time=last_ride.departure_time,
                arrival_time=segment.arrival_time,
                from_stop_sequence=last_ride.from_stop_sequence,
                to_stop_sequence=segment.to_stop_sequence,
            )
            continue

        rides.append(segment)

    return rides


def build_journey_from_segments(
    requested_departure_at: datetime,
    origin_stop: NearbyStop,
    destination_stop: NearbyStop,
    segments: list[ConnectionSegment],
) -> PublicTransportJourney | None:
    if not segments:
        return None

    ride_segments = compress_segments_into_rides(segments)
    service_day_start = requested_departure_at.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    access_walk_seconds = estimate_walking_seconds(origin_stop.distance_m)
    egress_walk_seconds = estimate_walking_seconds(destination_stop.distance_m)
    first_departure_offset = parse_gtfs_time(ride_segments[0].departure_time)

    if (
        requested_departure_at
        - service_day_start
        + timedelta(seconds=access_walk_seconds)
        > first_departure_offset
    ):
        return None

    legs: list[JourneyLeg] = [
        JourneyLeg(
            mode="walk",
            from_name="origin",
            to_name=origin_stop.stop_name,
            departure_at=requested_departure_at,
            arrival_at=requested_departure_at + timedelta(seconds=access_walk_seconds),
            duration_minutes=ceil(access_walk_seconds / 60),
        )
    ]

    in_vehicle_minutes = 0

    for ride in ride_segments:
        departure_at = service_day_start + parse_gtfs_time(ride.departure_time)
        arrival_at = service_day_start + parse_gtfs_time(ride.arrival_time)
        duration_minutes = ceil((arrival_at - departure_at).total_seconds() / 60)
        in_vehicle_minutes += duration_minutes

        legs.append(
            JourneyLeg(
                mode="ride",
                from_name=ride.from_stop_name,
                to_name=ride.to_stop_name,
                departure_at=departure_at,
                arrival_at=arrival_at,
                duration_minutes=duration_minutes,
                route_name=ride.route_short_name or ride.route_id,
                trip_headsign=ride.trip_headsign,
            )
        )

    final_vehicle_arrival_at = service_day_start + parse_gtfs_time(
        ride_segments[-1].arrival_time
    )
    final_arrival_at = final_vehicle_arrival_at + timedelta(seconds=egress_walk_seconds)

    legs.append(
        JourneyLeg(
            mode="walk",
            from_name=destination_stop.stop_name,
            to_name="destination",
            departure_at=final_vehicle_arrival_at,
            arrival_at=final_arrival_at,
            duration_minutes=ceil(egress_walk_seconds / 60),
        )
    )

    walking_minutes = ceil((access_walk_seconds + egress_walk_seconds) / 60)
    total_minutes = ceil(
        (final_arrival_at - requested_departure_at).total_seconds() / 60
    )

    return PublicTransportJourney(
        departure_at=requested_departure_at,
        arrival_at=final_arrival_at,
        total_minutes=total_minutes,
        in_vehicle_minutes=in_vehicle_minutes,
        walking_minutes=walking_minutes,
        transfers=max(len(ride_segments) - 1, 0),
        legs=legs,
    )


def find_public_transport_connections(
    engine: Engine,
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    requested_departure_at: datetime,
    max_stop_distance_m: int | None = None,
    stop_limit: int | None = None,
    max_transfers: int | None = None,
    search_window_hours: int | None = None,
    segment_limit: int | None = None,
    transfer_buffer_seconds: int | None = None,
    limit: int | None = None,
) -> list[PublicTransportJourney]:
    max_stop_distance_m = (
        max_stop_distance_m or settings.public_transport_max_stop_distance_m
    )
    stop_limit = stop_limit or settings.public_transport_stop_limit
    max_transfers = max_transfers or settings.public_transport_max_transfers
    search_window_hours = (
        search_window_hours or settings.public_transport_search_window_hours
    )
    segment_limit = segment_limit or settings.public_transport_segment_limit
    transfer_buffer_seconds = (
        transfer_buffer_seconds or settings.public_transport_transfer_buffer_seconds
    )
    limit = limit or settings.public_transport_result_limit

    origin_stops = fetch_nearest_stops(
        engine,
        lat=origin_lat,
        lon=origin_lon,
        radius_m=max_stop_distance_m,
        limit=stop_limit,
    )
    destination_stops = fetch_nearest_stops(
        engine,
        lat=destination_lat,
        lon=destination_lon,
        radius_m=max_stop_distance_m,
        limit=stop_limit,
    )

    if not origin_stops or not destination_stops:
        return []

    service_ids = fetch_active_service_ids(engine, requested_departure_at.date())
    if not service_ids:
        return []

    origin_stop_by_id = {stop.stop_id: stop for stop in origin_stops}
    destination_stop_by_id = {stop.stop_id: stop for stop in destination_stops}
    service_day_start = requested_departure_at.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    request_offset = requested_departure_at - service_day_start
    origin_ready_offsets = {
        stop.stop_id: request_offset
        + timedelta(seconds=estimate_walking_seconds(stop.distance_m))
        for stop in origin_stops
    }
    earliest_origin_ready = min(origin_ready_offsets.values())

    max_boardings = max_transfers + 1
    search_until_offset = earliest_origin_ready + timedelta(hours=search_window_hours)
    best_arrivals: dict[SearchState, timedelta] = {}
    predecessors: dict[SearchState, StateTransition] = {}

    for origin_stop in origin_stops:
        relax_state(
            best_arrivals=best_arrivals,
            predecessors=predecessors,
            state=SearchState(
                kind="offboard",
                stop_id=origin_stop.stop_id,
                boardings=0,
            ),
            arrival_time=origin_ready_offsets[origin_stop.stop_id],
            previous_state=None,
            segment=None,
        )

    for boardings in range(1, max_boardings + 1):
        ready_seconds_by_stop_id = {
            state.stop_id: timedelta_to_seconds(arrival_time)
            for state, arrival_time in best_arrivals.items()
            if state.kind == "offboard"
            and state.boardings == boardings - 1
            and arrival_time <= search_until_offset
        }
        if not ready_seconds_by_stop_id:
            break

        segments = fetch_reachable_connection_segments(
            engine,
            service_ids=service_ids,
            ready_seconds_by_stop_id=ready_seconds_by_stop_id,
            departure_time_to=format_gtfs_time(search_until_offset),
            limit=segment_limit,
        )
        if not segments:
            continue

        process_segments_for_boarding_round(
            segments=segments,
            boardings=boardings,
            best_arrivals=best_arrivals,
            predecessors=predecessors,
            transfer_buffer_seconds=transfer_buffer_seconds,
        )

    candidate_journeys: list[PublicTransportJourney] = []
    seen_signatures: set[tuple] = set()

    for destination_stop in destination_stops:
        for boardings in range(1, max_boardings + 1):
            final_state = SearchState(
                kind="offboard",
                stop_id=destination_stop.stop_id,
                boardings=boardings,
            )
            if final_state not in best_arrivals:
                continue

            ride_segments = reconstruct_segments(final_state, predecessors)
            if not ride_segments:
                continue

            first_origin_stop_id = ride_segments[0].from_stop_id
            if first_origin_stop_id not in origin_stop_by_id:
                continue

            journey = build_journey_from_segments(
                requested_departure_at=requested_departure_at,
                origin_stop=origin_stop_by_id[first_origin_stop_id],
                destination_stop=destination_stop,
                segments=ride_segments,
            )
            if journey is None:
                continue

            signature = tuple(
                (
                    leg.mode,
                    leg.from_name,
                    leg.to_name,
                    leg.departure_at,
                    leg.arrival_at,
                    leg.route_name,
                )
                for leg in journey.legs
            )
            if signature in seen_signatures:
                continue

            seen_signatures.add(signature)
            candidate_journeys.append(journey)

    candidate_journeys.sort(
        key=lambda journey: (
            journey.arrival_at,
            journey.transfers,
            journey.total_minutes,
        )
    )
    return candidate_journeys[:limit]
