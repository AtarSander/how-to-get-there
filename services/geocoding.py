from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config.settings import settings

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
WARSAW_VIEWBOX = "20.85,52.35,21.25,52.10"


@dataclass(frozen=True)
class GeocodedAddress:
    label: str
    lat: float
    lon: float

    def as_dict(self) -> dict[str, float | str]:
        return {"label": self.label, "lat": self.lat, "lon": self.lon}


def search_addresses(
    query: str,
    *,
    lang: str = "pl",
    limit: int = 8,
) -> list[GeocodedAddress]:
    normalized = query.strip()
    if len(normalized) < 3:
        return []

    query_params: dict[str, str] = {
        "q": normalized,
        "format": "json",
        "addressdetails": "0",
        "limit": str(limit),
        "countrycodes": "pl",
        "viewbox": WARSAW_VIEWBOX,
        "bounded": "1",
        "accept-language": lang,
    }
    if settings.geocoding_contact_email:
        query_params["email"] = settings.geocoding_contact_email

    params = urlencode(query_params, encoding="utf-8")
    request = Request(
        f"{NOMINATIM_SEARCH_URL}?{params}",
        headers={"User-Agent": settings.geocoding_user_agent},
    )

    with urlopen(request, timeout=settings.geocoding_timeout_seconds) as response:
        payload = json.load(response)

    if not isinstance(payload, list):
        return []

    results: list[GeocodedAddress] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        display_name = item.get("display_name")
        lat = item.get("lat")
        lon = item.get("lon")
        if not isinstance(display_name, str):
            continue
        try:
            results.append(
                GeocodedAddress(
                    label=display_name,
                    lat=float(lat),
                    lon=float(lon),
                )
            )
        except (TypeError, ValueError):
            continue

    return results
