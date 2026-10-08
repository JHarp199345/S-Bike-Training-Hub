"""planning_load.py - the plan's load outlook: the 3-day rate, the biggest day in the last 3 and the 28-day carried
load, recorded so far and projected through the planned sessions, beside phase targets. Read-only: it describes and
flags; the athlete and coach decide.

Each planned session gets an energy estimate:
  ride with planned power   mechanical kJ read as kcal (as for recorded rides)
  anything else             minutes x the athlete's own median kcal per minute for that sport over the last 90 days
                            (from the same primary energy estimates as the ledger), else a starting estimate

Phase targets (defaults the athlete and coach can change):
  base / maintain           3-day rate about the reference (typical) rate
  build / peak              reference x (1 + this week's report-gated step)
  recovery                  about 50-60% of the reference: the 3-day rate falls first, the 28-day load follows
  taper                     about 40-60% volume reduction (Bosquet et al. 2007)
  biggest day               at or below ~1.5x the typical training day unless a key session is planned (Foster 1998)

Starting capacities when there is little or no history (fewer than 14 days with recorded work):
  weekly training minutes from the activity guidelines by experience (WHO 2020: 150-300 min moderate a week; more
  for athletes already training), at an intensity in METs from the wearable's VO2max estimate when known
  (about 60% of VO2max; METs = VO2 / 3.5) or a default for the experience level, times body mass
  (1 MET ~ 1 kcal/kg/h; Ainsworth et al. 2011). The basis is always shown, and real history replaces it.
"""
import datetime as dt
import statistics

J_PER_KCAL = 4184
MIN_HISTORY_DAYS = 14
PEAK_CAP = 1.5
TARGETS = {"base": (0.9, 1.1), "maintain": (0.9, 1.1), "build": None, "peak": None,
           "recovery": (0.5, 0.6), "taper": (0.4, 0.6)}
START = {"new": (150, 4.0), "returning": (225, 5.0), "regular": (360, 6.0)}   # weekly minutes, default METs


def _date(x):
    return dt.date.fromisoformat(x) if isinstance(x, str) else x


def sport_rates(load, today, days=90):
    """Median primary kcal per minute by sport over the last `days` days, from recorded sessions."""
    start = (_date(today) - dt.timedelta(days=days - 1)).isoformat()
    by = {}
    for a in load.get("activities", []):
        kcal, minutes = a.get("energy_kcal"), a.get("minutes")
        if a.get("source") == "lifts" or not kcal or not minutes or not start <= a.get("date", "") <= str(today):
            continue
        by.setdefault({"bike": "ride"}.get(a["sport"], a["sport"]), []).append(kcal / minutes)
    return {s: {"kcal_per_min": statistics.median(v), "sessions": len(v)} for s, v in by.items()}


def starting(prof):
    """Reference daily energy (J) when history is thin, and how it was set."""
    level = max((prof.get("experience") or {}).values(), key=lambda v: ("new", "returning", "regular").index(v), default="new") \
        if prof.get("experience") else "new"
    minutes, mets = START.get(level, START["new"])
    basis = f"{level} athlete: {minutes} training min/week (WHO 2020 activity guidelines and above for athletes)"
    if prof.get("vo2max"):
        mets = round(0.6 * float(prof["vo2max"]) / 3.5, 1)
        basis += f", ~60% of your wearable's VO2max {prof['vo2max']} = {mets} METs"
    else:
        basis += f", {mets} METs default"
    kg = float(prof.get("weight_kg") or 80)
    kcal_week = minutes / 60 * mets * kg                       # 1 MET ~ 1 kcal/kg/h
    return {"daily_j": kcal_week / 7 * J_PER_KCAL, "kcal_per_min": mets * kg / 60, "level": level,
            "basis": basis + f" × {kg:g} kg (1 MET ≈ 1 kcal/kg/h). Replaced by your own history after {MIN_HISTORY_DAYS} days with work."}


def session_energy(s, rates, start):
    """(kcal, basis) for one planned session."""
    steps = (s.get("bike_plan") or {}).get("power_steps") or []
    if s.get("sport") == "ride" and steps and all(x.get("watts") is not None for x in steps):
        return sum(x["watts"] * x["minutes"] * 60 for x in steps) / 1000, "planned power"
    minutes = float(s.get("minutes") or 0)
    r = rates.get(s.get("sport"))
    if r:
        return minutes * r["kcal_per_min"], f"your {s['sport']} median {r['kcal_per_min']:.1f} kcal/min ({r['sessions']} sessions)"
    return minutes * start["kcal_per_min"], "starting estimate"


def outlook(d, load, prof, today, horizon=21, done=None):
    """Daily recorded + planned energy with rolling readings, phases, targets and flags, from 27 days back."""
    import training_block, progression
    today = _date(today)
    first, last = today - dt.timedelta(days=27 + 27), today + dt.timedelta(days=horizon)
    recorded = {}
    for a in load.get("activities", []):
        if a.get("source") == "lifts" or not a.get("energy_kcal"):
            continue
        recorded[a["date"]] = recorded.get(a["date"], 0.0) + a["energy_kcal"] * J_PER_KCAL
    history_days = sum(1 for k, v in recorded.items() if v > 0 and (today - dt.timedelta(days=89)).isoformat() <= k <= today.isoformat())
    rates, start = sport_rates(load, today), starting(prof)
    days, x = [], first
    while x <= last:
        key = x.isoformat()
        j, planned = (recorded.get(key, 0.0) if x <= today else 0.0), []
        if x >= today:
            sessions = training_block.sessions((d.get("plans") or {}).get(key) or {})
            if x == today and done:                         # today's finished sessions are already in the recorded energy
                import coach, copy
                sessions = coach.attach_completions(d, key, copy.deepcopy(sessions), copy.deepcopy(done.get(key, [])))
            for s in sessions:
                if s.get("skipped_id") or s.get("sport") in (None, "rest") or s.get("completion"):
                    continue
                kcal, basis = session_energy(s, rates, start)
                if kcal:
                    planned.append({"sport": s.get("sport"), "name": s.get("name"), "kcal": round(kcal), "basis": basis})
                    j += kcal * J_PER_KCAL
        days.append({"date": key, "j": j, "planned": planned, "future": x > today})
        x += dt.timedelta(days=1)
    # Reference: the typical daily rate and training day over the 28 days before today (or the starting estimate).
    past28 = [r for r in days if today - dt.timedelta(days=27) <= _date(r["date"]) <= today]
    if history_days >= MIN_HISTORY_DAYS:
        ref = sum(r["j"] for r in past28) / 28
        trained = sorted(r["j"] for r in past28 if r["j"] > 0)
        typical_day = statistics.median(trained) if trained else ref
        ref_basis = f"your last 28 days ({len(trained)} days with work)"
    else:
        ref, typical_day, ref_basis = start["daily_j"], start["daily_j"] * 7 / 3, "starting estimate: " + start["basis"]
    step = progression_step(d, today)
    import report_protocol
    held = report_protocol.holds(d, today)["impact_held"]
    out = []
    for i, r in enumerate(days):
        if _date(r["date"]) < today - dt.timedelta(days=27):
            continue
        w3 = days[max(0, i - 2):i + 1]
        w28 = days[max(0, i - 27):i + 1]
        rate3 = sum(x["j"] for x in w3) / 3
        peak = max(w3, key=lambda x: x["j"])
        phase = progression.context(d, r["date"], "ride")["phase"]
        band = TARGETS.get(phase, (0.9, 1.1)) or (1 + step["step"] - 0.02, 1 + step["step"] + 0.02)
        target = (ref * band[0], ref * band[1])
        flags = []
        if (r["future"] or r["date"] == today.isoformat()) and held and _date(r["date"]) <= today + dt.timedelta(days=1) \
                and any(p["sport"] in ("run", "walk") for p in r["planned"]):
            flags.append("running held by the bad-report protocol: re-check first")
        if r["future"] or r["date"] == today.isoformat():
            if rate3 > target[1] * 1.05:
                flags.append("3-day rate above the phase target")
            if peak["j"] > typical_day * PEAK_CAP and peak["date"] == r["date"]:
                flags.append(f"biggest day over {PEAK_CAP}× your typical training day")
        out.append({"date": r["date"], "future": r["future"], "energy_j": r["j"], "planned": r["planned"],
                    "rate3_j_per_day": rate3, "peak3": {"date": peak["date"], "j": peak["j"]},
                    "load28_j": sum(x["j"] for x in w28), "phase": phase,
                    "target_rate3": target, "flags": flags})
    return {"as_of": today.isoformat(), "well_tolerated": well_tolerated(d, today), "reference_rate_j_per_day": ref, "typical_training_day_j": typical_day,
            "reference_basis": ref_basis, "history_days": history_days, "sport_rates": rates, "build_step": step,
            "peak_cap": PEAK_CAP, "days": out,
            "basis": "Recorded days use the ledger's primary energy; planned sessions use planned power or your own "
                     "median kcal/min by sport. Phase bands are defaults: recovery 50-60% of the reference rate, "
                     "taper 40-60% (Bosquet et al. 2007), build steps gated by reports. Read-only: nothing is changed."}


def well_tolerated(d, today, days=90):
    """Sessions from the last `days` days that went as intended (or easier) without pain of 3+, with the 3-day rate
    and 28-day load they were done at (from frozen snapshots when present). The planner prefers these to meet a
    target, then varies them."""
    today = _date(today)
    start = (today - dt.timedelta(days=days - 1)).isoformat()
    groups = {}
    for key, f in (d.get("training_feedback") or {}).items():
        date = f.get("date") or key[:10]
        if not start <= date <= today.isoformat() or f.get("effort") not in ("as_intended", "too_easy"):
            continue
        if any((s.get("severity") or 0) >= 3 for s in f.get("symptoms") or []):
            continue
        snap = (f.get("snapshot") or {})
        g = groups.setdefault((f.get("sport"), f.get("session_name") or f.get("sport")), {"sport": f.get("sport"), "name": f.get("session_name"), "times": 0, "dates": [], "rates": []})
        g["times"] += 1
        g["dates"].append(date)
        if snap.get("context_3_days"):
            g["rates"].append(snap["context_3_days"]["cardio"]["j_per_day"])
    out = []
    for g in groups.values():
        out.append({"sport": g["sport"], "name": g["name"], "times": g["times"], "last": max(g["dates"]),
                    "at_rate3_j_per_day": statistics.median(g["rates"]) if g["rates"] else None})
    return sorted(out, key=lambda x: (x["times"], x["last"]), reverse=True)[:8]


def progression_step(d, today):
    """This week's build step (3-10%), gated by the last 7 days of reports. Pain or poor recovery holds it at 0."""
    import wellness, report_protocol
    today = _date(today)
    if report_protocol.holds(d, today)["increase_waits"]:
        return {"step": 0.0, "why": "a bad report in the last 7 days started a re-check: the next increase waits a week"}
    recent = [c for k, c in (d.get("checkins") or {}).items() if (today - dt.timedelta(days=6)).isoformat() <= k <= today.isoformat()]
    pains = [v for c in recent for v in (c.get("pain") or {}).values()]
    sessions = [f for f in (d.get("training_feedback") or {}).values()
                if (today - dt.timedelta(days=6)).isoformat() <= (f.get("date") or "") <= today.isoformat()]
    pains += [s.get("severity") or 0 for f in sessions for s in f.get("symptoms", [])]
    hooper = [wellness.hooper_index(c) for c in recent if wellness.hooper_index(c) is not None]
    rising = len(hooper) >= 3 and hooper[-1] - min(hooper[:-1]) >= 4
    worst = max(pains, default=0)
    if worst >= 5 or rising:
        return {"step": 0.0, "why": "pain of 5 or more, or a rising Hooper index, in the last 7 days: no increase"}
    soreness = [max(c.get("legs") or 0, c.get("feet") or 0) for c in recent]
    if worst >= 3 or any(v >= 6 for v in soreness):
        return {"step": 0.04, "why": "mild pain (3-4) or lingering soreness in the last 7 days: a small step"}
    if not recent:
        return {"step": 0.03, "why": "no check-ins in the last 7 days: the smallest step"}
    return {"step": 0.10, "why": "reports in the last 7 days settled well: a full step"}
