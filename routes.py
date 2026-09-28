"""routes.py - ride a real road: position, heading and grade from distance.

A route is a list of points (latitude, longitude, elevation in metres) along a
real road, planned on this Mac (planner.py) or imported from a GPX file. The
bridge supplies how far you've ridden (virtual distance from your watts); this
gives back where that is, which way the road points, and the grade there.

Grade comes from elevation over distance, smoothed over GRADE_WINDOW metres.
Elevation data is measured in ~30 m squares, so point-to-point it jumps;
ridden raw, every jump would be a resistance change. Real roads also rarely
exceed ~20%, so anything steeper is data noise and is capped.

Routes are stored as JSON in routes/ next to this file:
    {"id", "name", "created", "source", "points": [[lat, lon, ele], ...]}
"""
import bisect
import datetime as dt
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROUTES = Path(__file__).resolve().parent / "routes"
GRADE_WINDOW = 150.0     # metres either side: grade is the least-squares slope of the points in it
CLIMB_HYSTERESIS = 5.0   # metres of real rise before it counts as climbing (filters data wobble)
SMOOTH = 40.0            # metres: width of the elevation smoothing (Gaussian sigma)
MAX_GRADE = 20.0


def haversine(a, b):
    """Metres between two (lat, lon) points."""
    r = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing(a, b):
    """Compass heading in degrees from a to b."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


class Route:
    def __init__(self, points, name="Route", rid=None, source="", created=None):
        pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 and p[2] is not None else 0.0)
               for p in points]
        # Drop repeated points: they'd make zero-length segments.
        self.points = [pts[0]] + [p for q, p in zip(pts, pts[1:]) if haversine(q, p) > 0.5] if pts else []
        self.name, self.source = name, source
        self.created = created or dt.date.today().isoformat()
        self.id = rid or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] + "-" + dt.datetime.now().strftime("%Y%m%d%H%M%S")
        self.cum = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.cum.append(self.cum[-1] + haversine(a, b))
        self.ele_s = self._smooth()

    def _smooth(self):
        """Elevation smoothed along the road: each point becomes a distance-
        weighted average of its neighbours within 3 sigma. Two raw points 100 m
        apart with +/-2 m noise still misread a 5% climb as 7.7%."""
        out, n, j0 = [], len(self.points), 0
        for i in range(n):
            while self.cum[i] - self.cum[j0] > 3 * SMOOTH:
                j0 += 1
            num = den = 0.0
            j = j0
            while j < n and self.cum[j] - self.cum[i] <= 3 * SMOOTH:
                w = math.exp(-((self.cum[j] - self.cum[i]) / SMOOTH) ** 2 / 2)
                num += w * self.points[j][2]; den += w
                j += 1
            out.append(num / den)
        return out

    # ── lookups by distance ──────────────────────────────────────────────────
    @property
    def length(self):
        return self.cum[-1] if self.cum else 0.0

    def _seg(self, d):
        d = min(max(d, 0.0), self.length)
        i = max(0, min(bisect.bisect_right(self.cum, d) - 1, len(self.points) - 2))
        seg = self.cum[i + 1] - self.cum[i]
        f = 0.0 if seg <= 0 else (d - self.cum[i]) / seg
        return i, f

    def elevation_at(self, d):
        """Smoothed elevation at d (what grade and climbing are measured on)."""
        if len(self.points) < 2:
            return self.points[0][2] if self.points else 0.0
        i, f = self._seg(d)
        return self.ele_s[i] + f * (self.ele_s[i + 1] - self.ele_s[i])

    def position_at(self, d):
        """(lat, lon, heading) at d metres along the route."""
        if len(self.points) < 2:
            p = self.points[0] if self.points else (0, 0, 0)
            return p[0], p[1], 0.0
        i, f = self._seg(d)
        a, b = self.points[i], self.points[i + 1]
        return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]), bearing(a, b)

    def grade_at(self, d):
        """Grade in % at d: the least-squares slope of elevation against distance
        for the raw points within GRADE_WINDOW metres - the sound way to take a
        slope from noisy samples (two smoothed points still read 1.4% on a flat
        road). A new climb is felt fully over ~2 x GRADE_WINDOW, like a real one
        building under the wheels."""
        lo = bisect.bisect_left(self.cum, d - GRADE_WINDOW)
        hi = bisect.bisect_right(self.cum, d + GRADE_WINDOW)
        xs, ys = self.cum[lo:hi], [p[2] for p in self.points[lo:hi]]
        if len(xs) < 3 or xs[-1] - xs[0] < 20:
            if len(self.points) < 2:
                return 0.0
            i, _ = self._seg(d)                  # sparse points: the segment's own slope
            seg = self.cum[i + 1] - self.cum[i]
            g = 0.0 if seg <= 0 else (self.points[i + 1][2] - self.points[i][2]) / seg * 100
        else:
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            g = 0.0 if sxx == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx * 100
        return max(-MAX_GRADE, min(MAX_GRADE, g))

    # ── whole-route numbers, for choosing between routes ─────────────────────
    def profile(self, step=50.0):
        """(distance, elevation, grade) every `step` metres, for charts."""
        out, d = [], 0.0
        while d <= self.length:
            out.append((round(d), round(self.elevation_at(d), 1), round(self.grade_at(d), 1)))
            d += step
        return out

    def stats(self):
        prof = self.profile(25.0)
        # Count climbing only once the road has risen CLIMB_HYSTERESIS metres
        # from its last low (and descent likewise), as the planner does: on the
        # flat Tours-Amboise ride, adding every wobble gave 81 m vs its 11 m.
        climb = descent = 0.0
        ref = prof[0][1] if prof else 0.0
        for _, e, _ in prof:
            if e - ref >= CLIMB_HYSTERESIS:
                climb += e - ref; ref = e
            elif ref - e >= CLIMB_HYSTERESIS:
                descent += ref - e; ref = e
        grades = [p[2] for p in prof] or [0.0]
        steep = sum(1 for g in grades if g >= 5) * 25.0
        per_km = climb / max(self.length / 1000, 0.1)
        kind = "easy" if per_km < 8 and max(grades) < 5 else "hilly" if per_km >= 20 or max(grades) >= 8 else "mixed"
        return {"km": round(self.length / 1000, 1), "climb_m": round(climb), "descent_m": round(descent),
                "max_grade": round(max(grades), 1), "steep_km": round(steep / 1000, 1), "kind": kind}

    # ── storage ──────────────────────────────────────────────────────────────
    def to_json(self):
        return {"id": self.id, "name": self.name, "created": self.created, "source": self.source,
                "points": [[round(p[0], 6), round(p[1], 6), round(p[2], 1)] for p in self.points]}

    def save(self, folder=None):
        folder = Path(folder or ROUTES)
        folder.mkdir(exist_ok=True)
        path = folder / f"{self.id}.json"
        path.write_text(json.dumps(self.to_json()))
        return path


def load(rid, folder=None):
    d = json.loads((Path(folder or ROUTES) / f"{rid}.json").read_text())
    return Route(d["points"], d["name"], d["id"], d.get("source", ""), d.get("created"))


def list_routes(folder=None):
    out = []
    for p in sorted(Path(folder or ROUTES).glob("*.json"), key=lambda q: q.stat().st_mtime, reverse=True):
        try:
            r = load(p.stem, folder)
            out.append({"id": r.id, "name": r.name, "created": r.created, **r.stats()})
        except (OSError, ValueError, KeyError):
            pass
    return out


def from_gpx(text, name=None):
    """Import a GPX file (track or route points, with elevation if present)."""
    root = ET.fromstring(text)
    ns = {"g": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda tag: f".//g:{tag}") if ns else (lambda tag: f".//{tag}")
    pts = []
    for tag in ("trkpt", "rtept"):
        for p in root.findall(q(tag), ns):
            ele = p.find("g:ele", ns) if ns else p.find("ele")
            pts.append((float(p.get("lat")), float(p.get("lon")), float(ele.text) if ele is not None else 0.0))
        if pts:
            break
    title = root.find(q("name"), ns)
    return Route(pts, name or (title.text if title is not None and title.text else "Imported route"), source="gpx")


class RouteRide:
    """A route being ridden: distance in, everything the bridge and map need out."""

    def __init__(self, route, start_distance=0.0):
        self.route = route
        self.offset = start_distance     # the ride's virtual distance when the route started

    def along(self, vdistance):
        return max(0.0, vdistance - self.offset)

    def finished(self, vdistance):
        return self.along(vdistance) >= self.route.length

    def status(self, vdistance):
        d = self.along(vdistance)
        lat, lon, heading = self.route.position_at(d)
        return {"id": self.route.id, "name": self.route.name, "done_m": round(d), "total_m": round(self.route.length),
                "lat": round(lat, 6), "lon": round(lon, 6), "heading": round(heading, 1),
                "elevation": round(self.route.elevation_at(d), 1), "grade": round(self.route.grade_at(d), 1),
                "finished": self.finished(vdistance)}
