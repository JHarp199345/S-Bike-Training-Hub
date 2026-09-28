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
HABITUAL_STEPS = 6000     # an ordinary day's walking, which the feet maintain on their own
ALLOWANCE_FLOOR = 0.25    # the allowance shrinks with accumulated blocks, to a quarter at ALLOWANCE_ZERO_AT
ALLOWANCE_ZERO_AT = 40    # (blocks) - the "even walking is too much" end of overtraining: 1 - blocks/40, floor 0.25


def overlap_multiplier(before):
    """Extra cost of a run landing on load that's already there (a run's full multiplier)."""
    return 1 + min(3, before if before <= 1 else (before + 1) / 2)


def walking_day(steps, pts_per_step, severity, before, habitual_steps=HABITUAL_STEPS):
    """One day's walking (daily steps minus run steps): each step weighted by its own force (4th power), the
    overlap multiplier scaled by how hard a walking step is next to a jogging step, less the day's allowance -
    a normal day's walking the feet keep up with, which shrinks as accumulated load rises."""
    mult = 1 + (overlap_multiplier(before) - 1) * severity
    allow_frac = max(ALLOWANCE_FLOOR, 1 - before / ALLOWANCE_ZERO_AT)
    allowance = habitual_steps * allow_frac
    counted = max(0.0, steps * mult - allowance)
    return {"steps": int(steps), "multiplier": round(mult, 2), "allowance_steps": round(allowance),
            "points": counted * pts_per_step}


def remodeling_response(dates, doses, usual_week=None, weight_kg=70.0, feet_reports=None, walking=None, block=None):
    """Provisional blocks: 5 days/block plateau, 3 days/block decline (to 20%), then a ~4-month remodeling tail.
    walking: {"steps": {date: steps walked outside runs}, "pts_per_step", "severity", "habitual_steps"} - daily
    walking adds blocks above the allowance; it extends the plateau (5 days/block) instead of restarting it."""
    if not dates:
        return None
    doses = list(doses)
    reports = feet_reports or {}
    def high_report(value):
        if isinstance(value, dict):
            return any(x is not None and x >= 6 for x in value.values())
        return value >= 6

    def low_report(value):
        if isinstance(value, dict):
            return all(value.get(k) is not None and value[k] <= 3 for k in ("feet", "legs"))
        return value <= 3

    impacts = [i for i, x in enumerate(doses) if x > 0]
    clean = []
    for i in impacts:
        if i+4 < len(doses) and not any(doses[i+1:i+4]):
            after = [reports[dates[j]] for j in range(i+2,i+5) if dates[j] in reports]
            if len(after) >= 2 and all(low_report(x) for x in after):
                clean.append(i)
    credit = min(.3,.05*(len(clean)-3)) if len(clean)>=4 and clean[-1]-clean[0]>=28 else 0.0
    first = [doses[i] for i in impacts[:3]]
    reference = max(base_capacity(usual_week,weight_kg)*7/3,
                    statistics.median(first) if first else 0,1)*(1+credit)
    if block:                          # a calibrated block (benchmark runs taken well: calibration.py) replaces it
        reference = max(float(block), 1.0)

    def adjust(j,stop):
        observations = [(k-j,reports[dates[k]]) for k in range(j+1,min(stop,len(dates)))
                        if dates[k] in reports]
        high = sum(age>=2 and high_report(x) for age,x in observations)
        low = sum(age>=2 and low_report(x) for age,x in observations)
        return max(-2,min(10,.5*high-.5*max(0,low-2))),len(observations)

    def remaining(level,age,plateau,descent):
        if age<=plateau: return level
        if age<=plateau+descent: return level*(1-.8*(age-plateau)/descent)
        if age>=plateau+descent+TAIL_DAYS: return 0.0
        return level*.2*math.exp(-5*(age-plateau-descent)/TAIL_DAYS)

    walking = walking or {}
    wsteps = walking.get("steps") or {}
    walk_rows = []
    rows,events=[],[]
    anchor_day,anchor_level,plateau,descent=0,0.0,0.0,1.0
    used=0
    day0=dt.date.fromisoformat(dates[0])
    for i,dose in enumerate(doses+[0.0]*PROJECT_DAYS):
        level=remaining(anchor_level,i-anchor_day,plateau,descent)
        if i<len(doses) and dose>0:
            before=level
            raw=dose/reference
            multiplier=1+min(3,before if before<=1 else (before+1)/2)
            added=raw*multiplier
            level=before+added
            stop=next((j for j in impacts if j>i),len(doses))
            adjustment,n=adjust(i,stop)
            used+=n
            # Scales with the load, no cap: 13 blocks holds ~65 days, declines over ~39, then the tail.
            plateau=max(1,5*level+adjustment)
            descent=max(1,3*level)
            anchor_day,anchor_level=i,level
            events.append({"date":dates[i],"raw_blocks":round(raw,2),
                           "incoming_multiplier":round(multiplier,2),
                           "added_blocks":round(added,2),"before_blocks":round(before,2),
                           "after_blocks":round(level,2),"plateau_days":round(plateau,1),
                           "descent_days":round(descent,1),"report_adjust_days":adjustment})
        w = wsteps.get(dates[i]) if i < len(doses) else None
        if w:
            wd = walking_day(w, walking["pts_per_step"], walking["severity"], level,
                             walking.get("habitual_steps", HABITUAL_STEPS))
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
        age = i - anchor_day
        phase = "none" if level <= 0 else "plateau" if age <= plateau else "decline" if age <= plateau + descent else "tail"
        rows.append({"date":(day0+dt.timedelta(days=i)).isoformat(),
                     "score":round(level,2),"dose":round(dose/reference,2),"phase":phase})
    current=rows[len(doses)-1]["score"]
    end = int(anchor_day + plateau + descent + TAIL_DAYS) + 2          # through the end of the tail
    projection=rows[len(doses):max(len(doses) + 1, end)]
    below=0 if current<1.5 else next((i+1 for i,r in enumerate(projection)
                                     if r["score"]<1.5),None)
    clear = lambda r: r["score"] < 1.5 or (r["phase"] == "tail" and r["score"] <= 1.5 * TAIL_RUN_FACTOR)
    cleared = 0 if clear(rows[len(doses)-1]) else next((i+1 for i,r in enumerate(projection) if clear(r)), None)
    return {"score":current,"history":rows[:len(doses)],"projection":projection,
            "plateau_days":round(plateau,1),"descent_days":round(descent,1),
            "tail_days":TAIL_DAYS,
            "plateau_remaining_days":round(max(0,anchor_day+plateau-(len(doses)-1)),1),
            "below_threshold_in_days":below,"threshold_blocks":1.5,
            "phase":rows[len(doses)-1]["phase"],"tail_run_limit":round(1.5*TAIL_RUN_FACTOR,2),
            "cleared_to_run_in_days":cleared,
            "tail_starts_in_days":next((i+1 for i,r in enumerate(projection) if r["phase"]=="tail"),None),
            "reference_points":round(reference,1),"checkins_used":used,
            "conditioning_credit":round(credit,2),"confirmed_recoveries":len(clean),
            "components":events[-12:], "walking":walk_rows[-14:],
            "walking_week_blocks":round(sum(r["added_blocks"] for r in walk_rows[-7:]),2),
            "max_impact_multiplier":round(max((e["incoming_multiplier"] for e in events),default=1),2),
            "provisional":True}


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


def model(dates, doses, usual_week=None, weight_kg=70.0, feet_reports=None, run_doses=None, walking=None, block=None):
    """dates: consecutive ISO days; doses: impact points per day. Returns each tissue's backlog today,
    its history, and a no-more-running projection."""
    if not dates:
        return None
    doses = list(doses)
    remodeling = remodeling_response(dates, run_doses if run_doses is not None else doses, usual_week, weight_kg,
                                     feet_reports, walking, block)
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
