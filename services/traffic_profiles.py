from __future__ import annotations

from typing import TYPE_CHECKING, Any

from config.settings import settings
from database.queries import (
    fetch_zdm_apr_directional_hourly_volumes,
    fetch_zdm_apr_hourly_volumes,
)
from services.car_routing import GeoPoint, TrafficProfile

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
else:
    Engine = Any


def clamp_multiplier(value: float) -> float:
    return min(
        max(value, settings.car_traffic_profile_min_multiplier),
        settings.car_traffic_profile_max_multiplier,
    )


def hourly_multipliers_from_volumes(
    hourly_volumes: dict[int, float],
) -> dict[int, float]:
    volumes = {
        hour: max(float(hourly_volumes.get(hour, 0.0)), 0.0)
        for hour in range(24)
    }
    average_volume = sum(volumes.values()) / 24
    if average_volume <= 0:
        return {}

    return {
        hour: clamp_multiplier(
            1
            + ((volume / average_volume) - 1)
            * settings.car_traffic_profile_strength
        )
        for hour, volume in volumes.items()
    }


def traffic_profile_from_hourly_volumes(
    hourly_volumes: dict[int, float],
    directional_hourly_volumes: dict[int, dict[int, float]] | None = None,
) -> TrafficProfile | None:
    multipliers = hourly_multipliers_from_volumes(hourly_volumes)
    if not multipliers:
        return None

    directional_multipliers = (
        {
            direction: hourly_multipliers_from_volumes(volumes)
            for direction, volumes in directional_hourly_volumes.items()
        }
        if directional_hourly_volumes
        else None
    )

    return TrafficProfile(
        hourly_multipliers=multipliers,
        default_multiplier=1.0,
        directional_hourly_multipliers=directional_multipliers,
        center=GeoPoint(
            settings.car_traffic_center_lat,
            settings.car_traffic_center_lon,
        ),
    )


def load_zdm_apr_traffic_profile(engine: Engine) -> TrafficProfile | None:
    if not settings.car_traffic_profile_enabled:
        return None

    try:
        hourly_volumes = fetch_zdm_apr_hourly_volumes(engine)
        directional_hourly_volumes = fetch_zdm_apr_directional_hourly_volumes(engine)
    except Exception:
        return None

    return traffic_profile_from_hourly_volumes(
        hourly_volumes,
        directional_hourly_volumes=directional_hourly_volumes,
    )
