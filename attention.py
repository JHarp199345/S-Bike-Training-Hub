"""attention.py - what needs the athlete's and the assistant's attention in the coming week (the rider's design,
2026-10-03).

Every check-in returns this list, and the assistant works through it in the same conversation: it proposes the
lightest fix for each item, previews it, applies it once the athlete agrees, and says what changed and why (or
that the plan stands). The hub only lists; apart from the opt-in progression policy (at most one bounded change
per check-in, when the athlete has switched it on), it doesn't rewrite the plan on its own.

Most urgent first: stop/whole-body warnings, training-rule breaks, forecast conflicts, running deloads and
targets, calibration questions, missed sessions without a reason, then cautions.
"""
import datetime as dt

ORDER = ("stop", "warning", "rule", "forecast", "deload", "calibration", "missed", "running", "caution")


def items(d, load, done, workouts, today, days=7):
    import calibration, coach, coaching_review
    out = []
    end = (dt.date.fromisoformat(today) + dt.timedelta(days=days - 1)).isoformat()
    look = coaching_review.outlook(d, load, done, workouts, today, days)
    rp = look.get("running_progression") or {}

    def add(kind, date, what, fix, tool="preview_coaching_change"):
        out.append({"kind": kind, "date": date, "what": what, "fix": fix, "tool": tool})

    if rp.get("status") == "stop":
        add("stop", today, rp["advice"], "Take running out of the plan and suggest having it assessed.", "preview_coaching_change")
    if rp.get("whole_body_warning"):
        add("warning", today, rp["whole_body_warning"], "Ease all training today; ask how they feel and suggest a doctor if it's unusual or persists.", None)
    for f in look.get("training_rules") or []:
        if f["severity"] == "breaks":
            add("rule", f["dates"][-1], f"{f['rule']} on {', '.join(f['dates'])}: {f['why']}", "Move, swap or lighten one of the sessions.")
    for s in look.get("sessions") or []:
        if s["status"] == "conflict":
            add("forecast", s["date"], f"{s['name']} on {s['date']} lands over its forecast limit.",
                "Shorten it, space it from the work before, or swap it for an eligible session; preview until it fits.")
        elif s["status"] == "unknown":
            add("forecast", s["date"], f"{s['name']} on {s['date']} has no forecast (missing dose or reference).",
                "Check the session's details or record the missing capacity.", None)
    if rp.get("status") in ("over_target", "under_target") and (rp.get("deload") or {}).get("status") in ("deload", "deep_deload"):
        add("deload", today, f"Automatic running deload ({rp['deload']['status'].replace('_', ' ')}): {'; '.join(rp['deload']['why'][-2:])}. "
            f"Target {rp['target_blocks'][0]}-{rp['target_blocks'][1]} blocks until {rp['deload']['ends']}.",
            "Shorten or space this week's runs to the deload target, keeping a little easy running.")
    elif (rp.get("deload") or {}).get("status") == "re_entry":
        add("deload", today, f"Running comes back in at 0.8 blocks this week (until {rp['deload']['ends']}).",
            "Plan the week's runs at the bottom of the band.")
    acts = {a["date"]: a for a in (load or {}).get("activities", []) if a.get("sport") == "run"}
    for c in calibration.calibration_runs(d, acts):
        if c["needs_confirm"]:
            add("calibration", c["run_date"], f"A {c['minutes']}-min run on {c['run_date']} was near the planned calibration ({c['date']}).",
                "Ask whether it was the test and record it (record_test calibration_run, was_test).", "record_test")
        elif c["needs_reason"]:
            add("calibration", c["run_date"], f"The running calibration on {c['run_date']} stopped at {c['minutes']} min.",
                "Ask why (time, tired, form, pain, interrupted) and record it (record_test calibration_run, reason).", "record_test")
    week_ago = (dt.date.fromisoformat(today) - dt.timedelta(days=7)).isoformat()
    for date, missed in coach.missed_days(d, week_ago, today, done).items():
        for m in missed:
            if not m.get("reason"):
                add("missed", date, f"{m['name']} on {date} was missed.",
                    "Ask why (record_missed_session) and plan the week around what actually happened.", "record_missed_session")
    if rp.get("status") in ("under_target", "over_target") and not (rp.get("deload") or {}).get("status"):
        add("running", today, rp.get("advice") or "", "Adjust this week's runs toward the target, one well-spaced step.")
    elif rp.get("status") == "held":
        add("running", today, rp.get("advice") or "", "Keep runs out until the hold or symptom is resolved.", None)
    for f in look.get("training_rules") or []:
        if f["severity"] == "caution":
            add("caution", f["dates"][-1], f"{f['rule']} on {', '.join(f['dates'])}: {f['why']}", "Weigh it with the athlete; change it only if it doesn't fit.", None)
    out = [x for x in out if x["date"] <= end or x["kind"] in ("missed", "calibration")]
    out.sort(key=lambda x: (ORDER.index(x["kind"]), x["date"]))
    return {"as_of": today, "days": days, "items": out,
            "summary": "Nothing needs changing: the plan stands." if not out else
                       f"{len(out)} thing{'s' if len(out) != 1 else ''} to go through with the athlete, most urgent first.",
            "routine": "Go through the items in order: propose the lightest fix, preview it, apply it once the athlete "
                       "agrees, and say what changed and why. The hub changes nothing here by itself."}
