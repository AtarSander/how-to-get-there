from datetime import date, datetime

from services.public_transport import schedule_service_date_for


def test_schedule_service_date_for_uses_today() -> None:
    requested = datetime(2030, 1, 1, 12, 0, 0)
    assert schedule_service_date_for(requested) == date.today()
