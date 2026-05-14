from __future__ import annotations

from datetime import date

from config.metro import METRO_SERVICE_ID
from scripts.import_gtfs import GtfsImportScope, generate_pseudo_metro_data


def test_generate_pseudo_metro_data_adds_m1_m2_routes_and_segments() -> None:
    data = generate_pseudo_metro_data(
        GtfsImportScope(
            service_ids={"weekday"},
            trip_ids={"source-trip"},
            route_ids={"source-route"},
            service_dates=[date(2026, 5, 14)],
        )
    )

    route_short_names = set(data["gtfs_routes"]["route_short_name"])
    route_types = set(data["gtfs_routes"]["route_type"])
    stop_names = set(data["gtfs_stops"]["stop_name"])

    assert route_short_names == {"M1", "M2"}
    assert route_types == {1}
    assert "Metro Młociny" in stop_names
    assert "Metro Centrum" in stop_names
    assert "Metro Bródno" in stop_names
    assert len(data["gtfs_segments"]) > 0
    assert set(data["gtfs_trips"]["service_id"]) == {METRO_SERVICE_ID}
    assert set(data["gtfs_calendar"]["service_id"]) == {METRO_SERVICE_ID}
