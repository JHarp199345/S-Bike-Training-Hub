"""onboarding.py - the welcome page's orientation: the rider's numbers and where they're starting from.

The answers set the starting points the models need before there's any history:
  weight, resting and maximum heart rate (maximum estimated from age as 208 - 0.7 x age when not known)
  a starting usual week per body system, from experience in each sport and whether the rider starts fresh or
      loaded (sore joints, a heavy block behind them: everything starts 30% more cautious)
  known numbers (FTP, critical swim speed) recorded as the rider's own, until a test replaces them
  the lifting unit, and starter rules for the Rules tab
The usual weeks are starting estimates: check-ins, follow-ups and the Sunday check-in retune them.
"""
import datetime as dt
import json
import re
from pathlib import Path

SPORTS = ("bike", "run", "swim", "lift")
LEVELS = ("new", "returning", "regular")
# a usual week per system, in the load model's points (100 engine points = an hour at threshold; a 5 km jog = 40
# impact points), by experience - deliberately on the cautious side
ENGINE = {"new": 150, "returning": 250, "regular": 400}
IMPACT = {"new": 40, "returning": 80, "regular": 160}
MUSCLE = {"new": 60, "returning": 100, "regular": 160}
LOADED = 0.7


def first_run(base):
    """No setup done, no check-ins and no activities yet: show the welcome."""
    base = Path(base)
    try:
        if json.loads((base / "profile.json").read_text()).get("onboarded"):
            return False
    except (OSError, ValueError):
        pass
    try:
        if json.loads((base / "coach.json").read_text()).get("checkins"):
            return False
    except (OSError, ValueError):
        pass
    acts, rides = base / "activities", base / "rides"
    if acts.exists() and (any(acts.glob("*.fit")) or any(acts.glob("*.tcx"))):
        return False
    if rides.exists() and any(f.stat().st_size > 400 for f in rides.glob("ride_*.csv")):
        return False                                      # rides on the bike already
    return True


def _mmss(v):
    if v in (None, ""):
        return None
    m = re.fullmatch(r"\s*(\d+):(\d{1,2})\s*", str(v))
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return float(v)


def apply(base, form):
    """Save the orientation. Returns a summary of what was set, for the welcome."""
    import coach, lifting, rider
    base = Path(base)
    unit = form.get("unit") if form.get("unit") in ("lb", "kg") else "lb"
    to_kg = 0.45359237 if unit == "lb" else 1.0
    sports = [s for s in (form.get("sports") or []) if s in SPORTS]
    exp = {s: form.get("experience", {}).get(s) for s in sports}
    exp = {s: (v if v in LEVELS else "new") for s, v in exp.items()}
    start = "loaded" if form.get("start") == "loaded" else "fresh"
    p = rider.load(base / "profile.json")
    done = []
    if form.get("weight"):
        w = float(form["weight"]) * to_kg
        if not 30 <= w <= 250:
            raise ValueError("weight looks wrong")
        p["weight_kg"] = round(w, 1)
        done.append(f"weight {p['weight_kg']} kg")
    age = int(form["age"]) if form.get("age") else None
    if age and not 10 <= age <= 100:
        raise ValueError("age 10-100")
    if age:
        p["age"] = age
    if form.get("hr_rest"):
        p["hr_rest"] = max(30, min(120, int(form["hr_rest"])))
        done.append(f"resting heart rate {p['hr_rest']}")
    if form.get("hr_max"):
        p["hr_max"] = max(120, min(230, int(form["hr_max"])))
        done.append(f"maximum heart rate {p['hr_max']}")
    elif age:
        p["hr_max"] = round(208 - 0.7 * age)
        done.append(f"maximum heart rate {p['hr_max']} (estimated from age)")
    p["return_to_run"] = bool(form.get("return_to_run"))          # coming back from a running injury: the careful protocol
    p.update(sports=sports, experience=exp, start_state=start, smart_bike=bool(form.get("smart_bike")),
             onboarded=dt.date.today().isoformat())
    # starting capacities
    mult = LOADED if start == "loaded" else 1.0
    best = lambda keys: max((LEVELS.index(exp[k]) for k in keys if k in exp), default=None)
    note = f"starting estimate from the welcome setup ({start}); your reports retune it"
    cal = p.setdefault("load_calibration", {})
    e = best(sports)
    if e is not None:
        cal["engine"] = {"usual_week": round(ENGINE[LEVELS[e]] * mult), "note": note, "set": dt.date.today().isoformat()}
    if "run" in exp:
        cal["impact"] = {"usual_week": round(IMPACT[exp["run"]] * mult), "note": note, "set": dt.date.today().isoformat()}
    m = best([k for k in ("bike", "run", "lift") if k in exp])
    if m is not None:
        cal["muscle"] = {"usual_week": round(MUSCLE[LEVELS[m]] * mult), "note": note, "set": dt.date.today().isoformat()}
    if cal:
        done.append("starting usual weeks: " + ", ".join(f"{k} {v['usual_week']}" for k, v in cal.items() if "welcome" in (v.get("note") or "")))
    rider.save(p)
    ftp = form.get("ftp")
    if ftp:
        rider.set_ftp(rider.load(base / "profile.json"), int(ftp), "your own number (welcome setup)")
        done.append(f"FTP {int(ftp)} W")
    d = coach.load(base / "coach.json")
    import calibration
    if ftp:
        calibration.record(d, "ftp", int(ftp), "manual", note="your own number (welcome setup)")
    css = _mmss(form.get("css"))
    if css:
        calibration.record(d, "swim_css", css, "manual", note="your own number (welcome setup)")
        done.append(f"swim pace {int(css // 60)}:{int(css % 60):02d} per 100 m")
    k5 = _mmss(form.get("run5k"))
    if k5:
        p = rider.load(base / "profile.json"); p["run_5k_s"] = int(k5); rider.save(p)
        done.append(f"5K {int(k5 // 60)}:{int(k5 % 60):02d}")
    lifting.state(d)["unit"] = unit
    for line in (form.get("rules") or []):
        if str(line).strip():
            lifting.add_rule(d, str(line).strip())
            done.append(f"rule: {str(line).strip()}")
    coach.save(d)
    nxt = []
    nxt.append("Import your watch files (drop .fit or .tcx files into the activities folder, or ask your AI to import them)")
    nxt.append("Do your first check-in on the Coach page")
    nxt.append("Connect your AI assistant")
    if start == "loaded" and "run" in sports:
        nxt.insert(0, "Before your first run: the hop test on the Today tab (10 pain-free single-leg hops on each leg)")
    return {"set": done, "next": nxt, "start": start, "sports": sports}


def current(base):
    import rider
    p = rider.load(Path(base) / "profile.json")
    return {k: p.get(k) for k in ("weight_kg", "age", "hr_rest", "hr_max", "sports", "experience", "start_state",
                                  "smart_bike", "onboarded", "ftp", "return_to_run")}
