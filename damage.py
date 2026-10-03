"""Impact-load planning models.

The coaching page uses provisional accumulated blocks and a separate five-day
response. The tissue-capacity model below is retained for exploratory history;
neither model measures an individual's tissue damage or diagnoses injury.

Every step loads the foot with a force (body weight x ~2 jogging, more when faster or
downhill; see loads.foot_impact). Damage per step rises with the 4th power of that force,
so it's counted in "steps at 1,000 lb": one step at 1,000 lb = 1; a step at 556 lb =
(0.556)^4 = 0.096. It piles up in a backlog, and each tissue works the backlog off:

  * Repair is capacity-limited. A tissue can only rebuild so much a day, however big the
    pile - so a big pile drains at a fixed, slow rate (days, not hours), and every new
    run lands on top of what's still there.
  * Repair starts slow. Breakdown comes first (tendon collagen: net loss for 1-2 days
    after loading; bone: cracks are dug out for ~3 weeks before they're refilled), so the
    repair rate ramps up over the tissue's lag. The backlog falls slowly at first, then
    steadily, then tails off as it empties.
  * Capacity is conditioning. It starts at what an unconditioned body repairs (tuned to
    the rider's own usual week when set) and grows only with load actually repaired, over
    months (tendon ~3 months, bone ~4) - a spike doesn't condition you; it's debt.
  * Damage compounds a little: tissue still carrying a big backlog strains more per step.

The score is days of backlog: how many days of full-speed repair it would take to clear.
Training at up to ~80% of capacity keeps it under about 4 days.

  under 2 room to build    2-4 sweet spot    4-7 caution    over 7 danger

  SOFT     skin, fat pad, joint soreness: lag ~1 day, repairs ~4x faster than tendon
  TENDON   Achilles, plantar fascia: lag ~2.5 days - the base capacity
  BONE     lag ~3 weeks (the start of the ~4-month remodeling cycle); least certain,
           so it warns (easy) rather than benches (rest)

The shapes come from physiology; the capacities are estimates tuned to the rider.
"""
import datetime as dt
import math
import statistics

TISSUES = {
    "soft":   {"name": "soft tissue & joints", "lag": 1.0, "capacity": 4.0, "adapt": 21},
    "tendon": {"name": "tendons & fascia", "lag": 2.5, "capacity": 1.0, "adapt": 90},
    "bone":   {"name": "bone", "lag": 21.0, "capacity": 1.0, "adapt": 120, "at_most": "easy"},
}
ADAPT_GAIN = 0.8          # long-run: capacity grows toward base / (1 - 0.8) = 5x with steady, repaired training
FEEDBACK = 0.003          # per day of backlog over 4: extra strain (weakened tissue), capped at 5%
POWER = 4
UNTRAINED_KM_WEEK = 8     # equivalent km a week an unconditioned 70 kg adult's feet can repair (estimate)
ZONES = [(2, "room to build"), (4, "sweet spot"), (7, "caution"), (1e9, "danger")]
HORIZON = 126  # exploratory tissue model: days projected
PROJECT_DAYS = 800  # computed ahead (13 blocks is ~225 days; the projection is trimmed to the tail's end)
TAIL_RUN_FACTOR = 1.1  # in the tail, running is blocked only while the load is over 1.1x the limit
TAIL_DAYS = 120  # blocks: after the plateau and decline, a remodeling tail of ~4 months (the bone remodeling cycle)
EVENT_KERNEL = (0.6, 1.0, 0.85, 0.6, 0.3)  # separate five-day exertion response
HABITUAL_STEPS = 10000    # free walking a day when fresh, used only when there's no block to size it from
CLEAR_DAYS_PER_BLOCK = 8  # a block clears in ~5 days plateau + 3 decline: the feet repair ~1/8 block a day
ALLOWANCE_FLOOR = 0.25    # the allowance shrinks with accumulated blocks, never below a quarter of fresh
ALLOWANCE_ZERO_AT = 32.5  # (blocks) 1 - blocks/32.5: about 60% of fresh at 13 blocks
WALK_PROVEN_MIN = 3       # good mornings after walking needed before the walking habit counts as evidence
WALK_PROVEN_DAYS = 60     # ...looked for over this many days
WALK_MIN_STEPS = 3000     # a day this light proves nothing about capacity
REPAIR_DOWN, REPAIR_UP = 0.93, 1.02   # a rough morning after a day over the line lowers the repair estimate
                                      # faster than a good one raises it
REPAIR_RANGE = (0.5, 2.0)
HOP_CLEAR = 10            # pain-free single-leg hops (the worse leg) needed, with the model's date, to run again
HOP_POOR = 3              # this few is a poor hop test; it changes the curve only after the plateau
HOP_FRESH_DAYS = 3        # a hop test counts for clearance for this many days


def overlap_multiplier(before):
    """Extra cost of a run landing on load that's already there (a run's full multiplier)."""
    return 1 + min(3, before if before <= 1 else (before + 1) / 2)


def walking_day(steps, pts_per_step, severity, before, fresh_steps=HABITUAL_STEPS):
    """One day's walking (daily steps minus run steps). No step is free, but the feet repair a day's budget:
    the free steps are that budget in walking steps (fresh_steps - see remodeling_response), shrinking as
    accumulated load rises. Only the steps over the line count - each weighted by its own force (4th power) -
    and only those carry the overlap multiplier (scaled by how hard a walking step is next to a jogging step)."""
    mult = 1 + (overlap_multiplier(before) - 1) * severity
    allow_frac = max(ALLOWANCE_FLOOR, 1 - before / ALLOWANCE_ZERO_AT)
    allowance = fresh_steps * allow_frac
    counted = max(0.0, steps - allowance) * mult
    return {"steps": int(steps), "multiplier": round(mult, 2), "allowance_steps": round(allowance),
            "points": counted * pts_per_step}


LEARN_STEP_MAX = 1.6      # the first run's heart rate can grow the evidence-free block by at most 60%
LEARN_DOWN = 0.85         # a run followed by rough mornings or slower running shrinks it 15%, at once
LEARN_TOTAL_MAX = 6.0     # never more than 6x the evidence-free starting block
LEARN_FLOOR = 0.7         # never under 70% of it
# The weekly adaptation pathway (the rider's design, 2026-10-03): each week with in-band runs is scored on how
# easily they were absorbed, and a week that read as too easy grows the block 1-10%. Provisional weights/thresholds.
ADAPT_BAND = 0.8          # a run counts as evidence only if it carried at least this many blocks
ADAPT_EXPECT = (1.5, 2.0) # predicted next-morning legs/feet rating: 1.5 + 2.0 x blocks carried
ADAPT_MIN, ADAPT_MAX = 0.01, 0.10
ADAPT_ONE_RUN = 0.05      # one run is thin evidence
ADAPT_FEELINGS_ONLY = 0.03  # no heart-rate evidence: feelings alone grow it at most 3%
ADAPT_WEIGHTS = {"mornings": .30, "consistency": .20, "efficiency": .25, "drift": .15, "hops": .10}
ADAPT_EFF_FULL = 0.03     # pace per heartbeat +3% scores full
ADAPT_DRIFT = (3.0, 8.0)  # heart-rate drift: 3% or less scores full, 8% or more nothing (and holds growth)
EFFORT_FULL = 0.85        # share of heart-rate reserve treated as a run at the whole block


def _rough(x):
    if not isinstance(x, dict):
        return x >= 6
    return any(x.get(k) is not None and x[k] >= 6 for k in ("feet", "legs"))


def _clean(x):
    if not isinstance(x, dict):
        return x <= 3
    return all(x.get(k) is None or x[k] <= 3 for k in ("feet", "legs")) and x.get("feet") is not None


def _clamp(x):
    return max(0.0, min(1.0, x))


def learn_block(dates, doses, reports, runs, start_reference, since=None, **kw):
    """The block from evidence (the rider's design, 2026-10-03): how big a block is for this athlete.

    1. What the first run says: an easy run (share of heart-rate reserve e) followed by clean mornings used only
       part of the block: block >= dose x EFFORT_FULL / e.
    2. Any run followed by rough mornings, a hop-test drop, or slower running at the same heart rate shrinks the
       block 15% at once (shrink fast).
    3. Each week is scored on how easily its in-band runs (>= ADAPT_BAND blocks carried) were absorbed (grow by
       the week): mornings better than predicted for the load, the share of runs that read as too easy, pace per
       heartbeat against the previous comparable run, heart-rate drift, and the hop test. A week that read as too
       easy - mornings at least a point better than predicted, or the athlete said so - with heart rate not
       worse grows the block 1% + 9% x score (at most 5% on one run, 3% without heart-rate evidence). After rough
       mornings it can't regrow past its earlier size until two clean in-band runs.
    The plateau, decline, tail and the 1.5-block line are unchanged; only the size of a block learns.
    Returns (reference, steps)."""
    ref, steps = start_reference, []
    run_days = [i for i, x in enumerate(doses) if x > 0]
    if since:                     # a reviewed block is the anchor: only runs after the review teach it more
        run_days = [i for i in run_days if dates[i] > since]
    if not run_days:
        return ref, steps

    def mornings(i, n=3):
        return [reports[dates[j]] for j in range(i + 1, min(len(dates), i + 1 + n)) if dates[j] in reports]

    first = run_days[0]
    r0 = runs.get(dates[first]) or {}
    m0 = mornings(first)
    if not since and r0.get("hrr") and len(m0) >= 2 and all(_clean(x) for x in m0):
        cand = doses[first] * EFFORT_FULL / max(0.45, min(EFFORT_FULL, r0["hrr"]))
        if cand > ref * 1.05:
            new = min(cand, ref * LEARN_STEP_MAX)
            steps.append({"date": dates[first], "why": f"first run felt easy ({round(100 * r0['hrr'])}% of heart-rate "
                          "reserve) and the mornings after were clean", "from": round(ref, 1), "to": round(new, 1)})
            ref = new
    floor, top = start_reference * LEARN_FLOOR, start_reference * LEARN_TOTAL_MAX
    state = {"week": None, "obs": [], "rough": False, "ceiling": None}

    def monday(i):
        d = dt.date.fromisoformat(dates[i])
        return d - dt.timedelta(days=d.weekday())

    def close_week():
        nonlocal ref
        obs, wk = state["obs"], state["week"]
        state["obs"], rough, state["rough"] = [], state["rough"], False
        if not obs or rough or wk is None:
            return
        n = len(obs)
        easy = [o["margin"] >= 1 or o["said_easy"] for o in obs]
        effs = [o["eff"] for o in obs if o["eff"] is not None]
        drifts = [o["drift"] for o in obs if o["drift"] is not None]
        eff = sum(effs) / len(effs) if effs else None
        drift = sum(drifts) / len(drifts) if drifts else None
        if not any(easy) or (eff is not None and eff < -ADAPT_EFF_FULL) or (drift is not None and drift >= ADAPT_DRIFT[1]):
            return                                       # absorbed as predicted, or the heart says otherwise: hold
        hops = [o["hops"] for o in obs if o["hops"] is not None]
        signals = {"mornings": _clamp(sum(o["margin"] for o in obs) / n / 2)}
        if n >= 2:
            signals["consistency"] = sum(easy) / n
        if eff is not None:
            signals["efficiency"] = _clamp(eff / ADAPT_EFF_FULL)
        if drift is not None:
            signals["drift"] = _clamp((ADAPT_DRIFT[1] - drift) / (ADAPT_DRIFT[1] - ADAPT_DRIFT[0]))
        if hops:
            signals["hops"] = sum(hops) / len(hops)
        score = sum(ADAPT_WEIGHTS[k] * v for k, v in signals.items()) / sum(ADAPT_WEIGHTS[k] for k in signals)
        cap = ADAPT_ONE_RUN if n == 1 else ADAPT_MAX
        if eff is None and drift is None:
            cap = min(cap, ADAPT_FEELINGS_ONLY)
        pct = min(cap, ADAPT_MIN + (ADAPT_MAX - ADAPT_MIN) * score)
        new = min(top, ref * (1 + pct))
        if state["ceiling"]:
            new = min(new, max(ref, state["ceiling"][0]))
        if new > ref * 1.001:
            bits = [f"mornings {sum(o['margin'] for o in obs) / n:+.1f} vs predicted"]
            if eff is not None:
                bits.append(f"pace per beat {100 * eff:+.1f}%")
            if drift is not None:
                bits.append(f"heart-rate drift {drift:.1f}%")
            steps.append({"date": (wk + dt.timedelta(days=6)).isoformat(),
                          "why": f"week of {wk}: {sum(easy)} of {n} in-band run{'s' if n > 1 else ''} absorbed more easily "
                                 f"than predicted ({', '.join(bits)}): adaptation {score:.2f}, +{100 * (new / ref - 1):.1f}%",
                          "from": round(ref, 1), "to": round(new, 1), "score": round(score, 2), "signals": signals})
            ref = new

    prev = first
    for i in run_days[1:]:
        if state["week"] != monday(i):
            close_week()
            state["week"] = monday(i)
        curve = remodeling_response(dates[:i + 4], doses[:i + 4], block=ref, feet_reports=reports, **kw)
        ev = next((e for e in curve["components"] if e["date"] == dates[i]), None) if curve else None
        m = mornings(i)
        if not ev or len(m) < 2:
            prev = i
            continue
        r_now, r_prev = runs.get(dates[i]) or {}, runs.get(dates[prev]) or {}
        e_now, e_prev = r_now.get("eff"), r_prev.get("eff")
        h_now, h_prev = r_now.get("hrr"), r_prev.get("hrr")
        alike = h_now is not None and h_prev is not None and abs(h_now - h_prev) <= 0.08   # only like-for-like efforts compare
        slower = alike and e_now is not None and e_prev is not None and e_now < 0.97 * e_prev
        earlier = [x["hops"] for d, x in sorted(reports.items()) if isinstance(x, dict) and x.get("hops") is not None and d <= dates[i]]
        after = [x["hops"] for x in m if isinstance(x, dict) and x.get("hops") is not None]
        hops_drop = bool(earlier and after) and min(after) <= earlier[-1] - 2
        if any(_rough(x) for x in m) or slower or hops_drop:
            state["ceiling"] = [ref, 0]
            state["rough"] = True
            new = max(floor, ref * LEARN_DOWN)
            if new < ref:
                why = "rough mornings after" if any(_rough(x) for x in m) else "hop test dropped" if hops_drop else "running slowed at the same heart rate"
                steps.append({"date": dates[i], "why": why, "from": round(ref, 1), "to": round(new, 1)})
                ref = new
        elif ev["after_blocks"] >= ADAPT_BAND:
            felt = [max(v for v in (x.get("feet"), x.get("legs")) if v is not None) if isinstance(x, dict) else x
                    for x in m if not isinstance(x, dict) or x.get("feet") is not None or x.get("legs") is not None]
            if felt:
                expected = min(9.0, ADAPT_EXPECT[0] + ADAPT_EXPECT[1] * ev["after_blocks"])
                state["obs"].append({
                    "margin": expected - sum(felt) / len(felt),
                    "said_easy": r_now.get("effort") == "too_easy",
                    "eff": (e_now / e_prev - 1) if alike and e_now and e_prev else None,
                    "drift": r_now.get("drift") if (r_now.get("minutes") or 0) >= 30 else None,
                    "hops": (1.0 if min(after) >= earlier[-1] else 0.0) if earlier and after else None})
                if state["ceiling"] and all(_clean(x) for x in m):
                    state["ceiling"][1] += 1
                    if state["ceiling"][1] >= 2:
                        state["ceiling"] = None
        prev = i
    # the last week counts once it's over
    if state["week"] is not None and dt.date.fromisoformat(dates[-1]) >= state["week"] + dt.timedelta(days=6):
        close_week()
    return ref, steps


def remodeling_response(dates, doses, usual_week=None, weight_kg=70.0, feet_reports=None, walking=None, block=None, reviews=None,
                        runs=None, learn_since=None):
    """Provisional blocks: 5 days/block plateau, 3 days/block decline (to 20%), then a ~4-month remodeling tail.
    walking: {"steps": {date: steps walked outside runs}, "pts_per_step", "severity"} - daily walking adds blocks
    above the day's free steps; it extends the plateau (5 days/block) instead of restarting it.

    Free steps: no step is free, but the feet repair a daily budget. Fresh,
    that budget comes from the bigger of the two things that condition feet and bones - running (the block, in
    walking steps: one day's repair = 1/8 block to start, corrected by the mornings) and walking (steps walked
    and woken up fine from, scaled to fresh). Biking and swimming don't load them, so they earn nothing. The
    budget shrinks with the load carried, and only the steps over it count - and carry the overlap multiplier."""
    if not dates:
        return None
    doses = list(doses)
    reports = feet_reports or {}
    def high_report(value):
        if isinstance(value, dict):
            hops = value.get("hops")
            return (any(value.get(k) is not None and value[k] >= 6 for k in ("feet", "legs"))
                    or (hops is not None and hops <= HOP_POOR))
        return value >= 6

    def low_report(value):
        if isinstance(value, dict):
            return all(value.get(k) is not None and value[k] <= 3 for k in ("feet", "legs"))
        return value <= 3

    impacts = [i for i, x in enumerate(doses) if x > 0]
    clean = []
    for i in impacts:
        # Recovery reports cannot establish conditioning inside the five-day
        # minimum plateau. Require observations after it, with no new run.
        if i+8 < len(doses) and not any(doses[i+1:i+9]):
            after = [reports[dates[j]] for j in range(i+6,i+9) if dates[j] in reports]
            if len(after) >= 2 and all(low_report(x) for x in after):
                clean.append(i)
    credit = min(.3,.05*(len(clean)-3)) if len(clean)>=4 and clean[-1]-clean[0]>=28 else 0.0
    first = [doses[i] for i in impacts[:3]]
    reference = max(base_capacity(usual_week,weight_kg)*7/3,
                    statistics.median(first) if first else 0,1)*(1+credit)
    if block:                          # a calibrated block (benchmark runs taken well: calibration.py) replaces it
        reference = max(float(block), 1.0)
    learned = []
    if runs:                           # and the runs themselves teach how big it is (learn_block)
        reference, learned = learn_block(dates, doses, reports, runs, reference, since=learn_since, usual_week=usual_week,
                                         weight_kg=weight_kg, reviews=reviews)

    def adjust(j,stop,plateau_len):
        """Only reports after the mechanical plateau adjust the decline duration.

        Reports during the plateau still inform the immediate training decision,
        but cannot shorten or lengthen the accumulated-load curve.
        """
        observations = [reports[dates[k]] for k in range(j+1,min(stop,len(dates)))
                        if dates[k] in reports and k-j > plateau_len]
        high = low = 0
        for x in observations:
            high += high_report(x)
            low += low_report(x)
        return max(-2,min(10,.5*high-.5*max(0,low-2))),len(observations)

    def remaining(level,age,plateau,descent):
        if age<=plateau: return level
        if age<=plateau+descent: return level*(1-.8*(age-plateau)/descent)
        if age>=plateau+descent+TAIL_DAYS: return 0.0
        return level*.2*math.exp(-5*(age-plateau-descent)/TAIL_DAYS)

    walking = walking or {}
    wsteps = walking.get("steps") or {}
    walk_rows = []
    repair = 1.0                      # the running-side repair estimate, as a share of the 1/8-block starting guess
    proven = []                       # (day index, fresh-equivalent steps) walked and woken up fine from
    last_hops = None
    def morning(j):
        """The report the morning after day j, and whether it was good / rough for walking evidence."""
        if j + 1 >= len(dates) or dates[j + 1] not in reports:
            return None
        x = reports[dates[j + 1]]
        if not isinstance(x, dict):
            x = {"feet": x}
        hops = x.get("hops")
        dropped = hops is not None and last_hops is not None and hops <= last_hops - 2
        rough = any(x.get(k) is not None and x[k] >= 6 for k in ("feet", "legs")) or dropped
        good = (all(x.get(k) is not None and x[k] <= 3 for k in ("feet", "legs")) and not dropped)
        return {"good": good, "rough": rough, "hops": hops}
    walk_free = None
    rows,events=[],[]
    anchor_day,anchor_level,plateau,descent=0,0.0,0.0,1.0
    used=0
    review_log=[]
    review_dates={r["date"]:r for r in (reviews or []) if r.get("action") in ("begin_decline","restore_plateau") and r.get("date", "")<=dates[-1]}
    review_origin=None
    day0=dt.date.fromisoformat(dates[0])
    for i,dose in enumerate(doses+[0.0]*PROJECT_DAYS):
        level=remaining(anchor_level,i-anchor_day,plateau,descent)
        if i < len(dates) and isinstance(reports.get(dates[i]), dict) and reports[dates[i]].get("hops") is not None:
            last_hops = reports[dates[i]]["hops"]
        if i<len(doses) and dose>0:
            review_origin=None
            before=level
            raw=dose/reference
            multiplier=1+min(3,before if before<=1 else (before+1)/2)
            added=raw*multiplier
            level=before+added
            stop=next((j for j in impacts if j>i),len(doses))
            # Days already served count: the plateau still owed from before, plus 5 days per block this run added
            # (run, a day passes, run again as 2 blocks: 4 + 10 = 14 days). Scales with the load, no cap.
            owed=max(0.0,anchor_day+plateau-i) if anchor_level>0 else 0.0
            adjustment,n=adjust(i,stop,owed+5*added)
            used+=n
            plateau=max(1,owed+5*added)
            descent=max(1,3*level+adjustment)
            anchor_day,anchor_level=i,level
            events.append({"date":dates[i],"raw_blocks":round(raw,2),
                           "incoming_multiplier":round(multiplier,2),
                           "added_blocks":round(added,2),"before_blocks":round(before,2),
                           "after_blocks":round(level,2),"plateau_days":round(plateau,1),
                           "descent_days":round(descent,1),"report_adjust_days":adjustment})
        w = wsteps.get(dates[i]) if i < len(doses) else None
        if w:
            # free steps when fresh: the bigger of running conditioning (a day's repair, 1/8 of the block to
            # start, in walking steps) and walking conditioning (what's been walked and woken up fine from)
            from_run = reference / CLEAR_DAYS_PER_BLOCK / walking["pts_per_step"] * repair
            recent = [s for k, s in proven if i - k <= WALK_PROVEN_DAYS]
            from_walk = statistics.median(recent) if len(recent) >= WALK_PROVEN_MIN else 0.0
            fresh = max(from_run, from_walk)
            wd = walking_day(w, walking["pts_per_step"], walking["severity"], level, fresh)
            walk_free = {"fresh_steps": round(fresh), "from": "walking" if from_walk > from_run else "running",
                         "from_running": round(from_run), "from_walking": round(from_walk) or None,
                         "repair_estimate": round(repair, 3), "proven_days": len(recent)}
            mo = morning(i)
            if mo and i-anchor_day > plateau:
                frac = max(ALLOWANCE_FLOOR, 1 - level / ALLOWANCE_ZERO_AT)
                if mo["good"] and w >= WALK_MIN_STEPS:
                    proven.append((i, w / frac))          # woke up fine: that walk, scaled to a fresh foot
                if w > wd["allowance_steps"]:             # only a day over the line tests the line
                    if mo["rough"]:
                        repair = max(REPAIR_RANGE[0], repair * REPAIR_DOWN)
                    elif mo["good"]:
                        repair = min(REPAIR_RANGE[1], repair * REPAIR_UP)
                walk_free["repair_estimate"] = round(repair, 3)       # where it stands going into tomorrow
            added = wd["points"] / reference
            if added > 0:
                if level < 0.01:                          # nothing carried: walking starts its own small block
                    anchor_day, anchor_level = i, added
                    plateau, descent = max(1, 5 * added), max(1, 3 * added)
                else:                                     # on top of what's there: raise it, push the plateau out
                    f = level / anchor_level
                    anchor_level += added / f
                    # 5 days per block walked, but never more plateau left than 5 days per block now carried
                    anchor_day = min(anchor_day + 5 * added, i + 5 * (level + added) - plateau)
                level += added
            walk_rows.append({"date": dates[i], **{k: v for k, v in wd.items() if k != "points"},
                              "raw_blocks": round(w * walking["pts_per_step"] / reference, 3),
                              "added_blocks": round(added, 3)})
        review=review_dates.get((day0+dt.timedelta(days=i)).isoformat())
        age=i-anchor_day
        if review and review["action"]=="begin_decline" and i<len(doses) and dose==0 and plateau>0 and .60<=age/plateau<=1:
            # A reviewed transition changes time, not the amount of carried load.
            review_log.append({"date":review["date"],"action":"begin_decline","score":round(level,2),"protected_fraction":.60})
            review_origin=(anchor_day,anchor_level,plateau,descent)
            anchor_day,anchor_level,plateau,descent=i,level,0.0,max(1,3*level)
        if review and review["action"]=="restore_plateau" and review_origin is not None:
            j,original,p,decline=review_origin
            original_remaining=remaining(original,i-j,p,decline)
            restored=max(level,original_remaining)
            review_log.append({"date":review["date"],"action":"restore_plateau","before":round(level,2),"score":round(restored,2)})
            anchor_day,anchor_level,plateau,descent=i,restored,max(0,j+p-i),max(1,decline)
            level=restored;review_origin=None
        age = i - anchor_day
        phase = "none" if level <= 0 else "plateau" if plateau>0 and age <= plateau else "decline" if age <= plateau + descent else "tail"
        rows.append({"date":(day0+dt.timedelta(days=i)).isoformat(),
                     "score":round(level,2),"dose":round(dose/reference,2),"phase":phase})
    current=rows[len(doses)-1]["score"]
    hop_days=sorted(k for k,v in reports.items() if isinstance(v,dict) and v.get("hops") is not None and k<=dates[-1])
    last_hop=hop_days[-1] if hop_days else None
    hops={"last":reports[last_hop]["hops"] if last_hop else None,"date":last_hop,"needed":HOP_CLEAR,
          "fresh":bool(last_hop) and _days_between(last_hop,dates[-1])<HOP_FRESH_DAYS,
          "history":[{"date":k,"hops":reports[k]["hops"]} for k in hop_days[-14:]]}
    end = int(anchor_day + plateau + descent + TAIL_DAYS) + 2          # through the end of the tail
    projection=rows[len(doses):max(len(doses) + 1, end)]
    below=0 if current<1.5 else next((i+1 for i,r in enumerate(projection)
                                     if r["score"]<1.5),None)
    clear = lambda r: r["score"] < 1.5 or (r["phase"] == "tail" and r["score"] <= 1.5 * TAIL_RUN_FACTOR)
    cleared = 0 if clear(rows[len(doses)-1]) else next((i+1 for i,r in enumerate(projection) if clear(r)), None)
    return {"score":current,"history":rows[:len(doses)],"projection":projection,
            "plateau_days":round(plateau,1),"descent_days":round(descent,1),
            "reviewed_transitions":review_log,
            "tail_days":TAIL_DAYS,
            "plateau_remaining_days":round(max(0,anchor_day+plateau-(len(doses)-1)),1),
            "below_threshold_in_days":below,"threshold_blocks":1.5,
            "phase":rows[len(doses)-1]["phase"],"tail_run_limit":round(1.5*TAIL_RUN_FACTOR,2),
            "cleared_to_run_in_days":cleared,
            "tail_starts_in_days":next((i+1 for i,r in enumerate(projection) if r["phase"]=="tail"),None),
            "hops":hops,
            "reference_points":round(reference,1),"block_learning":learned,"checkins_used":used,
            "conditioning_credit":round(credit,2),"confirmed_recoveries":len(clean),
            "components":events[-12:], "walking":walk_rows[-14:],
            "walking_week_blocks":round(sum(r["added_blocks"] for r in walk_rows[-7:]),2),
            "walking_free":walk_free,
            "max_impact_multiplier":round(max((e["incoming_multiplier"] for e in events),default=1),2),
            "provisional":True}


def _days_between(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def zone(days):
    return next(z for lim, z in ZONES if days < lim)


def amp(days):
    """How much more damage a step does on tissue carrying `days` of backlog."""
    phi = min(0.05, FEEDBACK * max(0.0, days - 4))
    return (1 / (1 - phi)) ** POWER


def base_capacity(usual_week, weight_kg):
    """Points a day the tendons can repair: the tuned usual week, or an unconditioned estimate."""
    if usual_week:
        return usual_week / 7
    return UNTRAINED_KM_WEEK * 8 * (weight_kg / 70) ** 2 / 7     # heavier bodies' tissue is partly adapted to it


def event_response(dates, doses, usual_week=None, weight_kg=70.0, remodeling=None):
    """Five-day exertion response, separate from accumulated block recovery."""
    if not dates:
        return None
    ref=remodeling["reference_points"] if remodeling else max(base_capacity(usual_week,weight_kg)*7/3,1)
    doses=list(doses)
    all_doses=doses+[0.0]*len(EVENT_KERNEL)
    day0=dt.date.fromisoformat(dates[0])
    rows=[]
    for i,dose in enumerate(all_doses):
        score=sum(all_doses[i-age]/ref*k for age,k in enumerate(EVENT_KERNEL) if i>=age)
        rows.append({"date":(day0+dt.timedelta(days=i)).isoformat(),
                     "score":round(score,2),"dose":round(dose/ref,2)})
    return {"score":rows[len(doses)-1]["score"],"reference_points":round(ref,1),
            "history":rows[:len(doses)],"projection":rows[len(doses):],"base_days":5}


def run(doses, base, p, adapt_gain=ADAPT_GAIN):
    """Day by day: (backlog, capacity, repaired) for one tissue."""
    backlog = act = adapted = 0.0
    out = []
    for x in doses:
        cap = p["capacity"] * (base + adapt_gain * adapted)
        backlog += x * amp(backlog / cap)
        target = backlog / (backlog + cap) if backlog > 0 else 0.0
        act += (target - act) / p["lag"]                       # repair ramps up (and down) over the lag
        repaired = min(backlog, act * cap)
        backlog -= repaired
        adapted += (repaired / p["capacity"] - adapted) / p["adapt"]
        out.append((backlog, cap, repaired))
    return out


def model(dates, doses, usual_week=None, weight_kg=70.0, feet_reports=None, run_doses=None, walking=None, block=None, reviews=None,
          runs=None, learn_since=None):
    """dates: consecutive ISO days; doses: impact points per day. Returns each tissue's backlog today,
    its history, and a no-more-running projection."""
    if not dates:
        return None
    doses = list(doses)
    remodeling = remodeling_response(dates, run_doses if run_doses is not None else doses, usual_week, weight_kg,
                                     feet_reports, walking, block, reviews, runs, learn_since)
    event = event_response(dates, doses, usual_week, weight_kg, remodeling)
    base = base_capacity(usual_week, weight_kg)
    n = len(dates)
    doses = doses + [0.0] * HORIZON
    sims = {t: run(doses, base, p, remodeling["conditioning_credit"]) for t, p in TISSUES.items()}
    days_of = {t: [b / c for b, c, _ in sims[t]] for t in TISSUES}
    day0 = dt.date.fromisoformat(dates[0])
    iso = lambda i: (day0 + dt.timedelta(days=i)).isoformat()
    last = n - 1

    def first_under(t, lim):
        return next((i - last for i in range(last, len(doses)) if days_of[t][i] < lim), None)

    tissues = {}
    for t, p in TISSUES.items():
        b, c, _ = sims[t][last]
        d = days_of[t][last]
        pk = max(range(n), key=lambda i: days_of[t][i])
        tissues[t] = {"name": p["name"], "days": round(d, 1), "zone": zone(d),
                      "backlog_km": round(b / 8, 1), "backlog_1000lb_steps": round(b * STEPS_1000LB_PER_POINT),
                      "repairs_km_day": round(c / 8, 2), "repairs_1000lb_steps_day": round(c * STEPS_1000LB_PER_POINT),
                      "conditioning": round(c / (p["capacity"] * base), 2),
                      "next_step_costs": round(amp(d), 2),
                      "ok_to_run_in_days": first_under(t, 4), "clear_in_days": first_under(t, 2),
                      "at_most": p.get("at_most"),
                      "peak": {"days": round(days_of[t][pk], 1), "date": iso(pk)}}
    worst = max(tissues, key=lambda t: tissues[t]["days"] if not tissues[t]["at_most"] else 0)
    rows = lambda a, b: [{"date": iso(i), **{t: round(days_of[t][i], 2) for t in TISSUES}} for i in range(a, b)]
    return {"tissues": tissues, "limiting": worst, "days": tissues[worst]["days"], "zone": tissues[worst]["zone"],
            "event": event, "remodeling": remodeling,
            "base_km_week": round(base * 7 / 8, 1), "tuned": bool(usual_week),
            "history": rows(0, n), "projection": rows(n, len(doses))}


# one impact point in steps at 1,000 lb (see loads.REF_FORCE / REF_POINTS_PER_STEP): about 3.1
LBF = 4.44822
STEPS_1000LB_PER_POINT = (40 / 5060) ** -1 * (70 * 9.81 * (2.0 + 0.2 * 2.8) / LBF / 1000) ** POWER
