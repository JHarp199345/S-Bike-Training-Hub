"""planning_context.py - what the assistant plans from: facts and evidence, not prohibitions (2026-10-11).

Private brief: docs/design/multisport-program-planning.md. Two passes, both in the chat, both on request:
  pass 1 (program)  placeholders for the whole macrocycle: sport, day, role (improve / maintain), a duration band,
                    and lifting joint groups. Saved through the existing program tools (preview_program).
  pass 2 (week)     the coming week's actual workouts inside those placeholders. Saved through the existing reviewed
                    calendar draft (preview_coaching_change kind=calendar), after the athlete approves.

This module gathers the facts in each sport's own units (weekly volume, not "training load"), the athlete's
calibration (current routine and past best), the reports (a 45-day half-life trend plus the last 7 days verbatim),
the goal and phases, and a playbook of evidence written as what works. It describes; it never decides. mirror()
describes a drafted week against the athlete's recent weeks.
"""
import datetime as dt
import math

HALF_LIFE_DAYS = 45.0                     # a report 45 days old counts half as much as today's
REPORT_WINDOW_DAYS = 90
VERBATIM_DAYS = 7
SPORTS = ("bike", "run", "swim", "lift")
NAMES = {"bike": "Cycling", "run": "Running", "swim": "Swimming", "lift": "Lifting"}
UNITS = {"bike": "minutes (and km when recorded)", "run": "km and minutes", "swim": "km and minutes",
         "lift": "sessions and minutes (joint groups via the lifting framework)"}
SPORT_OF = {"bike": "bike", "ride": "bike", "cycling": "bike", "run": "run", "running": "run",
            "swim": "swim", "swimming": "swim", "gym": "lift", "lift": "lift", "strength": "lift"}
CHECKIN_NUMBERS = ("legs", "feet", "shoulders", "breathing", "sleep", "hooper_fatigue", "hooper_sleep",
                   "hooper_stress", "hooper_soreness", "hooper_index")
CALIBRATION_FIELDS = ("sessions_per_week", "weekly_km", "weekly_minutes", "longest_km", "longest_minutes",
                      "session_km", "session_minutes")

PLAYBOOK = [
    {"topic": "Reading the numbers",
     "principle": "Anchor on the recent average week. Lean toward the best week when reports are clean and that week was "
                  "well tolerated. Use the last week to see where the athlete is right now. The four weekly totals show the "
                  "shape: a heavy month that sat mostly in its first week leaves more room now than a steady one."},
    {"topic": "Maintaining a sport",
     "principle": "Performance holds when volume sits around 40-60% of the athlete's usual while intensity and frequency "
                  "are kept, for 1-3 weeks; the reports show how long this athlete holds. For longer stretches, two sessions "
                  "a week at kept intensity held endurance for weeks in non-athletes, and one hard set per exercise once a "
                  "week held strength. Beginners with no baseline: two sessions of 15-30 minutes.",
     "sources": ["Taper meta-analysis 2023 (PMC10171681)", "Bosquet et al. 2007 (PMID 17762369)",
                 "Spiering et al. 2021 (PMID 33629972)"]},
    {"topic": "Improving a sport",
     "principle": "Build from the recent average week, adding roughly 5-10% a week; clean reports and a proven best week "
                  "support the higher end. A lighter week (about 20-30% less) every 3-4 weeks consolidates. Start at the "
                  "baseline when the athlete has been consistent; after a break, illness, injury or race, start lower and "
                  "use the past peak to rebuild faster than a beginner would, letting the reports gate each step. Three "
                  "sessions a week is the usual improving frequency.",
     "sources": ["Nielsen et al. 2013 (weekly increases above ~20-30% preceded injuries)",
                 "Damsted et al. review (the 10% rule has weak evidence)", "Retraining case studies 2024 (PMC11621217)"]},
    {"topic": "Improvement isn't only volume",
     "principle": "Efficiency shows improvement too: the same distance at a lower heart rate, more distance in less time, a "
                  "faster pace at the same effort, more watts per heartbeat on the bike, less heart-rate drift. Read the "
                  "efficiency section's matched comparisons and trend with the conditions (heat, duration, illness). When "
                  "efficiency is climbing, holding volume steady still counts as building; when volume rises and efficiency "
                  "holds, the athlete is absorbing the work."},
    {"topic": "Running", "sports": ["run"],
     "principle": "For recreational runners, frequency and some intensity drive aerobic gains: 2-3 sessions a week work. "
                  "Tissue tolerance sets the pace of increases, so spreading runs through the week lets volume grow. One "
                  "longer run with shorter ones suits building.",
     "sources": ["Recreational-runner interval frequency study 2025 (PMC12451023)"]},
    {"topic": "Swimming", "sports": ["swim"],
     "principle": "Frequency matters more than session length: three swims a week improve, two maintain. Drills build "
                  "technique, and beginners weight them heavily.",
     "sources": ["USA Triathlon and coaching consensus (not controlled studies)"]},
    {"topic": "Lifting", "sports": ["lift"],
     "principle": "Plan by joint groups with get_lifting_framework: which groups on which days, how many main exercises, "
                  "a load level. One hard set per exercise maintains strength; more weekly sets build it. When lifting is "
                  "being built and the load allows, three sessions; otherwise one session covering all three groups with "
                  "one or two intense main exercises. Lifting groups follow the load every sport puts on the body: upper "
                  "lifting sits away from a hard swim, lower lifting away from hard runs."},
    {"topic": "Every sport affects the others",
     "principle": "Running costs the other sports most, cycling next, swimming least; cycling carries over to running, little "
                  "carries into swimming, and only running loads bone and tendon (get_transfer). Space sessions that load "
                  "the same tissue."},
    {"topic": "Strength with endurance", "sports": ["lift"],
     "principle": "When strength matters, about six hours between a lift and an endurance session works best; in one "
                  "session, lift first for strength, endurance first for aerobic gains. The effect is mostly felt by "
                  "trained athletes at high volume."},
    {"topic": "Health and history",
     "principle": "Plan around what the athlete shared in health_history as their own guidance: clinician advice first, "
                  "movements that don't aggravate recorded injuries or conditions, and gentle, achievable sessions when the "
                  "screening suggests seeing a doctor, saying so plainly until they report clearance. For mental health, "
                  "keep sessions small and flexible and treat missed days as normal. Never diagnose or clear anyone."},
    {"topic": "Reading the athlete",
     "principle": "Green reports point to the upper end of a range; strain or reported pain points to the lower end, or to "
                  "another sport for that tissue. The athlete's holds and rules are the athlete's: plan around them. "
                  "Criticism in the chat shapes the regenerated week: 'too light' raises the load; 'too tired' keeps the "
                  "scheduled sports and lifting groups and makes them easier (fewer exercises, less volume, lighter); pain "
                  "removes the affected tissue that day and is recorded as a pain report."},
]

PASSES = {
    "program": ("Pass 1, the program: place placeholders for the whole macrocycle, phase by phase, with preview_program "
                "(phase weekly_pattern or date_placements). Each slot: sport, a short purpose, role improve or maintain, a "
                "minutes band [low, high], and for lifting its joint groups (e.g. ['upper','trunk']). Choose which sports "
                "to improve from the goal, the hours and the evidence; give improving sports about three sessions and the "
                "others a maintenance dose relative to their baseline. Spread each sport through the week. Explain the "
                "reasoning to the athlete, show the preview, and apply only after approval."),
    "week": ("Pass 2, the week: fill the coming week's placeholders with real workouts. Lifting: exercises inside the "
             "scheduled groups (check with describe_lift_structure). Swimming: drills and sets. Cycling: the ERG workout and "
             "its ranges. Running: duration or distance, whichever comes first. Base the volumes on the weekly totals and "
             "the reports, and say why ('why this week': the anchor, the step, the reports weighed). Draft it with "
             "preview_coaching_change kind=calendar, show the mirror and the week, then ask: approve, regenerate, or what "
             "would you change? Apply only after approval. Plan one week at a time; later weeks stay placeholders."),
}


def _d(s):
    return dt.date.fromisoformat(str(s)[:10])


def sport_of(raw):
    return SPORT_OF.get(str(raw or "").lower())


def blocks(activities, today, count, size=7):
    """Rolling 7-day blocks ending today, oldest first: per sport sessions, minutes, km and the longest session."""
    end = _d(today)
    out = []
    for b in range(count - 1, -1, -1):
        last = end - dt.timedelta(days=b * size)
        first = last - dt.timedelta(days=size - 1)
        row = {"from": first.isoformat(), "to": last.isoformat(), "sports": {}}
        for a in activities or []:
            s = sport_of(a.get("sport"))
            try:
                day = _d(a.get("date"))
            except (TypeError, ValueError):
                continue
            if not s or not first <= day <= last:
                continue
            v = row["sports"].setdefault(s, {"sessions": 0, "minutes": 0.0, "km": 0.0, "longest_minutes": 0.0, "longest_km": 0.0})
            m, km = float(a.get("minutes") or 0), float(a.get("km") or (a.get("distance_m") or 0) / 1000)
            v["sessions"] += 1
            v["minutes"] += m
            v["km"] += km
            v["longest_minutes"] = max(v["longest_minutes"], m)
            v["longest_km"] = max(v["longest_km"], km)
        for v in row["sports"].values():
            for k in ("minutes", "km", "longest_minutes", "longest_km"):
                v[k] = round(v[k], 1 if k != "km" else 2)
        out.append(row)
    return out


def volume(activities, today):
    """Each sport's last 28 days as four weekly totals, its average, best and last week, and a 13-week trend."""
    four = blocks(activities, today, 4)
    trend = blocks(activities, today, 13)
    out = {}
    for s in SPORTS:
        weeks = [b["sports"].get(s, {"sessions": 0, "minutes": 0.0, "km": 0.0, "longest_minutes": 0.0, "longest_km": 0.0}) for b in four]
        if not any(w["sessions"] for w in weeks) and not any(b["sports"].get(s) for b in trend):
            continue
        avg = {k: round(sum(w[k] for w in weeks) / 4, 2) for k in ("sessions", "minutes", "km")}
        best = max(weeks, key=lambda w: (w["minutes"], w["km"]))
        out[s] = {"sport": NAMES[s], "units": UNITS[s],
                  "last_28_days_by_week": [{"from": b["from"], "to": b["to"], **w} for b, w in zip(four, weeks)],
                  "average_week": avg, "best_week": {k: best[k] for k in ("sessions", "minutes", "km")},
                  "last_week": {k: weeks[-1][k] for k in ("sessions", "minutes", "km")},
                  "longest_session_28d": {"minutes": max(w["longest_minutes"] for w in weeks), "km": max(w["longest_km"] for w in weeks)},
                  "trend_13_weeks": [{"to": b["to"], "minutes": b["sports"].get(s, {}).get("minutes", 0.0),
                                      "km": b["sports"].get(s, {}).get("km", 0.0), "sessions": b["sports"].get(s, {}).get("sessions", 0)}
                                     for b in trend]}
    return out


MATCH_DURATION = 0.25      # sessions compare like for like when their durations are within 25% of each other


HEAT_NOTE_C = 5            # a temperature difference this large is called out next to a comparison


def _conditions(a, sport, today, weather_on, cache_path=None, fetch=None):
    """Where and how warm: outdoor sessions get the hour's air temperature when the athlete has turned the lookup on."""
    out = {"watch_temp_c": a.get("watch_temp_c")}
    if not a.get("place"):
        out["setting"] = "pool" if sport == "swim" else "indoor"
        return out
    out["setting"] = "outdoor"
    if weather_on and a.get("start_ts"):
        import weather
        mid = dt.datetime.fromtimestamp(a["start_ts"] + float(a.get("minutes") or 0) * 30)   # the middle of the session
        w = weather.lookup(mid.date().isoformat(), mid.hour, a["place"], today, cache_path, fetch)
        if w:
            out.update({"air_temp_c": w["temp_c"], "humidity_pct": w["humidity_pct"], "source": w["source"]})
    return out


def _efficiency_rows(state, today, days=90, weather_on=False, cache_path=None, fetch=None):
    """Runs and swims: metres per minute per heartbeat; rides: watts per beat (aerobic.py's efficiency factor)."""
    end, out = _d(today), {"run": [], "swim": [], "bike": []}
    first = end - dt.timedelta(days=days - 1)
    for a in (state or {}).get("activities") or []:
        s = sport_of(a.get("sport"))
        try:
            day = _d(a.get("date"))
        except (TypeError, ValueError):
            continue
        if s not in ("run", "swim") or not first <= day <= end:
            continue
        m, km, hr = float(a.get("minutes") or 0), float(a.get("km") or 0), a.get("avg_hr")
        if m < 10 or km <= 0 or not isinstance(hr, (int, float)) or hr <= 0:
            continue
        row = {"date": day.isoformat(), "minutes": round(m, 1), "km": round(km, 2), "avg_hr": round(hr),
               "efficiency": round(km * 1000 / m / hr, 4), "efficiency_unit": "metres per minute per heartbeat"}
        row["pace"] = (f"{m / km:.2f} min/km" if s == "run" else f"{m / (km * 10):.2f} min/100 m")
        if isinstance(a.get("drift_pct"), (int, float)):
            row["hr_drift_pct"] = a["drift_pct"]
        row["conditions"] = _conditions(a, s, today, weather_on, cache_path, fetch)
        out[s].append(row)
    for r in ((state or {}).get("aerobic") or {}).get("rides") or []:
        try:
            day = _d(r.get("date"))
        except (TypeError, ValueError):
            continue
        if first <= day <= end and r.get("ef") and (r.get("minutes") or 0) >= 10:
            out["bike"].append({"date": day.isoformat(), "minutes": r.get("minutes"), "np_w": r.get("np"), "avg_hr": r.get("avg_hr"),
                                "efficiency": r["ef"], "efficiency_unit": "watts per heartbeat (normalized power / average heart rate)",
                                "hr_drift_pct": r.get("decoupling_pct"), "hr_at_110w": r.get("hr_at_band"),
                                "conditions": {"setting": "indoor (the S29)"}})
    for rows in out.values():
        rows.sort(key=lambda r: r["date"])
    return out


def _match(rows, row):
    """The closest earlier session of similar duration (within MATCH_DURATION); the most recent among equally close."""
    def gap(r):
        return abs(r["minutes"] - row["minutes"]) / max(r["minutes"], row["minutes"])
    candidates = [r for r in rows if r["date"] < row["date"] and r.get("minutes") and row.get("minutes") and gap(r) <= MATCH_DURATION]
    if not candidates:
        return None
    return min(candidates, key=lambda r: (round(gap(r), 2), -_d(r["date"]).toordinal()))


def _temperature_difference(row, m):
    """Air temperatures when both are known, else the watch's own (it reads warm, but alike on both days)."""
    a, b = row.get("conditions") or {}, m.get("conditions") or {}
    for key, label in (("air_temp_c", "air"), ("watch_temp_c", "watch sensor")):
        if isinstance(a.get(key), (int, float)) and isinstance(b.get(key), (int, float)):
            diff = round(a[key] - b[key], 1)
            out = {"temperature_difference_c": diff, "temperature_basis": label}
            if abs(diff) >= HEAT_NOTE_C:
                out["heat_note"] = (f"{abs(diff):g} °C {'warmer' if diff > 0 else 'cooler'} than the match ({label}): heat raises "
                                    f"heart rate, so part of this difference is the weather")
            return out
    return {}


def efficiency(state, today, weather_on=False, cache_path=None, fetch=None):
    """Improvement that isn't volume: each sport's efficiency per session, matched comparisons and a 4-week trend."""
    rows = _efficiency_rows(state, today, weather_on=weather_on, cache_path=cache_path, fetch=fetch)
    since = (_d(today) - dt.timedelta(days=27)).isoformat()
    prior = (_d(today) - dt.timedelta(days=55)).isoformat()
    out = {}
    for s, rs in rows.items():
        if not rs:
            continue
        comparisons = []
        for row in [r for r in rs if r["date"] >= since]:
            m = _match(rs, row)
            if not m:
                comparisons.append({"session": row, "match": None, "why": "no earlier session of similar duration in 90 days"})
                continue
            c = {"session": row, "match": m,
                 "efficiency_change_pct": round((row["efficiency"] / m["efficiency"] - 1) * 100, 1),
                 "avg_hr_change": round(row["avg_hr"] - m["avg_hr"]) if row.get("avg_hr") and m.get("avg_hr") else None,
                 "duration_difference_min": round(row["minutes"] - m["minutes"], 1)}
            if s != "bike":
                c["distance_difference_km"] = round(row["km"] - m["km"], 2)
            c.update(_temperature_difference(row, m))
            comparisons.append(c)
        recent = [r["efficiency"] for r in rs if r["date"] >= since]
        before = [r["efficiency"] for r in rs if prior <= r["date"] < since]
        trend = {"last_4_weeks": round(sum(recent) / len(recent), 4) if recent else None, "sessions": len(recent),
                 "previous_4_weeks": round(sum(before) / len(before), 4) if before else None, "previous_sessions": len(before)}
        if trend["last_4_weeks"] and trend["previous_4_weeks"]:
            trend["change_pct"] = round((trend["last_4_weeks"] / trend["previous_4_weeks"] - 1) * 100, 1)
        out[s] = {"sport": NAMES[s], "sessions_90_days": rs, "matched_comparisons": comparisons, "trend": trend}
    return {"by_sport": out,
            "weather_lookup": "on" if weather_on else "off (the athlete can turn on air-temperature lookups; the watch sensor is shown meanwhile)",
            "read_with": ["Heat raises heart rate and lowers efficiency; cool days flatter it. Each comparison shows the temperature difference when known.",
                          "Longer sessions drift upward in heart rate, so compare similar durations (matches are within 25%).",
                          "Illness, poor sleep and fatigue raise heart rate: read the check-ins alongside.",
                          "One matched pair is a hint; several moving the same way is a trend."]}


def _weight(age_days):
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def reports(d, today):
    """The 90-day trend (each number weighted by a 45-day half-life) and the last 7 days of reports verbatim."""
    end = _d(today)
    sums = {}
    for date, c in (d.get("checkins") or {}).items():
        try:
            age = (end - _d(date)).days
        except ValueError:
            continue
        if not 0 <= age < REPORT_WINDOW_DAYS:
            continue
        w = _weight(age)
        values = {k: c.get(k) for k in CHECKIN_NUMBERS}
        for site, v in (c.get("pain") or {}).items():
            values["pain_" + site] = v
        for k, v in values.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                acc = sums.setdefault(k, [0.0, 0.0, 0, None, None])
                acc[0] += w * v
                acc[1] += w
                acc[2] += 1
                if acc[4] is None or date > acc[4]:
                    acc[3], acc[4] = v, date
    trend = {k: {"weighted_average": round(a[0] / a[1], 2), "reports": a[2], "latest": a[3], "latest_date": a[4]}
             for k, a in sorted(sums.items()) if a[1] > 0}
    since = (end - dt.timedelta(days=VERBATIM_DAYS - 1)).isoformat()
    recent = {"checkins": [], "session_reports": [], "workout_reports": [], "weekly": [], "lift_followups": []}
    for date, c in sorted((d.get("checkins") or {}).items()):
        if since <= date <= end.isoformat():
            recent["checkins"].append({"date": date, **{k: c.get(k) for k in (*CHECKIN_NUMBERS, "pain", "journal", "verdict") if c.get(k) not in (None, {}, "")}})
    for f in (d.get("training_feedback") or {}).values():
        if since <= str(f.get("date", "")) <= end.isoformat():
            recent["session_reports"].append({k: f.get(k) for k in ("date", "sport", "session_name", "effort", "rpe", "symptoms", "note", "planned_minutes", "actual_minutes") if f.get(k) not in (None, [], "")})
    for date, r in (d.get("workout_reports") or {}).items():
        if since <= date <= end.isoformat():
            recent["workout_reports"].append({"date": date, **{k: v for k, v in r.items() if k not in ("snapshot",)}})
    for date, r in (d.get("weekly") or {}).items():
        if since <= str(r.get("date", date)) <= end.isoformat():
            recent["weekly"].append({k: v for k, v in r.items() if k != "snapshot"})
    for f in ((d.get("lifting") or {}).get("followups") or []):
        if isinstance(f, dict) and since <= str(f.get("date", "")) <= end.isoformat():
            recent["lift_followups"].append(f)
    recent["session_reports"].sort(key=lambda r: r.get("date", ""))
    return {"half_life_days": HALF_LIFE_DAYS, "window_days": REPORT_WINDOW_DAYS,
            "scales": "Hooper items 1 (very, very low or good) to 7 (very, very high or bad); legs, feet, shoulders and "
                      "pain 0 (none) to 10; breathing and sleep as in the daily check-in.",
            "trend": trend, f"last_{VERBATIM_DAYS}_days": recent}


def calibration(d):
    """The athlete's reported current routine and past best for each sport (set_sport_baseline)."""
    return d.get("sport_baselines") or {}


def set_baseline(d, sport, fields, today):
    s = sport_of(sport) or (sport if sport in SPORTS else None)
    if s not in SPORTS:
        raise ValueError("Sport is bike, run, swim or lift")
    entry = {"updated": today}
    for part in ("now", "best"):
        raw = fields.get(part) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{part} is an object")
        clean = {}
        for k in CALIBRATION_FIELDS:
            v = raw.get(k)
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 10000:
                raise ValueError(f"{part}.{k} is a number from 0 to 10000")
            clean[k] = v
        if part == "best" and raw.get("when"):
            clean["when"] = str(raw["when"])[:40]
        if clean:
            entry[part] = clean
    if fields.get("note"):
        entry["note"] = str(fields["note"])[:300]
    if "now" not in entry and "best" not in entry:
        raise ValueError("Give the current routine (now) or the past best (best)")
    d.setdefault("sport_baselines", {})[s] = entry
    return entry


def program_facts(d, today, week_from=None):
    goal = d.get("program_goal") or {}
    target = goal.get("target")
    phases = sorted(d.get("phase_profiles") or [], key=lambda p: p.get("start", ""))
    current = next((p for p in phases if p.get("start", "") <= today < p.get("end", "")), None)
    keep = ("kind", "stage", "label", "start", "end", "weeks", "modes", "purpose", "weekly_pattern")
    week_from = week_from or today
    week_to = (_d(week_from) + dt.timedelta(days=6)).isoformat()
    slots = [s for w in d.get("program_macro_weeks") or [] for s in w.get("slots", [])
             if week_from <= s.get("date", "") <= week_to and s.get("sport") != "rest"]
    import training_block
    scheduled = {}
    for i in range(7):
        day = (_d(week_from) + dt.timedelta(days=i)).isoformat()
        sessions = training_block.sessions((d.get("plans") or {}).get(day) or {})
        if sessions:
            scheduled[day] = [{k: s.get(k) for k in ("sport", "name", "minutes", "workout", "note") if s.get(k) is not None} for s in sessions]
    return {"goal": {k: goal.get(k) for k in ("goal", "outcome", "sport", "target", "hours", "priorities", "long_term_goal") if goal.get(k) is not None},
            "days_to_event": (_d(target) - _d(today)).days if target else None,
            "events": [{k: e.get(k) for k in ("name", "kind", "date") if e.get(k)} for e in d.get("events") or [] if str(e.get("date", "")) >= today],
            "current_phase": {k: current.get(k) for k in keep if current and current.get(k) is not None} if current else None,
            "phases": [{k: p.get(k) for k in ("kind", "stage", "label", "start", "end", "modes", "purpose") if p.get(k) is not None} for p in phases if p.get("end", "") > today],
            "week": {"from": week_from, "to": week_to, "placeholders": slots, "scheduled_sessions": scheduled}}


def context(d, activities, today, scope="week", week_from=None, gate=None, state=None):
    """Everything for one planning pass. scope: 'program' (pass 1) or 'week' (pass 2)."""
    if scope not in PASSES:
        raise ValueError("Scope is program or week")
    holds = None
    if gate:
        holds = {k: gate.get(k) for k in ("status", "reasons", "evidence") if gate.get(k) not in (None, "", [])}
        holds["about"] = ("Running holds only while the athlete has an unresolved reported symptom (reasons). Evidence lists "
                          "model readings, hop tests and checklists to weigh, not rules.")
    return {"scope": scope, "today": today, "how_to_plan": PASSES[scope],
            "volume": volume(activities, today),
            "efficiency": efficiency(state or {"activities": activities}, today, __import__("weather").enabled(d)),
            "calibration": calibration(d), "reports": reports(d, today),
            "health_history": __import__("health_history").summary(d),
            "program": program_facts(d, today, week_from), "running_gate": holds,
            "playbook": PLAYBOOK,
            "notes": ["Volumes are recorded sessions in each sport's own units; missing data is unknown, not zero effort.",
                      "Calibration is the athlete's own report: provisional until recorded weeks and reports confirm it.",
                      "Explain the reasoning in plain words and let the athlete criticise it; the hub describes, the "
                      "athlete decides."]}


def _session_km(s):
    for k in ("km",):
        if isinstance(s.get(k), (int, float)):
            return float(s[k])
    if isinstance(s.get("distance_m"), (int, float)):
        return s["distance_m"] / 1000
    for key in ("swim_recipe", "run_recipe"):
        recipe = s.get(key) or {}
        if isinstance(recipe, dict):
            for k in ("total_distance_m", "distance_m"):
                if isinstance(recipe.get(k), (int, float)) and recipe[k] > 0:
                    return recipe[k] / 1000
    plan = s.get("swim_plan") or {}
    if isinstance(plan, dict) and isinstance(plan.get("distance_m"), (int, float)):
        return plan["distance_m"] / 1000
    return 0.0


def mirror(activities, today, days):
    """Describe a drafted set of days against the athlete's recent weeks. days: {date: [session, ...]}."""
    vol = volume(activities, today)
    planned = {}
    for sessions in (days or {}).values():
        for s in sessions or []:
            sp = sport_of(s.get("sport"))
            if not sp:
                continue
            p = planned.setdefault(sp, {"sessions": 0, "minutes": 0.0, "km": 0.0})
            p["sessions"] += 1
            p["minutes"] += float(s.get("minutes") or 0)
            p["km"] += _session_km(s)
    out = {}
    for sp in sorted(set(planned) | set(vol)):
        p = planned.get(sp, {"sessions": 0, "minutes": 0.0, "km": 0.0})
        v = vol.get(sp, {})
        avg, best, last = v.get("average_week", {}), v.get("best_week", {}), v.get("last_week", {})
        row = {"sport": NAMES.get(sp, sp), "planned": {k: round(x, 1) for k, x in p.items()},
               "average_week": avg, "best_week": best, "last_week": last}
        for k in ("minutes", "km"):
            if avg.get(k) and (k == "minutes" or p[k] > 0):     # a draft without distances isn't 0% of the distance
                row[f"{k}_vs_average_pct"] = round(p[k] / avg[k] * 100)
        out[sp] = row
    return {"days": sorted(days or {}), "by_sport": out,
            "note": "A description against recent recorded weeks, not a verdict. Days outside the draft are not counted."}


# --- The brief and its sections (2026-10-11) -------------------------------------------------------------------
# A planning call used to return everything at once (about 60,000 characters). Now the default is a brief: the facts
# that should be obvious first, then an index of sections to ask for, each filtered to one sport when that's all the
# decision needs. Nothing is summarised away: every section still returns its full detail on request.

SECTIONS = {
    "volume": "each sport's last 28 days as four weekly totals, average/best/last week, longest session, 13-week trend",
    "efficiency": "efficiency against heart rate: matched comparisons with conditions and a 4-week trend (detail=true adds every session of 90 days)",
    "reports": "the 90-day report trend (45-day half-life) and the last 7 days verbatim: check-ins, session reports, weekly, lift follow-ups",
    "calibration": "the athlete's own current routine and past best per sport",
    "health_history": "screening, conditions, injuries, medications and clinician guidance",
    "program": "goal, events, current phase, every remaining phase and the week's placeholders and saved sessions",
    "running_gate": "running hold status, reasons and the evidence to weigh",
    "playbook": "evidence written as what works (general topics, plus the sport-specific ones for the sport asked)",
}
WORSE_WHEN_HIGHER = ("legs", "feet", "shoulders", "breathing", "hooper_fatigue", "hooper_sleep", "hooper_stress",
                     "hooper_soreness")   # breathing: 1 normal and easy, 10 unusually difficult
FLAG_STEP = 1.5            # a latest report this far above its weighted usual is called out


def _sport_filter(sport):
    if not sport:
        return None
    s = SPORT_OF.get(str(sport).lower())
    if not s:
        raise ValueError("sport is bike, run, swim or lift")
    return s


def _short(text, limit=240):
    text = str(text or "")
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _efficiency_brief(eff, detail=False):
    if detail:
        return eff
    keep = ("date", "minutes", "km", "avg_hr", "efficiency", "conditions", "temp_c")
    out = {}
    for s, x in eff.get("by_sport", {}).items():
        comps = []
        for c in x.get("matched_comparisons", []):
            row = {k: v for k, v in c.items() if k not in ("session", "match")}
            row["session"] = {k: c["session"].get(k) for k in keep if c["session"].get(k) is not None}
            if c.get("match"):
                row["match"] = {k: c["match"].get(k) for k in keep if c["match"].get(k) is not None}
            comps.append(row)
        out[s] = {"sport": x.get("sport"), "trend": x.get("trend"), "matched_comparisons": comps,
                  "sessions_90_days": len(x.get("sessions_90_days", []))}
    return {**{k: v for k, v in eff.items() if k != "by_sport"}, "by_sport": out}


def section(d, activities, today, name, sport=None, detail=False, week_from=None, gate=None, state=None, full=None):
    """One section in full, filtered to a sport where that makes sense."""
    if name not in SECTIONS:
        raise ValueError("section is one of " + ", ".join(SECTIONS))
    s = _sport_filter(sport)
    full = full if full is not None else context(d, activities, today, "program", week_from, gate, state)
    if name == "volume":
        v = full["volume"]
        return {k: x for k, x in v.items() if not s or k == s}
    if name == "efficiency":
        eff = _efficiency_brief(full["efficiency"], detail)
        if s:
            eff = {**eff, "by_sport": {k: x for k, x in eff["by_sport"].items() if k == s}}
        return eff
    if name == "calibration":
        c = full["calibration"]
        return {k: x for k, x in c.items() if not s or k == s}
    if name == "playbook":
        return [t for t in PLAYBOOK if not t.get("sports") or (s and s in t["sports"]) or (not s and detail)]
    return full[name]


def brief(d, activities, today, scope="week", week_from=None, gate=None, state=None):
    """The default answer: what should be obvious, then where the detail lives."""
    full = context(d, activities, today, scope, week_from, gate, state)
    prog, rep, vol = full["program"], full["reports"], full["volume"]
    eff = full["efficiency"].get("by_sport", {})
    phases = prog.get("phases") or []
    now = prog.get("current_phase")
    nxt = next((p for p in phases if now and p.get("start", "") >= now.get("end", "")), None)
    gate_view = full.get("running_gate") or {}
    holds = {"running": "held" if gate_view.get("reasons") else "not held",
             **({"reasons": gate_view["reasons"]} if gate_view.get("reasons") else {}),
             **({"evidence_to_weigh": gate_view["evidence"]} if gate_view.get("evidence") else {})}
    trend = rep.get("trend", {})
    flags = [f"{k}: {v['latest']} on {v['latest_date']} vs usual {v['weighted_average']}" for k, v in trend.items()
             if (k in WORSE_WHEN_HIGHER or k.startswith("pain_")) and isinstance(v.get("latest"), (int, float))
             and v["latest"] - v["weighted_average"] >= FLAG_STEP]
    recent = rep.get(f"last_{VERBATIM_DAYS}_days", {})
    checkins = [{**{k: v for k, v in c.items() if k != "journal"}, **({"journal": _short(c["journal"])} if c.get("journal") else {})}
                for c in recent.get("checkins", [])]
    usual = {}
    for s, x in vol.items():
        usual[s] = {"average_week": x["average_week"], "last_week": x["last_week"], "best_week": x["best_week"],
                    **({"efficiency_change_pct": eff[s]["trend"].get("change_pct")} if s in eff and eff[s]["trend"].get("change_pct") is not None else {})}
    hh = full["health_history"]
    health = ("no health check recorded yet" if not hh.get("screening") else f"health check on {hh['screening'].get('date')}: {hh['screening'].get('result') or hh['screening'].get('outcome')}")
    shared = {k: len(hh.get(k) or []) for k in ("conditions", "injuries", "medications", "guidance") if hh.get(k)}
    ask = lambda name: f"get_planning_context(scope={scope}, sections=['{name}']" + (", sport=…" if name in ("volume", "efficiency", "calibration", "playbook") else "") + ")"
    return {
        "scope": scope, "today": today, "how_to_plan": full["how_to_plan"],
        "at_a_glance": {
            "goal": {**prog.get("goal", {}), "days_to_event": prog.get("days_to_event")},
            "phase_now": {k: now.get(k) for k in ("label", "stage", "start", "end", "modes") if now and now.get(k) is not None} if now else None,
            "next_phase": {k: nxt.get(k) for k in ("label", "stage", "start", "end") if nxt.get(k) is not None} if nxt else None,
            "holds": holds,
            "report_flags": flags or ["no report is well above its usual"],
            "usual_week_by_sport": usual,
            "athlete_calibration": full["calibration"] or None,
            "health": {"status": health, **({"shared": shared} if shared else {}),
                       **({"heart_rate_note": hh["heart_rate_note"]} if hh.get("heart_rate_note") else {})},
            "upcoming_events": prog.get("events", []),
        },
        "last_7_days": {"checkins": checkins,
                        "session_reports": [{**r, **({"note": _short(r["note"], 160)} if r.get("note") else {})} for r in recent.get("session_reports", [])],
                        "weekly": recent.get("weekly", []), "lift_followups": recent.get("lift_followups", [])},
        "week": prog.get("week") if scope == "week" else None,
        "phases": [{k: p.get(k) for k in ("label", "stage", "start", "end", "modes")} for p in phases] if scope == "program" else None,
        "playbook": [t for t in PLAYBOOK if not t.get("sports")],
        "more": {name: {"what": what, "ask": ask(name)} for name, what in SECTIONS.items()},
        "notes": full["notes"] + ["This is the brief. Journals and notes are shortened here; sections=['reports'] has them in full."],
    }
