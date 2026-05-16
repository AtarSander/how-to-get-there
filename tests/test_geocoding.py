import json
from io import BytesIO
from unittest.mock import patch

from services.geocoding import search_addresses


def test_search_addresses_parses_nominatim_response():
    payload = json.dumps(
        [
            {
                "display_name": "Pałac Kultury, Warszawa, Polska",
                "lat": "52.2318",
                "lon": "21.0067",
            }
        ]
    ).encode()

    with patch("services.geocoding.urlopen") as urlopen_mock:
        urlopen_mock.return_value.__enter__.return_value = BytesIO(payload)
        results = search_addresses("pałac kultury")

    assert len(results) == 1
    assert results[0].label.startswith("Pałac Kultury")
    assert results[0].lat == 52.2318
    assert results[0].lon == 21.0067


def test_search_addresses_returns_empty_for_short_query():
    assert search_addresses("ab") == []
