"""course.py - a made-up course for a ride planned without a map route: the hills are the workout.

Asked for on 2026-09-29: a ride with a workout but no route gets its own experience - an 8-bit
side-scroller (web/course.html) instead of the map. The course is an ordinary route (routes.Route)
laid out in a straight line, so the bridge rides it exactly like a real one: the grade becomes the
hill, auto-shift and the day's focus keep cadence and watts in range. What's made up is the terrain:

  warm-up    flat, rising gently              (20% of the time)
  main set   steady climbs with short descents between them - the climbs are the steady blocks,
             the descents the spins           (60%)
  cool-down  easing back to flat and a little down (20%)

Grades stay gentle (the focus decides the watts; the terrain only leans on them), and each part is
long enough, at the focus's middle watts, to take its share of the minutes.

Gates ride along: a SPIN gate at the start of each descent (the top of the cadence range for 10 s)
and a PUSH gate in the middle of each climb (the top of the watt range for 10 s). They never ask for
more than the day's focus allows.
"""
import json
import math

import routes
import session

STEP_M = 20.0
FORM_MINUTES = 5          # minutes on the lit road (in both ranges) per form: bike -> unicorn -> gorilla -> panda -> dragon


def speed_at(watts, grade_pct, mass_kg):
    """The speed (m/s) that `watts` holds on `grade_pct` - the inverse of session.watts_for, by bisection."""
    lo, hi = 0.3, 25.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if session.watts_for(mid, grade_pct, mass_kg) > watts:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def layout(minutes, repeats=3):
    """The course's parts: (label, kind, minutes, grade at start, grade at end)."""
    warm, cool = minutes * 0.2, minutes * 0.2
    main = minutes - warm - cool
    rep = main / repeats
    parts = [("Warm-up", "warmup", warm, 0.0, 1.5)]
    for i in range(repeats):
        parts.append((f"Climb {i + 1}", "climb", rep * 2 / 3, 2.5, 2.5))
        parts.append((f"Spin {i + 1}", "spin", rep / 3, -1.0, -1.0))
    parts.append(("Cool-down", "cooldown", cool, 0.5, -1.0))
    return parts


def build(minutes, focus, mass_kg, name=None, repeats=3):
    """A Route for `minutes` at the focus's middle watts, plus what the course page needs (parts and gates)."""
    watts = sum(focus["watts"]) / 2 if focus.get("watts") else 110.0
    pts, meta_parts, gates = [], [], []
    d, e = 0.0, 100.0
    lat0, lon0 = 0.0, 0.0
    m_per_deg = 111320.0
    pts.append((lat0, lon0, e))
    for label, kind, mins, g0, g1 in layout(minutes, repeats):
        # distance for this part: its minutes at the mid watts on its average grade
        length = mins * 60 * speed_at(watts, (g0 + g1) / 2, mass_kg)
        start = d
        n = max(2, int(length / STEP_M))
        for k in range(1, n + 1):
            frac = k / n
            g = g0 + (g1 - g0) * frac
            step = length / n
            e += g / 100 * step
            d += step
            pts.append((lat0, lon0 + d / m_per_deg, e))
        meta_parts.append({"label": label, "kind": kind, "start_m": round(start), "end_m": round(d),
                           "minutes": round(mins, 1), "grade": [g0, g1]})
        if kind == "climb" and focus.get("watts"):
            gates.append({"kind": "push", "at_m": round(start + length / 2), "secs": 10,
                          "target": {"watts": focus["watts"][1] - 5}, "label": "Push gate"})
        if kind == "spin":
            gates.append({"kind": "spin", "at_m": round(start), "secs": 10,
                          "target": {"rpm": focus["rpm"][1] - 2}, "label": "Spin gate"})
    r = routes.Route(pts, name or f"Course {round(minutes)} min", source="course")
    return r, {"minutes": minutes, "focus": focus, "parts": meta_parts, "gates": gates,
               "form_minutes": FORM_MINUTES, "forms": ["bike", "unicorn", "gorilla", "panda", "dragon"]}


def save(route, meta, folder=None):
    """Saved like any route (so the bridge can ride it), with the course's parts and gates beside the points."""
    path = route.save(folder)
    d = json.loads(path.read_text())
    d["course"] = meta
    path.write_text(json.dumps(d))
    return path


def load(rid, folder=None):
    """A course, or any saved map route (its real hills become the terrain; no gates) - for the game view."""
    d = json.loads((routes.Path(folder or routes.ROUTES) / f"{rid}.json").read_text())
    meta = d.get("course") or {"minutes": None, "focus": None, "parts": [], "gates": [], "form_minutes": FORM_MINUTES,
                               "map_route": True}
    r = routes.Route(d["points"], d["name"], d["id"], d.get("source", ""), d.get("created"))
    return {"id": r.id, "name": r.name, "length_m": round(r.length), **meta,
            "profile": [[round(x), round(y, 1), g] for x, y, g in r.profile(step=STEP_M)]}
