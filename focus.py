"""focus.py - what today's riding is coaching for: a cadence range and a watt range.

Asked for on 2026-09-28: the gear should balance resistance so the ride stays
easy but still makes the watts, with cadence held where the coaching wants it.
The cadence range is a coaching choice, not a constant - 65-80 rpm builds the
habit of turning the pedals at that rhythm; a "grit" day wants the opposite
(bigger gear, lower cadence, more force), a leg-speed day faster and lighter.
For the same watts, cadence and resistance trade against each other, so each
focus is a pair of ranges. Auto-shift steers toward both (autoshift.py), and
the ride view shows where you are.

A focus is set per day in the coach plan (coach.set_plan(..., focus=)) as a
preset key or a custom {"name", "rpm": [lo, hi], "watts": [lo, hi] | "pct": [lo, hi]}.
With none set, the day's verdict picks: rest -> recovery, otherwise cadence habit.
"""

PRESETS = {
    "cadence":  {"name": "Cadence habit", "rpm": (65, 80), "pct": (0.56, 0.75),
                 "builds": "the rhythm of 65-80 rpm, and aerobic base (zone 2)"},
    "grit":     {"name": "Grit / force", "rpm": (50, 65), "pct": (0.76, 0.90),
                 "builds": "leg strength: a bigger gear at lower cadence (loads the leg muscles more)"},
    "speed":    {"name": "Leg speed", "rpm": (85, 100), "pct": (0.50, 0.67),
                 "builds": "smooth, fast pedalling at a light load"},
    "recovery": {"name": "Recovery spin", "rpm": (70, 85), "pct": (0.40, 0.55),
                 "builds": "blood flow without adding load"},
    "off":      {"name": "Cadence only", "rpm": None, "pct": None,
                 "builds": "no watt target: auto-shift keeps the cadence range only"},
}


class BadFocus(ValueError):
    pass


def _pair(v, lo, hi, what, gap):
    try:
        a, b = float(v[0]), float(v[1])
    except (TypeError, ValueError, IndexError, KeyError):
        raise BadFocus(f"{what} is [low, high]")
    if not (lo <= a < b <= hi) or b - a < gap:
        raise BadFocus(f"{what} must be between {lo} and {hi}, low below high, at least {gap} apart")
    return (round(a), round(b))


def check(f):
    """Validate a focus as stored in a plan: a preset key, a custom dict, or None. Returns what to store."""
    if f is None or f == "":
        return None
    if isinstance(f, str):
        if f not in PRESETS:
            raise BadFocus(f"focus is one of {', '.join(PRESETS)} or a custom {{name, rpm, watts}}")
        return f
    if not isinstance(f, dict):
        raise BadFocus("focus is a preset name or {name, rpm, watts}")
    out = {"name": str(f.get("name") or "Custom")[:40], "rpm": list(_pair(f.get("rpm"), 30, 130, "rpm", 8))}
    if f.get("watts") is not None:
        out["watts"] = list(_pair(f["watts"], 30, 800, "watts", 10))
    elif f.get("pct") is not None:
        out["pct"] = list(_pair([x * 100 for x in f["pct"]], 20, 150, "pct (of FTP)", 5))
        out["pct"] = [x / 100 for x in out["pct"]]
    return out


def resolve(f, ftp, default_rpm=(65, 80), verdict=None, levels=None):
    """The ranges to ride today: {key, name, rpm: [lo, hi], watts: [lo, hi] | None, builds}.
    levels: {preset key: {rpm, pct?}} - the rider's step on each skill ladder (skills.levels_for)."""
    if f is None:
        f = "recovery" if verdict == "rest" else "cadence"
    if isinstance(f, str):
        p = PRESETS.get(f, PRESETS["cadence"])
        key = f if f in PRESETS else "cadence"
        rpm = p["rpm"] or default_rpm
        if key == "cadence":
            rpm = default_rpm                # the rider's cadence range (the bridge's --cadence-low/high)
        pct = p["pct"]
        lv = (levels or {}).get(key)
        if lv:                               # the rider's step on this skill's ladder
            rpm, pct = lv.get("rpm", rpm), lv.get("pct", pct)
        watts = [round(pct[0] * ftp), round(pct[1] * ftp)] if pct else None
        return {"key": key, "name": p["name"], "rpm": list(rpm), "watts": watts, "builds": p["builds"]}
    watts = f.get("watts") or ([round(f["pct"][0] * ftp), round(f["pct"][1] * ftp)] if f.get("pct") else None)
    return {"key": "custom", "name": f["name"], "rpm": list(f["rpm"]), "watts": watts and list(watts),
            "builds": "a custom range"}


def label(f):
    return f"{f['name']}: {f['rpm'][0]}-{f['rpm'][1]} rpm" + (f", {f['watts'][0]}-{f['watts'][1]} W" if f["watts"] else "")


class Tracker:
    """Seconds in range while pedalling (not in ERG), and a hint when out of it."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.secs = self.rpm_in = self.watts_in = self.both_in = 0

    def add(self, f, cadence, power):
        if cadence < 20:
            return
        self.secs += 1
        r = f["rpm"][0] <= cadence <= f["rpm"][1]
        w = f["watts"] is None or f["watts"][0] <= power <= f["watts"][1]
        self.rpm_in += r
        self.watts_in += w
        self.both_in += r and w

    def status(self, f, cadence, power, limited=None):
        pct = lambda n: round(100 * n / self.secs) if self.secs else None
        r_ok = f["rpm"][0] <= cadence <= f["rpm"][1] if cadence >= 20 else None
        w = f["watts"]
        w_ok = None if (w is None or cadence < 20) else w[0] <= power <= w[1]
        hint = ""
        if cadence >= 20:
            if cadence < f["rpm"][0]:
                hint = "spin a little faster"
            elif cadence > f["rpm"][1]:
                hint = "settle the legs a little"
            elif w and power > w[1]:
                hint = ("the climb is steeper than today's range - ease off or ride it out" if limited == "easiest"
                        else "ease off a touch")
            elif w and power < w[0]:
                hint = ("descending - the hardest gear can't reach the range" if limited == "hardest"
                        else "press a little harder")
        return {**f, "rpm_ok": r_ok, "watts_ok": w_ok, "hint": hint, "seconds": self.secs,
                "in_range": {"rpm": pct(self.rpm_in), "watts": pct(self.watts_in), "both": pct(self.both_in)}}


def parse_label(text):
    """Back from an event line 'Focus - Name: 65-80 rpm, 101-135 W' to {name, rpm, watts}."""
    import re
    m = re.match(r"Focus - (.+): (\d+)-(\d+) rpm(?:, (\d+)-(\d+) W)?$", text)
    if not m:
        return None
    return {"name": m.group(1), "rpm": [int(m.group(2)), int(m.group(3))],
            "watts": [int(m.group(4)), int(m.group(5))] if m.group(4) else None}


def for_ride(rows, events):
    """Time in range over a ride, from its seconds (report.load) and the focus events in effect at each one.
    ERG seconds and coasting don't count. None if the ride had no focus."""
    import datetime as dt
    marks = sorted((dt.datetime.fromisoformat(t), f) for t, e in events if (f := parse_label(e)))
    if not marks:
        return None
    tr, cur, i, names = Tracker(), None, 0, []
    for r in rows:
        while i < len(marks) and marks[i][0] <= r["t"]:
            cur = marks[i][1]; i += 1
            if cur["name"] not in names:
                names.append(cur["name"])
        if cur is None:
            cur = marks[0][1]
            names = names or [cur["name"]]
        if r.get("erg") or r["cadence"] is None or r["power"] is None:
            continue
        tr.add(cur, r["cadence"], r["power"])
    if not tr.secs:
        return None
    pct = lambda n: round(100 * n / tr.secs)
    watts = any(f["watts"] for _, f in marks)
    return {"focus": " then ".join(names), "minutes": round(tr.secs / 60, 1), "rpm_pct": pct(tr.rpm_in),
            "watts_pct": pct(tr.watts_in) if watts else None, "both_pct": pct(tr.both_in) if watts else pct(tr.rpm_in)}
