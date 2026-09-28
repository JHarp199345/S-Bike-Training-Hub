"""adherence.py - how well a ride followed its workout, part by part.

The ride's events say which workout started, when, and at what FTP; the
workout's blocks say what each part asked for. Every planned second is
checked against the watts actually ridden:

    on target   within 10% of the target (at least 8 W either way)
    score       on-target seconds / planned seconds (a second not ridden
                counts as missed - skipping the end isn't "on target")
    grade       A 90%+ · B 80%+ · C 70%+ · D 60%+ · F below

Interval blocks become two parts, the efforts and the recoveries, so the radar
chart stays readable. The morning diagnostic is graded the same way.
"""
import csv
import datetime as dt
import re
from pathlib import Path

import bests

TOLERANCE, MIN_W = 0.10, 8.0
GRADES = [(0.9, "A"), (0.8, "B"), (0.7, "C"), (0.6, "D"), (0.0, "F")]


def grade(score):
    return next(g for lim, g in GRADES if score >= lim)


def _events(ride_csv):
    ev = Path(ride_csv).with_name(Path(ride_csv).stem + "_events.csv")
    try:
        return [(dt.datetime.fromisoformat(r["time"]), r["event"]) for r in csv.DictReader(open(ev, newline=""))]
    except (OSError, KeyError, ValueError):
        return []


def _parts_from_blocks(blocks, ftp):
    """[(label, kind, [(seconds, w_from, w_to), ...])] in riding order, intervals split into efforts/recoveries."""
    to_w = lambda b, key="pct": b["watts"] if b.get("watts") is not None else b.get(key, 60) / 100 * ftp
    order = []
    for i, b in enumerate(blocks):
        kind = b.get("type")
        if kind == "steady":
            name = f'{b["label"]} · {round(to_w(b))} W' if b.get("label") else f"Steady {round(to_w(b))} W"
            order.append((f"part{i}", name, "steady", [(b["minutes"] * 60, to_w(b), to_w(b))]))
        elif kind == "ramp":
            a, z = b["from"] / 100 * ftp, b["to"] / 100 * ftp
            name = f'{b.get("label") or "Ramp"} {round(a)}→{round(z)} W'
            order.append((f"part{i}", name, "ramp", [(b["minutes"] * 60, a, z)]))
        elif kind == "intervals":
            on, off = b["on"], b["off"]
            won, woff = to_w(on), to_w(off)
            seq = []                                    # in time order, each tagged effort or recovery
            for k in range(int(b["times"])):
                seq.append(("on", on["minutes"] * 60, won))
                if k < int(b["times"]) - 1 and float(off.get("minutes") or 0) > 0:
                    seq.append(("off", off["minutes"] * 60, woff))
            order.append((f"part{i}", None, "intervals", seq))
    return order


def plan_timeline(blocks, ftp, labels=None):
    """Timeline segments [(t0, t1, w_from, w_to, part_key)] from the start, plus the parts' labels."""
    segs, parts, t = [], {}, 0.0
    for key, label, kind, seq in _parts_from_blocks(blocks, ftp):
        if kind == "intervals":
            kon, koff = key + ":on", key + ":off"
            w_on = next(w for tag, _, w in seq if tag == "on")
            parts[kon] = {"label": f"Efforts {round(w_on)} W", "kind": "effort"}
            if any(tag == "off" for tag, *_ in seq):
                w_off = next(w for tag, _, w in seq if tag == "off")
                parts[koff] = {"label": f"Recoveries {round(w_off)} W", "kind": "rest"}
            for tag, sec, w in seq:
                segs.append((t, t + sec, w, w, kon if tag == "on" else koff))
                t += sec
        else:
            sec, a, z = seq[0]
            parts[key] = {"label": label, "kind": kind}
            segs.append((t, t + sec, a, z, key))
            t += sec
    if labels:
        for (key, p), lab in zip(parts.items(), labels):
            p["label"] = lab
    return segs, parts


def score(ride_csv, start, blocks, ftp, name, labels=None, end=None):
    """Part-by-part adherence for a workout started at `start` (datetime)."""
    segs, parts = plan_timeline(blocks, ftp, labels)
    total = segs[-1][1] if segs else 0
    if not total:
        return None
    t0 = start.timestamp()
    stop = end.timestamp() - t0 if end else None
    power = {s: w for s, w in (p for p in bests.ride_seconds(ride_csv) if p is not None)}
    for p in parts.values():
        p.update({"planned": 0, "ridden": 0, "on": 0, "watts": 0.0, "target": 0.0})
    for a, z, wa, wz, key in segs:
        p = parts[key]
        for k in range(int(a), int(z)):
            target = wa + (wz - wa) * ((k - a) / max(1.0, z - a))
            p["planned"] += 1
            p["target"] += target
            if stop is not None and k >= stop:
                continue                                        # stopped the workout early: missed
            w = power.get(int(t0) + k)
            if w is None or w <= 0:
                continue
            p["ridden"] += 1
            p["watts"] += w
            if abs(w - target) <= max(TOLERANCE * target, MIN_W):
                p["on"] += 1
    out = []
    for key, p in parts.items():
        if not p["planned"]:
            continue
        sc = p["on"] / p["planned"]
        out.append({"key": key, "label": p["label"], "kind": p["kind"], "share": p["planned"] / total,
                    "minutes": round(p["planned"] / 60, 1), "score": round(sc, 3), "grade": grade(sc),
                    "completed": round(p["ridden"] / p["planned"], 3),
                    "avg_w": round(p["watts"] / p["ridden"]) if p["ridden"] else 0,
                    "target_w": round(p["target"] / p["planned"])})
    overall = sum(p["score"] * p["share"] for p in out)
    return {"workout": name, "start": start.isoformat(timespec="minutes"), "ftp": ftp, "minutes": round(total / 60, 1),
            "parts": out, "score": round(overall, 3), "grade": grade(overall)}


def for_ride(ride_csv, workouts_list=None):
    """Adherence for the workout(s) ridden in this ride file - the last one started, or None."""
    import coach
    import workouts as W
    events = _events(ride_csv)
    found = None
    for i, (t, e) in enumerate(events):
        m = re.match(r"Workout started: (.+?) \(at FTP (\d+) W\)", e)
        diag = e.startswith("Morning diagnostic started")
        if not (m or diag):
            continue
        end = next((t2 for t2, e2 in events[i + 1:] if e2.startswith(("ERG off", "Workout started", "Morning diagnostic started",
                                                                      "FTP test started", "Stopping"))), None)
        if diag:
            blocks = [{"type": "steady", "minutes": s["minutes"], "watts": s["watts"]} for s in coach.TEST_STEPS]
            found = (t, blocks, 180, coach.TEST_NAME, ["Settle 60 W", "Steady 90 W", "Push 120 W", "Recovery"], end)
            continue
        name, ftp = m.group(1), int(m.group(2))
        wl = workouts_list if workouts_list is not None else W.list_all(ftp)
        w = next((x for x in wl if x["name"] == name), None)
        if w:
            found = (t, w["blocks"], ftp, name, None, end)
    if not found:
        return None
    t, blocks, ftp, name, labels, end = found
    return score(ride_csv, t, blocks, ftp, name, labels, end)


# ── charts (SVG, for the ride report) ────────────────────────────────────────

ZONE = [(0.55, "#6b7280"), (0.75, "#3b82f6"), (0.90, "#22c55e"), (1.05, "#eab308"), (1.20, "#f97316"), (99, "#ef4444")]
GRADE_COL = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}


def _col(w, ftp):
    return next(c for lim, c in ZONE if w / ftp < lim)


def pie_svg(a, size=260):
    import math
    r, ri, out, a0 = 100, 50, [], -math.pi / 2
    for p in a["parts"]:
        a1 = a0 + p["share"] * 2 * math.pi
        big = 1 if p["share"] > 0.5 else 0
        P = lambda ang, rr: f"{math.cos(ang) * rr:.2f} {math.sin(ang) * rr:.2f}"
        out.append(f'<path d="M {P(a0, r)} A {r} {r} 0 {big} 1 {P(a1, r)} L {P(a1, ri)} A {ri} {ri} 0 {big} 0 {P(a0, ri)} Z" '
                   f'fill="{_col(p["target_w"], a["ftp"])}" stroke="#0b0f14" stroke-width="2.5"><title>{p["label"]}: '
                   f'{round(p["share"] * 100)}% of the workout</title></path>')
        if p["share"] >= 0.07:
            am = (a0 + a1) / 2
            out.append(f'<text x="{math.cos(am) * 75:.1f}" y="{math.sin(am) * 75 + 4:.1f}" text-anchor="middle" '
                       f'font-size="12" font-weight="800" fill="#fff">{round(p["share"] * 100)}%</text>')
        a0 = a1
    out.append(f'<text x="0" y="-2" text-anchor="middle" font-size="24" font-weight="900" fill="{GRADE_COL[a["grade"]]}">{a["grade"]}</text>'
               f'<text x="0" y="17" text-anchor="middle" font-size="11" fill="#8b98a8">{round(a["score"] * 100)}% on target</text>')
    return f'<svg viewBox="-110 -110 220 220" width="{size}" height="{size}">{"".join(out)}</svg>'


def radar_svg(a, size=340):
    """One spoke per part; a spoke's length is that part's share of the workout (the
    biggest part reaches the edge). The planned shape is the outline; the filled
    shape grows from the centre along each spoke to the part's score."""
    import math
    parts = a["parts"]
    n = len(parts)
    if n < 3:
        return ""
    R, big = 120, max(p["share"] for p in parts)
    ang = lambda i: -math.pi / 2 + i * 2 * math.pi / n
    L = [R * (0.35 + 0.65 * p["share"] / big) for p in parts]        # a small part still gets a visible spoke
    pt = lambda i, rr: (math.cos(ang(i)) * rr, math.sin(ang(i)) * rr)
    out = []
    for f in (0.25, 0.5, 0.75):                                       # rings at 25/50/75% of each spoke
        ring = " ".join(f"{pt(i, L[i] * f)[0]:.1f},{pt(i, L[i] * f)[1]:.1f}" for i in range(n))
        out.append(f'<polygon points="{ring}" fill="none" stroke="#1f2937" stroke-width="1"/>')
    for i in range(n):
        x, y = pt(i, L[i])
        out.append(f'<line x1="0" y1="0" x2="{x:.1f}" y2="{y:.1f}" stroke="#2a3441" stroke-width="1"/>')
    plan = " ".join(f"{pt(i, L[i])[0]:.1f},{pt(i, L[i])[1]:.1f}" for i in range(n))
    out.append(f'<polygon points="{plan}" fill="none" stroke="#60a5fa" stroke-width="2" stroke-dasharray="5 4"/>')
    done = " ".join(f"{pt(i, L[i] * p['score'])[0]:.1f},{pt(i, L[i] * p['score'])[1]:.1f}" for i, p in enumerate(parts))
    out.append(f'<polygon points="{done}" fill="rgba(34,197,94,.35)" stroke="#22c55e" stroke-width="2.5"/>')
    for i, p in enumerate(parts):
        x, y = pt(i, L[i] * p["score"])
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{GRADE_COL[p["grade"]]}"/>')
        lx, ly = pt(i, L[i] + 22)
        anchor = "middle" if abs(lx) < 20 else ("start" if lx > 0 else "end")
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="11" fill="#b7c1cd">{p["label"]}</text>'
                   f'<text x="{lx:.1f}" y="{ly + 14:.1f}" text-anchor="{anchor}" font-size="12" font-weight="800" '
                   f'fill="{GRADE_COL[p["grade"]]}">{p["grade"]} · {round(p["score"] * 100)}%</text>')
    return f'<svg viewBox="-190 -170 380 350" width="{size}" height="{size * 350 / 380:.0f}">{"".join(out)}</svg>'


def report_html(a):
    rows = "".join(
        f'<tr><td>{p["label"]}</td><td>{p["minutes"]} min ({round(p["share"] * 100)}%)</td><td>{p["target_w"]} W</td>'
        f'<td>{p["avg_w"]} W</td><td>{round(p["completed"] * 100)}%</td>'
        f'<td><b style="color:{GRADE_COL[p["grade"]]}">{p["grade"]}</b> · {round(p["score"] * 100)}%</td></tr>'
        for p in a["parts"])
    return (f'<h2>Workout: {a["workout"]} · <span style="color:{GRADE_COL[a["grade"]]}">{a["grade"]}</span></h2>'
            f'<p class="legend">Pie: the plan, part by part. Radar: each spoke is a part, as long as its share of the workout; '
            f'the dashed outline is the plan, the green shape is how much of each part you held on target '
            f'(within 10%). Seconds not ridden count as missed.</p>'
            f'<div style="display:flex;flex-wrap:wrap;gap:24px;align-items:center">{pie_svg(a)}{radar_svg(a)}</div>'
            f'<table><tr><th>Part</th><th>Planned</th><th>Target</th><th>You rode</th><th>Completed</th><th>Grade</th></tr>'
            f'{rows}</table>')
