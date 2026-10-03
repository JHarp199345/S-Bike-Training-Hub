"""loads.py - training load per sport and per body system, and readiness.

Every activity - watch files (.fit from COROS, older .tcx exports) and bridge
rides the watch didn't record - is scored on three systems:

  ENGINE   heart, lungs, energy. Bike rides with power: training stress from
           watts (TSS). Everything else: heart-rate load (Banister TRIMP),
           calibrated to TSS on this rider's own rides that have both.
  IMPACT   feet, shins, calves, bones. Running and walking, step by step: each
           step's force (body weight x ~1.2 walking, ~2.0-3.0 jogging/running,
           more downhill) weighted to the 4th power, since tissue fatigue rises
           steeply with load per cycle. Also shown as "equivalent km" of a
           70 kg runner jogging.
  MUSCLE   thighs, glutes - force. Bike: pedal torque, squared (grinding at low
           cadence counts extra). Running: half its impact score. Gym: effort x
           minutes (the rider's RPE, or a default). Swimming: a trickle.

Units are "points": 100 engine points is an hour flat-out at threshold; impact
and muscle points are scaled to be comparable (a 5 km run at 70 kg ~ 40 impact).

Each system then gets fitness (chronic, slow average) and fatigue (acute, fast
average) and their ratio - the acute:chronic workload ratio (ACWR):

  under 0.8  room to build     0.8-1.3  near the chosen reference
  1.3-1.5    caution           over 1.5 higher than the chosen reference

The engine uses Banister's fitness (42-day) and fatigue (7-day) and is judged
by form, since the heart adapts fast. Impact and muscle use the standard
workload ratio (EWMA: last ~7 days vs last ~28). The 0.8-1.3 / 1.5 zones are
provisional coaching thresholds, not validated injury probabilities; soreness reports calibrate them over time. Readiness is
weakest-link: the worst system decides the day. The weekly budget per system
is 0.8-1.3 x its usual week, so it builds without outrunning recovery.

Numbers here are starting points from the sports-science literature; the
check-ins (legs, feet) are stored so the constants can be fit to the rider.
"""
import datetime as dt
import json
import math
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

import damage
import fit

SYSTEMS = ("engine", "impact", "muscle")
PHASES = {"run_durability": (0.35, 0.65), "aerobic_base": (0.60, 0.40),
          "bike_performance": (0.75, 0.25)}  # cardio, mechanical weights in the balance grade
TAU = {"engine": (42, 7)}                   # engine: Banister time constants (days) for fitness and fatigue
ACWR_N = (28, 7)                              # impact, muscle: Williams' EWMA acute:chronic ratio, 28 vs 7 days
ZONES = [(0.8, "room to build"), (1.3, "sweet spot"), (1.5, "caution"), (99, "danger")]      # chassis (impact, muscle)
FORM = [(-30, "big load for your base"), (-10, "training hard"), (5, "balanced"), (25, "fresh"), (999, "very fresh")]   # engine
GYM_RPE_DEFAULT = 5                    # a gym session's effort (RPE 1-10) when none is given; profile "gym_rpe" overrides
SPORT_OF = {"running": "run", "cycling": "bike", "swimming": "swim", "walking": "walk", "hiking": "walk",
            "training": "gym", "fitness_equipment": "gym", "generic": "gym"}
T_REF = 150 / (2 * math.pi * 90 / 60)  # pedal torque at 150 W, 90 rpm (~15.9 N·m)


def zone(acwr):
    if acwr is None:
        return "building baseline"
    return next(name for lim, name in ZONES if acwr < lim)


def form_band(tsb):
    return next(name for lim, name in FORM if tsb < lim)


# ── reading activities ──────────────────────────────────────────────────────

def _from_fit(p):
    a = fit.read(p)
    s = a["session"]
    sport = SPORT_OF.get(a["sport"], "gym" if not s.get("total_distance") else "other")
    recs = [{"t": r["timestamp"], "hr": r.get("heart_rate"), "w": r.get("power"), "rpm": r.get("cadence"),
             "d": r.get("distance"), "alt": r.get("altitude"), "v": r.get("speed"),
             "vo": r.get("vertical_oscillation"), "vr": r.get("vertical_ratio"), "step": r.get("step_length")}
            for r in a["records"] if "timestamp" in r]
    return {"id": Path(p).stem, "source": "watch", "start": a["start"], "sport": sport,
            "minutes": (s.get("total_timer_time") or (len(recs))) / 60, "distance_m": s.get("total_distance") or 0,
            "descent_m": s.get("total_descent") or 0, "records": recs,
            "session": s, "laps": a.get("laps", []), "events": a.get("events", []),     # the rest of what the watch saw (insights.py)
            "swim_lengths": a.get("lengths", []) if sport == "swim" else [],
            "pool_length_m": s.get("pool_length") if sport == "swim" else None,
            "swim_cadence": s.get("avg_cadence") if sport == "swim" else None}


def _from_tcx(p):
    ns = {"t": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
    root = ET.parse(p).getroot()
    act = root.find(".//t:Activity", ns)
    if act is None:
        return None
    sport = {"Running": "run", "Biking": "bike", "Other": "gym"}.get(act.get("Sport"), "gym")
    recs = []
    for tp in act.iter("{%s}Trackpoint" % ns["t"]):
        t = tp.find("t:Time", ns)
        if t is None:
            continue
        hr = tp.find("t:HeartRateBpm/t:Value", ns)
        d = tp.find("t:DistanceMeters", ns)
        alt = tp.find("t:AltitudeMeters", ns)
        w = tp.find(".//{*}Watts")
        cad = tp.find("t:Cadence", ns)
        if cad is None:
            cad = tp.find(".//{*}RunCadence")
        recs.append({"t": dt.datetime.fromisoformat(t.text.replace("Z", "+00:00")).timestamp(),
                     "hr": float(hr.text) if hr is not None else None, "w": float(w.text) if w is not None else None,
                     "rpm": float(cad.text) if cad is not None else None,
                     "d": float(d.text) if d is not None else None, "alt": float(alt.text) if alt is not None else None})
    if not recs:
        return None
    recs.sort(key=lambda r: r["t"])
    dist = max((r["d"] or 0) for r in recs)
    return {"id": Path(p).stem, "source": "watch", "start": recs[0]["t"], "sport": sport,
            "minutes": (recs[-1]["t"] - recs[0]["t"]) / 60, "distance_m": dist, "descent_m": _descent(recs),
            "records": recs}


def _descent(recs):
    down, last = 0.0, None
    for r in recs:
        a = r["alt"]
        if a is None:
            continue
        if last is not None and a < last - 2:                  # 2 m hysteresis against GPS noise
            down += last - a; last = a
        elif last is None or a > last + 2:
            last = a
    return down


def _from_bridge(p):
    import csv
    recs, seen = [], set()
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            if r["time"] in seen:
                continue
            seen.add(r["time"])
            try:
                recs.append({"t": dt.datetime.fromisoformat(r["time"]).timestamp(), "hr": None,
                             "w": float(r["power_w"] or 0), "rpm": float(r["cadence_rpm"] or 0), "d": None, "alt": None})
            except (ValueError, KeyError):
                continue
    moving = [r for r in recs if r["w"] > 0]
    if len(moving) < 120:
        return None
    return {"id": Path(p).stem, "source": "bridge", "start": recs[0]["t"], "sport": "bike",
            "minutes": len(moving) / 60, "distance_m": 0, "descent_m": 0, "records": recs}


def gather(folder_activities, folder_rides, extra_tcx=()):
    """Every activity once: watch files first; bridge rides the watch didn't record."""
    acts = []
    for p in sorted(Path(folder_activities).glob("*.fit")):
        try:
            acts.append(_from_fit(p))
        except (fit.FitError, OSError, KeyError):
            continue
    for p in list(Path(folder_activities).glob("*.tcx")) + [Path(x) for x in extra_tcx]:
        try:
            a = _from_tcx(p)
            if a:
                acts.append(a)
        except (ET.ParseError, OSError, ValueError):
            continue
    watch = [(a["start"], a["start"] + a["minutes"] * 60) for a in acts]
    for p in sorted(Path(folder_rides).glob("ride_*.csv")):
        if p.name.endswith(("_events.csv", "_report.csv")):
            continue
        b = _from_bridge(p)
        if b and not any(s - 600 <= b["start"] <= e for s, e in watch):
            acts.append(b)
    # the same watch activity imported twice (e.g. .fit and .tcx): keep one
    out, starts = [], []
    has_power = lambda a: any(r["w"] for r in a["records"][:600])
    for a in sorted(acts, key=lambda a: (round(a["start"] / 240), not has_power(a), a["source"] != "watch")):
        if a["minutes"] < 3 or any(abs(a["start"] - s) < 120 for s in starts):
            continue
        starts.append(a["start"]); out.append(a)
    return out


# ── scoring ─────────────────────────────────────────────────────────────────

def _avg_hr(a):
    hrs = [r["hr"] for r in a.get("records", []) if r.get("hr")]
    return round(statistics.fmean(hrs), 1) if len(hrs) >= 60 else None


def trimp(recs, hr_rest, hr_max):
    """Banister TRIMP: minutes x heart-rate reserve, weighted exponentially (men's 1.92)."""
    total, last = 0.0, None
    for r in recs:
        if r["hr"] is None:
            continue
        if last is not None:
            dt_min = min(r["t"] - last, 10) / 60
            x = max(0.0, min(1.0, (r["hr"] - hr_rest) / (hr_max - hr_rest)))
            total += dt_min * x * 0.64 * math.exp(1.92 * x)
        last = r["t"]
    return total


def power_tss(recs, ftp):
    """TSS from watts: NP from 30-s rolling average, IF = NP / FTP."""
    w = [r["w"] or 0 for r in recs if r["w"] is not None]
    if len(w) < 60:
        return None
    roll = [sum(w[i - 30:i]) / 30 for i in range(30, len(w) + 1)]
    np_ = (sum(x ** 4 for x in roll) / len(roll)) ** 0.25
    hours = len(w) / 3600
    return hours * (np_ / ftp) ** 2 * 100


# Foot impact: every step's force, weighted to the 4th power (Carter's bone "daily stress stimulus"
# exponent - tissue fatigue rises steeply with the force of each cycle, so a heavier or faster step counts
# disproportionately more). Reference: a 70 kg runner jogging at 2.8 m/s lands at ~2.56 x body weight;
# 5 km of that (~5,060 steps at 170 spm) = 40 points, so 8 points = one "equivalent km".
G = 9.81
REF_FORCE = 70 * G * (2.0 + 0.2 * 2.8)
REF_POINTS_PER_STEP = 40 / 5060
POWER = 4


def step_force(mass_kg, v, spm):
    """Peak vertical ground force (N) for one step: walking ~1.2x body weight, jogging ~2.0 + 0.2 x speed.
    Between 120 and 140 steps/min the gait blends from walking to running."""
    run_mult = 2.0 + 0.2 * max(v, 1.0)
    walk_mult = 1.2
    f = max(0.0, min(1.0, (spm - 120) / 20))
    return mass_kg * G * (walk_mult + f * (run_mult - walk_mult))


def automatic_run_learning(prof, reviews=None):
    """Protected/legacy recovery keeps its reviewed block size; ordinary training may learn (after a reviewed
    capacity change, only from runs since that review: see damage.learn_block)."""
    return (prof.get('return_to_run') is False and not prof.get('_protected_run_recovery') and not reviews)


def start_block(prof, scored):
    """The starting block from the setup's running answers (onboarding.running_start), until a calibration run
    measures it: a new runner's starting run is about 0.4 blocks (block = 2.5 x one run); someone who already runs
    has their usual week sit at about one block on the recovery curve. Points per minute come from their own runs
    when there are any, else the provisional prior."""
    rs = prof.get("running_start")
    if not rs:
        return None
    import starter_priors
    own = [a["impact"] / a["minutes"] for a in scored if a.get("sport") == "run" and a.get("minutes") and a.get("impact")][-10:]
    per_min = statistics.median(own) if own else starter_priors.RATES["run"]["impact"]
    run = per_min * rs["per_run"]
    if not rs.get("runs_now"):
        return round(2.5 * run, 1)
    # their usual week (rs['runs'] evenly spaced), repeated long enough to settle, peaks at about one block
    n, weeks = max(1, min(14, rs["runs"])), 8
    dates = [(dt.date(2026, 1, 5) + dt.timedelta(days=i)).isoformat() for i in range(7 * weeks)]
    doses = [0.0] * len(dates)
    for w in range(weeks):
        for k in range(n):
            doses[7 * w + round(k * 7 / n) % 7] += run
    peak = lambda b: max(c["after_blocks"] for c in damage.remodeling_response(dates, doses, block=b)["components"])
    lo, hi = run * 0.5, run * 40
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if peak(mid) > 1.0 else (lo, mid)
    return round(hi, 1)


RUN_DRIFT_MIN = 30      # heart-rate drift only means something on a steady run this long (minutes)


def run_drift(a):
    """Heart-rate drift on a steady run: speed per heartbeat, first half against second, after five minutes of
    settling (percent; under ~5% the run stayed comfortable). None if short, unsteady or missing speed/HR."""
    recs = [r for r in a.get("records") or [] if r.get("hr") and r.get("v")]
    if len(recs) < RUN_DRIFT_MIN * 60:
        return None
    body = recs[300:]
    v = [r["v"] for r in body]
    mean = sum(v) / len(v)
    if mean <= 0 or (sum((x - mean) ** 2 for x in v) / len(v)) ** 0.5 / mean > 0.15:   # intervals/hills: not steady
        return None
    half = len(body) // 2
    ratio = lambda part: (sum(r["v"] for r in part) / len(part)) / (sum(r["hr"] for r in part) / len(part))
    first, second = ratio(body[:half]), ratio(body[half:])
    return round(100 * (first - second) / first, 1)


def run_evidence(scored, prof):
    """Per running day, for learning the block: share of heart-rate reserve, pace per heartbeat (km/h per bpm
    over resting), heart-rate drift, and what the athlete said in the run report. The longest run of the day
    speaks for it."""
    out = {}
    rest, top = prof.get("hr_rest") or 60, prof.get("hr_max") or 185
    for a in scored:
        if a.get("sport") != "run" or not a.get("minutes") or not a.get("km"):
            continue
        if a["date"] in out and out[a["date"]]["minutes"] >= a["minutes"]:
            continue
        kmh = a["km"] / (a["minutes"] / 60)
        hr = a.get("avg_hr")
        said = (prof.get("_run_feedback") or {}).get(a["date"]) or {}
        out[a["date"]] = {"minutes": a["minutes"], "kmh": round(kmh, 2),
                          "hrr": round((hr - rest) / max(1, top - rest), 3) if hr else None,
                          "eff": round(kmh / max(1, hr - rest), 4) if hr else None,
                          "drift": a.get("drift_pct"), "effort": said.get("effort"), "rpe": said.get("rpe")}
    return out


def foot_impact(a, prof):
    """Impact points, steps and 70-kg-runner-equivalent km for a run or walk, second by second."""
    mass = prof["weight_kg"]
    default_spm = prof.get("run_cadence", 150) if a["sport"] == "run" else 105     # a run without cadence: jogging, not walking
    recs = a["records"]
    pts = steps = 0.0
    for i in range(1, len(recs)):
        r, q = recs[i], recs[i - 1]
        dt_s = min(r["t"] - q["t"], 10)
        if dt_s <= 0:
            continue
        v = r.get("v")
        if v is None and r["d"] is not None and q["d"] is not None:
            v = (r["d"] - q["d"]) / dt_s
        if not v or v < 0.3:
            continue                                                  # standing still: no steps
        spm = (r["rpm"] * 2) if r["rpm"] else default_spm             # watch cadence is per foot
        n = spm / 60 * dt_s
        f = step_force(mass, v, spm)
        if r["alt"] is not None and q["alt"] is not None and v > 0:
            grade = (r["alt"] - q["alt"]) / max(v * dt_s, 0.1)
            if grade < -0.03:                                         # downhill lands harder
                f *= 1 + min(0.4, 2 * (-grade - 0.03))
        pts += n * (f / REF_FORCE) ** POWER * REF_POINTS_PER_STEP
        steps += n
    if steps == 0 and a["distance_m"]:                                # no second-by-second data: from distance
        v = a["distance_m"] / max(a["minutes"] * 60, 1)
        steps = a["minutes"] * default_spm
        f = step_force(mass, v, default_spm)
        grade = 2 * a.get("descent_m", 0) / a["distance_m"]              # the descent spread over half the distance
        down = (1 + min(0.4, 2 * (grade - 0.03))) if grade > 0.03 else 1.0
        pts = steps * (f / REF_FORCE) ** POWER * REF_POINTS_PER_STEP * (1 + down ** POWER) / 2
    return pts, round(steps), pts / 8


def bike_muscle(recs):
    """Pedal force: sum of (torque / reference)^2 per second; 1 h at the reference = 12 points."""
    pts = 0.0
    for r in recs:
        w, rpm = r["w"] or 0, r["rpm"] or 0
        if w > 0 and rpm > 20:
            torque = w / (2 * math.pi * rpm / 60)
            pts += (torque / T_REF) ** 2 / 3600 * 12
    return pts


def personal_step(acts, prof):
    """This rider's typical impact per step and steps per minute on runs, from runs recorded with cadence -
    used for runs without it (a guessed cadence would misjudge walking vs jogging, and at the 4th power
    that difference is ~10x per step)."""
    per_step, spm = [], []
    for a in acts:
        if a["sport"] == "run" and sum(1 for r in a["records"] if r["rpm"]) > 60:
            pts, steps, _ = foot_impact(a, prof)
            if steps > 500:
                per_step.append(pts / steps)
                spm.append(steps / max(a["minutes"], 1))
    if not per_step:
        return None
    per_step.sort(); spm.sort()
    return {"points_per_step": per_step[len(per_step) // 2], "spm": spm[len(spm) // 2], "from_runs": len(per_step)}


def score(a, prof, k_hr):
    """Engine, impact and muscle points for one activity."""
    mass = prof["weight_kg"] / 70
    tr = trimp(a["records"], prof["hr_rest"], prof["hr_max"])
    ptss = power_tss(a["records"], prof["ftp"]) if a["sport"] == "bike" else None
    engine = ptss if ptss is not None else tr * k_hr
    engine_from = "watts" if ptss is not None else "heart rate"
    swim_kick = None
    css = prof.get("swim_css")
    fin_fraction = 0.0
    if a["sport"] == "swim":
        import swimload
        fin_fraction = swimload.equipment(a)["fins_fraction"]
    if a["sport"] == "swim" and fin_fraction:
        # Count observed HR time, not merely record count: FIT sampling is irregular.
        hr_times = sorted(r["t"] for r in a["records"] if r.get("hr") and prof["hr_rest"] <= r["hr"] <= prof["hr_max"])
        observed = sum(min(10, max(0, t - prev)) for prev, t in zip(hr_times, hr_times[1:]))
        coverage = observed / max(1, a["minutes"] * 60)
        if coverage >= .5:
            engine_from = "heart rate · fins (pace excluded)"
        elif a.get("swim_rpe") or a.get("rpe"):
            effort = a.get("swim_rpe") or a["rpe"]
            engine = a["minutes"] / 60 * (float(effort) / 7) ** 2 * 100
            engine_from = "effort proxy · fins (insufficient heart rate)"
        else:
            engine_from = "incomplete heart rate · fins (low confidence)"
    elif a["sport"] == "swim" and css and a["distance_m"] >= 100 and a["minutes"] > 0:
        pace = a["minutes"] * 60 / (a["distance_m"] / 100)                # s per 100 m
        engine = a["minutes"] / 60 * (css / pace) ** 3 * 100                # swim TSS: hours x (CSS / pace)^3 x 100
        ptss = engine
        engine_from = "swim pace vs CSS"
    impact = muscle = 0.0
    km = a["distance_m"] / 1000
    if a["sport"] in ("run", "walk"):
        impact, steps, eq_km = foot_impact(a, prof)
        ps = prof.get("_run_step")
        if a["sport"] == "run" and ps and sum(1 for r in a["records"] if r["rpm"]) <= 60:
            steps = round(a["minutes"] * ps["spm"])                   # no cadence: this rider's own runs decide
            impact = steps * ps["points_per_step"]
            eq_km = impact / 8
        v = a["distance_m"] / max(a["minutes"] * 60, 1)
        speed = max(1.0, 1 + 0.5 * (v / 2.8 - 1))
        linear = km * mass * 8 * speed                       # leg-muscle work stays proportional to weight x distance
        muscle = linear * (0.5 if a["sport"] == "run" else 0.3)
        a["_steps"], a["_eq_km"] = steps, eq_km
    elif a["sport"] == "bike":
        muscle = bike_muscle(a["records"])
    elif a["sport"] == "gym" and a.get("lift_muscle") is not None:
        muscle = a["lift_muscle"]                            # logged lifts: the leg regions' points (lifting.py)
    elif a["sport"] == "gym":
        rpe = a.get("rpe") or prof.get("gym_rpe") or GYM_RPE_DEFAULT
        muscle = a["minutes"] * rpe / 6 * 0.9
    elif a["sport"] == "swim":
        swim_kick = swimload.kick_dose(a)
        muscle = swim_kick["points"]
    return {"engine": engine, "impact": impact, "muscle": muscle, "trimp": tr, "power_tss": ptss, "engine_from": engine_from, "swim_kick": swim_kick}


def calibrate_hr(acts, prof):
    """Engine points per TRIMP, from this rider's rides with both watts and heart rate
    (the heart's cost of a known amount of work). Falls back to a threshold-heart-rate estimate."""
    ratios = []
    for a in acts:
        if a["sport"] == "bike":
            p = power_tss(a["records"], prof["ftp"])
            t = trimp(a["records"], prof["hr_rest"], prof["hr_max"])
            if p and t > 5 and a["minutes"] >= 20:
                ratios.append(p / t)
    if len(ratios) >= 2:
        ratios.sort()
        return ratios[len(ratios) // 2], len(ratios)
    x = (0.89 * prof["hr_max"] - prof["hr_rest"]) / (prof["hr_max"] - prof["hr_rest"])
    return 100 / (60 * x * 0.64 * math.exp(1.92 * x)), 0      # 1 h at threshold heart rate = 100


# ── the picture over days ───────────────────────────────────────────────────

def walking_inputs(scored, daily_steps, prof):
    """Steps walked outside runs each day (the watch's daily count minus run steps; recorded walks stay in it),
    each walking step's impact points, and how hard it is next to this rider's jogging step."""
    run_steps = {}
    for a in scored:
        if a["sport"] == "run":
            run_steps[a["date"]] = run_steps.get(a["date"], 0) + (a.get("steps") or 0)
    m = prof["weight_kg"]
    walk_pps = REF_POINTS_PER_STEP * (step_force(m, 1.3, 105) / REF_FORCE) ** POWER
    rs = prof.get("_run_step")
    jog_pps = rs["points_per_step"] if rs else REF_POINTS_PER_STEP * (step_force(m, 2.8, 170) / REF_FORCE) ** POWER
    return {"steps": {d: max(0, int(n) - run_steps.get(d, 0)) for d, n in (daily_steps or {}).items()},
            "pts_per_step": walk_pps, "severity": min(1.0, walk_pps / jog_pps),
            "step_force_lb": round(step_force(m, 1.3, 105) / damage.LBF)}


def analyse(acts, prof, today=None, meta=None, feet_reports=None, daily_steps=None, lift_blocks=None, weekly=(), run_reviews=None):
    today = today or dt.date.today()
    meta = meta or {}
    for a in acts:
        a.update(meta.get(a["id"], {}))                         # per-activity overrides, e.g. {"rpe": 7}
    k, n_cal = calibrate_hr(acts, prof)
    prof = dict(prof, _run_step=personal_step(acts, prof))
    scored = []
    for a in acts:
        s = score(a, prof, k)
        if a["sport"] == "swim":
            import swimload
            a["_swim_exposure"] = swimload.dose(a)
        extra = {"steps": a.pop("_steps"), "equiv_km": round(a.pop("_eq_km"), 1)} if "_steps" in a else {}
        if extra.get("steps"):                         # the force per step that carries the damage (its 4th-power mean), in lb
            f = (s["impact"] / extra["steps"] / REF_POINTS_PER_STEP) ** (1 / POWER) * REF_FORCE / damage.LBF
            extra |= {"force_lb": round(f), "steps_at_1000lb": round(s["impact"] * damage.STEPS_1000LB_PER_POINT)}
        if a["sport"] == "run":
            extra["drift_pct"] = run_drift(a)
        scored.append({**extra, "id": a["id"], "source": a["source"], "sport": a["sport"],
                       "date": dt.date.fromtimestamp(a["start"]).isoformat(),
                       "start": dt.datetime.fromtimestamp(a["start"]).strftime("%H:%M"),
                       "minutes": round(a["minutes"], 1), "km": round(a["distance_m"] / 1000, 2),
                       "avg_hr": _avg_hr(a), "descent_m": round(a.get("descent_m") or 0),
                       **{x: round(s[x], 1) for x in SYSTEMS},
                       **({"swim_exposure": a.pop("_swim_exposure")} if "_swim_exposure" in a else {}),
                       **({"swim_kick": s["swim_kick"]} if s["swim_kick"] is not None else {}),
                       "engine_from": s["engine_from"]})
    if not scored:
        return {"activities": [], "days": [], "today": None}
    first = min(dt.date.fromisoformat(s["date"]) for s in scored)
    by_day = {}
    for s in scored:
        d = by_day.setdefault(s["date"], {x: 0.0 for x in SYSTEMS} | {"sports": {}})
        for x in SYSTEMS:
            d[x] += s[x]
        sp = d["sports"].setdefault(s["sport"], {x: 0.0 for x in SYSTEMS} | {"minutes": 0.0})
        for x in SYSTEMS:
            sp[x] += s[x]
        sp["minutes"] += s["minutes"]
    fit_, fat = {x: 0.0 for x in SYSTEMS}, {x: 0.0 for x in SYSTEMS}
    days, day = [], first
    while day <= today:
        d = by_day.get(day.isoformat(), {x: 0.0 for x in SYSTEMS} | {"sports": {}})
        row = {"date": day.isoformat(), "sports": {k2: {x: round(v, 1) for x, v in sp.items()} for k2, sp in d["sports"].items()}}
        for x in SYSTEMS:
            if x in TAU:                                           # engine: Banister fitness/fatigue
                tf, ta = TAU[x]
                lf, la = 1 - math.exp(-1 / tf), 1 - math.exp(-1 / ta)
            else:                                                  # chassis: the standard injury-risk EWMA
                lf, la = 2 / (ACWR_N[0] + 1), 2 / (ACWR_N[1] + 1)
            fit_[x] += (d[x] - fit_[x]) * lf
            fat[x] += (d[x] - fat[x]) * la
            row[x] = {"load": round(d[x], 1), "fitness": round(fit_[x], 1), "fatigue": round(fat[x], 1),
                      "acwr": round(fat[x] / fit_[x], 2) if fit_[x] > 0.5 else None}
        days.append(row)
        day += dt.timedelta(days=1)
    have_days = (today - first).days + 1
    t = days[-1]
    cal = prof.get("calibration") or {}
    # "Tuned to you": a usual week per system set from how the body actually responded. It replaces the
    # model's estimate (which, with little history, can't know capacity) for the ratio, zone and budget.
    for x in SYSTEMS:
        u = (cal.get(x) or {}).get("usual_week")
        for r in days:
            r[x]["ratio"] = round(r[x]["fatigue"] * 7 / u, 2) if u else r[x]["acwr"]
    systems = {}
    for x in SYSTEMS:
        tuned = (cal.get(x) or {}).get("usual_week")
        ratio = t[x]["ratio"] if (tuned or have_days >= 14) else None                # two weeks of history, or tuned
        wk0 = today - dt.timedelta(days=today.weekday())
        used = sum(r[x]["load"] for r in days if r["date"] >= wk0.isoformat())
        usual = tuned or t[x]["fitness"] * 7
        tsb = round(t[x]["fitness"] - t[x]["fatigue"], 1)
        # Untuned, the engine is judged by form (the heart adapts fast; the tissue ratio zones don't fit it).
        # Tuned, every system uses its ratio to the usual week the rider's body has shown it can take.
        systems[x] = {"fitness": t[x]["fitness"], "fatigue": t[x]["fatigue"], "acwr": ratio, "form": tsb,
                      "zone": zone(ratio) if (tuned or x != "engine") else form_band(tsb),
                      "tuned": bool(tuned), "usual_week": round(usual), "model_usual_week": round(t[x]["fitness"] * 7),
                      "tuned_note": (cal.get(x) or {}).get("note"),
                      "week_used": round(used, 1),
                      "week_budget": [round(usual * 0.8), round(usual * 1.3)] if (tuned or have_days >= 14) else None,
                      "last7": round(sum(r[x]["load"] for r in days[-7:]), 1),
                      "prev7": round(sum(r[x]["load"] for r in days[-14:-7]), 1)}
    # Impact as damage still being repaired, tissue by tissue (see damage.py) - judged against the usual week.
    u_imp = systems["impact"]["usual_week"] if systems["impact"]["tuned"] else None
    walking = walking_inputs(scored, daily_steps, prof)
    systems["impact"]["tissue"] = damage.model([r["date"] for r in days], [r["impact"]["load"] for r in days],
                                                  u_imp, prof["weight_kg"], feet_reports,
                                                  run_doses=[r["sports"].get("run", {}).get("impact", 0.0) for r in days],
                                                  walking=walking, block=prof.get("block_points"), reviews=run_reviews,
                                                  runs=run_evidence(scored, prof) if automatic_run_learning(prof, run_reviews) else None,
                                                  learn_since=max([x for x in (prof.get('_reviewed_run_date'), prof.get('_block_test_date')) if x], default=None),
                                                  start_block=start_block(prof, scored) if not prof.get("block_points") else None)
    if systems["impact"]["tissue"]:
        systems["impact"]["tissue"]["walking"] = {k: v for k, v in walking.items() if k != "steps"}
    if systems["impact"]["tissue"]:
        systems["impact"]["zone"] = zone(systems["impact"]["tissue"]["remodeling"]["score"])
    import swimload
    swim_recovery = swimload.model([a for a in scored if a["sport"] == "swim"], prof, today, feet_reports, weekly)
    sports = {}
    for r in days[-7:]:
        for sp, v in r["sports"].items():
            s2 = sports.setdefault(sp, {x: 0.0 for x in SYSTEMS} | {"minutes": 0.0})
            for key in s2:
                s2[key] = round(s2[key] + v.get(key, 0), 1)
    phase = prof.get("phase", "run_durability")
    if phase not in PHASES:
        phase = "run_durability"
    cardio = systems["engine"]["last7"] / max(systems["engine"]["usual_week"], 1)
    impact = systems["impact"]["last7"] / max(systems["impact"]["usual_week"], 1)
    muscle = systems["muscle"]["last7"] / max(systems["muscle"]["usual_week"], 1)
    remodeling = systems["impact"]["tissue"]["remodeling"]["score"]
    block_limit = systems["impact"]["tissue"]["remodeling"]["threshold_blocks"]
    swim_ratio = (swim_recovery["score"] or 0) / swim_recovery["threshold_blocks"]
    lift_top = max((lift_blocks or {}).items(), key=lambda kv: kv[1], default=(None, 0.0))
    lift_ratio = lift_top[1] / 1.5                                            # a muscle group's lifting block vs its limit
    mechanical = max(impact, muscle, remodeling / block_limit, swim_ratio, lift_ratio)  # utilization ratios, not unlike units
    cardio_fit = max(0, 100 - 80 * abs(cardio - 0.9))
    mechanical_fit = max(0, 100 - 85 * max(0, mechanical - 1) - 20 * max(0, 0.6 - mechanical))
    cw, mw = PHASES[phase]
    balance = round(cw * cardio_fit + mw * mechanical_fit)
    grade = "A" if balance >= 85 else "B" if balance >= 70 else "C" if balance >= 55 else "D" if balance >= 40 else "E"
    headline = {"phase": phase, "cardio": {"ratio": round(cardio, 2), "last7": systems["engine"]["last7"],
                                               "usual_week": systems["engine"]["usual_week"]},
                "mechanical": {"ratio": round(mechanical, 2), "impact_ratio": round(impact, 2),
                               "muscle_ratio": round(muscle, 2), "remodeling_ratio": round(remodeling / block_limit, 2),
                               "remodeling_blocks": remodeling, "block_limit": block_limit,
                               "swim_blocks": swim_recovery["score"], "swim_ratio": round(swim_ratio, 2),
                               "lift_blocks": round(lift_top[1], 2) if lift_top[0] else None, "lift_region": lift_top[0],
                               "lift_ratio": round(lift_ratio, 2)},
                "balance": {"score": balance, "grade": grade, "cardio_weight": cw,
                            "mechanical_weight": mw, "provisional": True}}
    import bodymap
    bike_leg = sports.get("bike", {}).get("muscle", 0) / max(systems["muscle"]["usual_week"], 1)
    run_leg = sports.get("run", {}).get("muscle", 0) / max(systems["muscle"]["usual_week"], 1)
    swim_leg = sports.get("swim", {}).get("muscle", 0) / max(systems["muscle"]["usual_week"], 1)
    regional = bodymap.build(remodeling, swim_recovery["score"], bike_leg, run_leg, lift_blocks, swim_leg_ratio=swim_leg)
    return {"activities": scored, "days": days, "systems": systems, "headline": headline,
            "swim_recovery": swim_recovery, "body_map": regional, "sports_last7": sports,
            "calibration": {"engine_points_per_trimp": round(k, 3), "from_rides": n_cal, "run_step": prof.get("_run_step")},
            "history_days": have_days,
            "profile": {k2: prof[k2] for k2 in ("weight_kg", "hr_rest", "hr_max", "ftp")}}


def readiness(state, checkin=None):
    """Weakest link: each system's state from its load ratio and the rider's own report."""
    import journal
    checkin = journal.effective(checkin or {})                  # a confirmed journal flag counts like a slider
    out = {}
    order = {"go": 0, "easy": 1, "rest": 2}
    for x in SYSTEMS:
        s = state["systems"][x]
        level, why = "go", []
        if x == "engine" and not s.get("tuned"):
            if s["form"] < -30:
                level, why = "easy", [f"big engine load for your base (form {s['form']})"]
        elif x == "impact" and s.get("tissue"):
            recent = s["tissue"].get("event")
            if recent and recent["score"] >= 1:
                level = "rest"
                why.append(f"recent run response {recent['score']:.1f} reference sessions")
            elif recent and recent["score"] >= 0.5:
                level = "easy"
                why.append(f"recent run response {recent['score']:.1f} reference sessions")
            long = s["tissue"].get("remodeling")
            feels_good = all(checkin.get(k) is not None and checkin[k] <= 2 for k in ("feet", "legs"))
            if long and long.get("phase") == "tail" and long["score"] >= 1.0:
                # The remodeling tail: blocked only while over 1.1x the limit - and not on a day the feet and legs
                # both check in as particularly good (2/10 or better), when a short easy run is the call.
                over = long["score"] > long["tail_run_limit"]
                lv = "rest" if over and not feels_good else "easy"
                level = max(level, lv, key=lambda v: order[v])
                why.append(f"remodeling tail: {long['score']:.1f} blocks (tail limit {long['tail_run_limit']:.2f})"
                           + (" - but your feet and legs feel particularly good today" if over and feels_good else ""))
            elif long and long["score"] >= 1.5:
                level = "rest"
                why.append(f"accumulated mechanical load {long['score']:.1f} blocks (provisional limit {long['threshold_blocks']:.1f})"
                           + (f", cleared to run in ~{long['cleared_to_run_in_days']} days" if long.get("cleared_to_run_in_days") else ""))
            elif long and long["score"] >= 1.0:
                level = max(level, "easy", key=lambda v: order[v])
                why.append(f"accumulated mechanical load {long['score']:.1f} blocks (provisional limit {long['threshold_blocks']:.1f})")
            hops = (long or {}).get("hops") or {}
            if long and long["score"] >= 0.5 and level != "rest":
                # coming back from a block: the model's date AND the hop test (pain-free single-leg hops, worse leg)
                if not hops.get("fresh"):
                    level = "rest"
                    why.append(f"hop test first: {hops.get('needed', damage.HOP_CLEAR)} pain-free single-leg hops on the "
                               f"worse leg clears you to run" + (f" (last: {hops['last']} on {hops['date']})" if hops.get("date") else ""))
                elif hops["last"] < hops["needed"]:
                    level = "rest"
                    why.append(f"hop test: {hops['last']} pain-free hops - {hops['needed']} clears you to run")
            if long and long.get("walking_week_blocks", 0) >= 0.05:
                why.append(f"walking added {long['walking_week_blocks']:.2f} blocks this week")
        elif s["acwr"] is not None and (state["history_days"] >= 14 or s.get("tuned")):
            recent = [r[x]["ratio"] for r in state["days"][-8:-1] if r[x].get("ratio") is not None]
            if s["acwr"] >= 1.5:
                level, why = "rest", [f"{x} load {s['acwr']}x its usual"]
            elif s["acwr"] >= 1.3:
                level, why = "easy", [f"{x} load {s['acwr']}x its usual"]
            elif recent and max(recent) >= 1.5:
                # a spike's injury risk shows up in the week or two after it: tissue lags the numbers
                level, why = "easy", [f"{x} was at {max(recent)}x its usual in the last week - still settling"]
        elif s["last7"] and s["prev7"] and s["last7"] > 1.5 * s["prev7"]:
            level, why = "easy", [f"{x} load up {round(s['last7'] / s['prev7'], 1)}x on last week"]
        mo = state.get("morning")
        if x == "engine" and mo and mo["level"] != "go":           # the watch overnight: HRV, resting HR, sleep
            level = max(level, mo["level"], key=lambda v: order[v])
            why += ["this morning: " + w for w in mo["why"]]
        if x == "engine" and checkin.get("illness") and level == "go":
            level = "easy"; why.append("you confirmed your journal's flag: feeling ill")
        report = {"engine": checkin.get("breathing"), "impact": checkin.get("feet"), "muscle": checkin.get("legs")}[x]
        if report is not None:
            said = ("your confirmed journal flag (reads as 6/10)"
                    if {"impact": "feet", "muscle": "legs"}.get(x) in checkin.get("_flagged", []) else f"you rated it {report}/10")
            if report >= 8:
                level = "rest"; why.append(said)
            elif report >= 6 and level == "go":
                level = "easy"; why.append(said)
        out[x] = {"level": level, "why": why}
    # Two verdicts: the bike (engine and leg muscles - no impact on the bike) and running (feet and bones).
    names = {"engine": "heart and lungs", "impact": "feet and bones", "muscle": "leg muscles"}
    bike = [x for x in SYSTEMS if x != "impact"]
    worst = max((out[x]["level"] for x in bike), key=lambda v: order[v])
    limiting = [names[x] for x in bike if out[x]["level"] == worst and worst != "go"]
    run_level = max((out[x]["level"] for x in ("impact", "muscle")), key=lambda v: order[v])
    run_why = out["impact"]["why"] + (out["muscle"]["why"] if out["muscle"]["level"] != "go" else [])
    mo = state.get("morning")
    if mo and mo["level"] == "rest":
        run_level = "rest"
        run_why = run_why + ["this morning: " + w for w in mo["why"]]

    # lifting carries over: each muscle group's lifting blocks, weighted by how much that group works in the sport
    # (bodymap.REGIONS), count like that sport's own blocks - 1 block easy, 1.5 rest
    import bodymap
    lift_regions = ((state.get("lifting") or {}).get("regions") or {})
    shared_body=bodymap.from_state(state)
    def carry(sport):
        best = None
        for r, v in lift_regions.items():
            coef = bodymap.REGIONS.get(r, ("", {}))[1].get(sport, 0)
            eff = v["blocks"] * coef
            if coef and (best is None or eff > best[0]):
                best = (eff, v["name"], v["blocks"], coef)
        if not best or best[0] < 1:
            return None, None
        return ("rest" if best[0] >= 1.5 else "easy"), (f"lifting: {best[1].lower()} carrying {best[2]:.2f} blocks "
                                                         f"(participation weight {best[3]:.2f}; weighted indicator {best[0]:.2f})")
    for sport in ("bike", "run"):
        lv, why = carry(sport)
        if lv and sport == "bike":
            worst = max(worst, lv, key=lambda v: order[v])
            limiting.append(why)
        elif lv:
            run_level = max(run_level, lv, key=lambda v: order[v])
            run_why = run_why + [why]
    for sport in ("bike", "run", "swim"):
        notes=bodymap.overlap_advice(shared_body,sport)
        if notes and sport=="bike":
            worst=max(worst,"easy",key=lambda v:order[v]);limiting.extend(notes)
        elif notes and sport=="run":
            run_level=max(run_level,"easy",key=lambda v:order[v]);run_why.extend(notes)
    progression=state.get("run_progression")
    if progression and not progression.get("run_eligible"):
        run_level="rest";run_why.extend(progression.get("run_reasons",[]))
    run_how = {
        "rest": "Skip running today. Recheck the recent response and how your feet feel tomorrow; use the bike or pool if comfortable.",
        "easy": "Keep it flat and short: try 1 minute of easy jogging, 2 minutes walking, for about 10 minutes. Stop if discomfort builds and check again tomorrow.",
        "go": "Start with an easy, flat run no longer than a recent comfortable run. Check how your feet feel the next morning before adding steps.",
    }[run_level]
    swim_state = state.get("swim_recovery") or {}
    swim_blocks = swim_state.get("score")
    swim_level = out["engine"]["level"]
    swim_why = list(out["engine"]["why"])
    if swim_blocks is not None:
        if swim_blocks >= swim_state["threshold_blocks"]:
            swim_level = "rest"
            swim_why.append(f"swim recovery {swim_blocks:.2f} blocks (provisional limit 1.5)")
        elif swim_blocks >= 1:
            swim_level = max(swim_level, "easy", key=lambda v: order[v])
            swim_why.append(f"swim recovery {swim_blocks:.2f} blocks")
    lv, why = carry("swim")
    if lv:
        swim_level = max(swim_level, lv, key=lambda v: order[v])
        swim_why.append(why)
    notes=bodymap.overlap_advice(shared_body,"swim")
    if notes:
        swim_level=max(swim_level,"easy",key=lambda v:order[v]);swim_why.extend(notes)
    shoulders = checkin.get("shoulders")
    if shoulders is not None and shoulders >= 6:
        swim_level = max(swim_level, "rest" if shoulders >= 8 else "easy", key=lambda v: order[v])
        swim_why.append(f"shoulders {shoulders}/10")
    return {"systems": out, "verdict": worst, "limited_by": limiting,
            "running": {"verdict": run_level, "why": run_why, "how": run_how},
            "swimming": {"verdict": swim_level, "why": swim_why,
                         "how": {"go": "Swim within a recently comfortable volume; check your shoulders afterward.",
                                 "easy": "Keep the swim easy and shorter than usual; avoid hard pulling if shoulders feel heavy.",
                                 "rest": "Skip swimming today; choose comfortable work that does not load your shoulders."}[swim_level]}}


def load_profile(base):
    import rider
    p = rider.load(Path(base) / "profile.json")
    return {"weight_kg": float(p.get("weight_kg", 80.0)), "hr_rest": float(p.get("hr_rest", 60)),
            "hr_max": float(p.get("hr_max", 185)), "ftp": float(p.get("ftp", 150)),
            "calibration": p.get("load_calibration") or {}, "phase": p.get("training_phase", "run_durability"),
            "habitual_steps": int(p.get("habitual_steps") or damage.HABITUAL_STEPS),
            "gym_rpe": float(p.get("gym_rpe") or GYM_RPE_DEFAULT),
            "return_to_run": p.get("return_to_run"), "running_start": p.get("running_start")}


def load_steps(base):
    """Daily step counts from the watch, {date: steps} (activities/steps.json)."""
    try:
        return {d: int(n) for d, n in json.loads((Path(base) / "activities" / "steps.json").read_text()).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def set_steps(base, steps):
    """Record daily step counts ({YYYY-MM-DD: steps}); later values replace earlier ones for the same day."""
    import re
    clean = {}
    for d, n in (steps or {}).items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d)):
            raise ValueError(f"bad date {d!r}: use YYYY-MM-DD")
        n = int(n)
        if not 0 <= n <= 150000:
            raise ValueError(f"steps for {d} must be 0-150000")
        clean[str(d)] = n
    have = load_steps(base) | clean
    f = Path(base) / "activities" / "steps.json"
    f.parent.mkdir(exist_ok=True)
    tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(dict(sorted(have.items())), indent=1)); tmp.replace(f)
    return have


def set_phase(base, phase):
    """Set the phase used to weight the two headline systems."""
    import rider
    if phase not in PHASES:
        raise ValueError(f"phase is one of {', '.join(PHASES)}")
    p = rider.load(Path(base) / "profile.json")
    p["training_phase"] = phase
    rider.save(p)
    return phase


def set_swim_activity(base, activity_id, paddles=None, pull_buoy=None, swim_rpe=None, *, fins=None, snorkel=None, fins_fraction=None, snorkel_fraction=None, fin_type=None, kick_rpe=None, fin_kick_factor=None):
    """Record equipment and perceived effort for one imported swim."""
    base = Path(base)
    swims = {a["id"] for a in gather(base / "activities", base / "rides") if a["sport"] == "swim"}
    if activity_id not in swims:
        raise ValueError("activity_id must name an imported swim")
    path = base / "activities" / "meta.json"
    try:
        meta = json.loads(path.read_text())
    except (OSError, ValueError):
        meta = {}
    entry = meta.setdefault(activity_id, {})
    for name, value in (("fins", fins), ("snorkel", snorkel)):
        if value is not None:
            if not isinstance(value, bool):
                raise ValueError(name + " must be true or false")
            entry[name] = value
    for name, value, lo, hi in (("fins_fraction", fins_fraction, 0, 1), ("snorkel_fraction", snorkel_fraction, 0, 1),
                                ("kick_rpe", kick_rpe, 1, 10), ("fin_kick_factor", fin_kick_factor, 1, 2)):
        if value is not None:
            n = float(value)
            if not math.isfinite(n) or not lo <= n <= hi:
                raise ValueError(f"{name} must be between {lo} and {hi}")
            entry[name] = n
    if fin_type is not None:
        entry["fin_type"] = str(fin_type)[:100]
    if paddles is not None:
        if not isinstance(paddles, bool):
            raise ValueError("paddles must be true or false")
        entry["paddles"] = paddles
    if pull_buoy is not None:
        if not isinstance(pull_buoy, bool):
            raise ValueError("pull_buoy must be true or false")
        entry["pull_buoy"] = pull_buoy
    if swim_rpe is not None:
        n = int(swim_rpe)
        if not 1 <= n <= 10:
            raise ValueError("swim_rpe must be 1-10")
        entry["swim_rpe"] = n
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=1))
    tmp.replace(path)
    return entry


def set_capacity(base, system, usual_week, note=None):
    """Tune a system's usual week from how the body responded (None clears it back to the model)."""
    import rider
    if system not in SYSTEMS:
        raise ValueError(f"system is one of {', '.join(SYSTEMS)}")
    p = rider.load(Path(base) / "profile.json")
    cal = p.setdefault("load_calibration", {})
    if usual_week is None:
        cal.pop(system, None)
    else:
        u = float(usual_week)
        if not 1 <= u <= 5000:
            raise ValueError("usual_week must be between 1 and 5000 points")
        cal[system] = {"usual_week": round(u), "note": (note or "")[:300], "set": dt.date.today().isoformat()}
    rider.save(p)
    return cal


def summary(base, today=None):
    """Everything for the pages and the coach, from the project folder."""
    base = Path(base)
    try:
        meta = json.loads((base / "activities" / "meta.json").read_text())
    except (OSError, ValueError):
        meta = {}
    prof = load_profile(base)
    acts = gather(base / "activities", base / "rides")
    try:
        import coach
        checkins = coach.load(base / "coach.json")["checkins"]
        import journal
        checkins = {day: journal.effective(c) for day, c in checkins.items()}   # confirmed flags count like sliders
        feet_reports = {day: {k: float(c[k]) for k in ("feet", "legs", "hops", "shoulders") if c.get(k) is not None}
                        for day, c in checkins.items() if any(c.get(k) is not None for k in ("feet", "legs", "hops", "shoulders"))}
        prof["_run_feedback"] = {e["date"]: {"effort": e.get("effort"), "rpe": e.get("rpe")}
                                 for e in coach.load(base / "coach.json").get("training_feedback", {}).values()
                                 if e.get("sport") == "run"}
    except (OSError, ValueError, TypeError):
        feet_reports = {}
    try:                                        # calibrated capacities (calibration.py) feed the scoring
        import calibration, coach, rider
        d = coach.load(base / "coach.json")
        est = calibration.all_estimates(d, rider.load(base / "profile.json"), base / "rides",
                                        (today or dt.date.today()).isoformat())
        if est["swim_css"]["value"] and est["swim_css"]["source"] != "model":
            prof["swim_css"] = est["swim_css"]["value"]
        if est["block"]["value"] and "test" in (est["block"]["source"] or ""):
            prof["block_points"] = est["block"]["value"]
            prof["_block_test_date"] = est["block"].get("last_test")     # learning restarts from the measured block
    except Exception:
        est = None
    try:                                        # power and heart rate together, ride by ride (aerobic.py)
        import aerobic
        aero = aerobic.summary(acts, today=today)
    except Exception:
        aero = None
    lift_blocks, lifted = None, None
    try:                                        # logged lift sessions (lifting.py): leg points into the muscle system
        import coach as _coach, lifting
        dd = _coach.load(base / "coach.json")
        logs = [l for l in lifting.state(dd)["logs"] if l["date"] <= (today or dt.date.today()).isoformat()]
        for i, l in enumerate(logs):
            day0 = dt.datetime.fromisoformat(l["date"] + "T12:00").timestamp()
            for a in acts:                      # the watch's file of the same session: its heart rate stays, its muscle guess goes
                if a["sport"] == "gym" and dt.date.fromtimestamp(a["start"]).isoformat() == l["date"]:
                    a["lift_muscle"] = 0.0
            acts.append({"id": f"lift-{l['date']}-{i}", "source": "lifts", "start": day0 + i * 300, "sport": "gym",
                         "minutes": l.get("minutes") or 45, "distance_m": 0, "descent_m": 0, "records": [],
                         "lift_muscle": l["leg_points"]})
        lifted = lifting.model(dd, today)
        lift_blocks = {r: v["blocks"] for r, v in lifted["regions"].items()}
    except Exception:
        pass
    try:
        weekly = set(_coach.load(base / "coach.json").get("weekly", {}))
    except Exception:
        weekly = set()
    reviewed = next((x for x in reversed(coach.load(base / 'coach.json').get('capacity_adjustments', [])) if x['target']=='running_block' and x['date']<=(today or dt.date.today()).isoformat()), None)
    if reviewed:
        prof['block_points'] = reviewed['reference']
        prof['_reviewed_run_reference'] = True
        prof['_reviewed_run_date'] = reviewed['date']
    prof['_protected_run_recovery'] = bool(coach.load(base / 'coach.json').get('run_progression'))
    out = analyse(acts, prof, today, meta, feet_reports, load_steps(base), lift_blocks, weekly,
                  (coach.load(base / "coach.json").get("run_progression") or {}).get("reviews", []))
    out["lifting"] = lifted
    out["aerobic"] = aero
    try:                                        # the rest of what the watch saw, cross-referenced (insights.py)
        import insights
        out["insights"] = insights.summary(acts, out.get("days", []), checkins, aero, base / "rides", today)
    except Exception as e:
        out["insights"] = {"error": str(e)}
    try:                                        # how the sports carry over to each other (transfer.py)
        import transfer
        out["transfer"] = transfer.analyse(out.get("days", []), acts, (aero or {}).get("rides"),
                                           coach.load(base / "coach.json")["checkins"])
    except Exception as e:
        out["transfer"] = {"error": str(e)}
    rem = ((out.get("systems") or {}).get("impact", {}).get("tissue") or {}).get("remodeling") or {}
    import recovery
    # The return-to-run protocol (minimum wait between runs, repeated strength/balance/loading checks) is for
    # athletes coming back from a running injury: those who said so in the welcome setup, anyone already using it,
    # and installs from before the question existed (return_to_run absent). Everyone else runs on the blocks alone.
    cd_ = coach.load(base / "coach.json")
    if prof.get("return_to_run") is not False or cd_.get("run_progression"):
        out["run_progression"]=recovery.status(cd_,rem,today)
    else:
        out["run_progression"]=None
    if est and not est["block"]["value"] and rem.get("reference_points"):
        est["block"].update(value=round(rem["reference_points"] * damage.STEPS_1000LB_PER_POINT), source="first runs",
                            confidence=0.3)
    elif est and est["block"]["value"]:
        est["block"]["value"] = round(est["block"]["value"] * damage.STEPS_1000LB_PER_POINT)   # shown in 1,000-lb steps
    out["calibration_estimates"] = est
    import morning
    out["morning"] = morning.assess(morning.load(base), today)
    return out
