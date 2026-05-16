from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import os
from statistics import fmean, median, stdev
from time import perf_counter
from typing import Callable

import pytest

from config.park_and_ride import ParkAndRideLocation
from database.queries import ConnectionSegment, NearbyStop
from services.car_routing import (
    GeoPoint,
    RoadEdge,
    find_car_route,
    haversine_distance_m,
)
from services.park_and_ride import find_park_and_ride_routes
import services.public_transport as public_transport


RUN_PERFORMANCE_TESTS = os.getenv("RUN_ROUTE_PERFORMANCE") == "1"


@dataclass(frozen=True)
class BenchmarkCase:
    origin: GeoPoint
    destination: GeoPoint
    departure_at: datetime


@dataclass(frozen=True)
class PerformanceStats:
    mode: str
    run_count: int
    mean_ms: float
    median_ms: float
    min_ms: float
    max_ms: float
    stdev_ms: float


@dataclass(frozen=True)
class SyntheticStop:
    stop_id: str
    stop_name: str
    point: GeoPoint


@dataclass(frozen=True)
class SyntheticTransitDataset:
    stops: tuple[SyntheticStop, ...]
    segments_by_trip: dict[str, list[ConnectionSegment]]

    def fetch_nearest_stops(
        self,
        engine,
        lat: float,
        lon: float,
        radius_m: int | None = None,
        limit: int | None = None,
    ) -> list[NearbyStop]:
        point = GeoPoint(lat, lon)
        radius_m = radius_m or 1_000
        limit = limit or 25
        nearest: list[NearbyStop] = []

        for stop in self.stops:
            distance_m = haversine_distance_m(point, stop.point)
            if distance_m <= radius_m:
                nearest.append(
                    NearbyStop(
                        stop_id=stop.stop_id,
                        stop_name=stop.stop_name,
                        lat=stop.point.lat,
                        lon=stop.point.lon,
                        distance_m=distance_m,
                    )
                )

        nearest.sort(key=lambda stop: stop.distance_m)
        return nearest[:limit]

    def fetch_active_service_ids(self, engine, service_date: date) -> set[str]:
        return {"weekday"}

    def fetch_reachable_connection_segments(
        self,
        engine,
        service_ids: set[str],
        ready_seconds_by_stop_id: dict[str, int],
        departure_time_to: str,
        limit: int | None = None,
    ) -> list[ConnectionSegment]:
        if not service_ids or not ready_seconds_by_stop_id:
            return []

        departure_limit = _gtfs_seconds(departure_time_to)
        matched_segments: list[ConnectionSegment] = []

        for trip_segments in self.segments_by_trip.values():
            boarding_sequence = None
            for segment in trip_segments:
                ready_seconds = ready_seconds_by_stop_id.get(segment.from_stop_id)
                if ready_seconds is None:
                    continue
                departure_seconds = _gtfs_seconds(segment.departure_time)
                if ready_seconds <= departure_seconds <= departure_limit:
                    boarding_sequence = segment.from_stop_sequence
                    break

            if boarding_sequence is None:
                continue

            matched_segments.extend(
                segment
                for segment in trip_segments
                if segment.from_stop_sequence >= boarding_sequence
                and _gtfs_seconds(segment.departure_time) <= departure_limit
            )

        matched_segments.sort(
            key=lambda segment: (
                _gtfs_seconds(segment.departure_time),
                _gtfs_seconds(segment.arrival_time),
                segment.trip_id,
                segment.from_stop_sequence,
            )
        )
        return matched_segments[: limit or len(matched_segments)]


def _gtfs_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _gtfs_seconds(value: str) -> int:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)


def _grid_point(row: int, col: int) -> GeoPoint:
    return GeoPoint(52.18 + row * 0.002, 20.90 + col * 0.002)


def _build_road_grid(size: int = 35) -> list[RoadEdge]:
    edges: list[RoadEdge] = []

    for row in range(size):
        for col in range(size):
            source = f"N{row:02d}_{col:02d}"
            source_point = _grid_point(row, col)

            if col + 1 < size:
                target = f"N{row:02d}_{col + 1:02d}"
                target_point = _grid_point(row, col + 1)
                edges.append(
                    RoadEdge(
                        edge_id=f"E-{source}-{target}",
                        source=source,
                        target=target,
                        source_point=source_point,
                        target_point=target_point,
                        length_m=haversine_distance_m(source_point, target_point),
                        max_speed_kmh=50 if row % 5 else 70,
                    )
                )

            if row + 1 < size:
                target = f"N{row + 1:02d}_{col:02d}"
                target_point = _grid_point(row + 1, col)
                edges.append(
                    RoadEdge(
                        edge_id=f"E-{source}-{target}",
                        source=source,
                        target=target,
                        source_point=source_point,
                        target_point=target_point,
                        length_m=haversine_distance_m(source_point, target_point),
                        max_speed_kmh=40 if col % 5 else 60,
                    )
                )

    return edges


def _build_transit_dataset(stop_count: int = 30) -> SyntheticTransitDataset:
    stops = tuple(
        SyntheticStop(
            stop_id=f"A{index:02d}",
            stop_name=f"Stop A{index:02d}",
            point=_grid_point(15, index + 1),
        )
        for index in range(stop_count)
    )
    segments_by_trip: dict[str, list[ConnectionSegment]] = {}

    for trip_index, start_minutes in enumerate(range(7 * 60 + 45, 10 * 60, 5)):
        trip_id = f"trip-{trip_index:03d}"
        segments: list[ConnectionSegment] = []
        trip_start_seconds = start_minutes * 60

        for sequence, (from_stop, to_stop) in enumerate(
            zip(stops, stops[1:]),
            start=1,
        ):
            departure_seconds = trip_start_seconds + (sequence - 1) * 120
            arrival_seconds = departure_seconds + 120
            segments.append(
                ConnectionSegment(
                    trip_id=trip_id,
                    route_id="route-A",
                    route_short_name="A",
                    trip_headsign="Synthetic East",
                    from_stop_id=from_stop.stop_id,
                    from_stop_name=from_stop.stop_name,
                    to_stop_id=to_stop.stop_id,
                    to_stop_name=to_stop.stop_name,
                    departure_time=_gtfs_time(departure_seconds),
                    arrival_time=_gtfs_time(arrival_seconds),
                    from_stop_sequence=sequence,
                    to_stop_sequence=sequence + 1,
                    from_lat=from_stop.point.lat,
                    from_lon=from_stop.point.lon,
                    to_lat=to_stop.point.lat,
                    to_lon=to_stop.point.lon,
                )
            )

        segments_by_trip[trip_id] = segments

    return SyntheticTransitDataset(stops=stops, segments_by_trip=segments_by_trip)


def _build_parkings(dataset: SyntheticTransitDataset) -> list[ParkAndRideLocation]:
    parking_indexes = (2, 6, 10, 14, 18)
    return [
        ParkAndRideLocation(
            parking_id=f"synthetic-pr-{index}",
            name=f"Synthetic P+R {index}",
            lat=dataset.stops[index].point.lat - 0.001,
            lon=dataset.stops[index].point.lon,
            metro_station=dataset.stops[index].stop_name,
            metro_line="A",
            metro_lat=dataset.stops[index].point.lat,
            metro_lon=dataset.stops[index].point.lon,
        )
        for index in parking_indexes
    ]


def _build_benchmark_cases() -> list[BenchmarkCase]:
    base_departure = datetime(2026, 5, 18, 8, 0, 0)
    stop_pairs = ((1, 25), (3, 28), (0, 22), (6, 29), (4, 19))

    return [
        BenchmarkCase(
            origin=GeoPoint(
                _grid_point(15, start + 1).lat + 0.0003,
                _grid_point(15, start + 1).lon,
            ),
            destination=GeoPoint(
                _grid_point(15, end + 1).lat + 0.0002,
                _grid_point(15, end + 1).lon,
            ),
            departure_at=base_departure + timedelta(minutes=index * 4),
        )
        for index, (start, end) in enumerate(stop_pairs)
    ]


def _install_synthetic_transit(
    monkeypatch: pytest.MonkeyPatch,
) -> SyntheticTransitDataset:
    dataset = _build_transit_dataset()
    monkeypatch.setattr(
        public_transport,
        "fetch_nearest_stops",
        dataset.fetch_nearest_stops,
    )
    monkeypatch.setattr(
        public_transport,
        "fetch_active_service_ids",
        dataset.fetch_active_service_ids,
    )
    monkeypatch.setattr(
        public_transport,
        "fetch_reachable_connection_segments",
        dataset.fetch_reachable_connection_segments,
    )
    monkeypatch.setattr(
        public_transport,
        "resolve_ride_path_positions",
        lambda **kwargs: (
            (kwargs["from_lat"], kwargs["from_lon"]),
            (kwargs["to_lat"], kwargs["to_lon"]),
        ),
    )
    return dataset


def _find_synthetic_public_transport(
    engine,
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    requested_departure_at: datetime,
    **kwargs,
):
    return public_transport.find_public_transport_connections(
        engine=engine,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        requested_departure_at=requested_departure_at,
        max_stop_distance_m=1_500,
        stop_limit=6,
        max_transfers=1,
        search_window_hours=2,
        segment_limit=4_000,
        transfer_buffer_seconds=90,
        limit=1,
        road_edges=kwargs.get("road_edges"),
        include_geometry=kwargs.get("include_geometry", True),
    )


def _measure(
    mode: str,
    cases: list[BenchmarkCase],
    repeats: int,
    runner: Callable[[BenchmarkCase], object],
) -> PerformanceStats:
    samples_ms: list[float] = []

    for case in cases:
        result = runner(case)
        assert result

    for _ in range(repeats):
        for case in cases:
            started_at = perf_counter()
            result = runner(case)
            samples_ms.append((perf_counter() - started_at) * 1_000)
            assert result

    return PerformanceStats(
        mode=mode,
        run_count=len(samples_ms),
        mean_ms=fmean(samples_ms),
        median_ms=median(samples_ms),
        min_ms=min(samples_ms),
        max_ms=max(samples_ms),
        stdev_ms=stdev(samples_ms) if len(samples_ms) > 1 else 0.0,
    )


def _format_stats(stats: list[PerformanceStats]) -> str:
    fastest = min(stats, key=lambda item: item.mean_ms)
    rows = [
        "",
        "Route search performance benchmark",
        (
            "mode                 runs   mean ms   median ms   min ms   "
            "max ms   stdev ms   vs fastest"
        ),
    ]

    for item in sorted(stats, key=lambda stat: stat.mean_ms):
        rows.append(
            f"{item.mode:<20} {item.run_count:>4} "
            f"{item.mean_ms:>9.2f} {item.median_ms:>11.2f} "
            f"{item.min_ms:>8.2f} {item.max_ms:>8.2f} "
            f"{item.stdev_ms:>10.2f} {item.mean_ms / fastest.mean_ms:>11.1f}x"
        )

    return "\n".join(rows)


@pytest.mark.performance
@pytest.mark.skipif(
    not RUN_PERFORMANCE_TESTS,
    reason="Set RUN_ROUTE_PERFORMANCE=1 to run route performance benchmarks.",
)
def test_route_search_performance_by_category(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _install_synthetic_transit(monkeypatch)
    road_edges = _build_road_grid()
    parkings = _build_parkings(dataset)
    cases = _build_benchmark_cases()
    repeats = int(os.getenv("ROUTE_PERF_REPEATS", "5"))

    stats = [
        _measure(
            mode="car",
            cases=cases,
            repeats=repeats,
            runner=lambda case: find_car_route(
                edges=road_edges,
                origin=case.origin,
                destination=case.destination,
                departure_at=case.departure_at,
            ),
        ),
        _measure(
            mode="public_transport",
            cases=cases,
            repeats=repeats,
            runner=lambda case: _find_synthetic_public_transport(
                engine=object(),
                origin_lat=case.origin.lat,
                origin_lon=case.origin.lon,
                destination_lat=case.destination.lat,
                destination_lon=case.destination.lon,
                requested_departure_at=case.departure_at,
                road_edges=road_edges,
            ),
        ),
        _measure(
            mode="park_and_ride",
            cases=cases,
            repeats=repeats,
            runner=lambda case: find_park_and_ride_routes(
                engine=object(),
                origin_lat=case.origin.lat,
                origin_lon=case.origin.lon,
                destination_lat=case.destination.lat,
                destination_lon=case.destination.lon,
                departure_at=case.departure_at,
                road_edges=road_edges,
                parkings=parkings,
                candidate_limit=len(parkings),
                limit=1,
                public_transport_finder=_find_synthetic_public_transport,
            ),
        ),
    ]

    print(_format_stats(stats))

    for item in stats:
        assert item.mean_ms > 0
