"""workouts.py - the workout builder's side of things: blocks in, ERG steps out.

A workout file (workouts/<id>.json) keeps what the builder edits, "blocks",
and what the ERG engine runs, "steps" (a flat list of steady steps):

  {"type": "steady",    "minutes": 20, "pct": 61}
  {"type": "ramp",      "minutes": 3, "from": 50, "to": 65}       -> three equal stages
  {"type": "intervals", "times": 5, "on":  {"minutes": 3, "pct": 92},
                                    "off": {"minutes": 3, "pct": 50}}

Intensity is % of FTP, so every workout rescales when FTP changes. Older
files with only "steps" open in the builder as steady blocks.
"""
import json
import re
from pathlib import Path

import live

FOLDER = Path(__file__).resolve().parent / "workouts"
RAMP_STAGES = 3             # equal time; each stage advances a third of the planned rise
MAX_MINUTES = 6 * 60


class BadWorkout(ValueError):
    pass


def _num(v, lo, hi, what):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise BadWorkout(f"{what} must be a number")
    if not lo <= v <= hi:
        raise BadWorkout(f"{what} must be between {lo:g} and {hi:g}")
    return v


def flatten(blocks):
    """Blocks -> [{"minutes", "pct"}] steady steps, in order."""
    steps = []
    for i, b in enumerate(blocks, 1):
        kind = b.get("type")
        if kind == "steady" and b.get("watts") is not None:        # a fixed target in watts
            steps.append({"minutes": _num(b.get("minutes"), 1 / 60, 300, f"Block {i} time"),
                          "watts": round(_num(b.get("watts"), 20, 1500, f"Block {i} watts"))})
        elif kind == "steady":
            steps.append({"minutes": _num(b.get("minutes"), 1 / 60, 300, f"Block {i} time"),
                          "pct": round(_num(b.get("pct"), 20, 250, f"Block {i} intensity"))})
        elif kind == "ramp":
            mins = _num(b.get("minutes"), 0.5, 120, f"Block {i} time")
            a = _num(b.get("from"), 20, 250, f"Block {i} start")
            z = _num(b.get("to"), 20, 250, f"Block {i} end")
            n = RAMP_STAGES
            for k in range(n):
                pct = a + (z - a) * (k + 1) / n               # finish exactly at the interval's floor
                steps.append({"minutes": mins / n, "pct": round(pct)})
        elif kind == "intervals":
            times = int(_num(b.get("times"), 1, 50, f"Block {i} repeats"))
            on, off = b.get("on") or {}, b.get("off") or {}
            for k in range(times):
                steps.append({"minutes": _num(on.get("minutes"), 1 / 60, 60, f"Block {i} work time"),
                              "pct": round(_num(on.get("pct"), 20, 250, f"Block {i} work intensity"))})
                off_min = float(off.get("minutes") or 0)
                if off_min > 0 and k < times - 1 or (off_min > 0 and b.get("rest_after_last")):
                    steps.append({"minutes": _num(off_min, 1 / 60, 60, f"Block {i} rest time"),
                                  "pct": round(_num(off.get("pct"), 20, 250, f"Block {i} rest intensity"))})
        else:
            raise BadWorkout(f"Block {i}: unknown kind {kind!r}")
    # merge neighbours at the same intensity so the ride shows fewer, longer steps
    merged = []
    for s in steps:
        if merged and merged[-1].get("pct") == s.get("pct") and merged[-1].get("watts") == s.get("watts"):
            merged[-1]["minutes"] += s["minutes"]
        else:
            merged.append(dict(s))
    for s in merged:
        s["minutes"] = round(s["minutes"], 4)
    if not merged:
        raise BadWorkout("Add at least one block")
    if sum(s["minutes"] for s in merged) > MAX_MINUTES:
        raise BadWorkout("That's over six hours")
    return merged


def blocks_from_steps(steps):
    return [{"type": "steady", "minutes": s["minutes"], **({"watts": s["watts"]} if "watts" in s else {"pct": s.get("pct", 60)})}
            for s in steps if "pct" in s or "watts" in s]


def stats(steps, ftp):
    """Time, load (TSS), intensity and calories of a workout ridden exactly at FTP."""
    secs = sum(s["minutes"] * 60 for s in steps)
    if not secs:
        return {"minutes": 0, "tss": 0, "if": 0, "kcal": 0, "avg_w": 0}
    watts = [(s["minutes"] * 60, s["watts"] if "watts" in s else s["pct"] / 100 * ftp) for s in steps]
    avg = sum(d * w for d, w in watts) / secs
    np_ = (sum(d * w ** 4 for d, w in watts) / secs) ** 0.25          # steady steps: NP ~ 4th-power mean
    iff = np_ / ftp
    return {"minutes": round(secs / 60, 1), "tss": round(secs / 3600 * iff * iff * 100),
            "if": round(iff, 2), "avg_w": round(avg), "kcal": round(live.kcal_from_kj(avg * secs / 1000))}


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:50] or "workout"


def list_all(ftp, folder=None):
    folder = folder or FOLDER                        # looked up now, so tests can point it elsewhere
    out = []
    for f in sorted(Path(folder).glob("*.json")):
        try:
            w = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not w.get("steps"):
            continue
        w["id"] = f.stem
        w.setdefault("blocks", blocks_from_steps(w["steps"]))
        w.setdefault("note", "")
        w["stats"] = stats(w["steps"], ftp)
        out.append(w)
    return out


def save(data, folder=None):
    """Write a workout from the builder; returns its id."""
    folder = folder or FOLDER
    name = str(data.get("name") or "").strip()[:80]
    if not name:
        raise BadWorkout("Give the workout a name")
    blocks = data.get("blocks") or []
    steps = flatten(blocks)
    wid = data.get("id") or ""
    if not re.fullmatch(r"[a-z0-9-]{1,60}", wid) or not (Path(folder) / f"{wid}.json").exists():
        base = slug(name)
        wid, n = base, 2
        while (Path(folder) / f"{wid}.json").exists():
            wid, n = f"{base}-{n}", n + 1
    Path(folder).mkdir(exist_ok=True)
    out = {"name": name, "note": str(data.get("note") or "")[:300], "blocks": blocks, "steps": steps}
    tmp = Path(folder) / f".{wid}.tmp"
    tmp.write_text(json.dumps(out, indent=1))
    tmp.replace(Path(folder) / f"{wid}.json")
    return wid


def delete(wid, folder=None):
    folder = folder or FOLDER
    if not re.fullmatch(r"[a-z0-9-]{1,60}", wid or ""):
        raise BadWorkout("No such workout")
    p = Path(folder) / f"{wid}.json"
    if not p.exists():
        raise BadWorkout("No such workout")
    p.unlink()
