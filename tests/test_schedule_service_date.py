from datetime import date, datetime

import services.public_transport as public_transport
from services.public_transport import (
    gtfs_service_day_context,
    resolve_schedule_service_ids,
    schedule_reference_departure_at,
    schedule_search_context,
    schedule_service_date_for,
)


def test_schedule_service_date_before_rollover_uses_previous_day() -> None:
    requested = datetime(2026, 5, 17, 1, 30, 0)
    assert schedule_service_date_for(requested) == date(2026, 5, 16)


def test_schedule_service_date_after_rollover_uses_same_day() -> None:
    requested = datetime(2026, 5, 17, 5, 0, 0)
    assert schedule_service_date_for(requested) == date(2026, 5, 17)


def test_gtfs_request_offset_before_rollover_adds_24_hours() -> None:
    requested = datetime(2026, 5, 17, 1, 30, 0)
    context = gtfs_service_day_context(requested)
    assert context.request_offset_seconds == 25 * 3600 + 30 * 60
    assert context.service_day_start == datetime(2026, 5, 16, 0, 0, 0)


def test_gtfs_request_offset_during_day_is_unchanged() -> None:
    requested = datetime(2026, 5, 17, 14, 15, 0)
    context = gtfs_service_day_context(requested)
    assert context.request_offset_seconds == 14 * 3600 + 15 * 60
    assert context.service_date == date(2026, 5, 17)


class _FixedTodayDate(date):
    @classmethod
    def today(cls) -> date:
        return date(2026, 5, 16)


def test_schedule_reference_departure_at_future_uses_today_time(
    monkeypatch,
) -> None:
    monkeypatch.setattr(public_transport, "date", _FixedTodayDate)
    requested = datetime(2026, 5, 18, 8, 0, 0)
    reference = schedule_reference_departure_at(requested)
    assert reference == datetime(2026, 5, 16, 8, 0, 0)


def test_schedule_service_date_for_future_uses_today_calendar(
    monkeypatch,
) -> None:
    monkeypatch.setattr(public_transport, "date", _FixedTodayDate)
    requested = datetime(2026, 5, 18, 8, 0, 0)
    assert schedule_service_date_for(requested) == date(2026, 5, 16)


def test_schedule_search_context_future_night_uses_reference_offset(
    monkeypatch,
) -> None:
    monkeypatch.setattr(public_transport, "date", _FixedTodayDate)
    requested = datetime(2026, 5, 18, 0, 22, 0)
    context = schedule_search_context(requested)
    assert context.request_offset_seconds == 24 * 3600 + 22 * 60


def test_resolve_schedule_service_ids_falls_back_when_primary_missing(
    monkeypatch,
) -> None:
    requested = datetime(2026, 5, 17, 0, 22, 0)
    calls: list[date] = []

    def fake_fetch(_engine, service_date: date) -> set[str]:
        calls.append(service_date)
        if service_date == date(2026, 5, 17):
            return {"2_1"}
        return set()

    monkeypatch.setattr(public_transport, "fetch_active_service_ids", fake_fetch)

    class _Engine:
        pass

    service_ids = resolve_schedule_service_ids(_Engine(), requested)
    assert service_ids == {"2_1"}
    assert date(2026, 5, 16) in calls
    assert date(2026, 5, 17) in calls
