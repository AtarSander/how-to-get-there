from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import settings


@dataclass(frozen=True)
class ParkAndRideLocation:
    parking_id: str
    name: str
    lat: float
    lon: float
    metro_station: str
    metro_line: str
    metro_lat: float
    metro_lon: float


def park_and_ride_config_path() -> Path:
    return settings.config_data_path / "park_and_ride.json"


def park_and_ride_location_from_dict(
    data: dict[str, Any],
) -> ParkAndRideLocation:
    return ParkAndRideLocation(
        parking_id=str(data["parking_id"]),
        name=str(data["name"]),
        lat=float(data["lat"]),
        lon=float(data["lon"]),
        metro_station=str(data["metro_station"]),
        metro_line=str(data["metro_line"]),
        metro_lat=float(data["metro_lat"]),
        metro_lon=float(data["metro_lon"]),
    )


def load_park_and_ride_locations(
    path: Path | None = None,
) -> list[ParkAndRideLocation]:
    config_path = path or park_and_ride_config_path()
    with config_path.open(encoding="utf-8") as file:
        raw_locations = json.load(file)

    if not isinstance(raw_locations, list):
        raise ValueError(f"Expected a list of P+R locations in {config_path}")

    return [
        park_and_ride_location_from_dict(raw_location)
        for raw_location in raw_locations
    ]


PARK_AND_RIDE_LOCATIONS = load_park_and_ride_locations()
