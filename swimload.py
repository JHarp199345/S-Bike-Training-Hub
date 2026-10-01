"""Provisional, sport-specific swim exposure and recovery.

These are comparison units, not measured shoulder force, tissue damage, or a
validated injury threshold.  FIT pool lengths supply strokes and pace where
available.  The initial reference represents roughly three familiar swims;
the rider's repeated next-day reports are needed before it can be tuned.
"""
import datetime as dt
import math
import statistics

STROKES = {0: "freestyle", 1: "backstroke", 2: "breaststroke", 3: "butterfly", 4: "drill", 5: "mixed"}
# Relative pull-exposure assumptions for the first model, not EMG percentages.
STROKE_FACTOR = {"freestyle": 1.0, "backstroke": 0.8, "breaststroke": 0.7,
                 "butterfly": 1.3, "drill": 0.5, "mixed": 1.0}
HALF_LIFE_DAYS = 1.5
HISTORY_HALF_LIFE_DAYS = 14.0
HISTORY_FRACTION = 0.10
THRESHOLD = 1.5


# Conservative planning prior, not an experimentally measured Arena multiplier.
FIN_KICK_FACTOR = 1.25


def equipment(a):
    def fraction(name):
        return max(0.0, min(1.0, float(a.get(name + "_fraction", 1.0)))) if a.get(name) else 0.0
    return {"fins": bool(a.get("fins")), "snorkel": bool(a.get("snorkel")),
            "fins_fraction": fraction("fins"), "snorkel_fraction": fraction("snorkel"),
            "fin_type": a.get("fin_type") or ("short training fins" if a.get("fins") else None)}


def kick_dose(a):
    """Time/effort proxy; includes kick drills with zero recorded arm strokes."""
    gear = equipment(a)
    lengths = [x for x in a.get("swim_lengths", []) if x.get("length_type") == 1]
    seconds = sum(max(0, x.get("total_timer_time") or 0) for x in lengths)
    active = min(a.get("minutes", 0), seconds / 60) if seconds > 0 else a.get("minutes", 0)
    effort = a.get("kick_rpe") or a.get("swim_rpe") or a.get("rpe")
    intensity = max(0.5, min(2.0, float(effort) / 5)) if effort else 1.0
    factor = max(1.0, min(2.0, float(a.get("fin_kick_factor", FIN_KICK_FACTOR))))
    # Preserve the previous unassisted dose; replace only the fin-assisted portion.
    fraction = gear["fins_fraction"]
    unassisted = a.get("minutes", 0) * .05 * (1 - fraction)
    fin_points = active * .05 * intensity * factor * fraction
    return {"points": round(unassisted + fin_points, 4), "active_minutes": round(active, 2),
            "active_time_from": "watch active lengths" if seconds > 0 else "session duration fallback",
            "effort": effort, "effort_from": "kick report" if a.get("kick_rpe") else "session effort proxy",
            "fin_factor": factor if fraction else 1.0, "equipment": gear,
            "provisional": True, "note": "Fin factor is a configurable planning prior, not measured muscle force; no running impact added."}


def dose(a):
    """Return a relative pull-exposure dose with evidence about its inputs."""
    if a.get("sport") != "swim":
        return None
    lengths = [x for x in a.get("swim_lengths", []) if x.get("length_type") == 1]
    active = [x for x in lengths if (x.get("total_strokes") or 0) > 0]
    pool = a.get("pool_length_m") or 0
    equip = equipment(a)
    fin_fraction = equip["fins_fraction"]
    gear = 1.0
    # Gear is recorded per activity by the coach/assistant; effects depend on technique.
    if a.get("paddles"):
        gear *= 1.15
    if a.get("pull_buoy"):
        gear *= 1.05
    effort = a.get("swim_rpe") or a.get("rpe")
    effort_factor = max(0.8, min(1.3, 0.8 + float(effort) * 0.05)) if effort else 1.0
    if active:
        by_stroke = {}
        total_strokes = 0
        units = 0.0
        for x in active:
            n = x["total_strokes"]
            stroke = STROKES.get(x.get("swim_stroke"), "mixed")
            v = x.get("avg_speed") or (pool / max(x.get("total_timer_time") or 0, 1))
            # Hydrodynamic resistance rises roughly with speed squared.  This
            # remains a force proxy: hand force is not shoulder-tendon force.
            speed_factor = max(0.25, min(2.5, (v / 0.9) ** 2))
            # Fin-assisted velocity cannot isolate arm effort: use stroke exposure there.
            speed_factor = (1 - fin_fraction) * speed_factor + fin_fraction
            units += n * STROKE_FACTOR[stroke] * speed_factor
            total_strokes += n
            by_stroke[stroke] = by_stroke.get(stroke, 0) + n
        method = "watch pool lengths"
    else:
        # Missing length records: cadence is preferable to a distance-only guess.
        cadence = a.get("swim_cadence") or 20
        total_strokes = round(max(0, a.get("minutes", 0)) * cadence)
        v = a.get("distance_m", 0) / max(a.get("minutes", 0) * 60, 1)
        speed_factor = max(0.25, min(2.5, (v / 0.9) ** 2))
        units = total_strokes * ((1 - fin_fraction) * speed_factor + fin_fraction)
        by_stroke = {"unknown": total_strokes}
        method = "session cadence" if a.get("swim_cadence") else "estimated cadence"
    return {"units": round(units * gear * effort_factor, 1), "strokes": total_strokes,
            "by_stroke": by_stroke, "method": method,
            "paddles": bool(a.get("paddles")), "pull_buoy": bool(a.get("pull_buoy")),
            "effort": effort, "equipment": equip,
            "speed_basis": "stroke exposure on fin-assisted portion" if fin_fraction else "speed-squared proxy",
            "provisional": True}


# ── the block, fitted: every swim and the next morning's shoulders refine what one block is for this swimmer ──
# The model predicts the next-day shoulder rating from the swim score: 1/10 at nothing, 6/10 (the "rough" line) at
# the 1.5-block threshold. A grid of candidate block sizes is scored against every report (Gaussian, sd 1.5 points)
# under a log-normal prior centred on the first-swims estimate; the posterior mean is the block, with an 80%
# interval. With no reports it IS the prior, and says so. Refitted from all the data every time - continuous.
PRIOR_SD = 0.5                    # log-units: the first-swims guess could easily be off by ~1.6x either way
REPORT_SD = 1.5                   # rating points: how noisy a morning's shoulder number is
WEEKLY_SD = 1.0                   # the Sunday check-in: the week's considered answer
GRID = [math.exp(math.log(0.33) + i * (math.log(3.0) - math.log(0.33)) / 60) for i in range(61)]


def _initial(swims):
    first = [x["swim_exposure"]["units"] for x in swims if x["swim_exposure"]["units"] > 0][:3]
    # A familiar swim is roughly one third of the provisional demanding dose - this rider's report of tolerating
    # several successive swims, not a universal claim from the biomechanics literature.
    return 3 * statistics.median(first) if first else None


def _predict(score):
    return max(1.0, min(10.0, 1 + 5 * score / THRESHOLD))


def _fit(ordered, first, today, reports, initial, weekly=()):
    """Every shoulder report within a week after a swim is scored against the model's score for that day (the next
    morning's most of all, but any day counts); the Sunday check-in's rating is trusted a little more."""
    obs = []
    swim_days = sorted({a["date"] for a in ordered})
    for day, r in sorted(reports.items()):
        y = r.get("shoulders") if isinstance(r, dict) else None
        if y is None or day > today.isoformat():
            continue
        prior = [s for s in swim_days if s < day]
        if prior and (dt.date.fromisoformat(day) - dt.date.fromisoformat(prior[-1])).days <= 7:
            obs.append((day, float(y), WEEKLY_SD if day in weekly else REPORT_SD))
    if not obs:
        return initial, None, 0
    logw = []
    for g in GRID:
        ref = initial * g
        hist = {h["date"]: h["score"] for h in _simulate(ordered, first, today, reports, ref)[0]}
        ll = sum(-0.5 * ((y - _predict(hist.get(d, 0.0))) / sd) ** 2 for d, y, sd in obs)
        logw.append(ll - 0.5 * (math.log(g) / PRIOR_SD) ** 2)
    top = max(logw); w = [math.exp(x - top) for x in logw]; tot = sum(w)
    w = [x / tot for x in w]
    ref = initial * math.exp(sum(wi * math.log(g) for wi, g in zip(w, GRID)))
    cum, lo, hi = 0.0, None, None
    for wi, g in zip(w, GRID):
        cum += wi
        if lo is None and cum >= 0.1:
            lo = initial * g
        if hi is None and cum >= 0.9:
            hi = initial * g
    return ref, (round(lo, 1), round(hi, 1)), len(obs)


def _simulate(ordered, first, today, reports, reference):
    """Day by day: each swim's blocks (with the overlap cost), the recent and repeated-exposure decay, and a
    high shoulder report holding some recent load. Returns (history, events)."""
    by_day = {}
    for a in ordered:
        by_day.setdefault(a["date"], []).append(a)
    fast = slow = 0.0
    decay_fast = 2 ** (-1 / HALF_LIFE_DAYS)
    decay_slow = 2 ** (-1 / HISTORY_HALF_LIFE_DAYS)
    history, events = [], []
    day = first
    while day <= today:
        key = day.isoformat()
        if day != first:
            fast *= decay_fast
            slow *= decay_slow
        for a in by_day.get(key, []):
            raw = a["swim_exposure"]["units"] / reference
            before = fast + HISTORY_FRACTION * slow
            mult = 1 + min(0.75, 0.5 * before)
            added = raw * mult
            fast += added
            slow += added
            events.append({"date": key, "id": a["id"], "raw_blocks": round(raw, 2),
                           "incoming_multiplier": round(mult, 2), "added_blocks": round(added, 2),
                           "after_blocks": round(fast + HISTORY_FRACTION * slow, 2)})
        # A high shoulder report holds some of the fast load; a good report does not erase it.
        # Do not infer absence of symptoms from no report.
        report = reports.get(key) or {}
        shoulder = report.get("shoulders") if isinstance(report, dict) else None
        if shoulder is not None and shoulder >= 6:
            fast *= 1.10 if shoulder < 8 else 1.20
        history.append({"date": key, "score": round(fast + HISTORY_FRACTION * slow, 3),
                        "recent": round(fast, 3), "history": round(HISTORY_FRACTION * slow, 3),
                        "reported_shoulders": shoulder, "_fast": fast, "_slow": slow})
        day += dt.timedelta(days=1)
    return history, events


def model(swims, profile, today, reports=None, weekly=()):
    """Daily swim-specific remaining load, plus a no-new-swim projection."""
    swims = [a for a in swims if a["date"] <= today.isoformat()]
    empty = {"score": None, "threshold_blocks": THRESHOLD, "reference_units": None,
             "events": [], "history": [], "projection": []}
    if not swims:
        return {**empty, "reference_from": "awaiting swim"}
    reports = reports or {}
    ordered = sorted(swims, key=lambda x: (x["date"], x.get("start", "")))
    first = dt.date.fromisoformat(ordered[0]["date"])
    initial = _initial(ordered)
    if not initial:
        return {**empty, "reference_from": "awaiting usable swim data"}
    manual = (profile.get("calibration") or {}).get("swim_recovery", {}).get("reference_units")
    if manual:
        reference, interval, n_obs, source = float(manual), None, 0, "manual"
    else:
        reference, interval, n_obs = _fit(ordered, first, today, reports, initial, weekly)
        source = (f"fitted to {n_obs} shoulder report{'s' if n_obs != 1 else ''} · first swims as the prior"
                  if n_obs else "first comparable swims · provisional (no shoulder reports yet)")
    history, events = _simulate(ordered, first, today, reports, reference)
    fast, slow = history[-1]["_fast"], history[-1]["_slow"]
    for h in history:
        h.pop("_fast"); h.pop("_slow")
    decay_fast = 2 ** (-1 / HALF_LIFE_DAYS)
    decay_slow = 2 ** (-1 / HISTORY_HALF_LIFE_DAYS)
    projection = []
    for n in range(1, 31):
        fast *= decay_fast
        slow *= decay_slow
        projection.append({"date": (today + dt.timedelta(days=n)).isoformat(),
                           "score": round(fast + HISTORY_FRACTION * slow, 3)})
    score = history[-1]["score"]
    below = 0 if score < THRESHOLD else next((i + 1 for i, x in enumerate(projection)
                                              if x["score"] < THRESHOLD), None)
    return {"score": score, "threshold_blocks": THRESHOLD, "reference_units": round(reference, 1),
            "reference_from": source, "reference_interval": interval, "reference_initial": round(initial, 1),
            "shoulder_reports_used": n_obs, "recent": history[-1]["recent"],
            "history_component": history[-1]["history"], "below_threshold_in_days": below,
            "events": events, "history": history, "projection": projection,
            "method": "1.5-day recent and 14-day exposure half-lives; block fitted to next-day shoulder reports · provisional"}
