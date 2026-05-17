from datetime import date, datetime

import services.public_transport as public_transport
from services.public_transport import (
    gtfs_service_day_context,
    schedule_reference_departure_at,
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
