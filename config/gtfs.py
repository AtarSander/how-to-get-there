from __future__ import annotations

from sqlalchemy import Float, Integer, Text

GTFS_TABLES = {
    "agency.txt": "gtfs_agency",
    "stops.txt": "gtfs_stops",
    "routes.txt": "gtfs_routes",
    "trips.txt": "gtfs_trips",
    "stop_times.txt": "gtfs_stop_times",
    "segments": "gtfs_segments",
    "calendar.txt": "gtfs_calendar",
    "calendar_dates.txt": "gtfs_calendar_dates",
}

REQUIRED_GTFS_FILES = {file_name for file_name in GTFS_TABLES if file_name != "segments"}

GTFS_COLUMNS = {
    "agency.txt": [
        "agency_id",
        "agency_name",
        "agency_url",
        "agency_timezone",
        "agency_lang",
        "agency_phone",
    ],
    "stops.txt": [
        "stop_id",
        "stop_name",
        "stop_lat",
        "stop_lon",
    ],
    "routes.txt": [
        "route_id",
        "agency_id",
        "route_short_name",
        "route_long_name",
        "route_type",
    ],
    "trips.txt": [
        "route_id",
        "service_id",
        "trip_id",
        "trip_headsign",
        "direction_id",
    ],
    "stop_times.txt": [
        "trip_id",
        "arrival_time",
        "departure_time",
        "stop_id",
        "stop_sequence",
    ],
    "calendar.txt": [
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ],
    "calendar_dates.txt": [
        "service_id",
        "date",
        "exception_type",
    ],
}

GTFS_DTYPES = {
    "gtfs_agency": {
        "agency_id": Text(),
        "agency_name": Text(),
        "agency_url": Text(),
        "agency_timezone": Text(),
        "agency_lang": Text(),
        "agency_phone": Text(),
    },
    "gtfs_stops": {
        "stop_id": Text(),
        "stop_name": Text(),
        "stop_lat": Float(),
        "stop_lon": Float(),
    },
    "gtfs_routes": {
        "route_id": Text(),
        "agency_id": Text(),
        "route_short_name": Text(),
        "route_long_name": Text(),
        "route_type": Integer(),
    },
    "gtfs_trips": {
        "route_id": Text(),
        "service_id": Text(),
        "trip_id": Text(),
        "trip_headsign": Text(),
        "direction_id": Integer(),
    },
    "gtfs_stop_times": {
        "trip_id": Text(),
        "arrival_time": Text(),
        "departure_time": Text(),
        "stop_id": Text(),
        "stop_sequence": Integer(),
    },
    "gtfs_segments": {
        "trip_id": Text(),
        "service_id": Text(),
        "route_id": Text(),
        "from_stop_id": Text(),
        "to_stop_id": Text(),
        "departure_seconds": Integer(),
        "arrival_seconds": Integer(),
        "from_stop_sequence": Integer(),
        "to_stop_sequence": Integer(),
    },
    "gtfs_calendar": {
        "service_id": Text(),
        "monday": Integer(),
        "tuesday": Integer(),
        "wednesday": Integer(),
        "thursday": Integer(),
        "friday": Integer(),
        "saturday": Integer(),
        "sunday": Integer(),
        "start_date": Integer(),
        "end_date": Integer(),
    },
    "gtfs_calendar_dates": {
        "service_id": Text(),
        "date": Integer(),
        "exception_type": Integer(),
    },
}
