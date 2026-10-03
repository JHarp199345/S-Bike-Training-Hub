"""training_rules.py - which training patterns work together and which don't (the rider's design, 2026-10-03).

One check over a stretch of the plan, used by the program builder, the coaching-review preview and the assistant.
Each finding names the rule, the dates and why. 'breaks' blocks a reviewed change; 'caution' is shown for the
assistant to weigh (the running block, the athlete's conditioning, the event can justify it).

    rule                    severity  pattern
    hard_after_legs         breaks    a hard ride or run the day after a leg-lifting session (shared legs)
    same_tissue_double      breaks    two sessions the same day on the same tissue (a brick is the exception)
    full_body_48h           breaks    full-body lifting on consecutive days (48 h between)
    lift_days_in_row        breaks    more lifting days in a row than the athlete's split allows
    region_48h              breaks    a lifting region trained hard again the next day (48-72 h)
    hard_same_sport_48h     breaks    two hard sessions of one sport within 48 h
    calibration_watch       breaks    a run in the eight days after a running calibration
    runs_back_to_back       caution   runs on consecutive days (only when the running block supports it)
    legs_peak_together      caution   a week with 2+ hard runs and 2+ leg-lifting sessions
    shoulders_peak_together caution   a week with 2+ hard swims and 2+ upper-body lifting sessions
    no_check_week           caution   more than eight weeks of plan without a check week or test
"""
import datetime as dt

LEG_FOCUS = {"full", "lower", "push", "pull", "legs", "knee", "hip"}
UPPER_FOCUS = {"full", "upper", "push", "pull", "upper_push", "upper_pull"}
LEG_REGIONS = {"quads", "hamstrings", "glutes", "calves", "adductors", "hip_flexors"}
UPPER_REGIONS = {"pecs", "shoulders", "lats", "triceps", "biceps", "scapula"}
HARD_WORDS = ("test", "race", "brick", "quality", "steady", "interval", "tempo", "threshold", "vo2", "hard", "100s",
              "openers", "calibration", "ftp")
RULES = {
    "hard_after_legs": ("breaks", "A hard ride or run the day after leg lifting: the legs are shared and still recovering."),
    "same_tissue_double": ("breaks", "Two sessions the same day on the same tissue: pair different tissue (swim with a run, a ride with upper-body lifting)."),
    "full_body_48h": ("breaks", "Full-body lifting needs 48 hours between sessions."),
    "lift_days_in_row": ("breaks", "More lifting days in a row than the athlete's split allows."),
    "region_48h": ("breaks", "A lifting region trained hard again the next day: give each region 48-72 hours."),
    "hard_same_sport_48h": ("breaks", "Two hard sessions of one sport within 48 hours: hard days about 48 hours apart."),
    "calibration_watch": ("breaks", "A run during a running calibration's eight-day watch spoils the measurement."),
    "runs_back_to_back": ("caution", "Runs on consecutive days: only when the running block supports it (check the forecast)."),
    "legs_peak_together": ("caution", "Running and leg strength peaking the same week compete for the legs: alternate their peaks."),
    "shoulders_peak_together": ("caution", "Hard swimming and heavy upper-body lifting the same week compete for the shoulders."),
    "no_check_week": ("caution", "More than eight weeks without a check week: deload and retest before the block drifts."),
}


def _sessions(plan):
    import training_block as B
    return [s for s in B.sessions(plan or {}) if s.get("sport") not in (None, "rest")]


def hard(s):
    if s.get("sport") == "gym":
        return False
    if s.get("tier") in ("moderate", "hard", "race") or s.get("test"):
        return True
    name = (s.get("name") or "").lower()
    return any(w in name for w in HARD_WORDS) and "easy ride (instead" not in name


def light(s):
    """A lifting session that doesn't tire anything: a strength check (one comfortable set per lift), the
    familiarization week, light maintenance."""
    name = (s.get("name") or "").lower()
    return s.get("shape") == "check" or any(w in name for w in ("strength check", "calibration / familiarization", "(light)"))


def lift_parts(s):
    """(trains legs, trains upper body, regions, full body) for a lifting session; a light one trains nothing."""
    if light(s):
        return False, False, set(), False
    regions = set()
    for x in s.get("lifts") or []:
        regions |= set((x.get("regions") or {}).keys())
    focus = s.get("lift_focus")
    if focus:
        return focus in LEG_FOCUS, focus in UPPER_FOCUS, regions, focus == "full"
    legs, upper = bool(regions & LEG_REGIONS) or not regions, bool(regions & UPPER_REGIONS) or not regions
    return legs, upper, regions, legs and upper


def tissue(s):
    sp = s.get("sport")
    if sp == "gym":
        legs, upper, _, _ = lift_parts(s)
        return ({"legs"} if legs else set()) | ({"shoulders"} if upper else set())
    return {"run": {"legs", "impact"}, "ride": {"legs"}, "swim": {"shoulders"}, "walk": {"impact"}}.get(sp, set())


def check(d, start, end, options=None, extra_plans=None):
    """Findings for plan days start..end (inclusive), looking one week either side for spacing. extra_plans
    overrides saved days (a preview). Returns [{rule, severity, dates, why}]."""
    options = options or (d.get("program_goal") or {}).get("schedule_options") or {}
    in_row_max = options.get("max_lift_days_in_row", 4)
    s0, e0 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    lo, hi = s0 - dt.timedelta(days=9), e0 + dt.timedelta(days=7)
    plans = {**d.get("plans", {}), **(extra_plans or {})}
    days = [(lo + dt.timedelta(days=i)).isoformat() for i in range((hi - lo).days + 1)]
    ss = {k: _sessions(plans.get(k)) for k in days}
    out = []

    def add(rule, dates):
        if any(start <= x <= end for x in dates):
            out.append({"rule": rule, "severity": RULES[rule][0], "dates": sorted(set(dates)), "why": RULES[rule][1]})

    for i, k in enumerate(days):
        today, prev = ss[k], ss[days[i - 1]] if i else []
        # same-day pairing
        for a in range(len(today)):
            for b in range(a + 1, len(today)):
                x, y = today[a], today[b]
                brick = {x["sport"], y["sport"]} == {"ride", "run"} and any("brick" in (z.get("name") or "").lower() for z in (x, y))
                if not brick and tissue(x) & tissue(y):
                    add("same_tissue_double", [k])
        if not i:
            continue
        leg_lift_yesterday = any(p["sport"] == "gym" and lift_parts(p)[0] for p in prev)
        if leg_lift_yesterday and any(t["sport"] in ("ride", "run") and hard(t) for t in today):
            add("hard_after_legs", [days[i - 1], k])
        if any(p["sport"] == "run" for p in prev) and any(t["sport"] == "run" for t in today):
            add("runs_back_to_back", [days[i - 1], k])
        gym_y, gym_t = [p for p in prev if p["sport"] == "gym"], [t for t in today if t["sport"] == "gym"]
        if gym_y and gym_t:
            if any(lift_parts(p)[3] for p in gym_y) and any(lift_parts(t)[3] for t in gym_t):
                add("full_body_48h", [days[i - 1], k])
            ry = set().union(*[lift_parts(p)[2] for p in gym_y])
            rt = set().union(*[lift_parts(t)[2] for t in gym_t])
            if ry & rt and not (any(lift_parts(p)[3] for p in gym_y) and any(lift_parts(t)[3] for t in gym_t)):
                add("region_48h", [days[i - 1], k])
        for sp in ("ride", "run", "swim"):
            if any(p["sport"] == sp and hard(p) for p in prev) and any(t["sport"] == sp and hard(t) for t in today):
                add("hard_same_sport_48h", [days[i - 1], k])
    # lifting days in a row
    row = []
    for k in days + [None]:
        if k and any(s["sport"] == "gym" for s in ss[k]):
            row.append(k)
            continue
        if len(row) > in_row_max:
            add("lift_days_in_row", row)
        row = []
    # the calibration watch
    for k in days:
        if (plans.get(k) or {}).get("test") == "run_calibration":
            watch = [(dt.date.fromisoformat(k) + dt.timedelta(days=n)).isoformat() for n in range(1, 9)]
            runs = [x for x in watch if any(s["sport"] == "run" for s in ss.get(x) or _sessions(plans.get(x)))]
            if runs:
                add("calibration_watch", [k] + runs)
    # weeks: peaks that compete for the same tissue
    mon = s0 - dt.timedelta(days=s0.weekday())
    while mon <= e0:
        wk = [(mon + dt.timedelta(days=n)).isoformat() for n in range(7)]
        sess = [s for k in wk for s in (ss.get(k) if k in ss else _sessions(plans.get(k)))]
        hard_runs = sum(s["sport"] == "run" and hard(s) for s in sess)
        hard_swims = sum(s["sport"] == "swim" and hard(s) for s in sess)
        leg_lifts = sum(s["sport"] == "gym" and lift_parts(s)[0] for s in sess)
        upper_lifts = sum(s["sport"] == "gym" and lift_parts(s)[1] for s in sess)
        if hard_runs >= 2 and leg_lifts >= 2:
            add("legs_peak_together", [k for k in wk if start <= k <= end][:1] or [wk[0]])
        if hard_swims >= 2 and upper_lifts >= 2:
            add("shoulders_peak_together", [k for k in wk if start <= k <= end][:1] or [wk[0]])
        mon += dt.timedelta(days=7)
    # check weeks: more than eight weeks of plan without one
    tests = sorted(k for k, v in plans.items() if (v or {}).get("test") or any(s.get("shape") == "check" for s in _sessions(v)))
    planned = sorted(k for k, v in plans.items() if _sessions(v) and k <= end)
    if planned:
        marks = [planned[0]] + [t for t in tests if t <= end] + [end]
        gaps = [(a, b) for a, b in zip(marks, marks[1:]) if (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days > 56]
        if gaps and (dt.date.fromisoformat(end) - dt.date.fromisoformat(planned[0])).days > 56:
            add("no_check_week", [max(start, gaps[-1][1])])
    seen, unique = set(), []
    for f in out:
        key = (f["rule"], tuple(f["dates"]))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique
