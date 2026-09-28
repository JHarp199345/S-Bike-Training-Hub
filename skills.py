"""skills.py - progressions and regressions, skill by skill (after Michael Boyle's approach).

Each skill is a ladder of concrete steps. You earn the next step by doing the one
you're on well, twice; you drop a step when it's clearly beyond you, twice; and on
a day you're not recovered you ride one step down without losing your place.
Evidence only counts from when you reached the step, so each step is earned.

  cadence   the cadence-habit range: 65-80 -> 70-85 -> 75-90 -> 80-95 -> 85-100 rpm.
            Up: two rides on it with 75%+ of the time in range (20+ min, felt 7/10 or
            easier). Down: two under 50%.
  speed     leg speed: 85-100 -> 90-105 -> 95-110 rpm, the same way.
  grit      big-gear work at low cadence, harder and longer: 3x3 min -> 3x5 -> 3x8 ->
            2x12 -> 2x15, watts and cadence per step. Up: two grit rides 70%+ in range
            at 7/10 or easier. Down: under 45% in range, or 9/10+.
  climbing  climb time goals, from 110% of your best time on a climb down to 94%.
            Up: two goals made in a row. Down: a goal missed by more than 10%.
  running   the way back to running: walking only -> 10x(1 min jog, 2 walk) -> 8x(2/1)
            -> 6x(3/1) -> 20 min jog -> 30 min. Up: running cleared, and the feet and
            legs checked in 3/10 or better the two mornings after the last run.
            Down to walking only whenever running is on rest.

The bike ladders feed the day's focus (focus.py); the climbing step sets climb-goal
times; the running step is what an 'easy' running day means.
"""
import datetime as dt

LADDERS = {
    "cadence": {"name": "Cadence habit", "focus": "Cadence habit",
                "levels": [{"rpm": [65, 80]}, {"rpm": [70, 85]}, {"rpm": [75, 90]}, {"rpm": [80, 95]}, {"rpm": [85, 100]}]},
    "speed": {"name": "Leg speed", "focus": "Leg speed",
              "levels": [{"rpm": [85, 100]}, {"rpm": [90, 105]}, {"rpm": [95, 110]}]},
    "grit": {"name": "Grit / force", "focus": "Grit / force",
             "levels": [{"rpm": [55, 65], "pct": [0.76, 0.85], "sets": "3 x 3 min"},
                        {"rpm": [52, 62], "pct": [0.78, 0.88], "sets": "3 x 5 min"},
                        {"rpm": [50, 60], "pct": [0.80, 0.90], "sets": "3 x 8 min"},
                        {"rpm": [50, 60], "pct": [0.85, 0.92], "sets": "2 x 12 min"},
                        {"rpm": [48, 58], "pct": [0.88, 0.95], "sets": "2 x 15 min"}]},
    "climbing": {"name": "Climb pace",
                 "levels": [{"goal_factor": 1.10}, {"goal_factor": 1.05}, {"goal_factor": 1.0},
                            {"goal_factor": 0.97}, {"goal_factor": 0.94}]},
    "running": {"name": "Running return",
                "levels": [{"run": "walking only"}, {"run": "10 x (1 min easy jog, 2 min walk)"},
                           {"run": "8 x (2 min jog, 1 min walk)"}, {"run": "6 x (3 min jog, 1 min walk)"},
                           {"run": "20 min easy jog"}, {"run": "30 min easy jog"}]},
}


def describe(skill, lv):
    L = LADDERS[skill]["levels"][lv]
    if "rpm" in L and "pct" in L:
        return f"{L['sets']} at {round(L['pct'][0] * 100)}-{round(L['pct'][1] * 100)}% FTP, {L['rpm'][0]}-{L['rpm'][1]} rpm"
    if "rpm" in L:
        return f"{L['rpm'][0]}-{L['rpm'][1]} rpm"
    if "goal_factor" in L:
        return f"climb goals at {round(L['goal_factor'] * 100)}% of your best time"
    return L["run"]


def state(d):
    """The rider's place on each ladder: {skill: {level, since, history}} (kept in coach.json)."""
    sk = d.setdefault("skills", {})
    for k in LADDERS:
        sk.setdefault(k, {"level": 0, "since": None, "history": []})
    return sk


def step_today(d, date=None, morning_level=None):
    """-1 on a day you're not recovered (the watch overnight or your check-in says easy or rest): one step down."""
    date = date or dt.date.today().isoformat()
    c = d.get("checkins", {}).get(date) or {}
    if morning_level in ("easy", "rest") or c.get("verdict") in ("easy", "rest"):
        return -1
    return 0


def levels_for(d, step=0):
    """What each focus should use today: {focus key: level dict} - the rider's steps, `step` from them."""
    sk = state(d)
    out = {}
    for key, skill in (("cadence", "cadence"), ("speed", "speed"), ("grit", "grit")):
        n = len(LADDERS[skill]["levels"])
        out[key] = LADDERS[skill]["levels"][max(0, min(n - 1, sk[skill]["level"] + step))]
    return out


def set_level(d, skill, level, why, date=None):
    sk = state(d)
    if skill not in LADDERS:
        raise ValueError(f"skill is one of {', '.join(LADDERS)}")
    n = len(LADDERS[skill]["levels"])
    level = max(0, min(n - 1, int(level)))
    old = sk[skill]["level"]
    if level == old:
        return None
    date = date or dt.date.today().isoformat()
    sk[skill].update(level=level, since=date)
    ev = {"date": date, "from": old, "to": level, "why": why, "step": describe(skill, level)}
    sk[skill]["history"] = (sk[skill]["history"] + [ev])[-30:]
    return ev


def _ride_evidence(rides_dir, since, cache={}):
    """Recent rides: {id, date, focus name, minutes, rpm_pct, both_pct, rpe} (cached by file time)."""
    import report, story, focus as focus_mod
    from pathlib import Path
    out = []
    for p in sorted(Path(rides_dir).glob("ride_*.csv")):
        if p.stem.count("_") != 2 or p.stem[5:15] < since:
            continue
        key = (str(p), p.stat().st_mtime_ns)
        if key not in cache:
            try:
                f = focus_mod.for_ride(report.load(p), story._events(p))
            except Exception:
                f = None
            cache[key] = f
        f = cache[key]
        if f and f["minutes"] >= 20:
            out.append({"id": p.stem, "date": p.stem[5:15], **f})
    return out


def evaluate(d, rides_dir, running_verdict=None, last_run=None, today=None):
    """Move each ladder on the evidence since its step was reached. Returns the changes made (and records them)."""
    today = today or dt.date.today().isoformat()
    sk = state(d)
    ratings = d.get("ratings", {})
    changes = []
    oldest = min((sk[k]["since"] or "2000-01-01") for k in sk)
    rides = _ride_evidence(rides_dir, (dt.date.fromisoformat(today) - dt.timedelta(days=42)).isoformat()
                           if oldest == "2000-01-01" else oldest)
    for r in rides:
        r["rpe"] = (ratings.get(r["id"]) or {}).get("rpe")

    def ladder(skill, pct_key, up_at, down_at, rpe_up=7, rpe_down=None):
        L, cur = LADDERS[skill], sk[skill]
        # rides on this focus since the step was reached (the day after: that day's ride earned it)
        mine = [r for r in rides if L["focus"] in r["focus"] and (cur["since"] is None or r["date"] > cur["since"])]
        last2 = mine[-2:]
        if len(last2) == 2 and all(r[pct_key] >= up_at and (r["rpe"] is None or r["rpe"] <= rpe_up) for r in last2):
            ev = set_level(d, skill, cur["level"] + 1, f"two {L['name'].lower()} rides {last2[0][pct_key]}% and "
                           f"{last2[1][pct_key]}% in range", today)
        elif (len(last2) == 2 and all(r[pct_key] < down_at for r in last2)) or \
                (rpe_down and last2 and last2[-1]["rpe"] and last2[-1]["rpe"] >= rpe_down):
            ev = set_level(d, skill, cur["level"] - 1, f"{L['name'].lower()}: " + (
                f"rated {last2[-1]['rpe']}/10" if rpe_down and last2[-1]["rpe"] and last2[-1]["rpe"] >= rpe_down
                else f"two rides under {down_at}% in range"), today)
        else:
            ev = None
        if ev:
            changes.append({"skill": skill, **ev})

    ladder("cadence", "rpm_pct", 75, 50)
    ladder("speed", "rpm_pct", 75, 50)
    ladder("grit", "both_pct", 70, 45, rpe_down=9)

    # climbing: the climb goals from route sessions
    import json
    from pathlib import Path
    goals = []
    for f in sorted(Path(rides_dir).glob("ride_*_session.json")):
        if sk["climbing"]["since"] and f.stem[5:15] < sk["climbing"]["since"]:
            continue
        try:
            goals += [g for g in json.loads(f.read_text()).get("results", []) if g["type"] == "climb_time"]
        except (OSError, ValueError):
            pass
    if goals:
        if len(goals) >= 2 and goals[-1]["made"] and goals[-2]["made"]:
            ev = set_level(d, "climbing", sk["climbing"]["level"] + 1, "two climb goals made in a row", today)
        elif not goals[-1]["made"] and goals[-1]["took_s"] > 1.1 * goals[-1]["goal_s"]:
            ev = set_level(d, "climbing", sk["climbing"]["level"] - 1,
                           f"{goals[-1]['name']} missed by more than 10%", today)
        else:
            ev = None
        if ev:
            changes.append({"skill": "climbing", **ev})

    # running: walking only while running is on rest; up a step when cleared and the last run went down well
    run = sk["running"]
    if running_verdict == "rest" and run["level"] > 0:
        ev = set_level(d, "running", 0, "running is on rest (accumulated load over the limit)", today)
        if ev:
            changes.append({"skill": "running", **ev})
    elif running_verdict == "go":
        checks = d.get("checkins", {})
        after = [checks.get((dt.date.fromisoformat(last_run) + dt.timedelta(days=k)).isoformat()) or {}
                 for k in (1, 2)] if last_run else []
        if last_run and len(after) == 2 and all(c.get("feet") is not None and c["feet"] <= 3 and (c.get("legs") or 0) <= 3
                                                for c in after) and run.get("promoted_for") != last_run:
            ev = set_level(d, "running", run["level"] + 1, "the last run went down well (feet and legs 3/10 or better)", today)
            if ev:
                run["promoted_for"] = last_run
                changes.append({"skill": "running", **ev})
    return changes


def summary(d, step=0):
    """Each ladder: where you are, today's step (after a readiness step down), the next one, what's changed lately."""
    sk = state(d)
    out = {}
    for k, L in LADDERS.items():
        n = len(L["levels"])
        lv = sk[k]["level"]
        today = max(0, min(n - 1, lv + (step if k in ("cadence", "speed", "grit") else 0)))
        out[k] = {"name": L["name"], "level": lv + 1, "of": n, "now": describe(k, lv), "today": describe(k, today),
                  "stepped_down_today": today != lv, "next": describe(k, lv + 1) if lv + 1 < n else None,
                  "since": sk[k]["since"], "history": sk[k]["history"][-3:]}
    return out
