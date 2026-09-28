"""coach.py - the daily diagnostic, check-ins, today's plan, and time-split workouts.

Morning diagnostic (6 min, ERG, the same watts every day):
    0-2 min  60 W   settle in
    2-4 min  90 W   heart rate at the end of this is the key number
    4-5 min 120 W   how the legs answer a small push
    5-6 min  easy   heart-rate recovery: how far it falls in the 60 s after the push
Then legs (1-10, 10 = wrecked), breathing (1-10) and the gut call
(go / easy / no). Heart rate is read off the watch and typed in on the phone
(no extra Bluetooth); it can be corrected later from COROS.

Verdict: against the rider's own normal - the median of recent tests - once there
are three. Until then the gut call and the legs lead.
    HR at 90 W  6+ bpm above normal       -> fatigue (easy)
    recovery    6+ bpm less than normal   -> fatigue (easy)
    HR 8+ below normal with heavy legs    -> deep fatigue (rest)
    legs 8+ or gut "no"                   -> rest
    legs 6-7 or gut "easy"                -> easy
Today's plan (verdict, note, workout) is written by the coach - Claude,
through the hub command - or picked on the Coach page.

coach.json (beside the rides folder, kept out of git) holds it all.
"""
import datetime as dt
import json
import statistics
from pathlib import Path

TEST_STEPS = [{"minutes": 2, "watts": 60}, {"minutes": 2, "watts": 90}, {"minutes": 1, "watts": 120},
              {"minutes": 1, "watts": 30}]
TEST_NAME = "Morning diagnostic (6 min)"
VERDICTS = {"go": "Go - train as planned", "easy": "Easy only", "rest": "Rest"}


def file_for(rides_dir):
    return Path(rides_dir).resolve().parent / "coach.json"


def load(path):
    try:
        d = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("checkins", {})
    d.setdefault("plans", {})
    d["_path"] = str(path)
    return d


def save(d):
    p = Path(d["_path"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v for k, v in d.items() if k != "_path"}, indent=1))
    tmp.replace(p)


def today():
    return dt.date.today().isoformat()


def _num(v, lo, hi):
    if v in (None, ""):
        return None
    v = float(v)
    if not lo <= v <= hi:
        raise ValueError(f"{v:g} is outside {lo}-{hi}")
    return round(v)


def record(d, date, fields):
    """Add or update the day's check-in (partial updates are fine)."""
    c = d["checkins"].setdefault(date, {})
    for k, lo, hi in (("hr90", 40, 220), ("hr120", 40, 220), ("hr_after", 30, 220), ("legs", 1, 10), ("breathing", 1, 10),
                      ("sleep", 1, 10), ("motivation", 1, 10)):
        if k in fields:
            c[k] = _num(fields[k], lo, hi)
    if "gut" in fields:
        if fields["gut"] not in ("go", "easy", "no", None, ""):
            raise ValueError("gut is go, easy or no")
        c["gut"] = fields["gut"] or None
    for k in ("note", "test_ride", "test_at"):
        if k in fields:
            c[k] = str(fields[k])[:500] if fields[k] is not None else None
    top = c.get("hr120") or c.get("hr90")
    if top and c.get("hr_after"):
        c["hrr"] = top - c["hr_after"]                 # heart-rate recovery: end of the push -> 60 s later
    c["verdict"], c["why"] = verdict(d, date)
    return c


def baseline(d, before):
    """The rider's normal: medians of the last (up to) seven tests before this day."""
    past = [c for day, c in sorted(d["checkins"].items()) if day < before and c.get("hr90")][-7:]
    if len(past) < 3:
        return None
    b = {"tests": len(past), "hr90": statistics.median(c["hr90"] for c in past)}
    hrr = [c["hrr"] for c in past if c.get("hrr") is not None]
    b["hrr"] = statistics.median(hrr) if len(hrr) >= 3 else None
    return b


def verdict(d, date):
    """(go/easy/rest or None, reasons)."""
    c = d["checkins"].get(date, {})
    why, level = [], 0                                   # 0 go, 1 easy, 2 rest
    legs, gut = c.get("legs"), c.get("gut")
    if legs is not None:
        if legs >= 8:
            level = max(level, 2); why.append(f"legs {legs}/10")
        elif legs >= 6:
            level = max(level, 1); why.append(f"legs {legs}/10")
    if gut == "no":
        level = max(level, 2); why.append("your call: not happening")
    elif gut == "easy":
        level = max(level, 1); why.append("your call: easy only")
    b = baseline(d, date)
    if b and c.get("hr90"):
        diff = c["hr90"] - b["hr90"]
        if diff >= 6:
            level = max(level, 1); why.append(f"heart rate at 90 W {diff:+.0f} vs your normal")
        elif diff <= -8 and (legs or 0) >= 6:
            level = max(level, 2); why.append(f"heart rate {diff:+.0f} below normal with heavy legs (deep fatigue)")
        if b.get("hrr") is not None and c.get("hrr") is not None and c["hrr"] <= b["hrr"] - 6:
            level = max(level, 1); why.append(f"recovery {c['hrr']} bpm vs your normal {b['hrr']:.0f}")
    elif c.get("hr90") and not b:
        why.append(f"building your baseline ({sum(1 for x in d['checkins'].values() if x.get('hr90'))}/3 tests)")
    if legs is None and gut is None and not c.get("hr90"):
        return None, []
    if level == 0 and not [w for w in why if not w.startswith("building")]:
        why.insert(0, "everything looks normal")
    return ["go", "easy", "rest"][level], why


def set_plan(d, date, verdict_=None, note=None, workout=None):
    p = d["plans"].setdefault(date, {})
    if verdict_ is not None:
        if verdict_ not in VERDICTS:
            raise ValueError("verdict is go, easy or rest")
        p["verdict"] = verdict_
    if note is not None:
        p["note"] = str(note)[:1000]
    if workout is not None:
        p["workout"] = workout or None
    p["updated"] = dt.datetime.now().isoformat(timespec="minutes")
    return p


def day(d, date):
    return {"date": date, "checkin": d["checkins"].get(date), "plan": d["plans"].get(date),
            "baseline": baseline(d, date)}


# ── time-split workouts ─────────────────────────────────────────────────────

def split_parts(intervals):
    """The standard shape: warm-up, ramp, interval 1, rest, ..., interval N, cool-down."""
    parts = [{"kind": "warmup", "label": "Warm-up"}, {"kind": "ramp", "label": "Ramp"}]
    for i in range(intervals):
        parts.append({"kind": "interval", "label": f"Interval {i + 1}"})
        if i < intervals - 1:
            parts.append({"kind": "rest", "label": f"Rest {i + 1}"})
    parts.append({"kind": "cooldown", "label": "Cool-down"})
    return parts


def rebalance(minutes, index, new_value, total, floor=0.25):
    """Set part `index` to new_value; every other part changes in proportion to
    its current size so the total stays the same (the sliding bar chart)."""
    new_value = max(floor, min(total - floor * (len(minutes) - 1), new_value))
    others = [m for i, m in enumerate(minutes) if i != index]
    rest_now, rest_new = sum(others), total - new_value
    out = []
    for i, m in enumerate(minutes):
        if i == index:
            out.append(new_value)
        else:
            out.append(rest_new * (m / rest_now) if rest_now > 0 else rest_new / len(others))
    # keep every part at least `floor` without breaking the total: pin the ones that
    # fell short, take the difference from the rest, and repeat until nothing is short
    pinned = set()
    for _ in range(len(out)):
        short = [i for i, m in enumerate(out) if i != index and i not in pinned and m < floor - 1e-12]
        if not short:
            break
        for i in short:
            out[i] = floor
            pinned.add(i)
        spare = [i for i in range(len(out)) if i != index and i not in pinned]
        excess = sum(out) - total
        pool = sum(out[i] for i in spare)
        for i in spare:
            out[i] -= excess * out[i] / pool if pool else 0
    return out


def split_to_blocks(parts):
    """Coach-page parts (minutes + intensity) -> workout-builder blocks."""
    blocks = []
    for p in parts:
        m = float(p["minutes"])
        if m <= 0:
            continue
        label = {"label": str(p["label"])[:40]} if p.get("label") else {}   # names the part in the report
        if p["kind"] == "ramp":
            blocks.append({"type": "ramp", "minutes": m, "from": p.get("from", 50), "to": p.get("to", 75), **label})
        elif p.get("watts"):
            blocks.append({"type": "steady", "minutes": m, "watts": int(p["watts"]), **label})
        else:
            blocks.append({"type": "steady", "minutes": m, "pct": int(p.get("pct", 60)), **label})
    return blocks
