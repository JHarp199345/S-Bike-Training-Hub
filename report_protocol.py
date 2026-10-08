"""report_protocol.py - what happens when a report goes bad: re-check that evening and the next morning, then
resume, stay reduced, or step back. It schedules questions and flags work; it never cancels anything silently and never
diagnoses.

A report is bad when (pain-monitoring model, Silbernagel et al. 2007):
  - pain is 5 or more at any site, or
  - pain at a site is worse than the previous report (e.g. worse the next morning), or
  - leg or feet soreness is 3 or more points above the athlete's usual (median of the last 28 days).

Re-check answers: pain by site (0-10), stiffness, walking and stairs comfort, and red flags.
Outcome:
  red flag at any point            stop that work and see a professional
  settled (pain <= 2, not worse)   resume the plan; the next increase waits a week
  improving but not settled        stay reduced, no running; another morning re-check
  not better after 48 h, or worse  step back: hold the coming runs, record an OSTRC entry, suggest a professional
"""
import datetime as dt
import statistics
import uuid

RED_FLAGS = {"sharp_bone_pain": "Sharp or pinpoint bone pain", "swelling": "Swelling", "limping": "Limping",
             "night_pain": "Pain at night or at rest", "numbness": "Numbness or tingling"}
IMPACT = ("run", "walk")
EVENING_HOUR, MORNING_HOUR = 19, 8


def _pains(record, kind):
    if kind == "workout":
        out = {}
        for s in record.get("symptoms") or []:
            out[s["location"]] = max(out.get(s["location"], 0), s.get("severity") or 0)
        return out
    return dict(record.get("pain") or {})


def assess(d, kind, record, date):
    """Is this report bad? -> list of plain reasons (empty = not bad)."""
    reasons = []
    pains = _pains(record, kind)
    for site, v in pains.items():
        if v >= 5:
            reasons.append(f"{site.replace('_', ' ')} pain {v}/10")
    if kind == "checkin":
        prev = [c for k, c in sorted((d.get("checkins") or {}).items()) if k < date and c.get("pain") is not None]
        if prev:
            for site, v in pains.items():
                before = (prev[-1].get("pain") or {}).get(site, 0)
                if v > before and v >= 3:
                    reasons.append(f"{site} pain worse than last report ({before} → {v})")
        window = [c for k, c in (d.get("checkins") or {}).items()
                  if (dt.date.fromisoformat(date) - dt.timedelta(days=28)).isoformat() <= k < date]
        for key in ("legs", "feet"):
            usual = [c[key] for c in window if c.get(key) is not None]
            if record.get(key) is not None and len(usual) >= 5 and record[key] >= statistics.median(usual) + 3:
                reasons.append(f"{key} soreness {record[key]}/10, well above your usual {statistics.median(usual):g}")
    return list(dict.fromkeys(reasons))


def open_rechecks(d, today=None):
    return [r for r in (d.get("report_rechecks") or {}).values() if r["status"] == "open"]


def on_report(d, kind, key, record, date, now=None):
    """After a report is saved: start a re-check if it's bad and none is open. Returns the re-check or None."""
    now = now or dt.datetime.now()
    reasons = assess(d, kind, record, date)
    if not reasons:
        return None
    for r in open_rechecks(d):                       # one open re-check at a time; add the new reasons to it
        r["reasons"] = list(dict.fromkeys(r["reasons"] + reasons))
        return r
    day = dt.date.fromisoformat(date)
    evening = dt.datetime.combine(day, dt.time(EVENING_HOUR))
    if now >= evening - dt.timedelta(hours=2):       # reported late: re-check in about three hours instead
        evening = now + dt.timedelta(hours=3)
    morning = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(MORNING_HOUR))
    r = {"id": uuid.uuid4().hex[:12], "status": "open", "created": now.isoformat(timespec="minutes"),
         "trigger": {"kind": kind, "key": key, "date": date, "pain": _pains(record, kind)}, "reasons": reasons,
         "due": [{"slot": "evening", "at": evening.isoformat(timespec="minutes")},
                 {"slot": "morning", "at": morning.isoformat(timespec="minutes")}],
         "answers": [], "outcome": None,
         "advice": "Hold running and jumping today and tomorrow; non-impact work at a lower rate is fine if you want to train. Re-check this evening and tomorrow morning."}
    d.setdefault("report_rechecks", {})[r["id"]] = r
    return r


def answer(d, rid, fields, now=None):
    """Record a re-check answer and decide the outcome."""
    now = now or dt.datetime.now()
    r = (d.get("report_rechecks") or {}).get(rid)
    if not r or r["status"] != "open":
        raise ValueError("No open re-check with that id")
    pain = fields.get("pain") or {}
    if not isinstance(pain, dict) or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 10 for v in pain.values()):
        raise ValueError("pain is {site: 0-10}")
    flags = [f for f in fields.get("red_flags") or [] if f in RED_FLAGS]
    comfort = {k: fields.get(k) for k in ("walking", "stairs") if fields.get(k) in ("easy", "some", "hard")}
    stiffness = fields.get("stiffness")
    if stiffness is not None and not (isinstance(stiffness, (int, float)) and 0 <= stiffness <= 10):
        raise ValueError("stiffness is 0-10")
    slot = fields.get("slot") if fields.get("slot") in ("evening", "morning") else ("evening" if now.hour >= 12 else "morning")
    r["answers"].append({"at": now.isoformat(timespec="minutes"), "slot": slot, "pain": pain, "stiffness": stiffness,
                         "red_flags": flags, **comfort})
    worst_now = max(pain.values(), default=0)
    worst_then = max(r["trigger"]["pain"].values(), default=0)
    worse = any(v > r["trigger"]["pain"].get(s, 0) for s, v in pain.items()) or comfort.get("walking") == "hard"
    age_h = (now - dt.datetime.fromisoformat(r["created"])).total_seconds() / 3600
    if flags:
        outcome = ("stop", "Red flag reported (" + ", ".join(RED_FLAGS[f] for f in flags) + "). Stop that work and see a professional before resuming it.")
    elif worse or (age_h >= 48 and worst_now > 2):
        outcome = ("step_back", "Not better after 48 hours, or worse. Hold the coming runs, record the area in this week's OSTRC questions, and consider a professional assessment.")
    elif slot == "morning" and worst_now <= 2 and (stiffness or 0) <= 3:
        outcome = ("settled", "Settled by the morning. Resume the plan; the next increase waits a week.")
    elif slot == "morning":
        outcome = ("improving", "Improving but not settled. Stay at the reduced load with no running, and re-check tomorrow morning.")
        nxt = dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(MORNING_HOUR))
        r["due"].append({"slot": "morning", "at": nxt.isoformat(timespec="minutes")})
    else:
        outcome = ("waiting", "Thanks. The morning re-check decides what happens next.")
    r["outcome"] = {"result": outcome[0], "advice": outcome[1], "at": now.isoformat(timespec="minutes"),
                    "pain_then": worst_then, "pain_now": worst_now}
    if outcome[0] in ("settled", "stop", "step_back"):
        r["status"] = "closed"
    return r


def holds(d, today):
    """Running held today/tomorrow by an open re-check, and whether the next build increase waits (7 days after)."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else today
    rr = list((d.get("report_rechecks") or {}).values())
    open_ = [r for r in rr if r["status"] == "open"]
    recent = [r for r in rr if (today - dt.date.fromisoformat(r["trigger"]["date"])).days <= 7]
    stepped_back = [r for r in rr if (r.get("outcome") or {}).get("result") in ("step_back", "stop")]
    return {"impact_held": bool(open_) or any((today - dt.date.fromisoformat(r["trigger"]["date"])).days <= 14 for r in stepped_back),
            "increase_waits": bool(recent), "open": open_}
