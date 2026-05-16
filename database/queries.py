from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from config.settings import settings

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any


def _require_sqlalchemy():
    from sqlalchemy import bindparam, text

    return bindparam, text


def _gtfs_time_to_seconds(value: str) -> int:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)


def _seconds_to_gtfs_time(value: int) -> str:
    hours, remainder = divmod(int(value), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@dataclass(frozen=True)
class NearbyStop:
    stop_id: str
    stop_name: str
    lat: float
    lon: float
    distance_m: float


@dataclass(frozen=True)
class DirectConnectionCandidate:
    trip_id: str
    route_id: str
    route_short_name: str | None
    trip_headsign: str | None
    origin_stop_id: str
    origin_stop_name: str
    destination_stop_id: str
    destination_stop_name: str
    departure_time: str
    arrival_time: str
    stop_count: int
    from_stop_sequence: int | None = None
    to_stop_sequence: int | None = None
    from_shape_dist_traveled: float | None = None
    to_shape_dist_traveled: float | None = None


@dataclass(frozen=True)
class ConnectionSegment:
    trip_id: str
    route_id: str
    route_short_name: str | None
    trip_headsign: str | None
    from_stop_id: str
    from_stop_name: str
    to_stop_id: str
    to_stop_name: str
    departure_time: str
    arrival_time: str
    from_stop_sequence: int
    to_stop_sequence: int
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    from_shape_dist_traveled: float | None = None
    to_shape_dist_traveled: float | None = None


@dataclass(frozen=True)
class RoadEdgeRecord:
    edge_id: str
    source: str
    target: str
    source_lat: float
    source_lon: float
    target_lat: float
    target_lon: float
    length_m: float
    max_speed_kmh: float | None
    road_name: str | None
    oneway: bool


def fetch_nearest_stops(
    engine: Engine,
    lat: float,
    lon: float,
    radius_m: int | None = None,
    limit: int | None = None,
) -> list[NearbyStop]:
    radius_m = radius_m or settings.public_transport_max_stop_distance_m
    limit = limit or settings.public_transport_stop_limit

    _, text = _require_sqlalchemy()
    query = text(
        """
        SELECT
            stop_id,
            stop_name,
            stop_lat,
            stop_lon,
            ST_Distance(
                geom::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
            ) AS distance_m
        FROM gtfs_stops
        WHERE geom IS NOT NULL
          AND ST_DWithin(
              geom::geography,
              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
              :radius_m
          )
        ORDER BY distance_m ASC
        LIMIT :limit;
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(
            query,
            {
                "lat": lat,
                "lon": lon,
                "radius_m": radius_m,
                "limit": limit,
            },
        ).mappings()

        return [
            NearbyStop(
                stop_id=row["stop_id"],
                stop_name=row["stop_name"],
                lat=float(row["stop_lat"]),
                lon=float(row["stop_lon"]),
                distance_m=float(row["distance_m"]),
            )
            for row in rows
        ]


def fetch_active_service_ids(engine: Engine, service_date: date) -> set[str]:
    _, text = _require_sqlalchemy()
    weekday_column = {
        0: "monday",
        1: "tuesday",
        2: "wednesday",
        3: "thursday",
        4: "friday",
        5: "saturday",
        6: "sunday",
    }[service_date.weekday()]
    service_date_int = int(service_date.strftime("%Y%m%d"))

    calendar_query = text(
        f"""
        SELECT service_id
        FROM gtfs_calendar
        WHERE start_date <= :service_date
          AND end_date >= :service_date
          AND {weekday_column} = 1;
        """
    )
    additions_query = text(
        """
        SELECT service_id
        FROM gtfs_calendar_dates
        WHERE date = :service_date
          AND exception_type = 1;
        """
    )
    removals_query = text(
        """
        SELECT service_id
        FROM gtfs_calendar_dates
        WHERE date = :service_date
          AND exception_type = 2;
        """
    )

    with engine.begin() as conn:
        calendar_ids = {
            row["service_id"]
            for row in conn.execute(
                calendar_query,
                {"service_date": service_date_int},
            ).mappings()
        }
        added_ids = {
            row["service_id"]
            for row in conn.execute(
                additions_query,
                {"service_date": service_date_int},
            ).mappings()
        }
        removed_ids = {
            row["service_id"]
            for row in conn.execute(
                removals_query,
                {"service_date": service_date_int},
            ).mappings()
        }

    return (calendar_ids | added_ids) - removed_ids


def fetch_direct_connection_candidates(
    engine: Engine,
    origin_stop_ids: list[str],
    destination_stop_ids: list[str],
    service_ids: set[str],
    departure_time: str,
    limit: int = 30,
) -> list[DirectConnectionCandidate]:
    if not origin_stop_ids or not destination_stop_ids or not service_ids:
        return []

    bindparam, text = _require_sqlalchemy()
    query = text(
        """
        SELECT
            origin.trip_id,
            origin.route_id,
            routes.route_short_name,
            trips.trip_headsign,
            origin.from_stop_id AS origin_stop_id,
            origin_stops.stop_name AS origin_stop_name,
            destination.to_stop_id AS destination_stop_id,
            destination_stops.stop_name AS destination_stop_name,
            origin.departure_seconds,
            destination.arrival_seconds,
            destination.to_stop_sequence - origin.from_stop_sequence AS stop_count,
            origin.from_stop_sequence,
            destination.to_stop_sequence,
            origin.from_shape_dist_traveled,
            destination.to_shape_dist_traveled
        FROM gtfs_segments AS origin
        JOIN gtfs_segments AS destination
          ON destination.trip_id = origin.trip_id
         AND destination.to_stop_sequence > origin.from_stop_sequence
        JOIN gtfs_trips AS trips
          ON trips.trip_id = origin.trip_id
        LEFT JOIN gtfs_routes AS routes
          ON routes.route_id = origin.route_id
        JOIN gtfs_stops AS origin_stops
          ON origin_stops.stop_id = origin.from_stop_id
        JOIN gtfs_stops AS destination_stops
          ON destination_stops.stop_id = destination.to_stop_id
        WHERE origin.from_stop_id IN :origin_stop_ids
          AND destination.to_stop_id IN :destination_stop_ids
          AND origin.service_id IN :service_ids
          AND origin.departure_seconds >= :departure_seconds
        ORDER BY destination.arrival_seconds ASC, origin.departure_seconds ASC
        LIMIT :limit;
        """
    ).bindparams(
        bindparam("origin_stop_ids", expanding=True),
        bindparam("destination_stop_ids", expanding=True),
        bindparam("service_ids", expanding=True),
    )

    with engine.begin() as conn:
        rows = conn.execute(
            query,
            {
                "origin_stop_ids": origin_stop_ids,
                "destination_stop_ids": destination_stop_ids,
                "service_ids": sorted(service_ids),
                "departure_seconds": _gtfs_time_to_seconds(departure_time),
                "limit": limit,
            },
        ).mappings()

        return [
            DirectConnectionCandidate(
                trip_id=row["trip_id"],
                route_id=row["route_id"],
                route_short_name=row["route_short_name"],
                trip_headsign=row["trip_headsign"],
                origin_stop_id=row["origin_stop_id"],
                origin_stop_name=row["origin_stop_name"],
                destination_stop_id=row["destination_stop_id"],
                destination_stop_name=row["destination_stop_name"],
                departure_time=_seconds_to_gtfs_time(row["departure_seconds"]),
                arrival_time=_seconds_to_gtfs_time(row["arrival_seconds"]),
                stop_count=int(row["stop_count"]),
                from_stop_sequence=int(row["from_stop_sequence"]),
                to_stop_sequence=int(row["to_stop_sequence"]),
                from_shape_dist_traveled=_optional_float(
                    row.get("from_shape_dist_traveled")
                ),
                to_shape_dist_traveled=_optional_float(row.get("to_shape_dist_traveled")),
            )
            for row in rows
        ]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def fetch_trip_shape_id(engine: Engine, trip_id: str) -> str | None:
    _, text = _require_sqlalchemy()
    query = text(
        """
        SELECT shape_id
        FROM gtfs_trips
        WHERE trip_id = :trip_id
        LIMIT 1;
        """
    )

    with engine.begin() as conn:
        row = conn.execute(query, {"trip_id": trip_id}).mappings().first()

    if row is None:
        return None

    shape_id = row.get("shape_id")
    if shape_id is None:
        return None

    shape_id = str(shape_id).strip()
    return shape_id or None


def fetch_shape_points(
    engine: Engine,
    shape_id: str,
) -> tuple[tuple[float, float], ...]:
    _, text = _require_sqlalchemy()
    query = text(
        """
        SELECT shape_pt_lat, shape_pt_lon
        FROM gtfs_shapes
        WHERE shape_id = :shape_id
        ORDER BY shape_pt_sequence ASC;
        """
    )

    with engine.begin() as conn:
        rows = conn.execute(query, {"shape_id": shape_id}).mappings()

        return tuple(
            (float(row["shape_pt_lat"]), float(row["shape_pt_lon"]))
            for row in rows
        )


def fetch_stop_chain_positions(
    engine: Engine,
    trip_id: str,
    from_stop_sequence: int,
    to_stop_sequence: int,
) -> tuple[tuple[float, float], ...]:
    _, text = _require_sqlalchemy()
    query = text(
        """
        SELECT
            segments.from_stop_sequence,
            from_stops.stop_lat AS from_stop_lat,
            from_stops.stop_lon AS from_stop_lon,
            to_stops.stop_lat AS to_stop_lat,
            to_stops.stop_lon AS to_stop_lon,
            segments.to_stop_sequence
        FROM gtfs_segments AS segments
        JOIN gtfs_stops AS from_stops
          ON from_stops.stop_id = segments.from_stop_id
        JOIN gtfs_stops AS to_stops
          ON to_stops.stop_id = segments.to_stop_id
        WHERE segments.trip_id = :trip_id
          AND segments.from_stop_sequence >= :from_stop_sequence
          AND segments.to_stop_sequence <= :to_stop_sequence
        ORDER BY segments.from_stop_sequence ASC;
        """
    )

    with engine.begin() as conn:
        rows = list(
            conn.execute(
                query,
                {
                    "trip_id": trip_id,
                    "from_stop_sequence": from_stop_sequence,
                    "to_stop_sequence": to_stop_sequence,
                },
            ).mappings()
        )

    if not rows:
        return ()

    positions: list[tuple[float, float]] = []
    for row in rows:
        from_position = (float(row["from_stop_lat"]), float(row["from_stop_lon"]))
        to_position = (float(row["to_stop_lat"]), float(row["to_stop_lon"]))
        if not positions or positions[-1] != from_position:
            positions.append(from_position)
        if positions[-1] != to_position:
            positions.append(to_position)

    return tuple(positions)


def fetch_connection_segments(
    engine: Engine,
    service_ids: set[str],
    departure_time_from: str,
    departure_time_to: str,
    limit: int | None = None,
) -> list[ConnectionSegment]:
    if not service_ids:
        return []

    limit = limit or settings.public_transport_segment_limit

    bindparam, text = _require_sqlalchemy()
    query = text(
        """
        SELECT
            segments.trip_id,
            segments.route_id,
            route_short_name,
            trip_headsign,
            from_stop_id,
            from_stops.stop_name AS from_stop_name,
            from_stops.stop_lat AS from_stop_lat,
            from_stops.stop_lon AS from_stop_lon,
            to_stop_id,
            to_stops.stop_name AS to_stop_name,
            to_stops.stop_lat AS to_stop_lat,
            to_stops.stop_lon AS to_stop_lon,
            departure_seconds,
            arrival_seconds,
            from_stop_sequence,
            to_stop_sequence,
            from_shape_dist_traveled,
            to_shape_dist_traveled
        FROM gtfs_segments AS segments
        JOIN gtfs_stops AS from_stops
          ON from_stops.stop_id = segments.from_stop_id
        JOIN gtfs_stops AS to_stops
          ON to_stops.stop_id = segments.to_stop_id
        LEFT JOIN gtfs_routes AS routes
          ON routes.route_id = segments.route_id
        LEFT JOIN gtfs_trips AS trips
          ON trips.trip_id = segments.trip_id
        WHERE segments.service_id IN :service_ids
          AND departure_seconds >= :departure_seconds_from
          AND departure_seconds <= :departure_seconds_to
        ORDER BY
            departure_seconds ASC,
            arrival_seconds ASC,
            segments.trip_id ASC,
            segments.from_stop_sequence ASC
        LIMIT :limit;
        """
    ).bindparams(
        bindparam("service_ids", expanding=True),
    )

    with engine.begin() as conn:
        rows = conn.execute(
            query,
            {
                "service_ids": sorted(service_ids),
                "departure_seconds_from": _gtfs_time_to_seconds(departure_time_from),
                "departure_seconds_to": _gtfs_time_to_seconds(departure_time_to),
                "limit": limit,
            },
        ).mappings()

        return [
            ConnectionSegment(
                trip_id=row["trip_id"],
                route_id=row["route_id"],
                route_short_name=row["route_short_name"],
                trip_headsign=row["trip_headsign"],
                from_stop_id=row["from_stop_id"],
                from_stop_name=row["from_stop_name"],
                to_stop_id=row["to_stop_id"],
                to_stop_name=row["to_stop_name"],
                departure_time=_seconds_to_gtfs_time(row["departure_seconds"]),
                arrival_time=_seconds_to_gtfs_time(row["arrival_seconds"]),
                from_stop_sequence=int(row["from_stop_sequence"]),
                to_stop_sequence=int(row["to_stop_sequence"]),
                from_lat=float(row["from_stop_lat"]),
                from_lon=float(row["from_stop_lon"]),
                to_lat=float(row["to_stop_lat"]),
                to_lon=float(row["to_stop_lon"]),
                from_shape_dist_traveled=_optional_float(
                    row.get("from_shape_dist_traveled")
                ),
                to_shape_dist_traveled=_optional_float(row.get("to_shape_dist_traveled")),
            )
            for row in rows
        ]


def fetch_road_edges(engine: Engine, limit: int | None = None) -> list[RoadEdgeRecord]:
    _, text = _require_sqlalchemy()
    limit_clause = "LIMIT :limit" if limit is not None else ""
    query = text(
        f"""
        SELECT
            edge_id,
            source,
            target,
            source_lat,
            source_lon,
            target_lat,
            target_lon,
            length_m,
            max_speed_kmh,
            name AS road_name,
            oneway
        FROM osm_road_edges
        WHERE source IS NOT NULL
          AND target IS NOT NULL
          AND source_lat IS NOT NULL
          AND source_lon IS NOT NULL
          AND target_lat IS NOT NULL
          AND target_lon IS NOT NULL
          AND length_m IS NOT NULL
          AND length_m > 0
        {limit_clause};
        """
    )

    params = {"limit": limit} if limit is not None else {}

    with engine.begin() as conn:
        rows = conn.execute(query, params).mappings()

        return [
            RoadEdgeRecord(
                edge_id=row["edge_id"],
                source=row["source"],
                target=row["target"],
                source_lat=float(row["source_lat"]),
                source_lon=float(row["source_lon"]),
                target_lat=float(row["target_lat"]),
                target_lon=float(row["target_lon"]),
                length_m=float(row["length_m"]),
                max_speed_kmh=(
                    float(row["max_speed_kmh"])
                    if row["max_speed_kmh"] is not None
                    else None
                ),
                road_name=row["road_name"],
                oneway=bool(row["oneway"]),
            )
            for row in rows
        ]


def fetch_reachable_connection_segments(
    engine: Engine,
    service_ids: set[str],
    ready_seconds_by_stop_id: dict[str, int],
    departure_time_to: str,
    limit: int | None = None,
) -> list[ConnectionSegment]:
    if not service_ids or not ready_seconds_by_stop_id:
        return []

    limit = limit or settings.public_transport_segment_limit

    bindparam, text = _require_sqlalchemy()
    values_sql_parts: list[str] = []
    params: dict[str, object] = {
        "departure_seconds_to": _gtfs_time_to_seconds(departure_time_to),
        "limit": limit,
    }

    for index, (stop_id, ready_seconds) in enumerate(ready_seconds_by_stop_id.items()):
        stop_param = f"stop_id_{index}"
        ready_param = f"ready_seconds_{index}"
        values_sql_parts.append(f"(:{stop_param}, :{ready_param})")
        params[stop_param] = stop_id
        params[ready_param] = ready_seconds

    query = text(
        f"""
        WITH ready(stop_id, ready_seconds) AS (
            VALUES {", ".join(values_sql_parts)}
        ),
        boardable_trips AS (
            SELECT
                segments.trip_id,
                MIN(segments.from_stop_sequence) AS boarding_sequence
            FROM gtfs_segments AS segments
            JOIN ready
              ON ready.stop_id = segments.from_stop_id
            WHERE segments.service_id IN :service_ids
              AND segments.departure_seconds >= ready.ready_seconds
              AND segments.departure_seconds <= :departure_seconds_to
            GROUP BY segments.trip_id
        )
        SELECT
            segments.trip_id,
            segments.route_id,
            routes.route_short_name,
            trips.trip_headsign,
            segments.from_stop_id,
            from_stops.stop_name AS from_stop_name,
            from_stops.stop_lat AS from_stop_lat,
            from_stops.stop_lon AS from_stop_lon,
            segments.to_stop_id,
            to_stops.stop_name AS to_stop_name,
            to_stops.stop_lat AS to_stop_lat,
            to_stops.stop_lon AS to_stop_lon,
            segments.departure_seconds,
            segments.arrival_seconds,
            segments.from_stop_sequence,
            segments.to_stop_sequence,
            segments.from_shape_dist_traveled,
            segments.to_shape_dist_traveled
        FROM gtfs_segments AS segments
        JOIN boardable_trips
          ON boardable_trips.trip_id = segments.trip_id
         AND segments.from_stop_sequence >= boardable_trips.boarding_sequence
        JOIN gtfs_stops AS from_stops
          ON from_stops.stop_id = segments.from_stop_id
        JOIN gtfs_stops AS to_stops
          ON to_stops.stop_id = segments.to_stop_id
        LEFT JOIN gtfs_routes AS routes
          ON routes.route_id = segments.route_id
        LEFT JOIN gtfs_trips AS trips
          ON trips.trip_id = segments.trip_id
        WHERE segments.departure_seconds <= :departure_seconds_to
        ORDER BY
            segments.departure_seconds ASC,
            segments.arrival_seconds ASC,
            segments.trip_id ASC,
            segments.from_stop_sequence ASC
        LIMIT :limit;
        """
    ).bindparams(bindparam("service_ids", expanding=True))

    params["service_ids"] = sorted(service_ids)

    with engine.begin() as conn:
        rows = conn.execute(query, params).mappings()

        return [
            ConnectionSegment(
                trip_id=row["trip_id"],
                route_id=row["route_id"],
                route_short_name=row["route_short_name"],
                trip_headsign=row["trip_headsign"],
                from_stop_id=row["from_stop_id"],
                from_stop_name=row["from_stop_name"],
                to_stop_id=row["to_stop_id"],
                to_stop_name=row["to_stop_name"],
                departure_time=_seconds_to_gtfs_time(row["departure_seconds"]),
                arrival_time=_seconds_to_gtfs_time(row["arrival_seconds"]),
                from_stop_sequence=int(row["from_stop_sequence"]),
                to_stop_sequence=int(row["to_stop_sequence"]),
                from_lat=float(row["from_stop_lat"]),
                from_lon=float(row["from_stop_lon"]),
                to_lat=float(row["to_stop_lat"]),
                to_lon=float(row["to_stop_lon"]),
                from_shape_dist_traveled=_optional_float(
                    row.get("from_shape_dist_traveled")
                ),
                to_shape_dist_traveled=_optional_float(row.get("to_shape_dist_traveled")),
            )
            for row in rows
        ]
