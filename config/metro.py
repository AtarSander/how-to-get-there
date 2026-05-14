from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import settings


@dataclass(frozen=True)
class MetroStation:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class MetroLine:
    route_id: str
    short_name: str
    stations: tuple[MetroStation, ...]


@dataclass(frozen=True)
class MetroAgency:
    agency_id: str
    agency_name: str
    agency_url: str
    agency_timezone: str
    agency_lang: str


@dataclass(frozen=True)
class MetroFrequencyWindow:
    start_seconds: int
    end_seconds: int
    headway_seconds: int


@dataclass(frozen=True)
class MetroConfig:
    service_id: str
    agency: MetroAgency
    dwell_seconds: int
    average_speed_mps: float
    min_segment_seconds: int
    max_segment_seconds: int
    frequency_windows: tuple[MetroFrequencyWindow, ...]
    lines: tuple[MetroLine, ...]


def metro_config_path() -> Path:
    return settings.config_data_path / "metro.json"


def metro_station_from_dict(data: dict[str, Any]) -> MetroStation:
    return MetroStation(
        name=str(data["name"]),
        lat=float(data["lat"]),
        lon=float(data["lon"]),
    )


def metro_line_from_dict(data: dict[str, Any]) -> MetroLine:
    return MetroLine(
        route_id=str(data["route_id"]),
        short_name=str(data["short_name"]),
        stations=tuple(
            metro_station_from_dict(station) for station in data["stations"]
        ),
    )


def metro_config_from_dict(data: dict[str, Any]) -> MetroConfig:
    agency = data["agency"]
    return MetroConfig(
        service_id=str(data["service_id"]),
        agency=MetroAgency(
            agency_id=str(agency["agency_id"]),
            agency_name=str(agency["agency_name"]),
            agency_url=str(agency["agency_url"]),
            agency_timezone=str(agency["agency_timezone"]),
            agency_lang=str(agency["agency_lang"]),
        ),
        dwell_seconds=int(data["dwell_seconds"]),
        average_speed_mps=float(data["average_speed_mps"]),
        min_segment_seconds=int(data["min_segment_seconds"]),
        max_segment_seconds=int(data["max_segment_seconds"]),
        frequency_windows=tuple(
            MetroFrequencyWindow(
                start_seconds=int(window["start_seconds"]),
                end_seconds=int(window["end_seconds"]),
                headway_seconds=int(window["headway_seconds"]),
            )
            for window in data["frequency_windows"]
        ),
        lines=tuple(metro_line_from_dict(line) for line in data["lines"]),
    )


def load_metro_config(path: Path | None = None) -> MetroConfig:
    config_path = path or metro_config_path()
    with config_path.open(encoding="utf-8") as file:
        raw_config = json.load(file)

    if not isinstance(raw_config, dict):
        raise ValueError(f"Expected a JSON object in {config_path}")

    return metro_config_from_dict(raw_config)


METRO_CONFIG = load_metro_config()
METRO_SERVICE_ID = METRO_CONFIG.service_id
METRO_AGENCY_ID = METRO_CONFIG.agency.agency_id
METRO_AGENCY_NAME = METRO_CONFIG.agency.agency_name
METRO_AGENCY_URL = METRO_CONFIG.agency.agency_url
METRO_AGENCY_TIMEZONE = METRO_CONFIG.agency.agency_timezone
METRO_AGENCY_LANG = METRO_CONFIG.agency.agency_lang
METRO_DWELL_SECONDS = METRO_CONFIG.dwell_seconds
METRO_AVERAGE_SPEED_MPS = METRO_CONFIG.average_speed_mps
METRO_MIN_SEGMENT_SECONDS = METRO_CONFIG.min_segment_seconds
METRO_MAX_SEGMENT_SECONDS = METRO_CONFIG.max_segment_seconds
METRO_FREQUENCY_WINDOWS = METRO_CONFIG.frequency_windows
METRO_LINES = METRO_CONFIG.lines
