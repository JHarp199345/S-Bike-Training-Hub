"""weather.py - the air temperature when and where an outdoor session happened (opt-in).

Heat raises heart rate, so matched comparisons need the conditions. The watch's own sensor sits on the wrist and
reads warm; this asks Open-Meteo (free, no account) for the hour's air temperature and humidity instead.

Privacy: this is the one place the hub sends anything out, so it is off until the athlete turns it on
(coach.json "weather_lookup": true). Only a location rounded to one decimal place (about 10 km) and a date are
sent, never a track or an activity. Every answer is cached in weather_cache.json beside the app, so each
place-day is asked for once. Indoor sessions (no GPS) are never looked up.
"""
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = __import__("paths").DATA / "weather_cache.json"
FORECAST = "https://api.open-meteo.com/v1/forecast"          # covers roughly the last three months
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"    # older days (it lags a few days behind)
RECENT_DAYS = 80
TIMEOUT = 8


def enabled(d):
    return bool((d or {}).get("weather_lookup"))


def _load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def _fetch(date, lat, lon, today):
    recent = (dt.date.fromisoformat(today) - dt.date.fromisoformat(date)).days <= RECENT_DAYS
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": date, "end_date": date,
                                "hourly": "temperature_2m,relative_humidity_2m", "timezone": "auto"})
    with urllib.request.urlopen(f"{FORECAST if recent else ARCHIVE}?{q}", timeout=TIMEOUT) as r:
        h = json.load(r).get("hourly") or {}
    return {t[11:13]: {"temp_c": c, "humidity_pct": rh}
            for t, c, rh in zip(h.get("time") or [], h.get("temperature_2m") or [], h.get("relative_humidity_2m") or [])
            if c is not None}


def lookup(date, hour, place, today, cache_path=None, fetch=None):
    """{"temp_c", "humidity_pct", "source"} for the place-day's hour, or None. place: [lat, lon], already rounded."""
    if not place or len(place) != 2:
        return None
    lat, lon = round(float(place[0]), 1), round(float(place[1]), 1)
    path = Path(cache_path or CACHE)
    cache = _load(path)
    key = f"{date}|{lat}|{lon}"
    if key not in cache:
        try:
            cache[key] = (fetch or _fetch)(date, lat, lon, today)
        except Exception:                              # offline or refused: unknown, try again next time
            return None
        path.write_text(json.dumps(cache))
    hours = cache.get(key) or {}
    row = hours.get(f"{int(hour):02d}")
    return {**row, "source": "Open-Meteo hourly air temperature (place rounded to ~10 km)"} if row else None
