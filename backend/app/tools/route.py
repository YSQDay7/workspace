import json
import re
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "routes.json"
_routes = json.loads(DATA_PATH.read_text(encoding="utf-8"))


def all_routes() -> list[dict]:
    return _routes


def _parse_start_time(text: str, default: str) -> str:
    if not text:
        return default
    match = re.search(r"(\d{1,2})[:：点](\d{1,2})?", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    match = re.search(r"早上?|早晨", text)
    if match:
        return default
    return default


def _to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _to_hhmm(minutes: int) -> str:
    minutes = max(0, minutes % (24 * 60))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def build_itinerary(preference: str = "", start_time: str = "", scenic_areas: list[str] | None = None) -> dict | None:
    if not _routes:
        return None
    preference = preference or ""
    candidates = _routes
    if scenic_areas:
        candidates = [
            route
            for route in _routes
            if any(stop.get("scenic_area") in scenic_areas for stop in route.get("stops", []))
        ]
        if not candidates:
            candidates = _routes
    ranked = []
    for route in candidates:
        score = 0
        for keyword in route.get("preference", []):
            if keyword in preference:
                score += 1
        route_areas = {stop.get("scenic_area") for stop in route.get("stops", []) if stop.get("scenic_area")}
        if scenic_areas:
            coverage = len(route_areas & set(scenic_areas))
            score += coverage * 3
        ranked.append((score, route))
    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen = ranked[0][1]
    if ranked[0][0] == 0 and len(ranked) > 1:
        chosen = max(
            ranked,
            key=lambda pair: len(
                {
                    stop.get("scenic_area")
                    for stop in pair[1].get("stops", [])
                    if stop.get("scenic_area")
                }
            ),
        )[1]

    base = _parse_start_time(preference, chosen.get("default_start", "09:00"))
    base_minutes = _to_minutes(base)
    if start_time.strip():
        base = _parse_start_time(start_time, base)
        base_minutes = _to_minutes(base)

    stops = []
    for stop in chosen.get("stops", []):
        arrival = _to_hhmm(base_minutes + int(stop.get("offset_minutes", 0)))
        stops.append(
            {
                "name": stop["name"],
                "time": arrival,
                "duration_minutes": int(stop.get("duration_minutes", 30)),
                "description": stop.get("description", ""),
                "tips": stop.get("tips", ""),
                "latitude": stop.get("latitude"),
                "longitude": stop.get("longitude"),
                "scenic_area": stop.get("scenic_area"),
            }
        )
    last_offset = int(chosen["stops"][-1].get("offset_minutes", 0)) + int(
        chosen["stops"][-1].get("duration_minutes", 0)
    )
    end_time = _to_hhmm(base_minutes + last_offset)
    return {
        "route_id": chosen["id"],
        "title": chosen["title"],
        "summary": chosen["summary"],
        "start_time": base,
        "end_time": end_time,
        "total_hours": round(last_offset / 60, 1),
        "scenic_areas": sorted({stop.get("scenic_area") for stop in chosen.get("stops", []) if stop.get("scenic_area")}),
        "stops": stops,
    }
