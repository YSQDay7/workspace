import random
import time
from datetime import date, datetime, timedelta

import requests

from app import config

WMO_DESCRIPTIONS = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "强雷暴",
}

_cache: dict = {}


def _describe(code: int) -> str:
    return WMO_DESCRIPTIONS.get(code, "天气未知")


def _mock_weather() -> dict:
    seed = date.today().toordinal()
    rng = random.Random(seed)
    codes = [rng.choice([0, 1, 2, 3, 61, 63]), rng.choice([0, 1, 2, 3]), rng.choice([0, 1, 2, 3, 61])]
    daily = []
    for i, code in enumerate(codes):
        day = date.today() + timedelta(days=i)
        daily.append(
            {
                "date": day.isoformat(),
                "code": code,
                "description": _describe(code),
                "temp_max": round(rng.uniform(27, 34), 1),
                "temp_min": round(rng.uniform(20, 27), 1),
                "precipitation_probability": rng.choice([10, 20, 40, 60, 80]),
                "precipitation_mm": round(rng.uniform(0, 8), 1),
                "wind_speed": round(rng.uniform(6, 18), 1),
            }
        )
    return {
        "source": "mock",
        "location": "杭州",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "current": {
            "temperature": daily[0]["temp_min"] + 3,
            "apparent_temperature": daily[0]["temp_min"] + 5,
            "humidity": rng.randint(55, 90),
            "wind_speed": round(rng.uniform(4, 12), 1),
            "code": daily[0]["code"],
            "description": _describe(daily[0]["code"]),
            "is_day": True,
        },
        "daily": daily,
    }


def _fetch_open_meteo() -> dict:
    params = {
        "latitude": config.HANGZHOU_LAT,
        "longitude": config.HANGZHOU_LON,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max",
        "timezone": "Asia/Shanghai",
        "forecast_days": 3,
    }
    resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    current = data.get("current", {})
    daily_raw = data.get("daily", {})
    daily = []
    dates = daily_raw.get("time", [])
    for i, day in enumerate(dates):
        code = int(daily_raw["weather_code"][i])
        daily.append(
            {
                "date": day,
                "code": code,
                "description": _describe(code),
                "temp_max": daily_raw["temperature_2m_max"][i],
                "temp_min": daily_raw["temperature_2m_min"][i],
                "precipitation_probability": daily_raw["precipitation_probability_max"][i],
                "precipitation_mm": daily_raw["precipitation_sum"][i],
                "wind_speed": daily_raw["wind_speed_10m_max"][i],
            }
        )
    return {
        "source": "open-meteo",
        "location": "杭州",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "current": {
            "temperature": current.get("temperature_2m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "code": current.get("weather_code"),
            "description": _describe(int(current.get("weather_code", 0))),
            "is_day": bool(current.get("is_day", True)),
        },
        "daily": daily,
    }


def get_weather(force_refresh: bool = False) -> dict:
    cache_key = "hangzhou"
    now = time.time()
    cached = _cache.get(cache_key)
    if not force_refresh and cached and now - cached["ts"] < 1800:
        return cached["data"]
    try:
        data = _fetch_open_meteo()
    except Exception:
        data = _mock_weather()
    _cache[cache_key] = {"ts": now, "data": data}
    return data
