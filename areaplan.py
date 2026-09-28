"""areaplan.py - routes inside an area you circle on the map, chosen for today's focus.

Asked for on 2026-09-28: a third way to plan next to A->B and by distance -
circle the area you'd like to ride in, and the coach finds a route there that
suits the intensity the day calls for.

How a route is judged (for the focus's watt and cadence ranges, see focus.py):

  TIME        how long it takes at the middle of the watt range, grade by grade,
              with the bridge's own virtual-speed physics - climbs are slow at
              easy watts, so a hilly 15 km can take as long as a flat 22 km.
  HOLDABLE    the share of the ride where auto-shift's easiest gear, at the bottom
              of the cadence range, still lets you stay at or under the top of the
              watt range. It's the bridge's own grade -> resistance mapping plus the
              watts the S29 makes at a level and cadence (fitted to real rides).
              With these gears most roads are holdable; walls aren't.
  TERRAIN     cadence, leg-speed and recovery days want it gentle (little climbing
              per km); grit days want time on steady climbs (3%+).

Routes are loops from the circle's centre through waypoints inside it (it's a
virtual ride, so a loop is just the tidiest shape), resized until the time fits,
and kept only if they stay inside the circle.
"""
import math
from pathlib import Path
import random

import planner
import routes

S29_W = (0.72, 0.17)           # watts = (a + b x level) x cadence - fitted to real S29 rides (tests/test_erg.py)


class Terrain:
    """The bridge's grade -> resistance level mapping and gear floor, as numbers (no bike needed)."""
    def __init__(self, res_range=(1, 16), base_level=None, per_percent=None, hill_shift_every=3.0, min_gear=-2,
                 mass_kg=126.6):
        lo, hi = res_range
        self.lo, self.hi = lo, hi
        self.flat = base_level if base_level is not None else lo + 0.25 * (hi - lo)
        self.per = per_percent if per_percent is not None else (hi - lo) / 20
        self.every, self.min_gear, self.mass = hill_shift_every, min_gear, mass_kg

    @classmethod
    def of(cls, bridge):
        a = bridge.args
        rr = bridge.res_range if tuple(bridge.res_range) != (1.0, 32.0) else (1, 16)   # not connected yet: the S29's
        return cls(rr, a.base_level, a.per_percent, a.hill_shift_every, a.min_gear, bridge.ride.mass)

    def level(self, grade, gear):
        shift = (-min(4.0, grade / self.every) if grade > 0 else min(2.0, -grade / 3)) if self.every else 0.0
        return min(self.hi, max(self.lo, self.flat + grade * self.per + shift + gear))

    def floor_watts(self, grade, rpm):
        """The fewest watts auto-shift leaves you at this grade and cadence (its easiest gear)."""
        return (S29_W[0] + S29_W[1] * self.level(grade, self.min_gear)) * rpm


def judge(route, focus, terrain, minutes):
    """Time, holdable share, terrain fit and a score (0-1) for one route under one focus."""
    from bridge import virtual_speed
    lo_w, hi_w = focus["watts"] or (None, None)
    mid = (lo_w + hi_w) / 2 if lo_w else 120.0
    prof = route.profile(100.0)
    secs = held = climb_secs = 0.0
    worst = None
    for (d0, e0, g), (d1, _, _) in zip(prof, prof[1:]):
        v = max(0.5, virtual_speed(mid, g, terrain.mass))
        t = (d1 - d0) / v
        secs += t
        if g >= 3:
            climb_secs += t
        if hi_w is None or terrain.floor_watts(g, focus["rpm"][0]) <= hi_w:
            held += t
        elif worst is None or g > worst[1]:
            worst = (round(d0 / 1000, 1), g)
    mins = secs / 60
    st = route.stats()
    per_km = st["climb_m"] / max(st["km"], 0.1)
    time_fit = max(0.0, 1 - abs(mins - minutes) / minutes * 2)          # 10% off = 0.8
    holdable = held / secs if secs else 1.0
    climb_share = climb_secs / secs if secs else 0.0
    if focus["key"] == "grit":
        terrain_fit = max(0.0, 1 - abs(climb_share - 0.45) / 0.45)        # plenty of steady climbing
    else:
        terrain_fit = 1 / (1 + per_km / 10)                                # gentle is better
    score = 0.4 * time_fit + 0.35 * holdable + 0.25 * terrain_fit
    why = [f"about {mins:.0f} min at ~{mid:.0f} W", f"{st['climb_m']} m up, steepest {st['max_grade']}%"]
    if hi_w is not None:
        why.append("holdable in range the whole way" if holdable > 0.995 else
                   f"{holdable * 100:.0f}% holdable - the easiest auto gear still goes over {hi_w} W on the "
                   f"{worst[1]:.0f}% at km {worst[0]} (shift by hand or ride it out)")
    if focus["key"] == "grit":
        why.append(f"{climb_share * 100:.0f}% of the time climbing 3%+")
    return {"minutes": round(mins), "holdable_pct": round(holdable * 100), "climb_pct": round(climb_share * 100),
            "time_fit": round(time_fit, 2), "terrain_fit": round(terrain_fit, 2), "score": round(score, 3),
            "why": why}


def inside(route, centre, radius_m, slack=1.15):
    """Share of the route's points within the circle (with a little slack for roads that bend out)."""
    pts = route.points
    return sum(1 for p in pts if planner._apart(p, centre) <= radius_m * slack) / max(len(pts), 1)


def area_loop(centre, radius_m, km, seed, profile=planner.PROFILE):
    """One loop of about km from the centre through 3-4 waypoints inside the circle, resized toward km."""
    rnd = random.Random(seed)
    n = rnd.choice((3, 4))
    start_angle = rnd.uniform(0, 360)
    angles = sorted((start_angle + i * 360 / n + rnd.uniform(-25, 25)) % 360 for i in range(n))
    fracs = [rnd.uniform(0.45, 0.9) for _ in range(n)]
    scale = min(1.0, km * 1000 / (2 * math.pi * radius_m * 0.7))       # a small ride in a big circle stays small
    best = None
    for _ in range(5):
        way = [planner._offset(centre, radius_m * f * scale, a) for f, a in zip(fracs, angles)]
        r = planner._request([centre] + way + [centre], 0, profile)
        if best is None or abs(r.length - km * 1000) < abs(best.length - km * 1000):
            best = r
        ratio = r.length / (km * 1000)
        if 0.9 <= ratio <= 1.1:
            break
        scale = min(1.0 / max(fracs), scale / ratio)                        # never past the circle's edge
        if scale >= 1.0 / max(fracs) and ratio < 1:
            break                                                           # the circle is too small for this ride
    return best


def plan_area(centre, radius_km, minutes, focus, terrain, count=4, tries=10):
    """Loops inside the circle, judged for the focus and the minutes; the best `count`, best first."""
    from bridge import virtual_speed
    from concurrent.futures import ThreadPoolExecutor
    radius_m = radius_km * 1000
    mid = sum(focus["watts"]) / 2 if focus["watts"] else 120.0
    km = max(3.0, virtual_speed(mid, 0, terrain.mass) * minutes * 60 / 1000 * 0.9)   # flat speed; climbs slow it
    seed = random.randrange(1_000_000)
    def attempt(i):
        """A loop, re-planned shorter or longer until its time (not its distance) fits - climbs are slow."""
        k, best = km, None
        for _ in range(3):
            try:
                r = area_loop(centre, radius_m, k, seed + i)
            except planner.PlannerError:
                break
            mins = judge(r, focus, terrain, minutes)["minutes"]
            if best is None or abs(mins - minutes) < abs(best[1] - minutes):
                best = (r, mins)
            if abs(mins - minutes) <= 0.1 * minutes:
                break
            k *= minutes / max(mins, 1)
        return best and best[0]
    with ThreadPoolExecutor(2) as pool:                                     # the route server runs two at a time
        cands = [r for r in pool.map(attempt, range(tries)) if r]
    cands = [r for r in cands if inside(r, centre, radius_m) >= 0.9]
    if not cands:
        raise planner.PlannerError("no roads make a loop inside that circle - try a bigger circle or a different spot")
    judged = []
    for r in cands:
        j = judge(r, focus, terrain, minutes)
        if all(planner._apart(r.points[len(r.points) // 3], o.points[len(o.points) // 3]) > 300 or
               abs(r.length - o.length) > 300 for o, _ in judged):         # drop near-duplicates
            judged.append((r, j))
    judged.sort(key=lambda x: -x[1]["score"])
    for r, j in judged:
        r.name = f"{j['minutes']} min · {r.length / 1000:.0f} km in the area"
    return judged[:count]


# ── the last area drawn, so the coach can plan in it from a chat ─────────────
def save_area(folder, centre, radius_km):
    import json
    f = Path(folder or routes.ROUTES) / "last_area.json"
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps({"center": list(centre), "radius_km": radius_km}))


def last_area(folder=None):
    import json
    f = Path(folder or routes.ROUTES) / "last_area.json"
    try:
        d = json.loads(f.read_text())
        return tuple(d["center"]), float(d["radius_km"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
