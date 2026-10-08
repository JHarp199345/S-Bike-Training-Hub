"""report_snapshots.py - each report keeps the work context it was made in.

A report (daily or weekly check-in, workout report, lifting follow-up) is evidence about how recorded work felt. Its
3-day rate and 28-day carried load (work_rate.snapshot) are frozen when it is saved, so later formula changes never
move old evidence. Records saved before this existed are rebuilt once through preview -> apply: the same arithmetic,
only activities before each record's time, marked "rebuilt", never overwriting a field.

Timing rules for what a report "had in it":
  workout report       the whole report day (it is made after the session)
  check-in, weekly     sessions that started before it was saved; for a rebuilt record without a saved time,
                       none of that day's sessions
  lifting follow-up    as a check-in
"""
import copy
import datetime as dt
import hashlib
import json

import work_rate

KINDS = ("checkin", "weekly", "workout", "lift_followup")


def _hhmm(iso):
    try:
        return dt.datetime.fromisoformat(iso).strftime("%H:%M")
    except (TypeError, ValueError):
        return None


def records(d):
    """Every report: (kind, key, record, date, cutoff, session_id). cutoff None = whole day."""
    import lifting
    saved = {}
    for e in d.get("journal_entries", []):
        if e.get("saved_at"):
            saved[e["date"]] = max(saved.get(e["date"], ""), e["saved_at"])
    for date, c in sorted((d.get("checkins") or {}).items()):
        if isinstance(c, dict):
            yield "checkin", date, c, date, _hhmm(saved.get(date)) or "00:00", None
    for date, w in sorted((d.get("weekly") or {}).items()):
        if isinstance(w, dict):
            yield "weekly", date, w, w.get("date") or date, "00:00", None
    for key, f in sorted((d.get("training_feedback") or {}).items()):
        yield "workout", key, f, f.get("date") or key[:10], None, f.get("activity_id")
    for log_date, f in sorted((lifting.state(d).get("followups") or {}).items()):
        yield "lift_followup", log_date, f, f.get("date") or log_date, "00:00", None


def freeze(record, load, logs, feedback, date, kind, session=None, now=None):
    """At save: attach the snapshot to a report that was just written."""
    now = now or dt.datetime.now()
    cutoff = None if kind == "workout" else now.strftime("%H:%M") if date == now.date().isoformat() else None
    record["snapshot"] = work_rate.snapshot(load, logs, feedback, date, cutoff, "at_report", session,
                                            now.isoformat(timespec="seconds"))
    return record["snapshot"]


def current(snap):
    """Frozen and complete. A rebuilt snapshot made before a field was added (e.g. the peak day) may be topped up by
    the back-fill; one frozen when the report was saved is never rebuilt."""
    if not isinstance(snap, dict) or snap.get("version") != work_rate.SNAPSHOT:
        return False
    return snap.get("recorded") != "rebuilt" or "peak_day" in (snap.get("context_3_days") or {}).get("cardio", {})


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16]


def preview(d, load, logs):
    """What the back-fill would add: one rebuilt snapshot per report that has none. Nothing is saved."""
    rows = []
    for kind, key, rec, date, cutoff, session in records(d):
        if current(rec.get("snapshot")):
            continue
        snap = work_rate.snapshot(load, logs, d.get("training_feedback"), date, cutoff, "rebuilt", session, "back-fill")
        rows.append({"kind": kind, "key": key, "date": date, "cutoff": cutoff, "snapshot": snap})
    return {"token": _digest(rows), "count": len(rows), "records": rows,
            "already_frozen": sum(1 for _, _, rec, *_ in records(d) if isinstance(rec.get("snapshot"), dict)),
            "basis": "Rebuilt with the current ledger from activities before each record's time; marked 'rebuilt'. "
                     "Existing fields are never changed."}


def apply(d, load, logs, token):
    """Write exactly the previewed snapshots, if nothing changed since the preview. Returns a receipt."""
    fresh = preview(d, load, logs)
    if token != fresh["token"]:
        raise ValueError("The records or the ledger changed since the preview; preview again before applying.")
    by = {(r["kind"], r["key"]): r["snapshot"] for r in fresh["records"]}
    before = {}
    for kind, key, rec, *_ in records(d):
        snap = by.get((kind, key))
        if snap is not None and not current(rec.get("snapshot")):
            before[f"{kind}:{key}"] = copy.deepcopy(rec)
            rec["snapshot"] = snap
    return {"applied": len(before), "token": token, "keys": sorted(before),
            "receipt": {"at": dt.datetime.now().isoformat(timespec="seconds"), "model": work_rate.MODEL,
                        "before": before}}
