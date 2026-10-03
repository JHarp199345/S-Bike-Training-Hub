"""calibration.py - what you can do, estimated from tests and from training, with how sure we are.

Asked for on 2026-09-28: tests and the rolling estimate aren't either/or. Training
evidence moves a capacity a little every week but drifts; a test pins it down but
goes stale. Each capacity here combines them - a recent test anchors it, training
since then nudges it, a manual setting wins - and says how sure it is. When a test
is getting old it comes due, and the coach puts it on the calendar: tests are plan
items, not buttons.

  ftp          FTP ramp test; between tests, 95% of a 20-min best (the bridge does this)
  engine_hr90  the 6-min morning diagnostic: heart rate at 90 W (lower = fitter engine)
  legs_3min    big-gear test: best 3 minutes at 50-60 rpm; between tests, grit rides
  swim_css     critical swim speed: a 400 m and a 200 m time trial -> s per 100 m.
               Swims are then scored like TSS for the pool (hours x (CSS / pace)^3 x 100)
  block        the running block: how much running fits in one block. A benchmark run
               (2 miles, same flat loop, fixed easy pace) grows it by a graded amount -
               see block_test. Recovery time per block never changes (5 days); what
               conditioning changes is how much running a block holds.

The capacities feed the rest: FTP scales every bike number, the block sizes the
running load, CSS scores the swims, and the diagnostic sets "your normal".
"""
import datetime as dt
import statistics

TESTS = {
    "ftp": {"name": "FTP ramp test", "sport": "test", "minutes": 25, "every": 42, "capacity": "ftp",
            "how": "On the bike: 5 min warm-up, then +10 W a minute from about 55% of your FTP until you can't hold "
                   "it, then 5 min easy. The bridge runs it (Ride it on the Coach page, or Tests in the ride menu). "
                   "Fresh legs: nothing hard the two days before."},
    "diagnostic": {"name": "Morning diagnostic", "sport": "ride", "minutes": 6, "every": 7, "capacity": "engine_hr90",
                   "how": "6 minutes at fixed watts; your heart rate at 90 W is the number. Same time of day each time."},
    "big_gear": {"name": "Big-gear test", "sport": "test", "minutes": 20, "every": 42, "capacity": "legs_3min",
                 "focus": {"name": "Big-gear test", "rpm": [50, 60]},
                 "how": "On the bike: 10 min easy, then 3 minutes as hard as you can hold at 50-60 rpm (auto-shift "
                        "keeps you in that cadence - you push the watts), then easy. The best 3 minutes is the number."},
    "css": {"name": "Swim CSS test", "sport": "swim", "minutes": 40, "every": 42, "capacity": "swim_css",
            "how": "10 min easy warm-up. Swim 400 m as fast as you can hold evenly, rest 5-10 min easy, then 200 m "
                   "hard. Report both times (or the coach reads them from the watch's laps)."},
    "benchmark_run": {"name": "Benchmark run", "sport": "run", "minutes": 30, "every": 28, "capacity": "block",
                      "needs_running": True,
                      "how": "2 miles (3.2 km) on your same flat loop, at your fixed easy pace - not a race. Rested: "
                             "nothing hard the day before, about the same time of day. Afterwards say how it felt "
                             "(1-10) and whether anything hurt; then check in feet, legs and the hop test the next "
                             "two mornings - that's the test."},
    "run_calibration": {"name": "Running calibration", "sport": "run", "minutes": 60, "every": 42, "capacity": "block",
                        "needs_running": True,
                        "how": "One continuous effort, all at once: up to 60 minutes of running or run/walk in heart-rate "
                               "zone 2 (conversational), on a day you feel 100%. The test ends at 60 minutes. Don't stop "
                               "early unless you're out of time, too tired to keep going, your form breaks down or something "
                               "hurts - stopping for anything else ruins the test, and you'd wait a few days until you're "
                               "100% again to retry. If you stop early, the hub asks why. Then no running for 8 days: ride, "
                               "swim and lift as planned, and check in feet, legs and the hop test each morning. Day 9 sets "
                               "your running block."},
}

CAPACITIES = {
    "ftp": {"name": "FTP", "unit": "W", "test": "ftp"},
    "engine_hr90": {"name": "Heart rate at 90 W", "unit": "bpm", "test": "diagnostic", "lower_is_better": True},
    "legs_3min": {"name": "Big-gear 3 min", "unit": "W", "test": "big_gear"},
    "swim_css": {"name": "Critical swim speed", "unit": "s/100 m", "test": "css", "lower_is_better": True},
    "block": {"name": "Running block", "unit": "steps at 1,000 lb", "test": "benchmark_run"},
    "cp": {"name": "Critical power", "unit": "W", "test": "ftp"},
    "w_prime": {"name": "W' (work above CP)", "unit": "kJ", "test": "ftp"},
    "swim_dprime": {"name": "Swim D' (metres above CSS)", "unit": "m", "test": "css"},
}


def _days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def estimate(entries, every, today, prior=None):
    """entries: [{date, kind: test|manual|training|model, value}]. The latest test or manual setting anchors it;
    training since then moves it 30% of the way to their average; with no anchor, training (or the prior) leads.
    Confidence fades from 1 over twice the test interval."""
    entries = sorted(entries, key=lambda e: e["date"])
    anchors = [e for e in entries if e["kind"] in ("test", "manual")]
    if anchors:
        a = anchors[-1]
        after = [e["value"] for e in entries if e["kind"] == "training" and e["date"] > a["date"]]
        value = a["value"] + (0.3 * (statistics.fmean(after) - a["value"]) if after else 0.0)
        age = _days(a["date"], today)
        return {"value": value, "source": a["kind"] + (" + training" if after else ""), "last_test": a["date"],
                "confidence": round(max(0.2, 1 - age / (2 * every)), 2), "due_in_days": max(0, every - age)}
    train = [e["value"] for e in entries if e["kind"] == "training"][-3:]
    if train:
        return {"value": statistics.fmean(train), "source": "training", "last_test": None, "confidence": 0.4, "due_in_days": 0}
    guesses = [e["value"] for e in entries if e["kind"] == "model"]
    if guesses:
        prior = guesses[-1]                       # a starting guess (e.g. a watch's estimate) until something better
    if prior is not None:
        return {"value": prior, "source": "model", "last_test": None, "confidence": 0.2, "due_in_days": 0}
    return None


# ── evidence, capacity by capacity ───────────────────────────────────────────
def ftp_entries(profile):
    """From the profile's FTP history: ramp tests are tests, 20-min bests are training, the rest is a starting guess."""
    out = []
    def kind(src):
        s = (src or "").lower()
        return "test" if "ramp test" in s else "training" if "20-min best" in s else "manual" if "manual" in s else "model"
    import re
    src = profile.get("ftp_source", "")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", src)
    out.append({"date": m.group(1) if m else dt.date.today().isoformat(), "kind": kind(src), "value": float(profile["ftp"])})
    for h in profile.get("history", []):              # what FTP was, from the change that set it
        m = re.search(r"(\d{4}-\d{2}-\d{2})", h.get("source", ""))
        if m:
            out.append({"date": m.group(1), "kind": kind(h["source"]), "value": float(h["ftp"])})
    return out


def hr90_entries(d):
    return [{"date": day, "kind": "test", "value": float(c["hr90"])} for day, c in d.get("checkins", {}).items() if c.get("hr90")]


def best_low_cadence(path, secs=180, lo=45, hi=65):
    """The best `secs`-second average power with the average cadence in lo-hi (a big-gear effort), or None."""
    import report
    rows = report.load(path)
    w = [r["power"] or 0 for r in rows]
    c = [r["cadence"] or 0 for r in rows]
    if len(w) < secs:
        return None
    best, sw, sc = None, sum(w[:secs]), sum(c[:secs])
    for i in range(secs, len(w) + 1):
        if lo <= sc / secs <= hi and (best is None or sw > best):
            best = sw
        if i < len(w):
            sw += w[i] - w[i - secs]; sc += c[i] - c[i - secs]
    return round(best / secs) if best else None


def legs_entries(d, rides_dir, since, cache={}):
    """Big-gear 3 minutes from rides: on a big-gear test day it's a test, on grit rides it's training."""
    from pathlib import Path
    out = []
    for p in sorted(Path(rides_dir).glob("ride_*.csv")):
        if p.stem.count("_") != 2 or p.stem[5:15] < since:
            continue
        day = p.stem[5:15]
        plan = d.get("plans", {}).get(day) or {}
        grit = plan.get("focus") == "grit" or plan.get("test") == "big_gear"
        if not grit:
            continue
        key = (str(p), p.stat().st_mtime_ns)
        if key not in cache:
            try:
                cache[key] = best_low_cadence(p)
            except Exception:
                cache[key] = None
        if cache[key]:
            out.append({"date": day, "kind": "test" if plan.get("test") == "big_gear" else "training",
                        "value": float(cache[key])})
    return out


def css_from_times(t400, t200):
    """Critical swim speed from a 400 m and a 200 m time trial (seconds) -> seconds per 100 m."""
    t400, t200 = float(t400), float(t200)
    if not (t200 > 0 and t400 > t200 * 1.5):
        raise ValueError("the 400 m should take a bit more than twice the 200 m")
    return 100 * (t400 - t200) / 200


# ── storing what isn't derived from other data (swim tests, block tests, manual settings) ──
def record(d, capacity, value, kind="test", date=None, note=""):
    if capacity not in CAPACITIES:
        raise ValueError(f"capacity is one of {', '.join(CAPACITIES)}")
    if kind not in ("test", "manual", "training"):
        raise ValueError("kind is test, manual or training")
    e = {"date": date or dt.date.today().isoformat(), "kind": kind, "value": round(float(value), 1), "note": str(note)[:200]}
    d.setdefault("calibration", {}).setdefault(capacity, []).append(e)
    return e


# ── the benchmark run: a graded, predicted test of the running block ────────
# Each benchmark is predicted (heart rate at the fixed pace, from the last
# benchmarks), then graded on four things: how it felt, heart rate against the prediction, the check-ins leading
# up to it, and the two mornings after. Growth follows a curve of diminishing returns (fast gains early, a
# tapped-out mine near the ~5x ceiling), and the results overrule the curve: beating the prediction grows more
# and shifts the curve up for next time; falling short grows little. A painful or scary one grows nothing - repeat it.
BENCH_M = 3219              # 2 miles
BENCH_TOL = 0.15            # within 15% of 2 miles counts as the standard run
BENCH_CLIMB_M = 30          # flat: no more than this much descent over the run
G_MAX = 0.125               # the curve's growth for a good benchmark at the start (x0.8 headroom there = 10%)
CEILING_X = 5               # long-run capacity: about 5x the starting block (damage.ADAPT_GAIN 0.8 -> 1/(1-0.8))
SURPRISE_K = 0.5            # extra growth per unit the heart rate beats the prediction past 3%
MAX_GAIN = 0.15


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


# ── the running calibration: one measured effort sets the block (the rider's design, 2026-10-03) ─────────
# A block is one effort and its ~8-day recovery (5-day plateau, 3-day decline), so the most direct measure is one
# controlled effort and the 8 days after it. The block is that run's load times how well it was absorbed:
# heart-rate drift says how comfortably aerobic it stayed; the mornings and hop tests say what the tissue thought.
CAL_WATCH_DAYS = 8
CAL_DRIFT = ((3.0, 1.5), (5.0, 1.25), (8.0, 1.0))   # drift up to x% with clean mornings -> multiplier
CAL_OVER = 0.8                                      # rough mornings, a hop drop, pain or 8%+ drift: the run was more than a block
CAL_MINUTES = 60                                    # the test ends at an hour
CAL_COMPLETE = 58                                   # a watch file this long completed it
# Stopped early: why, and the most the multiplier may then be (None: the test is void - retry when 100% again)
CAL_STOPS = {"time": ("I ran out of time", 1.25), "tired": ("I was too tired to keep going", 1.0),
             "form": ("My form broke down", 1.0), "pain": ("Something hurt", CAL_OVER),
             "interrupted": ("Something else interrupted it", None)}


def calibration_stop(d, date, reason, note=""):
    """Why a running calibration stopped short of the hour."""
    if reason not in CAL_STOPS:
        raise ValueError("reason is " + ", ".join(CAL_STOPS))
    dt.date.fromisoformat(date)
    rec = d.setdefault("benchmarks", {}).setdefault("calibrations", {}).setdefault(date, {})
    if rec.get("result"):
        raise ValueError("That calibration is already graded")
    rec.update({"stopped": reason, "stop_note": str(note or "")[:300]})
    if reason == "pain":
        rec["pain"] = True
    return rec


def calibration_runs(d, acts):
    """Running calibrations on the plan: completed or stopped early, and which ones still need the reason."""
    out = []
    for day, plan in sorted(d.get("plans", {}).items()):
        if plan.get("test") != "run_calibration" or day not in acts:
            continue
        rec = ((d.get("benchmarks") or {}).get("calibrations") or {}).get(day) or {}
        mins = acts[day].get("minutes") or 0
        done = mins >= CAL_COMPLETE
        out.append({"date": day, "minutes": round(mins), "completed": done, "stopped": rec.get("stopped"),
                    "needs_reason": not done and not rec.get("stopped") and not rec.get("result"),
                    "result": {k: rec.get(k) for k in ("result", "block", "multiplier", "why")} if rec.get("result") else None,
                    "reasons": {k: v[0] for k, v in CAL_STOPS.items()}})
    return out[-3:]


def run_calibration(d, date, run, checkins, today, other_runs=()):
    """Grade a running calibration once its eight-day watch is over. `run` is the scored activity (impact points,
    drift_pct, minutes). Records the block as a test and returns the result; None while watching or already done."""
    cals = d.setdefault("benchmarks", {}).setdefault("calibrations", {})
    rec = cals.setdefault(date, {})
    if rec.get("result"):
        return None
    day = dt.date.fromisoformat(date)
    elapsed = _days(date, today)
    if elapsed <= CAL_WATCH_DAYS:
        return None
    window = [(day + dt.timedelta(days=k)).isoformat() for k in range(1, CAL_WATCH_DAYS + 1)]
    said = [checkins[k] for k in window if k in checkins and (checkins[k].get("feet") is not None or checkins[k].get("legs") is not None)]
    if len(said) < (6 if elapsed < 14 else 4):
        return None
    worst = max(c[k] for c in said for k in ("feet", "legs") if c.get(k) is not None)
    hop = lambda c: c.get("hops") if c.get("hops") is not None else min([x for x in (c.get("hops_left"), c.get("hops_right")) if x is not None], default=None)
    before = [hop(c) for k, c in sorted(checkins.items()) if k <= date and hop(c) is not None]
    after = [hop(checkins[k]) for k in window if k in checkins and hop(checkins[k]) is not None]
    dropped = bool(before and after) and min(after) <= before[-1] - 2
    drift = run.get("drift_pct")
    points = float(run.get("impact") or 0)
    if not points:
        return None
    minutes = run.get("minutes") or 0
    if minutes > CAL_MINUTES:                       # the test ends at an hour
        points *= CAL_MINUTES / minutes
    completed = minutes >= CAL_COMPLETE
    stopped = rec.get("stopped")
    if not completed and not stopped and elapsed < 14:
        return None                                  # waiting for why it stopped early
    cap = None if completed else CAL_STOPS[stopped][1] if stopped else 1.0
    if not completed and stopped and cap is None:
        rec.update({"result": "void", "graded": today, "minutes": minutes,
                    "why": f"stopped at {round(minutes)} min ({CAL_STOPS[stopped][0].lower()}): the test is void - retry on a day you're 100% again"})
        return rec
    if worst >= 6 or dropped or rec.get("pain") or (drift is not None and drift >= CAL_DRIFT[-1][0]):
        mult, why = CAL_OVER, ("rough mornings" if worst >= 6 else "the hop test dropped" if dropped else
                               "it hurt" if rec.get("pain") else f"heart rate drifted {drift:.1f}%") + ": the run was more than one block"
    elif worst >= 4:
        mult, why = 1.0, f"mornings up to {worst:g}/10: about one full block"
    elif drift is None:
        mult, why = 1.0, "clean mornings, but no heart-rate drift reading (under 30 min or unsteady): one block, no headroom claimed"
    else:
        mult = next(m for limit, m in CAL_DRIFT if drift <= limit)
        why = f"clean mornings and {drift:.1f}% heart-rate drift"
    if other_runs:
        mult = min(mult, 1.0)
        why += f"; ran again during the watch ({', '.join(other_runs)}), so no headroom claimed"
    if cap is not None and mult > cap:
        mult = cap
        why += (f"; stopped at {round(minutes)} min ({CAL_STOPS[stopped][0].lower()})" if stopped else
                f"; stopped at {round(minutes)} min with no reason given") + f", so at most x{cap}"
        if stopped == "time":
            why += " - a short test: repeat it with a full hour when you can"
    elif completed:
        why = "completed the hour; " + why
    block = round(points * mult, 1)
    rec.update({"result": "set", "points": round(points, 1), "multiplier": mult, "block": block, "drift_pct": drift,
                "worst_morning": worst, "hop_drop": dropped, "minutes": minutes, "completed": completed, "graded": today, "why": why})
    record(d, "block", block, "test", date, f"running calibration: {round(points)} pts x {mult} ({why})")
    return rec


def benchmark_report(d, date, rpe=None, pain=False, note=""):
    """How the benchmark felt (1 = nothing, 10 = a fight) and whether anything hurt."""
    r = d.setdefault("benchmarks", {}).setdefault("runs", {}).setdefault(date, {})
    if rpe is not None:
        rpe = int(rpe)
        if not 1 <= rpe <= 10:
            raise ValueError("rpe is 1-10")
        r["rpe"] = rpe
    r["pain"] = bool(pain)
    if note:
        r["note"] = str(note)[:300]
    return r


def _efficiency(run):
    """Metres a minute per heartbeat - and whether it was the standard run (2 miles, flat)."""
    if not isinstance(run, dict) or not run.get("minutes") or not run.get("km"):
        return None, False
    standard = abs(run["km"] * 1000 - BENCH_M) <= BENCH_M * BENCH_TOL and (run.get("descent_m") or 0) <= BENCH_CLIMB_M
    eff = run["km"] * 1000 / run["minutes"] / run["avg_hr"] if run.get("avg_hr") else None
    return eff, standard


def benchmark_expectation(d, date, prior_block):
    """The prediction for a benchmark on `date`: heart-rate efficiency (median of the last three standard
    benchmarks) and the growth if it goes as predicted, feels easy, and the mornings after are clean."""
    bm = d.get("benchmarks") or {}
    past = [r["eff"] for k, r in sorted((bm.get("runs") or {}).items()) if k < date and r.get("eff") and r.get("standard")][-3:]
    start = bm.get("start_block") or prior_block
    headroom = max(0.0, 1 - prior_block / (CEILING_X * start))
    return {"predicted_eff": round(statistics.median(past), 4) if past else None, "from_benchmarks": len(past),
            "rate": round(bm.get("rate", 1.0), 3), "headroom": round(headroom, 3),
            "growth_if_as_predicted": round(G_MAX * bm.get("rate", 1.0) * headroom, 4)}


def block_test(d, date, run, checkins, prior_block):
    """Grade a benchmark run once both mornings after are in. Returns the result (and records the new block when
    it grew), or None while waiting / already graded. `run` is the scored activity (impact, km, minutes, avg_hr,
    descent_m); a bare number is taken as its impact points."""
    bm = d.setdefault("benchmarks", {})
    runs = bm.setdefault("runs", {})
    rec = runs.setdefault(date, {})
    if rec.get("result"):
        return None
    day = dt.date.fromisoformat(date)
    after = [checkins.get((day + dt.timedelta(days=k)).isoformat()) or {} for k in (1, 2)]
    if not all(c.get("feet") is not None for c in after):
        return None
    run = run if isinstance(run, dict) else {"impact": float(run)}
    exp = benchmark_expectation(d, date, prior_block)
    bm.setdefault("start_block", prior_block)
    eff, standard = _efficiency(run)
    pred = exp["predicted_eff"] if standard else None
    ratio = eff / pred if eff and pred else None
    feel = _clamp((8 - rec["rpe"]) / 5, 0.2, 1.0) if rec.get("rpe") else None
    hr = _clamp((ratio - 0.95) / 0.10, 0.0, 1.0) if ratio else None
    parts = [x for x in (feel, hr) if x is not None]
    grade = sum(parts) / len(parts) if parts else 0.5
    before = [checkins.get((day - dt.timedelta(days=k)).isoformat()) or {} for k in range(1, 8)]
    before = [c for c in before if c.get("feet") is not None or c.get("legs") is not None]
    good = sum(all(c.get(k) is not None and c[k] <= 3 for k in ("feet", "legs")) for c in before)
    if any(c.get(k) is not None and c[k] >= 6 for c in before for k in ("feet", "legs")):
        leadup = 0.5
    else:
        leadup = 0.6 + 0.4 * good / len(before) if before else 0.8
    worst = max(c[k] for c in after for k in ("feet", "legs") if c.get(k) is not None)
    mornings = 1.0 if worst <= 3 else 0.5 if worst <= 5 else 0.0
    rate = bm.get("rate", 1.0)
    if rec.get("pain") or mornings == 0:
        gain, outcome = 0.0, "repeat"
    else:
        if ratio:
            rate = _clamp(rate * (1 + 2 * (ratio - 1)), 0.5, 2.0)      # the results overrule the curve
        curve = G_MAX * rate * exp["headroom"] * grade * leadup * mornings
        surprise = SURPRISE_K * max(0.0, ratio - 1.03) * mornings if ratio else 0.0
        gain = min(MAX_GAIN, curve + surprise)
        outcome = "grew" if gain >= 0.005 else "held"
    bm["rate"] = round(rate, 4)
    new = round(prior_block * (1 + gain), 1)
    rec.update({"result": outcome, "gain_pct": round(100 * gain, 1), "block_before": round(prior_block, 1),
                "block_after": new if outcome == "grew" else round(prior_block, 1),
                "eff": round(eff, 4) if eff else None, "standard": standard, "predicted_eff": pred,
                "vs_prediction": round(ratio, 3) if ratio else None,
                "grade": {"feel": feel, "heart_rate": hr, "lead_up": round(leadup, 2), "mornings_after": mornings,
                          "headroom": exp["headroom"], "rate": round(rate, 3)}})
    if outcome == "grew":
        why = (f"benchmark {'(standard 2 mi flat) ' if standard else ''}+{rec['gain_pct']}%"
               + (f", heart rate {ratio:.0%} of predicted" if ratio else "") + (f", felt {rec['rpe']}/10" if rec.get("rpe") else ""))
        record(d, "block", new, "test", date, why)
    return rec


def all_estimates(d, profile, rides_dir, today=None, block_prior=None):
    """Every capacity: value, where it came from, how sure, last tested, and when the next test is due."""
    today = today or dt.date.today().isoformat()
    since = (dt.date.fromisoformat(today) - dt.timedelta(days=90)).isoformat()
    stored = d.get("calibration", {})
    ev = {"ftp": ftp_entries(profile), "engine_hr90": hr90_entries(d),
          "legs_3min": legs_entries(d, rides_dir, since) + stored.get("legs_3min", []),
          "swim_css": stored.get("swim_css", []), "block": stored.get("block", [])}
    ev["ftp"] += stored.get("ftp", [])
    try:                                              # CP and W' from the best-effort curve (cp.py)
        import cp as cp_mod
        ftp_now = float(profile.get("ftp", 180))
        c = cp_mod.estimate(cp_mod.best_curve(rides_dir, today=dt.date.fromisoformat(today)), ftp_now)
        kind = "training" if c["source"] == "your best efforts" else "model"
        ev["cp"] = [{"date": today, "kind": kind, "value": float(c["cp"])}] + stored.get("cp", [])
        ev["w_prime"] = [{"date": today, "kind": kind, "value": round(c["w_prime"] / 1000, 1)}] + stored.get("w_prime", [])
        cp_note = c["source"]
    except Exception:
        ev["cp"], ev["w_prime"], cp_note = stored.get("cp", []), stored.get("w_prime", []), None
    ev["swim_dprime"] = stored.get("swim_dprime", [])
    ev["engine_hr90"] += stored.get("engine_hr90", [])
    out = {}
    for cap, meta in CAPACITIES.items():
        t = TESTS[meta["test"]]
        e = ev[cap]
        if cap == "engine_hr90" and len(e) >= 3:           # a diagnostic is noisy: the median of the last few
            recent = sorted(e, key=lambda x: x["date"])[-5:]
            e = [{"date": recent[-1]["date"], "kind": "test", "value": statistics.median(x["value"] for x in recent)}]
        est = estimate(e, t["every"], today, block_prior if cap == "block" else None)
        if est:
            est["value"] = round(est["value"], 1)
        out[cap] = {"name": meta["name"], "unit": meta["unit"], "test": meta["test"], "test_name": t["name"],
                    "every_days": t["every"], **(est or {"value": None, "source": None, "confidence": 0.0,
                                                          "last_test": None, "due_in_days": 0})}
        hist = sorted(ev[cap], key=lambda x: x["date"])
        out[cap]["history"] = hist[-6:]
    if cp_note:
        out["cp"]["note"] = out["w_prime"]["note"] = cp_note
    return out


def due(estimates, running_cleared=True):
    """Tests coming due (confidence fading), most urgent first - for Coming Up and for the coach to schedule."""
    out = []
    for cap, e in estimates.items():
        t = TESTS[e["test"]]
        if t.get("needs_running") and not running_cleared:
            continue
        if e["due_in_days"] <= 7:
            out.append({"test": e["test"], "name": t["name"], "capacity": e["name"], "due_in_days": e["due_in_days"],
                        "last_test": e["last_test"], "confidence": e["confidence"]})
    return sorted(out, key=lambda x: (x["due_in_days"], x["confidence"]))


def schedule(d, date, test):
    """Put a test on the calendar: the day's marker, time, how-to, and (big-gear) the focus that runs it."""
    import coach
    if test not in TESTS:
        raise ValueError(f"test is one of {', '.join(TESTS)}")
    t = TESTS[test]
    coach.set_plan(d, date, "go" if t["sport"] == "test" else None, f"{t['name']}: {t['how']}",
                   focus_=t.get("focus"), sport=t["sport"], minutes=t["minutes"])
    d["plans"][date]["test"] = test
    return d["plans"][date]


TEST_WEEK_EVERY = 6        # weeks between test weeks (a recovery week that peaks on test day, then rest)


def plan_test_week(d, monday, due_tests=None):
    """A test week that's also the recovery week: load comes down so you peak on test day, the tests are your best
    effort, the rest of the week is off, and training starts again the next Monday. The swim test goes two days
    out (arms first); the bike test is Saturday - FTP, or the big-gear test when FTP isn't due (one leg test a day).
    Returns the days planned."""
    import coach
    mon = dt.date.fromisoformat(monday)
    if mon.weekday() != 0:
        raise ValueError("a test week starts on a Monday")
    due_tests = set(due_tests or ["ftp", "css", "diagnostic"])
    bike_test = "ftp" if "ftp" in due_tests or "big_gear" not in due_tests else "big_gear"
    day = lambda i: (mon + dt.timedelta(days=i)).isoformat()
    easy = lambda i, sport, mins, note, focus=None: coach.set_plan(d, day(i), "easy", note, focus_=focus, sport=sport, minutes=mins)
    easy(0, "ride", 30, "Test week, recovery: easy 30 min spin - about half your usual.", "recovery")
    easy(1, "swim", 30, "Test week, recovery: easy 30 min swim.")
    easy(2, "ride", 30, "Test week, recovery: easy 30 min, cadence habit.", "cadence")
    if "css" in due_tests:
        schedule(d, day(3), "css")
    else:
        easy(3, "swim", 30, "Test week, recovery: easy 30 min swim.")
    schedule(d, day(4), "diagnostic")
    d["plans"][day(4)]["note"] = ("Test week: the 6-minute morning diagnostic first thing (your freshest reading), "
                                 "then rest - tomorrow is test day.")
    schedule(d, day(5), bike_test)
    d["plans"][day(5)]["note"] = "TEST DAY - " + d["plans"][day(5)]["note"]
    coach.set_plan(d, day(6), "rest", "Off - the day after test day. Training starts again tomorrow.", sport="rest", minutes=0)
    coach.add_event(d, day(5), f"Test day: {TESTS[bike_test]['name']}" + (" + swim CSS (Thu)" if "css" in due_tests else ""),
                    "test", "bike")
    return {day(i): d["plans"][day(i)] for i in range(7)}


def next_test_week(d, today=None):
    """The Monday of the next test week: six weeks after the last one, or next Monday if there's never been one."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else (today or dt.date.today())
    past = sorted(k for k, v in d.get("plans", {}).items() if v.get("test") in ("ftp", "big_gear") and k <= today.isoformat())
    nxt_mon = today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)
    if not past:
        return nxt_mon.isoformat()
    last = dt.date.fromisoformat(past[-1])
    last_mon = last - dt.timedelta(days=last.weekday())
    return max(nxt_mon, last_mon + dt.timedelta(weeks=TEST_WEEK_EVERY)).isoformat()
