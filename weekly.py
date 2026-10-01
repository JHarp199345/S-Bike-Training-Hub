"""weekly.py - the Sunday check-in: one look back at the week, for calibration (the rider's design, 2026-09-30).

Every Sunday (open through Tuesday) Today asks about what the week actually held, and nothing else:
  bike        legs, 1-10
  run         feet and bones 1-10, and the hop test per leg (only in a week with running)
  swim        shoulders, 1-10
  lifting     each muscle group the week's lifting worked hardest, 1-10
  the week    how it felt overall, 1-10, and a note
The answers fill that Sunday's daily check-in where it's empty (so the running and swim models read them like any
report), and the swim and lifting fits give them extra weight as the week's anchor.
"""
import datetime as dt

OPEN_DAYS = 2             # Sunday's check-in stays open through Tuesday


def sunday_for(today):
    """The Sunday whose check-in is open on `today` (that Sunday, or the one before on Monday/Tuesday), else None."""
    back = (today.weekday() + 1) % 7                      # Sunday = 0 days back
    return today - dt.timedelta(days=back) if back <= OPEN_DAYS else None


def questions(d, sunday, done):
    """What to ask for the week Monday-Sunday ending on `sunday`. done: {date: [{sport, minutes}]}."""
    import lifting
    days = [(sunday - dt.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    sports = {x["sport"] for day in days for x in done.get(day, [])}
    run_goal = any(e.get("kind") == "race" and e.get("sport") in ("run", "tri") and e.get("date", "") >= sunday.isoformat()
                   for e in d.get("events", []))
    logs = [l for l in lifting.state(d)["logs"] if l["date"] in days]
    regs = {}
    for l in logs:
        for r, v in l["regions"].items():
            regs[r] = regs.get(r, 0) + v
    names = lifting.regions()
    q = []
    if "bike" in sports:
        q.append({"key": "legs", "label": "Leg muscles after the week's riding", "scale": "1 fresh, 10 wrecked"})
    if "run" in sports:
        q.append({"key": "feet", "label": "Feet and bones after the week's running", "scale": "1 fine, 10 very sore"})
        q.append({"key": "hops", "label": "Hop test, only if comfortable", "scale": "optional pain-free single-leg hops, each leg"})
    elif run_goal:
        q.append({"key": "feet", "label": "Feet and lower legs while running is paused", "scale": "1 fine, 10 very sore"})
    if "swim" in sports:
        q.append({"key": "shoulders", "label": "Shoulders after the week's swimming", "scale": "1 fine, 10 very sore"})
    for r in sorted(regs, key=regs.get, reverse=True)[:6]:
        q.append({"key": f"lift:{r}", "label": f"{names[r]} after the week's lifting", "scale": "1 fine, 10 very sore"})
    q.append({"key": "week", "label": "The week overall", "scale": "1 easy, 10 too much"})
    return {"sunday": sunday.isoformat(), "week": [days[0], days[-1]], "sports": sorted(sports | ({"gym"} if logs else set())),
            "run_goal": run_goal, "lift_sessions": len(logs),
            "questions": q}


def due(d, today, done):
    s = sunday_for(today)
    if s is None or s.isoformat() in d.get("weekly", {}):
        return None
    return questions(d, s, done)


def record(d, sunday, fields):
    """Save the week's answers and fill that Sunday's check-in where it's empty."""
    import coach
    if dt.date.fromisoformat(sunday).weekday() != 6:
        raise ValueError("the weekly check-in belongs to a Sunday")
    rate = lambda v: max(1, min(10, int(v)))
    out = {"date": dt.date.today().isoformat()}
    for k in ("legs", "feet", "shoulders", "week"):
        if fields.get(k) is not None:
            out[k] = rate(fields[k])
    for k in ("hops_left", "hops_right"):
        if fields.get(k) is not None:
            out[k] = max(0, min(100, int(fields[k])))
    lift = {r: rate(v) for r, v in (fields.get("lift") or {}).items()}
    if lift:
        import lifting
        bad = [r for r in lift if r not in lifting.regions()]
        if bad:
            raise ValueError(f"unknown regions: {', '.join(bad)}")
        out["lift"] = lift
    if fields.get("note"):
        out["note"] = str(fields["note"])[:1000]
    progress = fields.get("progress") or {}
    if not isinstance(progress, dict) or any(k not in ("bike", "run", "swim", "gym") or v not in ("better", "same", "worse")
                                              for k, v in progress.items()):
        raise ValueError("progress must name a sport and better, same or worse")
    if progress:
        out["progress"] = progress
    if fields.get("run_response") is not None:
        if fields["run_response"] not in ("resolved", "pulling", "not_tested"):
            raise ValueError("run_response is resolved, pulling or not_tested")
        out["run_response"] = fields["run_response"]
    if len(out) == 1:
        raise ValueError("answer at least one question")
    d.setdefault("weekly", {})[sunday] = out
    c = d["checkins"].get(sunday) or {}
    fill = {k: out[k] for k in ("legs", "feet", "shoulders", "hops_left", "hops_right") if k in out and c.get(k) is None}
    if fill:
        coach.record(d, sunday, fill)
    return out
