"""planner.py - plan bike routes on this Mac with BRouter.

BRouter runs locally (java) on the road and elevation data downloaded to
maps/ (made by setup.sh), so planning needs no internet and sends nothing anywhere.
It is started on first use and left running.

    plan(start, end)          A -> B: the main route plus up to 3 alternatives
    loops(start, km)          round trips of about km, a different shape each time

Each result is a routes.Route with stats (km, climb, max grade, easy/mixed/hilly),
so the panel can offer "easy day" or "hilly day" choices.
"""
import json
import math
import random
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import routes

MAPS = Path(__import__("os").environ.get("S_BIKE_MAPS") or Path(__file__).resolve().parent / "maps")
BROUTER = MAPS / "tools" / "brouter" / "brouter-1.7.10"
PORT = 17777
PROFILE = "fastbike"            # road bike, avoids unpaved; "trekking" is gentler, "fastbike-lowtraffic" quieter


class PlannerError(Exception):
    pass


def _up():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def ensure_server():
    """Start BRouter if it isn't running (localhost only)."""
    if _up():
        return
    (MAPS / "brouter" / "customprofiles").mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        ["java", "-Xmx768M", "-cp", str(BROUTER / "brouter-1.7.10-all.jar"), "btools.server.RouteServer",
         str(MAPS / "brouter" / "segments4"), str(BROUTER / "profiles2"), str(MAPS / "brouter" / "customprofiles"),
         str(PORT), "2", "127.0.0.1"],
        stdout=open(MAPS / "brouter.log", "a"), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(40):
        if _up():
            return
        time.sleep(0.25)
    raise PlannerError("the route planner didn't start (see maps/brouter.log)")


def _request(points, alt=0, profile=PROFILE, timeout=90):
    """points: [(lat, lon), ...] -> routes.Route, or PlannerError."""
    ensure_server()
    lonlats = "|".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    url = (f"http://127.0.0.1:{PORT}/brouter?lonlats={urllib.parse.quote(lonlats, safe='|,')}"
           f"&profile={profile}&alternativeidx={alt}&format=geojson")
    try:
        raw = urllib.request.urlopen(url, timeout=timeout).read()
    except Exception as e:
        body = getattr(e, "read", lambda: b"")().decode(errors="replace")[:200]
        raise PlannerError(body or str(e))
    try:
        f = json.loads(raw)["features"][0]
    except (ValueError, KeyError, IndexError):
        raise PlannerError(raw.decode(errors="replace")[:200])
    coords = f["geometry"]["coordinates"]
    return routes.Route([(c[1], c[0], c[2] if len(c) > 2 else 0.0) for c in coords], "route", source="planner")


BACKUP_PROFILE = "trekking"     # takes big coast roads (PCH) that fastbike detours 40 km around
DETOUR = 0.75                   # ...but it also takes gravel, so it's only offered when it's this much shorter


def plan(start, end, alternatives=3, profile=PROFILE):
    """The main route and up to `alternatives` different ones, duplicates dropped.
    Fastbike sometimes refuses a major road and detours for miles (Santa Monica
    to Malibu: 61 km instead of 19 along the PCH); when the trekking profile's
    route is much shorter it goes first. It isn't offered otherwise, because
    trekking happily uses forest tracks."""
    out = []
    def keep(r):
        if all(abs(r.length - o.length) > 50 or r.stats()["climb_m"] != o.stats()["climb_m"] for o in out):
            out.append(r)
    for alt in range(alternatives + 1):
        try:
            keep(_request([start, end], alt, profile))
        except PlannerError:
            if alt == 0 and profile == PROFILE:
                break                              # the backup may still find a way
            if alt == 0:
                raise
            break                                  # no more alternatives exist
    if profile != BACKUP_PROFILE:
        try:
            b = _request([start, end], 0, BACKUP_PROFILE)
            if not out or b.length < DETOUR * out[0].length:
                out.insert(0, b)
        except PlannerError:
            if not out:
                raise
    if not out:
        raise PlannerError("no road connects those two points")
    for i, r in enumerate(out, 1):
        r.name = f"Route {i}"
    return out[:alternatives + 1]


def _offset(start, metres, bearing_deg):
    lat, lon = start
    b = math.radians(bearing_deg)
    dlat = metres * math.cos(b) / 111_195
    dlon = metres * math.sin(b) / (111_195 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def loop(start, km, seed=None, profile=PROFILE):
    """One round trip of about km. Three waypoints on a circle at a random
    starting angle, routed on real roads; the circle is resized until the
    route's length is within 8% of km (roads are longer than circles)."""
    rnd = random.Random(seed)
    angle = rnd.uniform(0, 360)
    clockwise = rnd.choice((1, -1))
    radius = km * 1000 / (2 * math.pi) * 0.8
    best = None
    for _ in range(6):
        # Centre of the circle sits `radius` away from the start, so the loop passes through it.
        centre = _offset(start, radius, angle)
        pts = [start] + [_offset(centre, radius, angle + 180 + clockwise * a) for a in (90, 180, 270)] + [start]
        r = _request(pts, 0, profile)
        if best is None or abs(r.length - km * 1000) < abs(best.length - km * 1000):
            best = r
        ratio = r.length / (km * 1000)
        if 0.92 <= ratio <= 1.08:
            break
        radius /= ratio
    best.name = f"{best.length / 1000:.0f} km loop"
    return best


def loops(start, km, count=4, want=None, profile=PROFILE):
    """`count` loops. want="easy" keeps the flattest of a dozen candidates,
    want="hilly" the hilliest (random directions from a valley start were all valley-
    floor easy; the hills have to be sought out); otherwise a varied mix."""
    tries = count * 2 if want is None else count * 3
    cands, seed = [], random.randrange(1_000_000)
    for i in range(tries):
        try:
            cands.append(loop(start, km, seed + i, profile))
        except PlannerError:
            continue
    # closest to the asked-for distance first; a loop more than 15% off only if nothing better
    off = lambda r: abs(r.length / (km * 1000) - 1)
    cands = [r for r in cands if off(r) <= 0.15] or sorted(cands, key=off)
    if want is None:
        cands.sort(key=off)
    if want in ("easy", "hilly"):
        per_km = lambda r: r.stats()["climb_m"] / max(r.length / 1000, 0.1)
        cands.sort(key=per_km, reverse=(want == "hilly"))
    return cands[:count]


COMPASS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


def one_way(start, km, bearing, profile=PROFILE):
    """A ride of about km that heads off toward `bearing` and ends wherever the
    distance runs out - it's a virtual ride, so there's no need to come back.
    The finish is pulled in or pushed out until the road distance is within 8%."""
    radius = km * 1000 * 0.75                     # roads wander: straight line is ~3/4 of the ride
    best = None
    for _ in range(5):
        end = _offset(start, radius, bearing)
        r = _request([start, end], 0, profile)
        if best is None or abs(r.length - km * 1000) < abs(best.length - km * 1000):
            best = r
        ratio = r.length / (km * 1000)
        if 0.92 <= ratio <= 1.08:
            break
        radius /= ratio
    best.bearing = bearing
    return best


def _name_ride(r, km):
    try:
        import places
        n = places.nearest(r.points[-1][0], r.points[-1][1], max_km=15)
    except Exception:
        n = None
    toward = COMPASS[round(getattr(r, "bearing", 0) / 45) % 8]
    r.name = f"{r.length / 1000:.0f} km to {n['name']}" if n else f"{r.length / 1000:.0f} km {toward}"


def outs(start, km, count=4, want=None, profile=PROFILE):
    """`count` one-way rides of about km from start, in different directions.
    want="easy" keeps the flattest, "hilly" the hilliest, of rides tried in
    ten directions; otherwise the ones closest to the distance, spread around."""
    from concurrent.futures import ThreadPoolExecutor
    n = 10 if want else 8
    turn = random.uniform(0, 360 / n)
    bearings = [(turn + i * 360 / n) % 360 for i in range(n)]
    def attempt(b):
        try:
            return one_way(start, km, b, profile)
        except PlannerError:
            return None
    with ThreadPoolExecutor(2) as pool:           # the local route server runs two at a time
        cands = [r for r in pool.map(attempt, bearings) if r]
    if not cands:
        raise PlannerError("no roads lead out from there")
    off = lambda r: abs(r.length / (km * 1000) - 1)
    cands = [r for r in cands if off(r) <= 0.15] or sorted(cands, key=off)
    # two directions that ended up on the same road to the same place count once
    kept = []
    for r in sorted(cands, key=off):
        if all(_apart(r.points[-1], o.points[-1]) > 1500 for o in kept):
            kept.append(r)
    per_km = lambda r: r.stats()["climb_m"] / max(r.length / 1000, 0.1)
    if want in ("easy", "hilly"):
        kept.sort(key=per_km, reverse=(want == "hilly"))
    else:                                          # a mix: flattest and hilliest first, then the rest
        by = sorted(kept, key=per_km)
        kept = [by[0], by[-1]] + by[1:-1] if len(by) > 2 else by
    out = kept[:count]
    for r in out:
        _name_ride(r, km)
    return out


def _apart(a, b):
    dy = (a[0] - b[0]) * 111_195
    dx = (a[1] - b[1]) * 111_195 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)
