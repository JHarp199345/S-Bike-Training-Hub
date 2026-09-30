"""insights.py - the rest of what the watch saw, read across the hub (the rider's ask, 2026-09-30).

The load models use a slice of each watch file. This reads the rest and cross-references it.
Everything here is a signal for the rider and the coach: it FLAGS with the numbers behind it,
it never scores, and it changes no load model.

  SWIM   length by length: SWOLF (seconds + strokes), stroke rate, pace. Where the stroke
         changes, by how much and how fast:
             held      no change worth the name
             gradual   a slow drift over the set - ordinary fatigue
             sudden    a step between neighbouring lengths - even a small one is the more
                       telling strain signal
         and how far into the swim it first broke down (or that it never did): over several
         swims that is the session length the stroke can hold. Heart-rate drop in the rests
         (a wrist reading in water: rough). A set's first length, off the wall on fresh arms,
         is left out so it can't fake a fade.
  RUN    splits (per lap and per five minutes): power, cadence, heart rate, pace, vertical
         oscillation and ratio, step length; ground contact per lap. Form in the last third
         against the first - judged only when the pace matched.
  RIDE   work (kJ) against the next morning's legs; heart rate at the start against the usual;
         heart-rate recovery after hard efforts; cadence and heart rate on days the legs carry
         running load; heart rate on a climb against the last time up it. (Drift within a ride
         and heart rate at the same watts live in aerobic.py and are quoted here.)
  ALL    pauses: stops mid-workout, counted and timed. A lot of them asks a question.
"""
import datetime as dt
import json
import statistics
from pathlib import Path

import swimload

mean, median = statistics.fmean, statistics.median

# ── pauses ───────────────────────────────────────────────────────────────────
PAUSE_MIN_S = 30          # a stop shorter than this is a breath, not a pause
PAUSES_MANY = 3           # this many, or...
PAUSED_SHARE = 0.10       # ...this share of the workout stopped, asks the question


def pauses(a):
    """Stops mid-workout: the watch's own timer stops, and (bike, run) stretches of standing still."""
    spans = []
    ev = [e for e in a.get("events", []) if e.get("event") == 0 and "timestamp" in e]
    stop = None
    for e in ev:
        if e.get("event_type") in (1, 4):
            stop = e["timestamp"]
        elif e.get("event_type") == 0 and stop is not None:
            if e["timestamp"] - stop >= PAUSE_MIN_S:
                spans.append((stop, e["timestamp"]))
            stop = None
    recs = a.get("records", [])
    if a["sport"] in ("bike", "run") and len(recs) > 120:
        still = (lambda r: not (r.get("rpm") or 0)) if a["sport"] == "bike" else \
                (lambda r: not (r.get("rpm") or 0) and (r.get("v") or 0) < 0.3)
        begin, prev = None, recs[0]["t"]
        for r in recs:
            if r["t"] - prev >= PAUSE_MIN_S:                         # the file itself has a hole: the watch was paused
                spans.append((prev, r["t"]))
            if still(r):
                begin = r["t"] if begin is None else begin
            else:
                if begin is not None and r["t"] - begin >= PAUSE_MIN_S and begin > recs[0]["t"] + 60:
                    spans.append((begin, r["t"]))
                begin = None
            prev = r["t"]
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1] + 5:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    total = sum(e - s for s, e in merged)
    whole = max(1.0, a["minutes"] * 60 + total)
    many = len(merged) >= PAUSES_MANY or total / whole >= PAUSED_SHARE and bool(merged)
    return {"count": len(merged), "seconds": round(total), "share": round(total / whole, 2), "many": many,
            "at_min": [round((s - a["start"]) / 60, 1) for s, _ in merged]}


# ── swimming ─────────────────────────────────────────────────────────────────
STEP_MIN = 2.0            # SWOLF points: the smallest change that counts (one stroke and one second)
FADE_PCT = 5.0            # % over a set: under this it held
WINDOW = 4                # lengths averaged either side when looking for a step


def _hr_at(recs, t, span=3):
    near = [r["hr"] for r in recs if r.get("hr") and abs(r["t"] - t) <= span]
    return mean(near) if near else None


def swim(a):
    """One pool swim, length by length. None when the file has no lengths."""
    raw = a.get("swim_lengths") or []
    pool = a.get("pool_length_m")
    if not raw or not pool:
        return None
    # the sets: runs of active lengths between rests
    sets, cur, rests = [], [], []
    for x in raw:
        if x.get("length_type") == 1:
            cur.append(x)
        else:
            if cur:
                sets.append(cur); cur = []
            if (x.get("total_elapsed_time") or 0) >= 10 and sets:
                rests.append(x)
    if cur:
        sets.append(cur)
    counted = [x for s in sets for x in s if (x.get("total_strokes") or 0) > 0]
    if len(counted) < 8:
        return None
    styles = [x.get("swim_stroke") for x in counted]
    main = max(set(styles), key=styles.count)
    t_med = median(x["total_timer_time"] for x in counted if x.get("swim_stroke") == main)

    def good(x):          # the main stroke, strokes counted, and not two lengths the watch merged into one
        return (x.get("swim_stroke") == main and (x.get("total_strokes") or 0) > 0
                and 0.6 * t_med <= x["total_timer_time"] <= 1.6 * t_med)
    lengths, done_m = [], 0.0
    for si, s in enumerate(sets):
        for li, x in enumerate(s):
            done_m += pool
            if good(x) and li > 0:        # a set's first length is a push-off on fresh arms: it would fake a fade
                t, n = x["total_timer_time"], x["total_strokes"]
                lengths.append({"set": si, "m": round(done_m), "min": round((x["start_time"] - a["start"]) / 60, 1),
                                "seconds": round(t, 1), "strokes": n, "swolf": round(t + n, 1),
                                "rate": x.get("avg_swimming_cadence"), "pace_100": round(t / pool * 100, 1)})
    if len(lengths) < 8:
        return None
    sw = [x["swolf"] for x in lengths]
    base = median(sw[:6])
    diffs = [abs(b - a_) for a_, b in zip(sw, sw[1:])]
    noise = 1.48 * median(abs(d - median(diffs)) for d in diffs) if len(diffs) > 4 else 1.0
    need = max(STEP_MIN, 2 * noise / (WINDOW ** 0.5) * 2 ** 0.5)       # two noise widths of a window-to-window difference

    # per set: the last third against the first third
    set_rows, biggest = [], None
    for si in sorted({x["set"] for x in lengths}):
        ls = [x for x in lengths if x["set"] == si]
        if len(ls) < 6:
            continue
        k = max(2, len(ls) // 3)
        first, last = ls[:k], ls[-k:]
        f = lambda key, part: mean(x[key] for x in part)
        fade = 100 * (f("swolf", last) - f("swolf", first)) / f("swolf", first)
        # a step: neighbouring windows inside the set, where the later one sits higher and stays there
        step = None
        for i in range(WINDOW, len(ls) - WINDOW + 1):
            before, after = ls[i - WINDOW:i], ls[i:i + WINDOW]
            jump = f("swolf", after) - f("swolf", before)
            stays = f("swolf", ls[i:]) - f("swolf", ls[:i]) >= jump / 2
            if jump >= need and stays and (step is None or jump > step["jump"]):
                ds, dtm = f("strokes", after) - f("strokes", before), f("seconds", after) - f("seconds", before)
                step = {"jump": round(jump, 1), "pct": round(100 * jump / f("swolf", before), 1), "at_m": ls[i]["m"],
                        "at_min": ls[i]["min"], "length_in_set": i + 1,
                        "what": "more strokes" if ds >= 0.75 and dtm < 1 else "slower" if dtm >= 1 and ds < 0.75
                                else "more strokes and slower" if ds >= 0.75 else "slower"}
        kind = "sudden" if step else "gradual" if fade >= FADE_PCT else "held"
        row = {"set": len(set_rows) + 1, "lengths": len(ls), "metres": round(len(ls) * pool),
               "swolf_first": round(f("swolf", first), 1), "swolf_last": round(f("swolf", last), 1),
               "strokes_first": round(f("strokes", first), 1), "strokes_last": round(f("strokes", last), 1),
               "pace_first": round(f("pace_100", first), 1), "pace_last": round(f("pace_100", last), 1),
               "rate_first": round(f("rate", first), 1) if all(x["rate"] for x in first) else None,
               "rate_last": round(f("rate", last), 1) if all(x["rate"] for x in last) else None,
               "fade_pct": round(fade, 1), "kind": kind, "step": step}
        set_rows.append(row)
        if step and (biggest is None or step["jump"] > biggest["jump"]):
            biggest = step | {"set": row["set"]}

    # how far in the stroke first broke down: a rolling average over the baseline, and staying there
    roll = [mean(sw[i:i + WINDOW]) for i in range(len(sw) - WINDOW + 1)]
    broke = None
    for i, v in enumerate(roll):
        if i >= 2 and v >= base + need and all(u >= base + need / 2 for u in roll[i:i + WINDOW]):
            broke = {"at_m": lengths[i]["m"], "at_min": lengths[i]["min"], "swolf": round(v, 1)}
            break
    # heart rate in the rests: the drop over the first 30 s and 60 s
    recs = a.get("records", [])
    drops = []
    for x in rests:
        t0, dur = x["start_time"], x.get("total_elapsed_time") or 0
        peak = [r["hr"] for r in recs if r.get("hr") and t0 - 10 <= r["t"] <= t0 + 15]
        top = max(peak) if peak else None                    # the wrist reads late in water: take the peak around the wall
        row = {"rest_s": round(dur), "hr_start": round(top) if top else None}
        for s in (30, 60):
            if dur >= s and top:
                h = _hr_at(recs, t0 + s - 3, 2)               # the seconds just before the mark: still inside the rest
                row[f"drop_{s}"] = round(top - h) if h else None
        if top:
            drops.append(row)
    d30 = [r["drop_30"] for r in drops if r.get("drop_30") is not None]
    d60 = [r["drop_60"] for r in drops if r.get("drop_60") is not None]
    total_m = round(sum(len(s) for s in sets) * pool)
    kinds = [r["kind"] for r in set_rows]
    overall = "sudden" if "sudden" in kinds else "gradual" if "gradual" in kinds else "held"
    return {"stroke": swimload.STROKES.get(main, str(main)), "pool_m": pool, "total_m": total_m,
            "lengths_read": len(lengths), "baseline_swolf": round(base, 1), "noise": round(noise, 1),
            "swolf_avg": round(mean(sw), 1), "strokes_avg": round(mean(x["strokes"] for x in lengths), 1),
            "rate_avg": round(mean(x["rate"] for x in lengths if x["rate"]), 1) if any(x["rate"] for x in lengths) else None,
            "sets": set_rows, "kind": overall, "biggest_step": biggest, "broke_down": broke,
            "held_m": broke["at_m"] if broke else total_m,
            "rests": drops, "rest_drop_30": round(median(d30)) if d30 else None,
            "rest_drop_60": round(median(d60)) if d60 else None, "lengths": lengths}


def swim_length_trend(rows):
    """Across swims: how far in the stroke held. rows = [{date, total_m, held_m, broke}] oldest first."""
    if not rows:
        return None
    last = rows[-5:]
    held_all = [r for r in last if not r["broke"]]
    out = {"swims": rows, "median_held_m": round(median(r["held_m"] for r in last))}
    if len(last) < 3:
        out["read"] = f"{len(rows)} swim{'s' if len(rows) != 1 else ''} read; three are needed before it says anything about length."
    elif len(held_all) >= len(last) - 1:
        out["read"] = (f"The stroke held to the end in {len(held_all)} of the last {len(last)} swims "
                       f"(longest {max(r['total_m'] for r in last)} m): there is room to swim longer.")
    else:
        out["read"] = (f"The stroke has been breaking down around {out['median_held_m']} m in; "
                       f"sessions much past that are swum on a tired stroke.")
    return out


# ── running ──────────────────────────────────────────────────────────────────
def _split(recs):
    mv = [r for r in recs if (r.get("v") or 0) > 0.5]
    if len(mv) < 30:
        return None
    g = lambda k: [r[k] for r in mv if r.get(k)]
    avg = lambda k, nd=0: round(mean(g(k)), nd) if g(k) else None
    v = mean(r["v"] for r in mv)
    return {"seconds": len(mv), "pace_min_km": round(1000 / v / 60, 2), "speed": round(v, 2), "hr": avg("hr"), "watts": avg("w"),
            "steps_min": round(2 * mean(g("rpm"))) if g("rpm") else None, "vertical_osc_mm": avg("vo"),
            "vertical_ratio_pct": avg("vr", 1), "step_length_m": round(mean(g("step")) / 1000, 2) if g("step") else None}


def run(a):
    recs = a.get("records", [])
    if len(recs) < 300:
        return None
    s = a.get("session") or {}
    t0 = recs[0]["t"]
    five = []
    for i in range(0, int((recs[-1]["t"] - t0) // 300) + 1):
        sp = _split([r for r in recs if t0 + 300 * i <= r["t"] < t0 + 300 * (i + 1)])
        if sp and sp["seconds"] >= 120:
            five.append({"from_min": 5 * i} | sp)
    laps = [{"lap": i + 1, "minutes": round((l.get("total_timer_time") or 0) / 60, 1),
             "km": round((l.get("total_distance") or 0) / 1000, 2), "hr": l.get("avg_heart_rate"),
             "watts": l.get("avg_power"), "steps_min": 2 * l["avg_cadence"] if l.get("avg_cadence") else None,
             "contact_ms": l.get("avg_stance_time"), "vertical_osc_mm": l.get("avg_vertical_oscillation"),
             "vertical_ratio_pct": l.get("avg_vertical_ratio"),
             "step_length_m": round(l["avg_step_length"] / 1000, 2) if l.get("avg_step_length") else None}
            for i, l in enumerate(a.get("laps", [])) if (l.get("total_timer_time") or 0) >= 60]
    third = len(recs) // 3
    first, last = _split(recs[:third]), _split(recs[-third:])
    drift = None
    if first and last:
        pct = lambda k: round(100 * (last[k] - first[k]) / first[k], 1) if first.get(k) and last.get(k) else None
        same_pace = abs(last["speed"] - first["speed"]) / first["speed"] <= 0.05
        drift = {"pace_matched": same_pace, "speed_pct": pct("speed"), "hr_pct": pct("hr"), "watts_pct": pct("watts"),
                 "steps_min_pct": pct("steps_min"), "vertical_ratio_pct": pct("vertical_ratio_pct"),
                 "step_length_pct": pct("step_length_m")}
        if len(laps) >= 2 and laps[0]["contact_ms"] and laps[-1]["contact_ms"]:
            drift["contact_pct"] = round(100 * (laps[-1]["contact_ms"] - laps[0]["contact_ms"]) / laps[0]["contact_ms"], 1)
        tells = []
        if same_pace:                                        # at a different pace the form changes by design
            if (drift.get("vertical_ratio_pct") or 0) >= 5: tells.append("more bounce per step")
            if (drift.get("step_length_pct") or 0) <= -5: tells.append("shorter steps")
            if (drift.get("contact_pct") or 0) >= 5: tells.append("longer on the ground")
        drift["form_changed"] = tells
    return {"steps": 2 * s["total_cycles"] if s.get("total_cycles") else None, "watts": s.get("avg_power"),
            "contact_ms": s.get("avg_stance_time"), "vertical_osc_mm": s.get("avg_vertical_oscillation"),
            "vertical_ratio_pct": s.get("avg_vertical_ratio"),
            "step_length_m": round(s["avg_step_length"] / 1000, 2) if s.get("avg_step_length") else None,
            "laps": laps, "five_min": five, "drift": drift}


# ── riding ───────────────────────────────────────────────────────────────────
START = (120, 300)        # seconds: the easy opening minutes, once the heart has woken up
START_HIGH = 8            # bpm over the usual at the same watts: a "not recovered" flag


def efforts(recs):
    """Heart-rate recovery after hard efforts: a minute clearly above the ride, then a minute clearly easier."""
    w = [r.get("w") or 0 for r in recs]
    hr = [r.get("hr") for r in recs]
    if len(w) < 600 or sum(1 for h in hr if h) < 300:
        return []
    moving = [x for x in w if x > 0]
    ref = median(moving) if moving else 0
    out, i = [], 60
    while i < len(w) - 60:
        before, after = mean(w[i - 60:i]), mean(w[i:i + 60])
        if before >= max(ref * 1.2, ref + 20) and after <= 0.75 * before:
            top = [h for h in hr[max(0, i - 5):i + 15] if h]
            later = [h for h in hr[i + 55:i + 65] if h]
            if top and later:
                out.append({"at_min": round(i / 60, 1), "watts": round(before), "hr_top": round(max(top)),
                            "drop_60": round(max(top) - mean(later))})
            i += 90
        else:
            i += 1
    return out


def ride(a, aero=None):
    recs = a.get("records", [])
    if len(recs) < 300:
        return None
    s = a.get("session") or {}
    w = [r.get("w") or 0 for r in recs]
    kj = (s.get("total_work") or sum(w)) / 1000
    ped = [r["rpm"] for r in recs if (r.get("rpm") or 0) >= 20]
    out = {"work_kj": round(kj), "cadence": round(mean(ped)) if ped else None,
           "hr_min": s.get("min_heart_rate"), "hr_max": s.get("max_heart_rate")}
    start = [r for r in recs[START[0]:START[1]] if r.get("hr")]
    if len(start) >= 120:
        out["start_hr"] = round(mean(r["hr"] for r in start))
        out["start_watts"] = round(mean(r.get("w") or 0 for r in start))
    ef = efforts(recs)
    out["efforts"] = ef
    out["recovery_60"] = round(median(e["drop_60"] for e in ef)) if ef else None
    if aero:
        out.update({k: aero.get(k) for k in ("ef", "decoupling_pct", "judged", "aerobic", "hr_at_band", "np", "avg_hr")})
        if aero.get("judged") and aero.get("decoupling_pct") is not None:
            out["drift_read"] = ("Heart rate stayed with the watts: this length was inside the aerobic range, and could go longer."
                                 if aero["aerobic"] else
                                 f"Heart rate drifted {aero['decoupling_pct']}% for the same watts: that was the limit for the day.")
    return out


def _fit_line(pairs):
    """Least squares y on x, and the correlation. None under 5 points or when x doesn't vary."""
    if len(pairs) < 5:
        return None
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    mx, my = mean(xs), mean(ys)
    sxx, syy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    if not sxx:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return {"slope": sxy / sxx, "r": round(sxy / (sxx * syy) ** 0.5, 2) if syy else 0.0, "n": len(pairs)}


def work_vs_legs(rides_by_day, run_days, checkins):
    """A day's riding (kJ) against the next morning's legs (1-10, higher is heavier). Days with a run are left
    out: the run would own the legs."""
    pairs = []
    for day, kj in sorted(rides_by_day.items()):
        nxt = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
        legs = (checkins.get(nxt) or {}).get("legs")
        if legs is not None and day not in run_days:
            pairs.append({"date": day, "work_kj": round(kj), "legs_next": legs})
    fit = _fit_line([(p["work_kj"], p["legs_next"]) for p in pairs])
    out = {"pairs": pairs, "needed": 5}
    if fit:
        out.update(legs_per_100kj=round(fit["slope"] * 100, 2), r=fit["r"])
        out["read"] = (f"Over {fit['n']} rides, each 100 kJ moved the next morning's legs by {fit['slope'] * 100:+.1f} "
                       f"(correlation {fit['r']:+.2f}).")
    else:
        out["read"] = f"{len(pairs)} of 5 ride days with a legs check-in the next morning: not enough to fit yet."
    return out


def leg_check(rows, days):
    """Does the ride show the running load? Each ride's cadence and heart rate at the same watts, against the
    impact fatigue the legs carried that morning (the day before's number)."""
    fatigue = {d["date"]: d["impact"]["fatigue"] for d in days if d.get("impact")}
    pts = []
    for r in rows:
        prev = (dt.date.fromisoformat(r["date"]) - dt.timedelta(days=1)).isoformat()
        if prev in fatigue and r["ride"].get("cadence") and r["minutes"] >= 10:
            pts.append({"date": r["date"], "leg_load": round(fatigue[prev], 1), "cadence": r["ride"]["cadence"],
                        "hr_at_band": r["ride"].get("hr_at_band")})
    cad = _fit_line([(p["leg_load"], p["cadence"]) for p in pts])
    hrb = _fit_line([(p["leg_load"], p["hr_at_band"]) for p in pts if p["hr_at_band"]])
    out = {"rides": pts, "needed": 5, "cadence": cad and {"r": cad["r"], "n": cad["n"]}, "hr_at_band": hrb and {"r": hrb["r"], "n": hrb["n"]}}
    if cad:
        out["read"] = (f"Cadence against the leg load carried into the ride: correlation {cad['r']:+.2f} over {cad['n']} rides"
                       + (f"; heart rate at the same watts {hrb['r']:+.2f} over {hrb['n']}" if hrb else "")
                       + ". Clearly negative for cadence (or positive for heart rate) means the ride shows the running load.")
    else:
        out["read"] = f"{len(pts)} of 5 rides with a leg-load reading the day before: not enough to say yet."
    return out


def climbs(rides_dir, acts):
    """Every recorded climb with the watch's heart rate over it, against the last time up the same climb."""
    try:
        have = json.loads((Path(rides_dir) / "climbs.json").read_text())
    except (OSError, ValueError):
        return []
    out = []
    for c in have:
        row = {k: c.get(k) for k in ("date", "route", "route_id", "n", "seconds", "avg_w", "avg_rpm")}
        end = c.get("ended")
        if end:
            for a in acts:
                if a["source"] == "watch" and a["start"] <= end <= a["start"] + a["minutes"] * 60 + 600:
                    hrs = [r["hr"] for r in a["records"] if r.get("hr") and end - c["seconds"] <= r["t"] <= end]
                    if len(hrs) >= 20:
                        row.update(avg_hr=round(mean(hrs)), max_hr=max(hrs))
                    break
        before = [o for o in out if o["route_id"] == row["route_id"] and o["n"] == row["n"]]
        if before:
            p = before[-1]
            row["vs_last"] = {"date": p["date"], "seconds": row["seconds"] - p["seconds"],
                              "avg_w": (row["avg_w"] or 0) - (p["avg_w"] or 0),
                              "avg_rpm": (row["avg_rpm"] or 0) - (p["avg_rpm"] or 0),
                              "avg_hr": row["avg_hr"] - p["avg_hr"] if row.get("avg_hr") and p.get("avg_hr") else None}
        out.append(row)
    return out


# ── everything together ──────────────────────────────────────────────────────
def summary(acts, days=(), checkins=None, aero=None, rides_dir=None, today=None, keep=30):
    """The recent activities in detail (newest first), the trends across them, and the flags."""
    checkins = checkins or {}
    today = today or dt.date.today()
    aero_by = {r["id"]: r for r in (aero or {}).get("rides", [])}
    rows, flags = [], []
    for a in sorted(acts, key=lambda a: a["start"]):
        day = dt.date.fromtimestamp(a["start"]).isoformat()
        row = {"id": a["id"], "date": day, "sport": a["sport"], "minutes": round(a["minutes"]), "source": a["source"]}
        if a["minutes"] < 10:
            continue                                          # an attempt, not a session (coach.counts)
        s = a.get("session") or {}
        if s.get("total_calories"):
            row["kcal"] = s["total_calories"]
        if s.get("avg_temperature") is not None:
            row["wrist_temp_c"] = s["avg_temperature"]
        try:
            row["pauses"] = pauses(a)
            if a["sport"] == "swim":
                row["swim"] = swim(a)
            elif a["sport"] == "run":
                row["run"] = run(a)
            elif a["sport"] == "bike":
                row["ride"] = ride(a, aero_by.get(a["id"]))
        except Exception as e:                                # one odd file must not take the page down
            row["error"] = str(e)
        rows.append(row)
    recent = (today - dt.timedelta(days=7)).isoformat()
    name = {"swim": "swim", "run": "run", "bike": "ride", "gym": "gym session", "walk": "walk"}
    for r in rows:
        if r["date"] < recent:
            continue
        what = f"{r['date']} {name.get(r['sport'], r['sport'])}"
        p = r.get("pauses") or {}
        if p.get("many"):
            flags.append({"id": f"pauses-{r['id']}", "kind": "pauses", "date": r["date"], "activity": r["id"],
                          "text": f"{what}: {p['count']} pause{'s' if p['count'] != 1 else ''}, "
                                  f"{p['seconds'] // 60} min {p['seconds'] % 60:02d} s stopped.",
                          "ask": "Was there anything going on?"})
        sw = r.get("swim")
        if sw and sw["kind"] != "held":
            st = sw["biggest_step"]
            if st:
                text = (f"{what}: the stroke changed suddenly in set {st['set']}, {st['at_m']} m in "
                        f"(SWOLF +{st['jump']}, {st['pct']}%: {st['what']}).")
            else:
                worst = max(sw["sets"], key=lambda x: x["fade_pct"])
                text = (f"{what}: the stroke faded gradually in set {worst['set']} "
                        f"(SWOLF {worst['swolf_first']} to {worst['swolf_last']}, {worst['fade_pct']:+.1f}%).")
            flags.append({"id": f"stroke-{r['id']}", "kind": "stroke_" + sw["kind"], "date": r["date"], "activity": r["id"],
                          "text": text, "ask": "How did the shoulders feel at that point?"})
        rn = r.get("run")
        if rn and (rn.get("drift") or {}).get("form_changed"):
            flags.append({"id": f"form-{r['id']}", "kind": "run_form", "date": r["date"], "activity": r["id"],
                          "text": f"{what}: at the same pace, the last third had " + ", ".join(rn["drift"]["form_changed"]) + ".",
                          "ask": "Were the legs tiring, or did something hurt?"})
    # rides: the start heart rate against the usual at the same watts, and the trends
    ride_rows = [r for r in rows if r.get("ride")]
    for i, r in enumerate(ride_rows):
        rd = r["ride"]
        if rd.get("start_hr") is None:
            continue
        like = [x["ride"]["start_hr"] for x in ride_rows[:i]
                if x["ride"].get("start_hr") and abs(x["ride"]["start_watts"] - rd["start_watts"]) <= 15]
        if len(like) >= 3:
            rd["start_hr_usual"] = round(median(like[-8:]))
            rd["start_hr_diff"] = rd["start_hr"] - rd["start_hr_usual"]
            if rd["start_hr_diff"] >= START_HIGH and r["date"] >= recent:
                flags.append({"id": f"starthr-{r['id']}", "kind": "start_hr", "date": r["date"], "activity": r["id"],
                              "text": f"{r['date']} ride: heart rate in the opening minutes was {rd['start_hr']}, "
                                      f"{rd['start_hr_diff']} above your usual at those watts.",
                              "ask": "Short on sleep, or still carrying yesterday?"})
    kj_by_day = {}
    for r in ride_rows:
        kj_by_day[r["date"]] = kj_by_day.get(r["date"], 0) + r["ride"]["work_kj"]
    run_days = {r["date"] for r in rows if r["sport"] == "run"}
    rec = [(r["date"], r["ride"]["recovery_60"]) for r in ride_rows if r["ride"].get("recovery_60") is not None]
    swims = [{"date": r["date"], "total_m": r["swim"]["total_m"], "held_m": r["swim"]["held_m"],
              "broke": bool(r["swim"]["broke_down"]), "kind": r["swim"]["kind"], "swolf": r["swim"]["swolf_avg"],
              "rest_drop_30": r["swim"]["rest_drop_30"]} for r in rows if r.get("swim")]
    for r in rows:                                            # the page and the coach get the sets; the lengths on request
        if r.get("swim"):
            r["swim"] = {k: v for k, v in r["swim"].items() if k != "lengths"} if r not in rows[-3:] else r["swim"]
    return {"activities": rows[::-1][:keep], "flags": flags[::-1],
            "swim": {"session_length": swim_length_trend(swims)},
            "ride": {"work_vs_legs": work_vs_legs(kj_by_day, run_days, checkins),
                     "leg_check": leg_check(ride_rows, days),
                     "recovery": {"rides": [{"date": d, "drop_60": v} for d, v in rec],
                                  "latest": rec[-1][1] if rec else None,
                                  "usual": round(median(v for _, v in rec[:-1])) if len(rec) >= 4 else None},
                     "climbs": climbs(rides_dir, acts) if rides_dir else []}}
