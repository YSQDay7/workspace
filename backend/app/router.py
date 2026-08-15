import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_scenic_areas = json.loads((DATA_DIR / "scenic_areas.json").read_text(encoding="utf-8"))
_alias_index: list[tuple[str, dict]] = []
for _area in _scenic_areas:
    names = [_area["name"], *_area.get("aliases", [])]
    for name in names:
        if name:
            _alias_index.append((name, _area))
_alias_index.sort(key=lambda item: len(item[0]), reverse=True)


def all_scenic_areas() -> list[dict]:
    return _scenic_areas


def detect_scenic_areas(text: str) -> list[dict]:
    text = (text or "").strip()
    if not text:
        return []
    found: dict[str, dict] = {}
    for alias, area in _alias_index:
        if alias and alias in text and area["code"] not in found:
            found[area["code"]] = area
    return list(found.values())


def scenic_codes(text: str) -> list[str]:
    return [area["code"] for area in detect_scenic_areas(text)]
