from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from api.serialization import serialize_route_comparison
from database.connection import get_engine
from services.geocoding import search_addresses
from services.route_comparison import compare_routes

api_bp = Blueprint("api", __name__)


def _parse_coordinate(value: object, field_name: str) -> float:
    if value is None:
        raise ValueError(f"{field_name} is required.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc


def _parse_departure_at(payload: dict) -> datetime:
    raw = payload.get("departure_at")
    if raw is None:
        return datetime.now().replace(microsecond=0)

    if not isinstance(raw, str):
        raise ValueError("departure_at must be an ISO-8601 string.")

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            "departure_at must be an ISO-8601 datetime, e.g. 2026-05-16T08:00:00."
        ) from exc

    return parsed.replace(tzinfo=None)


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.get("/geocode/search")
def geocode_search():
    query = request.args.get("q", "")
    lang = request.args.get("lang", "pl")
    if not isinstance(query, str):
        return jsonify({"error": "q must be a string."}), 400
    if lang not in {"pl", "en"}:
        lang = "pl"

    try:
        results = search_addresses(query, lang=lang)
    except Exception as exc:
        return jsonify({"error": f"Address search failed: {exc}"}), 502

    return jsonify({"results": [item.as_dict() for item in results]})


@api_bp.post("/routes/compare")
def routes_compare():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    try:
        origin_lat = _parse_coordinate(payload.get("origin_lat"), "origin_lat")
        origin_lon = _parse_coordinate(payload.get("origin_lon"), "origin_lon")
        destination_lat = _parse_coordinate(
            payload.get("destination_lat"),
            "destination_lat",
        )
        destination_lon = _parse_coordinate(
            payload.get("destination_lon"),
            "destination_lon",
        )
        departure_at = _parse_departure_at(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        comparison = compare_routes(
            engine=get_engine(),
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=destination_lat,
            destination_lon=destination_lon,
            departure_at=departure_at,
        )
    except Exception as exc:
        return jsonify({"error": f"Route comparison failed: {exc}"}), 500

    return jsonify(serialize_route_comparison(comparison))
