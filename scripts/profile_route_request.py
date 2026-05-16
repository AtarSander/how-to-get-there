from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean
from time import perf_counter
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import event
from sqlalchemy.engine import Engine

from api.serialization import serialize_route_comparison
from config.settings import settings
from database.connection import get_engine
from services.car_routing import GeoPoint, estimate_direct_car_route, find_car_route
from services.park_and_ride import find_park_and_ride_routes
import services.park_and_ride as park_and_ride_module
from services.public_transport import find_public_transport_connections
from services.route_comparison import (
    RouteComparison,
    build_unavailable_option,
    load_road_edges_from_database,
    option_from_car_route,
    option_from_park_and_ride,
    option_from_public_transport,
)
from services.traffic_profiles import load_zdm_apr_traffic_profile


DEFAULT_CASES = {
    "centrum_to_mokotow": (52.2297, 21.0122, 52.1934, 21.0346),
    "wola_to_praga": (52.2309, 20.9862, 52.2551, 21.0354),
    "praga_to_wola": (52.2551, 21.0354, 52.2309, 20.9862),
    "mlociny_to_mokotow": (52.31, 20.93, 52.1934, 21.0346),
}

TOP_LEVEL_COMPONENTS = (
    "road_edges_load",
    "traffic_profile_load",
    "car_route",
    "public_transport",
    "park_and_ride",
    "option_sort",
    "serialization",
)

NESTED_COMPONENTS = (
    "park_and_ride.car_route",
    "park_and_ride.direct_car_estimate",
    "park_and_ride.walk_to_metro",
    "park_and_ride.public_transport",
)


@dataclass(frozen=True)
class RouteCase:
    name: str
    origin_lat: float
    origin_lon: float
    destination_lat: float
    destination_lon: float


class Profiler:
    def __init__(self) -> None:
        self.timings: dict[str, list[float]] = defaultdict(list)
        self.sql_timings: dict[str, list[float]] = defaultdict(list)
        self.stack: list[str] = []
        self._before_cursor_execute = None
        self._after_cursor_execute = None

    @contextmanager
    def time(self, label: str) -> Iterator[None]:
        self.stack.append(label)
        started_at = perf_counter()
        try:
            yield
        finally:
            self.timings[label].append(perf_counter() - started_at)
            self.stack.pop()

    def install_sql_hooks(self, engine: Engine) -> None:
        def before_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ) -> None:
            context._spdb_profile_started_at = perf_counter()

        def after_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ) -> None:
            started_at = getattr(context, "_spdb_profile_started_at", None)
            if started_at is None:
                return

            label = self.stack[-1] if self.stack else "unscoped"
            self.sql_timings[label].append(perf_counter() - started_at)

        self._before_cursor_execute = before_cursor_execute
        self._after_cursor_execute = after_cursor_execute
        event.listen(engine, "before_cursor_execute", before_cursor_execute)
        event.listen(engine, "after_cursor_execute", after_cursor_execute)

    def remove_sql_hooks(self, engine: Engine) -> None:
        if self._before_cursor_execute is not None:
            event.remove(
                engine,
                "before_cursor_execute",
                self._before_cursor_execute,
            )
        if self._after_cursor_execute is not None:
            event.remove(
                engine,
                "after_cursor_execute",
                self._after_cursor_execute,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile a real /api/routes/compare backend route search.",
    )
    parser.add_argument(
        "--case",
        choices=sorted(DEFAULT_CASES),
        action="append",
        help="Named route case to run. Can be repeated. Defaults to all cases.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="How many times to run each case.",
    )
    parser.add_argument(
        "--departure-at",
        default=None,
        help=(
            "ISO datetime used for every route search. Defaults to current local "
            "time, matching the API default."
        ),
    )
    return parser.parse_args()


def load_profile_cases(case_names: list[str] | None) -> list[RouteCase]:
    selected_names = case_names or list(DEFAULT_CASES)
    return [
        RouteCase(
            name=name,
            origin_lat=coords[0],
            origin_lon=coords[1],
            destination_lat=coords[2],
            destination_lon=coords[3],
        )
        for name in selected_names
        for coords in [DEFAULT_CASES[name]]
    ]


def timed_park_and_ride(
    profiler: Profiler,
    **kwargs: Any,
):
    original_find_car_route = park_and_ride_module.find_car_route
    original_estimate_direct_car_route = park_and_ride_module.estimate_direct_car_route
    original_build_walk_to_metro_leg = park_and_ride_module.build_walk_to_metro_leg

    def timed_find_car_route(*args: Any, **inner_kwargs: Any):
        with profiler.time("park_and_ride.car_route"):
            return original_find_car_route(*args, **inner_kwargs)

    def timed_estimate_direct_car_route(*args: Any, **inner_kwargs: Any):
        with profiler.time("park_and_ride.direct_car_estimate"):
            return original_estimate_direct_car_route(*args, **inner_kwargs)

    def timed_build_walk_to_metro_leg(*args: Any, **inner_kwargs: Any):
        with profiler.time("park_and_ride.walk_to_metro"):
            return original_build_walk_to_metro_leg(*args, **inner_kwargs)

    def timed_public_transport(*args: Any, **inner_kwargs: Any):
        with profiler.time("park_and_ride.public_transport"):
            return find_public_transport_connections(*args, **inner_kwargs)

    park_and_ride_module.find_car_route = timed_find_car_route
    park_and_ride_module.estimate_direct_car_route = timed_estimate_direct_car_route
    park_and_ride_module.build_walk_to_metro_leg = timed_build_walk_to_metro_leg

    try:
        return find_park_and_ride_routes(
            **kwargs,
            public_transport_finder=timed_public_transport,
        )
    finally:
        park_and_ride_module.find_car_route = original_find_car_route
        park_and_ride_module.estimate_direct_car_route = original_estimate_direct_car_route
        park_and_ride_module.build_walk_to_metro_leg = original_build_walk_to_metro_leg


def profile_route_case(
    engine: Engine,
    profiler: Profiler,
    route_case: RouteCase,
    departure_at: datetime,
) -> tuple[RouteComparison, dict[str, Any]]:
    metadata: dict[str, Any] = {}
    origin = GeoPoint(route_case.origin_lat, route_case.origin_lon)
    destination = GeoPoint(route_case.destination_lat, route_case.destination_lon)
    options = []

    with profiler.time("backend_total"):
        with profiler.time("road_edges_load"):
            resolved_road_edges = None
            if settings.car_use_database_edges:
                try:
                    resolved_road_edges = load_road_edges_from_database(engine)
                except Exception as exc:
                    metadata["road_edges_error"] = str(exc)

            metadata["road_edge_count"] = (
                len(resolved_road_edges) if resolved_road_edges is not None else 0
            )

        with profiler.time("traffic_profile_load"):
            traffic_profile = load_zdm_apr_traffic_profile(engine)
            metadata["traffic_profile_loaded"] = traffic_profile is not None

        with profiler.time("car_route"):
            car_route = (
                find_car_route(
                    resolved_road_edges,
                    origin,
                    destination,
                    departure_at,
                    traffic_profile,
                )
                if resolved_road_edges
                else estimate_direct_car_route(
                    origin=origin,
                    destination=destination,
                    departure_at=departure_at,
                    traffic_profile=traffic_profile,
                )
            )
        if car_route is None:
            options.append(
                build_unavailable_option(
                    mode="car",
                    label="Samochod",
                    departure_at=departure_at,
                    reason="Nie znaleziono trasy samochodowej.",
                )
            )
        else:
            options.append(option_from_car_route(car_route, departure_at))

        with profiler.time("public_transport"):
            public_transport_journeys = find_public_transport_connections(
                engine,
                route_case.origin_lat,
                route_case.origin_lon,
                route_case.destination_lat,
                route_case.destination_lon,
                departure_at,
                limit=1,
                road_edges=resolved_road_edges,
            )
        metadata["public_transport_result_count"] = len(public_transport_journeys)
        if public_transport_journeys:
            options.append(
                option_from_public_transport(
                    public_transport_journeys[0],
                    departure_at,
                )
            )
        else:
            options.append(
                build_unavailable_option(
                    mode="public_transport",
                    label="Komunikacja miejska",
                    departure_at=departure_at,
                    reason="Nie znaleziono polaczenia komunikacja miejska.",
                )
            )

        with profiler.time("park_and_ride"):
            park_and_ride_routes = timed_park_and_ride(
                profiler=profiler,
                engine=engine,
                origin_lat=route_case.origin_lat,
                origin_lon=route_case.origin_lon,
                destination_lat=route_case.destination_lat,
                destination_lon=route_case.destination_lon,
                departure_at=departure_at,
                road_edges=resolved_road_edges,
                traffic_profile=traffic_profile,
            )
        metadata["park_and_ride_result_count"] = len(park_and_ride_routes)
        if park_and_ride_routes:
            options.append(
                option_from_park_and_ride(park_and_ride_routes[0], departure_at)
            )
        else:
            options.append(
                build_unavailable_option(
                    mode="park_and_ride",
                    label="Park & Ride",
                    departure_at=departure_at,
                    reason="Nie znaleziono trasy Park & Ride.",
                )
            )

        with profiler.time("option_sort"):
            options.sort(
                key=lambda option: (
                    not option.available,
                    option.total_minutes
                    if option.total_minutes is not None
                    else 10**9,
                    option.transfers if option.transfers is not None else 10**9,
                )
            )
            comparison = RouteComparison(
                origin=origin,
                destination=destination,
                departure_at=departure_at,
                options=options,
            )

        with profiler.time("serialization"):
            serialized = serialize_route_comparison(comparison)

        metadata["serialized_option_count"] = len(serialized["options"])
        metadata["best_option"] = (
            serialized["best_option"]["mode"]
            if serialized.get("best_option") is not None
            else None
        )

    return comparison, metadata


def format_seconds(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:8.3f}"


def print_case_report(
    route_case: RouteCase,
    profiler: Profiler,
    metadata: dict[str, Any],
) -> None:
    total = sum(profiler.timings.get("backend_total", []))
    print(f"\nCase: {route_case.name}")
    print(
        "component                         calls   total s    avg ms   share   sql calls   sql s"
    )

    for component in TOP_LEVEL_COMPONENTS:
        values = profiler.timings.get(component, [])
        sql_values = profiler.sql_timings.get(component, [])
        total_seconds = sum(values)
        avg_ms = fmean(values) * 1000 if values else None
        share = (total_seconds / total * 100) if total else 0
        print(
            f"{component:<33} {len(values):>5} "
            f"{format_seconds(total_seconds)} "
            f"{avg_ms if avg_ms is not None else 0:8.1f} "
            f"{share:6.1f}% "
            f"{len(sql_values):>10} {format_seconds(sum(sql_values))}"
        )

    print("nested inside park_and_ride")
    for component in NESTED_COMPONENTS:
        values = profiler.timings.get(component, [])
        sql_values = profiler.sql_timings.get(component, [])
        if not values and not sql_values:
            continue
        print(
            f"{component:<33} {len(values):>5} "
            f"{format_seconds(sum(values))} "
            f"{(fmean(values) * 1000) if values else 0:8.1f} "
            f"{'':>7} "
            f"{len(sql_values):>10} {format_seconds(sum(sql_values))}"
        )

    print(
        "metadata: "
        f"road_edges={metadata.get('road_edge_count')}, "
        f"pt_results={metadata.get('public_transport_result_count')}, "
        f"pr_results={metadata.get('park_and_ride_result_count')}, "
        f"traffic_profile={metadata.get('traffic_profile_loaded')}, "
        f"best={metadata.get('best_option')}"
    )
    if "road_edges_error" in metadata:
        print(f"road_edges_error: {metadata['road_edges_error']}")
    print(f"backend_total: {sum(profiler.timings['backend_total']):.3f} s")


def main() -> None:
    args = parse_args()
    departure_at = (
        datetime.fromisoformat(args.departure_at)
        if args.departure_at is not None
        else datetime.now().replace(microsecond=0)
    )
    cases = load_profile_cases(args.case)
    engine = get_engine()

    for route_case in cases:
        for run_index in range(1, args.repeat + 1):
            profiler = Profiler()
            profiler.install_sql_hooks(engine)
            try:
                _comparison, metadata = profile_route_case(
                    engine=engine,
                    profiler=profiler,
                    route_case=route_case,
                    departure_at=departure_at,
                )
            finally:
                profiler.remove_sql_hooks(engine)
            if args.repeat > 1:
                print(f"\nRun {run_index}/{args.repeat}")
            print_case_report(route_case, profiler, metadata)


if __name__ == "__main__":
    main()
