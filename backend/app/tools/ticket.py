import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "tickets.json"
_tickets = json.loads(DATA_PATH.read_text(encoding="utf-8"))


def all_tickets() -> list[dict]:
    return _tickets


def search_tickets(keyword: str, scenic_areas: list[str] | None = None, top_k: int = 3) -> list[dict]:
    keyword = (keyword or "").strip()
    candidates = _tickets
    if scenic_areas:
        candidates = [ticket for ticket in _tickets if ticket.get("scenic_area") in scenic_areas]
    if not keyword:
        return candidates[:top_k]
    scored = []
    for ticket in candidates:
        haystack = " ".join(
            [
                ticket["name"],
                ticket["category"],
                ticket["price"],
                ticket["price_note"],
                ticket["opening_hours"],
                " ".join(ticket.get("tags", [])),
            ]
        )
        score = 0
        if ticket["name"] in keyword:
            score += 5
        for tag in ticket.get("tags", []):
            if tag and tag in keyword:
                score += 2
        for token in [keyword, *keyword.split()]:
            if token and token in ticket["name"]:
                score += 3
            elif token and token in haystack:
                score += 1
        if score > 0:
            scored.append((score, ticket))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]
