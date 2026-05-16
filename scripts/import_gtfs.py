from __future__ import annotations

import sys
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import Engine, bindparam, text

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.gtfs import GTFS_COLUMNS, GTFS_DTYPES, GTFS_TABLES
from config.logging import configure_logging
from config.metro import (
    METRO_AGENCY_ID,
    METRO_AGENCY_LANG,
    METRO_AGENCY_NAME,
    METRO_AGENCY_TIMEZONE,
    METRO_AGENCY_URL,
    METRO_AVERAGE_SPEED_MPS,
    METRO_DWELL_SECONDS,
    METRO_FREQUENCY_WINDOWS,
    METRO_LINES,
    METRO_MAX_SEGMENT_SECONDS,
    METRO_MIN_SEGMENT_SECONDS,
    METRO_SERVICE_ID,
    MetroStation,
)
from config.settings import settings
from database.connection import get_engine
from services.car_routing import GeoPoint, haversine_distance_m


@dataclass(frozen=True)
class GtfsImportScope:
    service_ids: set[str]
    trip_ids: set[str]
    route_ids: set[str]
    shape_ids: set[str]
    service_dates: list[date]


def drop_gtfs_tables(engine: Engine) -> None:
    logger.info("Dropping existing GTFS tables.")

    with engine.begin() as conn:
        for table_name in reversed(list(GTFS_TABLES.values())):
            logger.info("Dropping table {}.", table_name)
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;'))

    logger.success("Dropped existing GTFS tables.")


def read_existing_columns(path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def get_available_usecols(file_name: str, path) -> list[str]:
    wanted_columns = GTFS_COLUMNS[file_name]
    existing_columns = set(read_existing_columns(path))

    available_columns = [
        column for column in wanted_columns if column in existing_columns
    ]

    missing_columns = set(wanted_columns) - set(available_columns)

    if missing_columns:
        logger.warning(
            "File {} is missing optional/expected columns: {}.",
            file_name,
            sorted(missing_columns),
        )

    if not available_columns:
        raise RuntimeError(f"No usable columns found in {path}")

    return available_columns


def get_weekday_column(service_date: date) -> str:
    return {
        0: "monday",
        1: "tuesday",
        2: "wednesday",
        3: "thursday",
        4: "friday",
        5: "saturday",
        6: "sunday",
    }[service_date.weekday()]


def gtfs_time_to_seconds(values: pd.Series) -> pd.Series:
    parts = values.astype(str).str.split(":", expand=True).astype(int)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def find_import_dates(calendar_df: pd.DataFrame) -> list[date]:
    configured_start = settings.gtfs_import_start_date

    if configured_start is not None:
        start_date = configured_start
    else:
        today = date.today()
        calendar_start = pd.to_datetime(
            calendar_df["start_date"].astype(str),
            format="%Y%m%d",
        ).dt.date.min()
        calendar_end = pd.to_datetime(
            calendar_df["end_date"].astype(str),
            format="%Y%m%d",
        ).dt.date.max()

        if today < calendar_start:
            start_date = calendar_start
        elif today > calendar_end:
            start_date = calendar_start
        else:
            start_date = today

    return [
        start_date + timedelta(days=offset)
        for offset in range(max(settings.gtfs_import_days, 1))
    ]


def get_active_service_ids_for_dates(
    calendar_df: pd.DataFrame,
    calendar_dates_df: pd.DataFrame,
    service_dates: list[date],
) -> set[str]:
    active_service_ids: set[str] = set()

    for service_date in service_dates:
        service_date_int = int(service_date.strftime("%Y%m%d"))
        weekday_column = get_weekday_column(service_date)

        base_services = calendar_df[
            (calendar_df["start_date"] <= service_date_int)
            & (calendar_df["end_date"] >= service_date_int)
            & (calendar_df[weekday_column] == 1)
        ]["service_id"].astype(str)

        active_service_ids.update(base_services)

        if not calendar_dates_df.empty:
            service_exceptions = calendar_dates_df[
                calendar_dates_df["date"] == service_date_int
            ]
            additions = service_exceptions[
                service_exceptions["exception_type"] == 1
            ]["service_id"].astype(str)
            removals = service_exceptions[
                service_exceptions["exception_type"] == 2
            ]["service_id"].astype(str)

            active_service_ids.update(additions)
            active_service_ids.difference_update(removals)

    return active_service_ids


def build_import_scope() -> GtfsImportScope:
    calendar_path = settings.gtfs_path / "calendar.txt"
    calendar_dates_path = settings.gtfs_path / "calendar_dates.txt"
    trips_path = settings.gtfs_path / "trips.txt"

    calendar_df = pd.read_csv(calendar_path, low_memory=False)
    calendar_dates_df = (
        pd.read_csv(calendar_dates_path, low_memory=False)
        if calendar_dates_path.exists() and calendar_dates_path.stat().st_size > 0
        else pd.DataFrame(columns=["service_id", "date", "exception_type"])
    )
    service_dates = find_import_dates(calendar_df)
    service_ids = get_active_service_ids_for_dates(
        calendar_df,
        calendar_dates_df,
        service_dates,
    )

    if not service_ids:
        raise RuntimeError(
            f"No active GTFS service_ids found for import dates: {service_dates}"
        )

    trip_scope_columns = [
        column
        for column in ["trip_id", "service_id", "route_id", "shape_id"]
        if column in read_existing_columns(trips_path)
    ]
    trips_df = pd.read_csv(
        trips_path,
        usecols=trip_scope_columns,
        low_memory=False,
    )
    scoped_trips_df = trips_df[trips_df["service_id"].astype(str).isin(service_ids)]

    if scoped_trips_df.empty:
        raise RuntimeError(
            f"No GTFS trips found for active service_ids: {sorted(service_ids)}"
        )

    shape_ids: set[str] = set()
    if "shape_id" in scoped_trips_df.columns:
        shape_ids = {
            str(shape_id)
            for shape_id in scoped_trips_df["shape_id"].dropna().astype(str)
            if str(shape_id).strip()
        }

    logger.info(
        "GTFS import scope: dates={}, service_ids={}, trips={}, shape_ids={}.",
        [service_date.isoformat() for service_date in service_dates],
        sorted(service_ids),
        len(scoped_trips_df),
        len(shape_ids),
    )

    return GtfsImportScope(
        service_ids=set(scoped_trips_df["service_id"].astype(str)),
        trip_ids=set(scoped_trips_df["trip_id"].astype(str)),
        route_ids=set(scoped_trips_df["route_id"].astype(str)),
        shape_ids=shape_ids,
        service_dates=service_dates,
    )


def filter_gtfs_dataframe(
    file_name: str,
    df: pd.DataFrame,
    scope: GtfsImportScope,
) -> pd.DataFrame:
    if file_name == "routes.txt" and "route_id" in df.columns:
        return df[df["route_id"].astype(str).isin(scope.route_ids)]

    if file_name == "trips.txt" and "service_id" in df.columns:
        return df[df["service_id"].astype(str).isin(scope.service_ids)]

    if file_name == "calendar.txt" and "service_id" in df.columns:
        return df[df["service_id"].astype(str).isin(scope.service_ids)]

    if file_name == "calendar_dates.txt" and "service_id" in df.columns:
        return df[df["service_id"].astype(str).isin(scope.service_ids)]

    return df


def load_small_table(
    engine: Engine,
    file_name: str,
    table_name: str,
    scope: GtfsImportScope,
) -> None:
    path = settings.gtfs_path / file_name

    if not path.exists():
        raise FileNotFoundError(f"Missing GTFS file: {path}")

    logger.info("Loading {} into {}.", file_name, table_name)

    usecols = get_available_usecols(file_name, path)

    df = pd.read_csv(
        path,
        usecols=usecols,
        low_memory=False,
    )
    df = filter_gtfs_dataframe(file_name, df, scope)

    df.to_sql(
        table_name,
        engine,
        if_exists="replace",
        index=False,
        chunksize=settings.gtfs_small_table_sql_chunksize,
        dtype=GTFS_DTYPES.get(table_name),
    )

    logger.success("Loaded {} rows into {}.", len(df), table_name)


def load_stop_times_table(engine: Engine, scope: GtfsImportScope) -> None:
    file_name = "stop_times.txt"
    table_name = "gtfs_stop_times"
    path = settings.gtfs_path / file_name

    if not path.exists():
        raise FileNotFoundError(f"Missing GTFS file: {path}")

    logger.info("Loading {} into {} in chunks.", file_name, table_name)

    usecols = get_available_usecols(file_name, path)

    total_rows = 0
    first_chunk = True

    for chunk in pd.read_csv(
        path,
        usecols=usecols,
        low_memory=False,
        chunksize=settings.gtfs_stop_times_read_chunksize,
    ):
        chunk = chunk[chunk["trip_id"].astype(str).isin(scope.trip_ids)]

        if chunk.empty:
            continue

        chunk.to_sql(
            table_name,
            engine,
            if_exists="replace" if first_chunk else "append",
            index=False,
            chunksize=settings.gtfs_sql_insert_chunksize,
            dtype=GTFS_DTYPES.get(table_name),
        )

        total_rows += len(chunk)
        first_chunk = False

        logger.info("Loaded {} rows into {} so far.", total_rows, table_name)

    logger.success("Loaded {} rows into {}.", total_rows, table_name)


def load_shapes_table(engine: Engine, scope: GtfsImportScope) -> None:
    file_name = "shapes.txt"
    table_name = "gtfs_shapes"
    path = settings.gtfs_path / file_name

    if not path.exists():
        logger.warning("Skipping {} import because file is missing.", file_name)
        return

    if not scope.shape_ids:
        logger.warning("Skipping {} import because no trip shape_ids are in scope.", file_name)
        return

    logger.info(
        "Loading {} into {} for {} shape_ids.",
        file_name,
        table_name,
        len(scope.shape_ids),
    )

    usecols = get_available_usecols(file_name, path)
    total_rows = 0
    first_chunk = True

    for chunk in pd.read_csv(
        path,
        usecols=usecols,
        low_memory=False,
        chunksize=settings.gtfs_shapes_read_chunksize,
    ):
        chunk = chunk[chunk["shape_id"].astype(str).isin(scope.shape_ids)]
        if chunk.empty:
            continue

        chunk = chunk[
            ["shape_id", "shape_pt_sequence", "shape_pt_lat", "shape_pt_lon"]
        ]

        chunk.to_sql(
            table_name,
            engine,
            if_exists="replace" if first_chunk else "append",
            index=False,
            chunksize=settings.gtfs_sql_insert_chunksize,
            dtype=GTFS_DTYPES.get(table_name),
        )

        total_rows += len(chunk)
        first_chunk = False
        logger.info("Loaded {} rows into {} so far.", total_rows, table_name)

    if first_chunk:
        logger.warning("No shape points matched the import scope.")
        return

    logger.success("Loaded {} rows into {}.", total_rows, table_name)


def load_table(
    engine: Engine,
    file_name: str,
    table_name: str,
    scope: GtfsImportScope,
) -> None:
    if table_name == "gtfs_stop_times":
        load_stop_times_table(engine, scope)
        return

    load_small_table(engine, file_name, table_name, scope)


def create_segments_table(engine: Engine, scope: GtfsImportScope) -> None:
    logger.info("Creating precomputed GTFS segments table.")

    trips_df = pd.read_csv(
        settings.gtfs_path / "trips.txt",
        usecols=["trip_id", "service_id", "route_id"],
        low_memory=False,
    )
    trips_df = trips_df[trips_df["trip_id"].astype(str).isin(scope.trip_ids)]

    stop_time_chunks: list[pd.DataFrame] = []
    stop_time_columns = [
        column
        for column in [
            "trip_id",
            "arrival_time",
            "departure_time",
            "stop_id",
            "stop_sequence",
            "shape_dist_traveled",
        ]
        if column in read_existing_columns(settings.gtfs_path / "stop_times.txt")
    ]

    for chunk in pd.read_csv(
        settings.gtfs_path / "stop_times.txt",
        usecols=stop_time_columns,
        low_memory=False,
        chunksize=settings.gtfs_stop_times_read_chunksize,
    ):
        chunk = chunk[chunk["trip_id"].astype(str).isin(scope.trip_ids)]
        if not chunk.empty:
            stop_time_chunks.append(chunk)

    if not stop_time_chunks:
        raise RuntimeError("No GTFS stop_times available for segments table.")

    stop_times_df = pd.concat(stop_time_chunks, ignore_index=True)
    stop_times_df["trip_id"] = stop_times_df["trip_id"].astype(str)
    stop_times_df["stop_id"] = stop_times_df["stop_id"].astype(str)
    stop_times_df = stop_times_df.sort_values(["trip_id", "stop_sequence"])

    if "shape_dist_traveled" in stop_times_df.columns:
        stop_times_df["shape_dist_traveled"] = pd.to_numeric(
            stop_times_df["shape_dist_traveled"],
            errors="coerce",
        )
    else:
        stop_times_df["shape_dist_traveled"] = pd.NA

    grouped = stop_times_df.groupby("trip_id", sort=False)
    segments_df = pd.DataFrame(
        {
            "trip_id": stop_times_df["trip_id"],
            "from_stop_id": stop_times_df["stop_id"],
            "to_stop_id": grouped["stop_id"].shift(-1),
            "departure_time": stop_times_df["departure_time"],
            "arrival_time": grouped["arrival_time"].shift(-1),
            "from_stop_sequence": stop_times_df["stop_sequence"],
            "to_stop_sequence": grouped["stop_sequence"].shift(-1),
            "from_shape_dist_traveled": stop_times_df["shape_dist_traveled"],
            "to_shape_dist_traveled": grouped["shape_dist_traveled"].shift(-1),
        }
    ).dropna(subset=["to_stop_id", "arrival_time", "to_stop_sequence"])

    segments_df["to_stop_sequence"] = segments_df["to_stop_sequence"].astype(int)
    segments_df["departure_seconds"] = gtfs_time_to_seconds(
        segments_df["departure_time"]
    )
    segments_df["arrival_seconds"] = gtfs_time_to_seconds(segments_df["arrival_time"])

    segments_df = segments_df.merge(
        trips_df[["trip_id", "service_id", "route_id"]],
        on="trip_id",
        how="left",
    )

    columns = [
        "trip_id",
        "service_id",
        "route_id",
        "from_stop_id",
        "to_stop_id",
        "departure_seconds",
        "arrival_seconds",
        "from_stop_sequence",
        "to_stop_sequence",
        "from_shape_dist_traveled",
        "to_shape_dist_traveled",
    ]

    segments_df[columns].to_sql(
        "gtfs_segments",
        engine,
        if_exists="replace",
        index=False,
        chunksize=settings.gtfs_sql_insert_chunksize,
        dtype=GTFS_DTYPES["gtfs_segments"],
    )

    logger.success("Created {} rows in gtfs_segments.", len(segments_df))


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")
    return slug


def metro_stop_id(station: MetroStation) -> str:
    return f"metro_{slugify(station.name.removeprefix('Metro '))}"


def metro_segment_duration_seconds(first: MetroStation, second: MetroStation) -> int:
    distance_m = haversine_distance_m(
        GeoPoint(first.lat, first.lon),
        GeoPoint(second.lat, second.lon),
    )
    duration_seconds = round(distance_m / METRO_AVERAGE_SPEED_MPS + 25)
    return max(
        METRO_MIN_SEGMENT_SECONDS,
        min(METRO_MAX_SEGMENT_SECONDS, duration_seconds),
    )


def iter_metro_departures() -> list[int]:
    departures: list[int] = []

    for window in METRO_FREQUENCY_WINDOWS:
        departure_seconds = window.start_seconds
        while departure_seconds <= window.end_seconds:
            departures.append(departure_seconds)
            departure_seconds += window.headway_seconds

    return sorted(set(departures))


def generate_pseudo_metro_data(scope: GtfsImportScope) -> dict[str, pd.DataFrame]:
    service_start = min(scope.service_dates)
    service_end = max(scope.service_dates)
    start_date = int(service_start.strftime("%Y%m%d"))
    end_date = int(service_end.strftime("%Y%m%d"))
    station_by_stop_id = {
        metro_stop_id(station): station
        for metro_line in METRO_LINES
        for station in metro_line.stations
    }
    departures = iter_metro_departures()

    agency_df = pd.DataFrame(
        [
            {
                "agency_id": METRO_AGENCY_ID,
                "agency_name": METRO_AGENCY_NAME,
                "agency_url": METRO_AGENCY_URL,
                "agency_timezone": METRO_AGENCY_TIMEZONE,
                "agency_lang": METRO_AGENCY_LANG,
                "agency_phone": None,
            }
        ]
    )
    stops_df = pd.DataFrame(
        [
            {
                "stop_id": stop_id,
                "stop_name": station.name,
                "stop_lat": station.lat,
                "stop_lon": station.lon,
            }
            for stop_id, station in station_by_stop_id.items()
        ]
    )
    routes_df = pd.DataFrame(
        [
            {
                "route_id": metro_line.route_id,
                "agency_id": METRO_AGENCY_ID,
                "route_short_name": metro_line.short_name,
                "route_long_name": f"Metro {metro_line.short_name}",
                "route_type": 1,
            }
            for metro_line in METRO_LINES
        ]
    )
    calendar_df = pd.DataFrame(
        [
            {
                "service_id": METRO_SERVICE_ID,
                "monday": 1,
                "tuesday": 1,
                "wednesday": 1,
                "thursday": 1,
                "friday": 1,
                "saturday": 1,
                "sunday": 1,
                "start_date": start_date,
                "end_date": end_date,
            }
        ]
    )

    trips: list[dict[str, object]] = []
    segments: list[dict[str, object]] = []

    for metro_line in METRO_LINES:
        directions = [
            (0, metro_line.stations, metro_line.stations[-1].name),
            (1, tuple(reversed(metro_line.stations)), metro_line.stations[0].name),
        ]

        for direction_id, stations, headsign in directions:
            travel_times = [
                metro_segment_duration_seconds(stations[index], stations[index + 1])
                for index in range(len(stations) - 1)
            ]

            for departure_seconds in departures:
                trip_id = (
                    f"{metro_line.route_id}_{direction_id}_{departure_seconds}"
                )
                trips.append(
                    {
                        "route_id": metro_line.route_id,
                        "service_id": METRO_SERVICE_ID,
                        "trip_id": trip_id,
                        "trip_headsign": headsign,
                        "direction_id": direction_id,
                    }
                )

                current_departure = departure_seconds
                for index, travel_seconds in enumerate(travel_times):
                    arrival_seconds = current_departure + travel_seconds
                    segments.append(
                        {
                            "trip_id": trip_id,
                            "service_id": METRO_SERVICE_ID,
                            "route_id": metro_line.route_id,
                            "from_stop_id": metro_stop_id(stations[index]),
                            "to_stop_id": metro_stop_id(stations[index + 1]),
                            "departure_seconds": current_departure,
                            "arrival_seconds": arrival_seconds,
                            "from_stop_sequence": index + 1,
                            "to_stop_sequence": index + 2,
                        }
                    )
                    current_departure = arrival_seconds + METRO_DWELL_SECONDS

    return {
        "gtfs_agency": agency_df,
        "gtfs_stops": stops_df,
        "gtfs_routes": routes_df,
        "gtfs_trips": pd.DataFrame(trips),
        "gtfs_calendar": calendar_df,
        "gtfs_segments": pd.DataFrame(segments),
    }


def append_pseudo_metro(engine: Engine, scope: GtfsImportScope) -> None:
    if not settings.gtfs_include_pseudo_metro:
        logger.info("Skipping pseudo-metro GTFS generation.")
        return

    logger.info("Generating pseudo-GTFS for Warsaw metro.")
    metro_data = generate_pseudo_metro_data(scope)
    route_ids = list(metro_data["gtfs_routes"]["route_id"])
    stop_ids = list(metro_data["gtfs_stops"]["stop_id"])

    logger.info("Removing existing pseudo-metro GTFS rows.")
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM gtfs_segments WHERE service_id = :service_id;"),
            {"service_id": METRO_SERVICE_ID},
        )
        conn.execute(
            text("DELETE FROM gtfs_trips WHERE service_id = :service_id;"),
            {"service_id": METRO_SERVICE_ID},
        )
        conn.execute(
            text("DELETE FROM gtfs_calendar WHERE service_id = :service_id;"),
            {"service_id": METRO_SERVICE_ID},
        )
        conn.execute(
            text("DELETE FROM gtfs_routes WHERE route_id IN :route_ids;").bindparams(
                bindparam("route_ids", expanding=True)
            ),
            {"route_ids": route_ids},
        )
        conn.execute(
            text("DELETE FROM gtfs_stops WHERE stop_id IN :stop_ids;").bindparams(
                bindparam("stop_ids", expanding=True)
            ),
            {"stop_ids": stop_ids},
        )
        conn.execute(
            text("DELETE FROM gtfs_agency WHERE agency_id = :agency_id;"),
            {"agency_id": METRO_AGENCY_ID},
        )

    for table_name, df in metro_data.items():
        df.to_sql(
            table_name,
            engine,
            if_exists="append",
            index=False,
            chunksize=settings.gtfs_small_table_sql_chunksize,
            dtype=GTFS_DTYPES[table_name],
        )
        logger.success("Appended {} pseudo-metro rows to {}.", len(df), table_name)


def drop_stop_times_table(engine: Engine) -> None:
    logger.info("Dropping gtfs_stop_times to reduce database size.")

    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "gtfs_stop_times" CASCADE;'))

    logger.success("Dropped gtfs_stop_times.")


def create_indexes(engine: Engine) -> None:
    logger.info("Creating GTFS indexes.")

    statements = [
        (
            "idx_gtfs_stops_stop_id",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_stops_stop_id
            ON gtfs_stops(stop_id);
            """,
        ),
        (
            "idx_gtfs_routes_route_id",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_routes_route_id
            ON gtfs_routes(route_id);
            """,
        ),
        (
            "idx_gtfs_trips_trip_id",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_trips_trip_id
            ON gtfs_trips(trip_id);
            """,
        ),
        (
            "idx_gtfs_calendar_service_id",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_calendar_service_id
            ON gtfs_calendar(service_id);
            """,
        ),
        (
            "idx_gtfs_segments_service_departure",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_segments_service_departure
            ON gtfs_segments(service_id, departure_seconds);
            """,
        ),
        (
            "idx_gtfs_segments_from_stop_departure",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_segments_from_stop_departure
            ON gtfs_segments(from_stop_id, departure_seconds);
            """,
        ),
        (
            "idx_gtfs_segments_trip_sequence",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_segments_trip_sequence
            ON gtfs_segments(trip_id, from_stop_sequence);
            """,
        ),
        (
            "idx_gtfs_shapes_shape_sequence",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_shapes_shape_sequence
            ON gtfs_shapes(shape_id, shape_pt_sequence);
            """,
        ),
        (
            "idx_gtfs_trips_shape_id",
            """
            CREATE INDEX IF NOT EXISTS idx_gtfs_trips_shape_id
            ON gtfs_trips(shape_id);
            """,
        ),
    ]

    if settings.gtfs_keep_stop_times and settings.gtfs_create_heavy_indexes:
        statements.extend(
            [
                (
                    "idx_gtfs_stop_times_stop_id",
                    """
                    CREATE INDEX IF NOT EXISTS idx_gtfs_stop_times_stop_id
                    ON gtfs_stop_times(stop_id);
                    """,
                ),
                (
                    "idx_gtfs_stop_times_trip_id_stop_sequence",
                    """
                    CREATE INDEX IF NOT EXISTS idx_gtfs_stop_times_trip_id_stop_sequence
                    ON gtfs_stop_times(trip_id, stop_sequence);
                    """,
                ),
            ]
        )
    else:
        logger.warning(
            "Skipping heavy gtfs_stop_times indexes. "
            "Set GTFS_CREATE_HEAVY_INDEXES=true only on a database with enough resources."
        )

    if settings.gtfs_create_optional_indexes:
        statements.extend(
            [
                (
                    "idx_gtfs_trips_route_id",
                    """
                    CREATE INDEX IF NOT EXISTS idx_gtfs_trips_route_id
                    ON gtfs_trips(route_id);
                    """,
                ),
                (
                    "idx_gtfs_trips_service_id",
                    """
                    CREATE INDEX IF NOT EXISTS idx_gtfs_trips_service_id
                    ON gtfs_trips(service_id);
                    """,
                ),
                (
                    "idx_gtfs_calendar_dates_service_id",
                    """
                    CREATE INDEX IF NOT EXISTS idx_gtfs_calendar_dates_service_id
                    ON gtfs_calendar_dates(service_id);
                    """,
                ),
                (
                    "idx_gtfs_segments_from_stop",
                    """
                    CREATE INDEX IF NOT EXISTS idx_gtfs_segments_from_stop
                    ON gtfs_segments(from_stop_id);
                    """,
                ),
                (
                    "idx_gtfs_segments_to_stop",
                    """
                    CREATE INDEX IF NOT EXISTS idx_gtfs_segments_to_stop
                    ON gtfs_segments(to_stop_id);
                    """,
                ),
            ]
        )
    else:
        logger.warning(
            "Skipping optional GTFS indexes. "
            "Set GTFS_CREATE_OPTIONAL_INDEXES=true only when the database has spare disk."
        )

    for index_name, statement in statements:
        logger.info("Creating GTFS index {}.", index_name)
        with engine.begin() as conn:
            conn.execute(text(statement))
        logger.success("Created GTFS index {}.", index_name)

    logger.info("Analyzing GTFS tables.")
    with engine.begin() as conn:
        conn.execute(text("ANALYZE gtfs_stops;"))
        conn.execute(text("ANALYZE gtfs_routes;"))
        conn.execute(text("ANALYZE gtfs_trips;"))
        conn.execute(text("ANALYZE gtfs_calendar;"))
        conn.execute(text("ANALYZE gtfs_segments;"))
        conn.execute(text("ANALYZE gtfs_shapes;"))

    logger.success("Created GTFS indexes.")


def create_postgis_geometry(engine: Engine) -> None:
    logger.info("Creating PostGIS geometry for GTFS stops.")

    with engine.begin() as conn:
        logger.info("Ensuring PostGIS extension exists.")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

        logger.info("Adding geom column to gtfs_stops.")
        conn.execute(text("""
            ALTER TABLE gtfs_stops
            ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);
        """))

        logger.info("Populating gtfs_stops.geom.")
        conn.execute(text("""
            UPDATE gtfs_stops
            SET geom = ST_SetSRID(
                ST_MakePoint(stop_lon::double precision, stop_lat::double precision),
                4326
            )
            WHERE stop_lon IS NOT NULL
              AND stop_lat IS NOT NULL;
        """))

        logger.info("Creating GTFS stops spatial index idx_gtfs_stops_geom.")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_gtfs_stops_geom
            ON gtfs_stops
            USING GIST (geom);
        """))

    logger.success("Created PostGIS geometry and spatial index for GTFS stops.")


def import_gtfs(engine: Engine) -> None:
    scope = build_import_scope()
    drop_gtfs_tables(engine)

    for file_name, table_name in GTFS_TABLES.items():
        if file_name in {"segments", "shapes.txt"}:
            continue

        if file_name == "stop_times.txt" and not settings.gtfs_keep_stop_times:
            logger.info(
                "Skipping gtfs_stop_times table load because GTFS_KEEP_STOP_TIMES=false."
            )
            continue

        try:
            load_table(engine, file_name, table_name, scope)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to import {file_name} into {table_name}"
            ) from exc

    load_shapes_table(engine, scope)
    create_segments_table(engine, scope)
    append_pseudo_metro(engine, scope)

    create_indexes(engine)
    create_postgis_geometry(engine)


def main() -> None:
    configure_logging()

    try:
        engine = get_engine()
        import_gtfs(engine)
        logger.success("GTFS imported successfully.")
    except Exception as exc:
        logger.exception("GTFS import failed: {}", exc)
        raise


if __name__ == "__main__":
    main()
