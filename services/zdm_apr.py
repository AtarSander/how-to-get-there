from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config.settings import settings
from database.queries import ZdmAprHourlyProfileRecord, ZdmAprPointRecord

APR_STATIC_FIELDS = [
    "ObjectId",
    "NR",
    "Ulica",
    "Odcinek_lokalizacji",
    "Lat",
    "Long",
    "Nazwa_dzielnicy",
    "Kordon_lub_ekran",
]
APR_HOUR_FIELDS = [
    f"G{hour}_{direction}"
    for direction in (1, 2)
    for hour in range(24)
]
APR_OUT_FIELDS = ",".join(APR_STATIC_FIELDS + APR_HOUR_FIELDS)


@dataclass(frozen=True)
class ZdmAprImportDataset:
    points: list[ZdmAprPointRecord]
    hourly_profiles: list[ZdmAprHourlyProfileRecord]


def optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def optional_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def profile_volume(value: object) -> int:
    if value is None:
        return 0
    return max(int(value), 0)


def point_lat_lon(attributes: dict[str, Any], geometry: dict[str, Any]) -> tuple[float, float]:
    lat_value = attributes.get("Lat")
    lon_value = attributes.get("Long")

    if lat_value is not None and lon_value is not None:
        return float(lat_value), float(lon_value)

    return float(geometry["y"]), float(geometry["x"])


def parse_zdm_apr_feature(
    feature: dict[str, Any],
    source_year: int | None = None,
) -> tuple[ZdmAprPointRecord, list[ZdmAprHourlyProfileRecord]]:
    source_year = source_year or settings.zdm_apr_source_year
    attributes = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}

    source_object_id = int(attributes["ObjectId"])
    lat, lon = point_lat_lon(attributes, geometry)

    point = ZdmAprPointRecord(
        source_object_id=source_object_id,
        point_number=optional_int(attributes.get("NR")),
        street=optional_text(attributes.get("Ulica")),
        location_section=optional_text(attributes.get("Odcinek_lokalizacji")),
        district=optional_text(attributes.get("Nazwa_dzielnicy")),
        screen=optional_text(attributes.get("Kordon_lub_ekran")),
        lat=lat,
        lon=lon,
        source_year=source_year,
    )

    hourly_profiles = [
        ZdmAprHourlyProfileRecord(
            source_object_id=source_object_id,
            direction=direction,
            hour=hour,
            volume=profile_volume(attributes.get(f"G{hour}_{direction}")),
        )
        for direction in (1, 2)
        for hour in range(24)
    ]

    return point, hourly_profiles


def parse_zdm_apr_features(
    features: list[dict[str, Any]],
    source_year: int | None = None,
) -> ZdmAprImportDataset:
    points: list[ZdmAprPointRecord] = []
    hourly_profiles: list[ZdmAprHourlyProfileRecord] = []

    for feature in features:
        point, point_profiles = parse_zdm_apr_feature(feature, source_year)
        points.append(point)
        hourly_profiles.extend(point_profiles)

    return ZdmAprImportDataset(points=points, hourly_profiles=hourly_profiles)


def build_zdm_apr_query_url(
    base_url: str,
    offset: int,
    page_size: int,
) -> str:
    params = {
        "f": "json",
        "where": "1=1",
        "outFields": APR_OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "orderByFields": "ObjectId ASC",
    }
    return f"{base_url.rstrip('/')}/query?{urlencode(params)}"


def fetch_zdm_apr_features(
    base_url: str | None = None,
    page_size: int | None = None,
    timeout_seconds: int | None = None,
) -> list[dict[str, Any]]:
    base_url = base_url or settings.zdm_apr_feature_layer_url
    page_size = page_size or settings.zdm_apr_download_page_size
    timeout_seconds = timeout_seconds or settings.zdm_apr_download_timeout_seconds

    features: list[dict[str, Any]] = []
    offset = 0

    while True:
        url = build_zdm_apr_query_url(base_url, offset, page_size)
        request = Request(
            url,
            headers={"User-Agent": settings.gtfs_download_user_agent},
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if "error" in payload:
            raise RuntimeError(f"ZDM APR query failed: {payload['error']}")

        page_features = payload.get("features") or []
        features.extend(page_features)

        if len(page_features) < page_size or not payload.get("exceededTransferLimit"):
            break

        offset += page_size

    return features


def fetch_zdm_apr_import_dataset() -> ZdmAprImportDataset:
    return parse_zdm_apr_features(
        fetch_zdm_apr_features(),
        source_year=settings.zdm_apr_source_year,
    )
