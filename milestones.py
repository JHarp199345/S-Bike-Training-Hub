"""milestones.py - streaks, lifetime totals and milestones, from the ride files.

Everything is worked out again from the rides themselves (each ride's numbers
are cached by file size), in date order, so every milestone knows exactly
which ride earned it - nothing to keep in sync, nothing to lose.

  Day streak    days in a row with a ride of 10+ min (today still counts if
                you rode yesterday - the streak isn't broken until tomorrow)
  Week streak   Mon-Sun weeks in a row with the weekly goal met (default 3
                rides of 20+ min; profile.json "weekly_rides"); the current
                week is "in progress", never a break
  Milestones    tiers of rides, distance, climbing, hours, calories, single-
                ride length and climbing, firsts, and streaks - with fun
                comparisons (Eiffel Tower, Alpe d'Huez, Everest, LA-San Diego)
"""
import datetime as dt
import json
from pathlib import Path

DAY_MIN, WEEK_MIN = 10, 20
EIFFEL, ALPE, EVEREST = 330, 1071, 8849

# (key, stat, thresholds, name template, icon)
TIERS = [
    ("rides", "rides", [1, 5, 10, 25, 50, 100, 250, 500], "{n} rides", "🚴"),
    ("km", "km", [50, 100, 250, 500, 1000, 2500, 5000, 10000], "{n:,} km ridden", "🛣"),
    ("climb", "climb_m", [EIFFEL, ALPE, 2500, 5000, EVEREST, 20000, 50000, 100000], "{n:,} m climbed", "⛰"),
    ("hours", "hours", [5, 10, 25, 50, 100, 250, 500], "{n} hours in the saddle", "⏱"),
    ("kcal", "kcal", [1000, 5000, 10000, 25000, 50000, 100000], "{n:,} kcal burned", "🔥"),
    ("long", "longest_min", [30, 60, 90, 120, 180], "{h} ride", "📏"),
    ("bigclimb", "biggest_climb", [100, 250, 500, 1000, 1500], "{n:,} m in one ride", "🏔"),
    ("daystreak", "best_day_streak", [3, 7, 14, 30, 60, 100], "{n}-day streak", "📅"),
    ("weekstreak", "best_week_streak", [2, 4, 8, 12, 26, 52], "{n} weeks on goal", "🗓"),
]
FIRSTS = [("first_route", "First ride on a real road", "🗺"), ("first_workout", "First workout", "🎯"),
          ("first_test", "First FTP test", "🧪"), ("first_ghost_win", "First win against my ghost", "👻"),
          ("first_pb", "First personal best", "🏆")]
TRIPS = [(30, "Santa Monica to Malibu and back"), (190, "LA to San Diego"), (465, "Paris to Lyon"),
         (615, "LA to San Francisco"), (1000, "across France"), (4500, "coast to coast across the US"),
         (40075, "around the world")]


def _label(tier, n):
    if tier[0] == "rides" and n == 1:
        return "First ride"
    if tier[0] == "long":
        return f"{n // 60} h ride" if n % 60 == 0 and n >= 60 else f"{n} min ride"
    return tier[3].format(n=n, h=n)


def equivalents(totals):
    """Fun comparisons for the totals."""
    out = []
    c = totals["climb_m"]
    if c >= EVEREST:
        out.append(f"Everest ×{c / EVEREST:.1f}")
    elif c >= ALPE:
        out.append(f"Alpe d'Huez ×{c / ALPE:.1f}")
    elif c > 0:
        out.append(f"Eiffel Tower ×{c / EIFFEL:.1f}")
    km = totals["km"]
    done = [t for t in TRIPS if km >= t[0]]
    nxt = next((t for t in TRIPS if km < t[0]), None)
    if done:
        out.append(f"{done[-1][1]} ✓")
    if nxt:
        out.append(f"{nxt[0] - km:,.0f} km to {nxt[1]}")
    if totals["kcal"] >= 250:
        n = totals["kcal"] // 250
        out.append(f"{n:,} donut{'s' if n != 1 else ''} 🍩")
    return out


def ride_facts(path, cache):
    """Distance, climbing, time, calories and what happened, for one ride (cached by size)."""
    p = Path(path)
    key = f"{p.stem}:{p.stat().st_size}"
    if key in cache:
        return cache[key]
    import report
    import story
    facts = None
    try:
        rows = report.load(p)
        events = story._events(p)
        a = report.analyse(rows, events)
        if a:
            ev = [e for _, e in events]
            moving = sum(1 for r in rows if r["power"] > 0)
            facts = {"ride": p.stem, "date": a["start"].date().isoformat(), "minutes": round(moving / 60, 1),
                     "km": round(a["km"], 2), "climb_m": round(a["climb_m"]),
                     "kcal": round(a["avg_w"] * a["minutes"] * 60 / 1000 / 4.184 / 0.24),
                     "route": any(e.startswith("Route started:") for e in ev),
                     "workout": any(e.startswith("Workout started:") for e in ev),
                     "test": any(e.startswith("FTP test done") for e in ev),
                     "ghost_win": any(e.startswith("Ghost result:") and "ahead of" in e for e in ev),
                     "pb": any("personal best" in e for e in ev)}
    except Exception:
        facts = None
    cache[key] = facts
    return facts


def _week_start(d):
    return d - dt.timedelta(days=d.weekday())


def compute(rides_dir, weekly_goal=3, today=None, extra=None, exclude=None):
    """Totals, streaks, milestones earned (with the ride that earned each) and what's next.
    extra: the ride in progress as live facts, so milestones can be crossed mid-ride.
    exclude: a ride (file stem) to leave out - the bridge's own ride in progress."""
    today = today or dt.date.today()
    rides_dir = Path(rides_dir)
    cache_path = rides_dir.resolve().parent / "milestones_cache.json"
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    facts = []
    for p in sorted(rides_dir.glob("ride_*.csv")):
        if p.name.endswith(("_events.csv", "_report.csv")) or p.stem == exclude:
            continue
        f = ride_facts(p, cache)
        if f and f["minutes"] >= 1:
            facts.append(f)
    try:
        cache_path.write_text(json.dumps(cache))
    except OSError:
        pass
    if extra:
        facts = [f for f in facts if f["ride"] != extra["ride"]] + [extra]
    try:                                             # records set before live tracking existed count too
        import bests
        pb_rides = {l["ride"] for l in bests.load(bests.file_for(rides_dir))["log"]}
        for f in facts:
            f["pb"] = f.get("pb") or f["ride"] in pb_rides
    except Exception:
        pass
    facts.sort(key=lambda f: f["ride"])

    tot = {"rides": 0, "km": 0.0, "climb_m": 0, "hours": 0.0, "kcal": 0, "longest_min": 0, "biggest_climb": 0,
           "best_day_streak": 0, "best_week_streak": 0}
    earned, got = [], set()
    ride_days, week_rides = set(), {}

    def award(key, name, icon, f, value=None):
        if key not in got:
            got.add(key)
            earned.append({"key": key, "name": name, "icon": icon, "ride": f["ride"], "date": f["date"], "value": value})

    for f in facts:
        d = dt.date.fromisoformat(f["date"])
        tot["rides"] += 1
        tot["km"] += f["km"]; tot["climb_m"] += f["climb_m"]; tot["hours"] += f["minutes"] / 60; tot["kcal"] += f["kcal"]
        tot["longest_min"] = max(tot["longest_min"], f["minutes"])
        tot["biggest_climb"] = max(tot["biggest_climb"], f["climb_m"])
        if f["minutes"] >= DAY_MIN:
            ride_days.add(d)
        if f["minutes"] >= WEEK_MIN:
            week_rides[_week_start(d)] = week_rides.get(_week_start(d), 0) + 1
        # streaks as of this ride
        run, x = 0, d
        while x in ride_days:
            run += 1; x -= dt.timedelta(days=1)
        tot["best_day_streak"] = max(tot["best_day_streak"], run)
        wrun, w = 0, _week_start(d)
        if week_rides.get(w, 0) < weekly_goal:
            w -= dt.timedelta(days=7)                 # this week isn't done yet: count from last week
        while week_rides.get(w, 0) >= weekly_goal:
            wrun += 1; w -= dt.timedelta(days=7)
        if week_rides.get(_week_start(d), 0) >= weekly_goal and wrun == 0:
            wrun = 1
        tot["best_week_streak"] = max(tot["best_week_streak"], wrun)
        for tier in TIERS:
            for n in tier[2]:
                if tot[tier[1]] >= n:
                    award(f"{tier[0]}:{n}", _label(tier, n), tier[4], f, n)
        for key, flag in (("first_route", "route"), ("first_workout", "workout"), ("first_test", "test"),
                          ("first_ghost_win", "ghost_win"), ("first_pb", "pb")):
            if f.get(flag):
                name, icon = next((n, i) for k, n, i in FIRSTS if k == key)
                award(key, name, icon, f)

    # current streaks, as of today
    run, x = 0, today if today in ride_days else today - dt.timedelta(days=1)
    while x in ride_days:
        run += 1; x -= dt.timedelta(days=1)
    this_week = week_rides.get(_week_start(today), 0)
    wrun, w = 0, _week_start(today) - dt.timedelta(days=7)
    while week_rides.get(w, 0) >= weekly_goal:
        wrun += 1; w -= dt.timedelta(days=7)
    if this_week >= weekly_goal:
        wrun += 1
    streaks = {"days": run, "rode_today": today in ride_days, "best_days": tot["best_day_streak"],
               "weeks": wrun, "best_weeks": tot["best_week_streak"], "this_week": this_week, "goal": weekly_goal,
               "days_left_in_week": 6 - today.weekday()}

    # every badge, earned or not, with progress toward the locked ones
    badges = []
    for tier in TIERS:
        for n in tier[2]:
            key = f"{tier[0]}:{n}"
            e = next((x for x in earned if x["key"] == key), None)
            have = tot[tier[1]]
            badges.append({"key": key, "group": tier[0], "name": _label(tier, n), "icon": tier[4], "earned": e,
                           "progress": min(1.0, have / n), "have": round(have, 1), "need": n})
    for key, name, icon in FIRSTS:
        e = next((x for x in earned if x["key"] == key), None)
        badges.append({"key": key, "group": "firsts", "name": name, "icon": icon, "earned": e,
                       "progress": 1.0 if e else 0.0, "have": None, "need": None})
    nxt = sorted((b for b in badges if not b["earned"] and b["need"] and b["group"] not in ("long", "bigclimb")),
                 key=lambda b: -b["progress"])
    seen, next_up = set(), []
    for b in nxt:                                    # the closest one of each kind
        if b["group"] not in seen:
            seen.add(b["group"]); next_up.append(b)
    totals = {k: round(v, 1) if isinstance(v, float) else v for k, v in tot.items()}
    return {"totals": totals, "streaks": streaks, "earned": earned, "badges": badges, "next": next_up[:4],
            "equivalents": equivalents(totals), "weekly_goal": weekly_goal}


def new_on(ride, data):
    """The milestones this ride earned."""
    return [e for e in data["earned"] if e["ride"] == ride]
