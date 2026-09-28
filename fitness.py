"""fitness.py - fitness, fatigue and form from power (the Performance Management Chart).

COROS works these out from heart rate, which can under-read bike rides (HR
stays low on the bike). Power is the direct measure, so:

  Training load of a ride (TSS) = hours x IF^2 x 100, where
      NP (normalized power) = 4th-power mean of the 30-s rolling average watts
      IF (intensity)        = NP / FTP on the day of the ride
  An hour at exactly FTP is 100.

  Fitness (CTL) = load averaged over ~6 weeks (exponential, 42-day constant)
  Fatigue (ATL) = load averaged over ~1 week  (7-day constant)
  Form    (TSB) = yesterday's fitness - yesterday's fatigue

Every day counts, rides or not: a rest day is a zero, so fatigue drops fast
and fitness slowly - that's what makes form rise after a rest.

Only bridge rides (the ride files) count: runs and swims aren't in here.
"""
import datetime as dt
import json
import math
from pathlib import Path

import bests
import rider

CTL_DAYS, ATL_DAYS = 42, 7


def normalized_power(seconds):
    """NP from bests.ride_seconds output (a None splits the ride at a stop)."""
    segs, cur = [], []
    for p in seconds:
        if p is None:
            segs.append(cur); cur = []
        else:
            cur.append(p[1])
    segs.append(cur)
    fourth, n = 0.0, 0
    for seg in segs:
        if len(seg) < 30:
            fourth += sum(w ** 4 for w in seg); n += len(seg)   # short bits: their own watts
            continue
        run = sum(seg[:30])
        for i in range(30, len(seg) + 1):
            fourth += (run / 30) ** 4; n += 1
            if i < len(seg):
                run += seg[i] - seg[i - 30]
    return (fourth / n) ** 0.25 if n else 0.0


def ftp_on(profile, day):
    """The FTP in force on that day, from the profile's history."""
    for h in sorted(profile.get("history", []), key=lambda h: h["until"]):
        if day.isoformat() < h["until"]:
            return h["ftp"]
    return profile["ftp"]


def ride_load(path, profile):
    """{'ride', 'date', 'minutes', 'np', 'avg', 'if', 'tss', 'ftp'} for one ride file, or None."""
    secs = bests.ride_seconds(path)
    pts = [p for p in secs if p is not None]
    moving = [p for p in pts if p[1] > 0]
    if len(moving) < 60:                                   # under a minute of pedalling: not a ride
        return None
    day = dt.date.fromtimestamp(pts[0][0])
    ftp = ftp_on(profile, day)
    np_ = normalized_power(secs)
    hours = len(pts) / 3600
    iff = np_ / ftp
    return {"ride": Path(path).stem, "date": day.isoformat(),
            "start": dt.datetime.fromtimestamp(pts[0][0]).strftime("%H:%M"),
            "minutes": round(len(pts) / 60, 1), "np": round(np_), "avg": round(sum(p[1] for p in pts) / len(pts)),
            "if": round(iff, 2), "tss": round(hours * iff * iff * 100, 1), "ftp": ftp}


def all_rides(rides_dir, profile, cache_path=None):
    """Load of every ride; finished rides are cached (by file size) so this stays quick."""
    cache = {}
    if cache_path:
        try:
            cache = json.loads(Path(cache_path).read_text())
        except (OSError, ValueError):
            cache = {}
    out, fresh = [], {}
    for p in sorted(Path(rides_dir).glob("ride_*.csv")):
        if p.name.endswith(("_events.csv", "_report.csv")):
            continue
        key = f"{p.stem}:{p.stat().st_size}:{profile['ftp']}"
        r = cache.get(key) if key in cache else ride_load(p, profile)
        fresh[key] = r
        if r:
            out.append(r)
    if cache_path:
        try:
            Path(cache_path).write_text(json.dumps(fresh))
        except OSError:
            pass
    return out


def chart(rides, today=None, ahead=14):
    """Day by day: load, fitness, fatigue, form - from the first ride to today,
    then `ahead` days of rest projected (dashed on the chart)."""
    today = today or dt.date.today()
    if not rides:
        return []
    by_day = {}
    for r in rides:
        by_day[r["date"]] = by_day.get(r["date"], 0) + r["tss"]
    day = min(dt.date.fromisoformat(d) for d in by_day)
    ctl = atl = 0.0
    kc, ka = 1 - math.exp(-1 / CTL_DAYS), 1 - math.exp(-1 / ATL_DAYS)
    days = []
    while day <= today + dt.timedelta(days=ahead):
        tsb = ctl - atl                                         # form = yesterday's fitness - fatigue
        tss = by_day.get(day.isoformat(), 0.0)
        ctl += (tss - ctl) * kc
        atl += (tss - atl) * ka
        days.append({"date": day.isoformat(), "tss": round(tss, 1), "ctl": round(ctl, 1),
                     "atl": round(atl, 1), "tsb": round(tsb, 1), "future": day > today})
        day += dt.timedelta(days=1)
    return days


def advice(d):
    """What today's numbers mean, in plain words."""
    tsb, ctl = d["tsb"], d["ctl"]
    if tsb < -30:
        return "Very tired: a lot of load recently. An easy day or rest would pay off."
    if tsb < -10:
        return "Training hard - normal in a build week. Keep easy days easy."
    if tsb <= 5:
        return "Balanced: training and recovering about equally."
    if tsb <= 25:
        return "Fresh: a good day for a hard effort, a test or an event."
    return "Very fresh - fitness will start to slip if this goes on long." if ctl > 10 else \
        "Rested. Fitness builds from here, ride by ride."


def summary(rides_dir, today=None):
    profile = rider.load(Path(rides_dir).resolve().parent / "profile.json")
    rides = all_rides(rides_dir, profile, Path(rides_dir).resolve().parent / "fitness_cache.json")
    days = chart(rides, today)
    now = next((d for d in reversed(days) if not d["future"]), None)
    week = [r for r in rides if dt.date.fromisoformat(r["date"]) > (today or dt.date.today()) - dt.timedelta(days=7)]
    return {"ftp": profile["ftp"], "ftp_source": profile["ftp_source"], "days": days,
            "rides": list(reversed(rides))[:60], "today": now,
            "advice": advice(now) if now else "Ride with the bridge and your fitness starts building here.",
            "week": {"rides": len(week), "tss": round(sum(r["tss"] for r in week)),
                     "hours": round(sum(r["minutes"] for r in week) / 60, 1)}}
