"""predictions.py - race predictions, refined as the program goes (the rider's design, 2026-10-03).

The assistant makes the prediction; the hub keeps it honest. Using the hub's own models (FTP/critical power and W'
for the bike, critical swim speed for the swim, the running block and run evidence for the run, the check-week
retests for how this athlete responds), the assistant predicts a range for a race and saves it here with its
legs, what it was based on and the biggest levers. The hub keeps every prediction it was given, never a rewritten
one, so the log shows how the forecast moved and narrowed as the evidence came in.

  REFINE   a test or calibration recorded after the latest prediction, or three weeks without one, makes it due
           again; the check-in attention list says so.
  GRADE    once the race result is recorded, every prediction is graded: how far off the most likely time was and
           whether the result fell inside the range.
"""
import datetime as dt

REFRESH_DAYS = 21
LEGS = ("swim", "t1", "bike", "t2", "run")


def seconds(v):
    """90, '1:30', '1:02:30' -> seconds."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        if v <= 0:
            raise ValueError("times are positive")
        return round(float(v))
    parts = str(v).strip().split(":")
    if not 1 <= len(parts) <= 3 or not all(p.strip().replace(".", "", 1).isdigit() for p in parts):
        raise ValueError(f"time '{v}' is seconds, m:ss or h:mm:ss")
    s = 0.0
    for p in parts:
        s = s * 60 + float(p)
    if s <= 0:
        raise ValueError("times are positive")
    return round(s)


def clock(s):
    if s is None:
        return None
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _event(d, event):
    evs = [e for e in d.get("events", []) if e.get("kind") == "race"]
    e = next((e for e in evs if event in (e.get("id"), e.get("date"))), None)
    if not e:
        raise ValueError(f"no race '{event}' on the calendar (add it with set_event first)")
    return e


def save(d, event, likely, low, high, legs=None, basis="", levers=None, today=None):
    """Save one prediction for a race (its id or date). Times in seconds or h:mm:ss."""
    e = _event(d, event)
    likely, low, high = seconds(likely), seconds(low), seconds(high)
    if None in (likely, low, high) or not low <= likely <= high:
        raise ValueError("the range is low <= likely <= high")
    legs = {k: seconds(v) for k, v in (legs or {}).items() if k in LEGS and v not in (None, "")}
    p = {"event": e["id"], "event_date": e["date"], "made_on": today or dt.date.today().isoformat(),
         "likely": likely, "low": low, "high": high, "legs": legs, "basis": str(basis or "")[:1500],
         "levers": [str(x)[:200] for x in (levers or [])][:5]}
    d.setdefault("race_predictions", []).append(p)
    return p


def result(d, event, time, legs=None, note=""):
    """The race result, which grades every prediction made for it."""
    e = _event(d, event)
    r = {"time": seconds(time), "legs": {k: seconds(v) for k, v in (legs or {}).items() if k in LEGS and v not in (None, "")},
         "note": str(note or "")[:300]}
    if not r["time"]:
        raise ValueError("the result needs a finishing time")
    d.setdefault("race_results", {})[e["id"]] = r
    return r


def _evidence(d, since, today):
    """Tests and calibrations recorded after `since` (inclusive of today)."""
    out = []
    for cap, rows in (d.get("calibration") or {}).items():
        out += [f"{r['date']}: {cap.replace('_', ' ')} {r.get('kind', 'test')} ({r.get('value')})"
                for r in rows if since < r.get("date", "") <= today]
    for date, rec in ((d.get("benchmarks") or {}).get("calibrations") or {}).items():
        when = rec.get("run_date") or date
        if since < when <= today:
            out.append(f"{when}: running calibration")
    return sorted(out)


def view(d, today=None):
    """Every race with predictions or coming up: the prediction log, how it moved, whether it's due, the grade."""
    today = today or dt.date.today().isoformat()
    preds = d.get("race_predictions", [])
    out = []
    for e in sorted((e for e in d.get("events", []) if e.get("kind") == "race"), key=lambda e: e["date"]):
        mine = sorted((p for p in preds if p["event"] == e["id"]), key=lambda p: p["made_on"])
        if e["date"] < today and not mine:
            continue
        r = (d.get("race_results") or {}).get(e["id"])
        log = []
        for p in mine:
            row = {k: p[k] for k in ("made_on", "basis", "levers")} | {
                "likely": clock(p["likely"]), "range": f"{clock(p['low'])}-{clock(p['high'])}", "range_width_s": p["high"] - p["low"],
                "legs": {k: clock(v) for k, v in p["legs"].items()}}
            if r:
                row["off_by_s"] = r["time"] - p["likely"]
                row["inside_range"] = p["low"] <= r["time"] <= p["high"]
            log.append(row)
        item = {"event": e["id"], "name": e["name"], "date": e["date"], "sport": e.get("sport"),
                "days_to_go": (dt.date.fromisoformat(e["date"]) - dt.date.fromisoformat(today)).days, "predictions": log}
        if r:
            item["result"] = {"time": clock(r["time"]), "legs": {k: clock(v) for k, v in r["legs"].items()}, "note": r["note"]}
            hits = sum(x["inside_range"] for x in log)
            item["grade"] = (f"{hits} of {len(log)} predictions had the result inside their range; the last was off by "
                             f"{abs(log[-1]['off_by_s'])} s ({'slower' if log[-1]['off_by_s'] > 0 else 'faster'})") if log else "no predictions were made"
        elif e["date"] >= today:
            last = mine[-1] if mine else None
            new = _evidence(d, last["made_on"], today) if last else []
            stale = last and (dt.date.fromisoformat(today) - dt.date.fromisoformat(last["made_on"])).days >= REFRESH_DAYS
            item["due"] = not last or bool(new) or bool(stale)
            item["why_due"] = ("no prediction yet" if not last else
                               f"new since {last['made_on']}: {'; '.join(new)}" if new else
                               f"{REFRESH_DAYS}+ days since {last['made_on']}" if stale else None)
            if len(mine) > 1:
                item["moved"] = (f"most likely {clock(mine[0]['likely'])} -> {clock(mine[-1]['likely'])}; range "
                                 f"{clock(mine[0]['high'] - mine[0]['low'])} wide -> {clock(mine[-1]['high'] - mine[-1]['low'])} wide")
        out.append(item)
    return {"as_of": today, "races": out}
