"""morning.py - readiness from the watch overnight: sleep HRV, resting heart rate, sleep.

The coach (Claude, through the COROS connector) records each morning's numbers with
record_morning; the hub keeps them in activities/morning.json (personal, git-ignored).

  HRV        the watch's own nightly average against its own normal range (COROS works
             out the range from your history). Under it: the nervous system hasn't
             recovered - easy. Under it two mornings running: rest.
  RESTING HR against its median over the last two weeks: 5+ bpm up - easy; 8+ - rest.
  SLEEP      under 5 hours - easy (under 4: say so plainly). Short sleep blunts
             recovery from the day before and makes hard efforts cost more.

It judges the heart and lungs (the engine): the bike verdict. The feet and legs
have their own models; a rest morning is still mentioned on the running verdict.
"""
import datetime as dt
import json
import statistics
from pathlib import Path

FIELDS = ("hrv", "hrv_low", "hrv_high", "hrv_baseline", "resting_hr", "sleep_min", "deep_min", "rem_min")


def path(base):
    return Path(base) / "activities" / "morning.json"


def load(base):
    try:
        return json.loads(path(base).read_text())
    except (OSError, ValueError):
        return {}


def record(base, days):
    """days: {"YYYY-MM-DD": {hrv, hrv_low, hrv_high, hrv_baseline, resting_hr, sleep_min, ...}} - merged by date."""
    import re
    have = load(base)
    for d, v in (days or {}).items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d)) or not isinstance(v, dict):
            raise ValueError(f"bad day {d!r}: use YYYY-MM-DD: {{hrv, resting_hr, sleep_min, ...}}")
        clean = {}
        for k in FIELDS:
            if v.get(k) is not None:
                x = float(v[k])
                if not 0 <= x <= 1440:
                    raise ValueError(f"{d} {k}={x} is out of range")
                clean[k] = round(x, 1)
        have[str(d)] = {**have.get(str(d), {}), **clean}
    f = path(base)
    f.parent.mkdir(exist_ok=True)
    tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(dict(sorted(have.items())), indent=1)); tmp.replace(f)
    return have


def _hm(m):
    return f"{int(m) // 60}h{int(m) % 60:02d}"


def assess(days, today=None):
    """This morning's read: {date, level (go/easy/rest), why, and the numbers against normal}. None without data."""
    today = today or dt.date.today()
    key = today.isoformat()
    m = days.get(key) or days.get((today - dt.timedelta(days=1)).isoformat())
    if not m:
        return None
    date = key if key in days else (today - dt.timedelta(days=1)).isoformat()
    order = {"go": 0, "easy": 1, "rest": 2}
    level, why = "go", []
    def worse(lv, msg):
        nonlocal level
        level = max(level, lv, key=lambda v: order[v]); why.append(msg)
    out = {"date": date}
    hrv, lo, hi = m.get("hrv"), m.get("hrv_low"), m.get("hrv_high")
    if hrv is not None and lo is not None:
        out["hrv"] = {"ms": hrv, "normal": [lo, hi], "baseline": m.get("hrv_baseline")}
        if hrv < lo:
            prev = days.get((dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()) or {}
            twice = prev.get("hrv") is not None and prev.get("hrv_low") is not None and prev["hrv"] < prev["hrv_low"]
            worse("rest" if twice else "easy", f"HRV {hrv:.0f} ms, under your normal {lo:.0f}-{hi:.0f}"
                  + (" two mornings running" if twice else ""))
    rhr = m.get("resting_hr")
    if rhr is not None:
        before = [v["resting_hr"] for d, v in days.items() if d < date and v.get("resting_hr") is not None
                  and d >= (dt.date.fromisoformat(date) - dt.timedelta(days=14)).isoformat()]
        norm = statistics.median(before) if len(before) >= 3 else None
        out["resting_hr"] = {"bpm": rhr, "normal": norm}
        if norm is not None and rhr >= norm + 8:
            worse("rest", f"resting heart rate {rhr:.0f}, {rhr - norm:.0f} above your normal {norm:.0f}")
        elif norm is not None and rhr >= norm + 5:
            worse("easy", f"resting heart rate {rhr:.0f}, {rhr - norm:.0f} above your normal {norm:.0f}")
    sl = m.get("sleep_min")
    if sl is not None:
        out["sleep_min"] = sl
        if sl < 240:
            worse("easy", f"only {_hm(sl)} of sleep - recovery runs short on nights like that")
        elif sl < 300:
            worse("easy", f"{_hm(sl)} of sleep")
    out.update(level=level, why=why)
    return out
