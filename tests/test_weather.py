import sys, pathlib, tempfile, json; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import weather, planning_context as C

calls = []
def fake(date, lat, lon, today):
    calls.append((date, lat, lon))
    return {"09": {"temp_c": 14.0, "humidity_pct": 70}, "17": {"temp_c": 27.5, "humidity_pct": 40}}

cache = pathlib.Path(tempfile.mkdtemp()) / "weather_cache.json"
w = weather.lookup("2026-10-11", 9, [45.512, -122.658], "2026-10-11", cache, fake)
assert w["temp_c"] == 14.0 and calls == [("2026-10-11", 45.5, -122.7)]        # the place is rounded before sending
assert weather.lookup("2026-10-11", 17, [45.51, -122.66], "2026-10-11", cache, fake)["temp_c"] == 27.5
assert len(calls) == 1 and json.loads(cache.read_text())                        # one request per place-day, cached
assert weather.lookup("2026-10-11", 3, [45.5, -122.7], "2026-10-11", cache, fake) is None    # hour not returned
assert weather.lookup("2026-10-11", 9, None, "2026-10-11", cache, fake) is None             # indoor: never asked
def broken(*a): raise OSError("offline")
assert weather.lookup("2026-10-12", 9, [45.5, -122.7], "2026-10-12", cache, broken) is None  # offline: unknown
assert weather.enabled({"weather_lookup": True}) and not weather.enabled({})

# matched comparisons carry conditions and call out a big temperature difference
import datetime as dt
ts = lambda day, hour: dt.datetime(*map(int, day.split("-")), hour).timestamp()
state = {"activities": [
    {"date": "2026-09-23", "sport": "run", "minutes": 30, "km": 4.0, "avg_hr": 150, "place": [45.5, -122.7], "start_ts": ts("2026-09-23", 17), "watch_temp_c": 36},
    {"date": "2026-10-11", "sport": "run", "minutes": 26, "km": 3.4, "avg_hr": 140, "place": [45.5, -122.7], "start_ts": ts("2026-10-11", 9), "watch_temp_c": 30},
    {"date": "2026-10-09", "sport": "swim", "minutes": 53, "km": 2.29, "avg_hr": 124}]}
def fetch(date, lat, lon, today):
    return {"17": {"temp_c": 29.0, "humidity_pct": 35}, "09": {"temp_c": 15.0, "humidity_pct": 75}}
e = C.efficiency(state, "2026-10-11", True, cache.with_name("w2.json"), fetch)["by_sport"]
run = [c for c in e["run"]["matched_comparisons"] if c["session"]["date"] == "2026-10-11"][0]
assert run["session"]["conditions"]["air_temp_c"] == 15.0 and run["match"]["conditions"]["air_temp_c"] == 29.0
assert run["temperature_difference_c"] == -14.0 and run["temperature_basis"] == "air" and "cooler" in run["heat_note"]
assert e["swim"]["sessions_90_days"][0]["conditions"]["setting"] == "pool"
off = C.efficiency(state, "2026-10-11")["by_sport"]["run"]["matched_comparisons"][-1]   # lookup off: the watch sensor
assert off["temperature_basis"] == "watch sensor" and off["temperature_difference_c"] == -6 and "heat_note" in off
print("PASS weather: rounded, cached, opt-in lookups; temperature in matched comparisons")
