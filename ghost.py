"""ghost.py - race your last ride on the same route.

Kinomap doesn't tell the bridge which route is playing, but it sends the grade
at every point. So a route is recognised by its hill profile: the grade at
each point along the (virtual) distance. Once the ride in progress has covered
enough recognisable road, it is compared with every past ride; if one has the
same climbs at the same distances, that ride becomes the ghost.

The gap is time at the same point on the road: when you reach 1.2 km, how many
seconds earlier or later than the ghost did. Negative = ahead.

Flat stretches can't identify anything (every flat road looks alike), so the
ghost waits until the grade has varied before it locks on, and keeps checking
afterwards - if the profiles part ways, the ghost is dropped.
"""
import bisect
import csv
import datetime as dt
import math
import statistics
from pathlib import Path

STEP = 25            # metres between compared points
MIN_DIST = 300       # metres of riding before trying to recognise the route
MAX_DIFF = 0.6       # mean grade difference (percentage points) that still counts as "same road"
MIN_SPREAD = 0.5     # grade must vary at least this much (std, %) to identify anything


class Profile:
    """One ride as (distance m, elapsed s, grade %) points, distance increasing."""

    def __init__(self, name, points):
        self.name = name
        self.d = [p[0] for p in points]
        self.t = [p[1] for p in points]
        self.g = [p[2] for p in points]

    @property
    def length(self):
        return self.d[-1] if self.d else 0.0

    def grade_at(self, dist):
        i = bisect.bisect_right(self.d, dist) - 1
        return self.g[max(0, i)] if self.g else 0.0

    def time_at(self, dist):
        """Seconds this ride took to reach dist (interpolated), or None past its end."""
        if not self.d or dist > self.d[-1]:
            return None
        i = bisect.bisect_left(self.d, dist)
        if i == 0:
            return self.t[0]
        d0, d1, t0, t1 = self.d[i - 1], self.d[i], self.t[i - 1], self.t[i]
        return t0 if d1 == d0 else t0 + (t1 - t0) * (dist - d0) / (d1 - d0)


def load_ride(path, min_len=1000):
    """A past ride as a Profile, or None if it has no virtual distance/grade."""
    pts, start, last_d = [], None, -1.0
    try:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if "virtual_distance_m" not in r or not r.get("grade_pct"):
                    return None
                d = float(r["virtual_distance_m"] or 0)
                if d <= last_d:
                    continue
                t = dt.datetime.fromisoformat(r["time"])
                start = start or t
                pts.append((d, (t - start).total_seconds(), float(r["grade_pct"] or 0)))
                last_d = d
    except (OSError, ValueError, KeyError):
        return None
    if not pts or pts[-1][0] < min_len:
        return None
    prof = Profile(Path(path).stem, pts)
    prof.start = start                           # wall-clock start, for route ghosts
    return prof


def compare(a, b, upto):
    """Mean |grade difference| over 0..upto, and how much the grade varies there."""
    xs = range(0, int(upto), STEP)
    ga = [a.grade_at(x) for x in xs]
    gb = [b.grade_at(x) for x in xs]
    if len(ga) < 4:
        return None, 0.0
    return statistics.fmean(abs(x - y) for x, y in zip(ga, gb)), statistics.pstdev(ga)


class Ghost:
    def __init__(self, rides_dir, exclude=None):
        self.library = []
        for p in sorted(Path(rides_dir).glob("ride_*.csv"), key=lambda q: q.stat().st_mtime):
            if p.name.endswith("_events.csv") or (exclude and Path(p).resolve() == Path(exclude).resolve()):
                continue
            prof = load_ride(p)
            if prof:
                self.library.append(prof)       # oldest first; the latest match wins
        self.points = []                         # this ride: (distance, elapsed, grade)
        self.match = None
        self.checked_at = 0.0
        self.rides_dir, self.exclude = Path(rides_dir).resolve(), exclude
        self.route_id = None                     # set when riding one of our own routes

    def use_route(self, route_id):
        """Riding a planned route: no recognising needed - the ghost is the most
        recent past ride of this exact route, measured from its start line."""
        self.route_id, self.points, self.match = route_id, [], None
        tag = f"Route started: {route_id} at "
        for ev in sorted(self.rides_dir.glob("ride_*_events.csv"), key=lambda q: q.stat().st_mtime, reverse=True):
            ride = ev.with_name(ev.name[: -len("_events.csv")] + ".csv")
            if self.exclude and ride.resolve() == Path(self.exclude).resolve():
                continue
            try:
                with open(ev, newline="") as f:
                    rows = list(csv.DictReader(f))
            except OSError:
                continue
            starts = []
            for row in rows:
                event = row.get("event") or ""
                if not event.startswith(tag):
                    continue
                try:
                    offset = float(event[len(tag):].split(" m")[0])
                    t0 = dt.datetime.fromisoformat(row["time"])
                except (ValueError, TypeError, KeyError):
                    continue
                if math.isfinite(offset):
                    starts.append((offset, t0))
            if not starts:
                continue
            offset, t0 = starts[-1]
            prof = load_ride(ride, min_len=0)
            if not prof:
                continue
            pts = [(d - offset, t - (t0 - prof.start).total_seconds(), g)
                   for d, t, g in zip(prof.d, prof.t, prof.g) if d >= offset]
            if len(pts) > 10:
                self.match = Profile(ride.stem, pts)
                return

    def add(self, dist, elapsed, grade):
        if not self.points or dist > self.points[-1][0]:
            self.points.append((dist, elapsed, grade))
        if self.route_id:
            return                               # route ghost: already known, nothing to recognise
        if dist - self.checked_at >= 100:        # re-check every 100 m
            self.checked_at = dist
            self._recognise(dist)

    def _recognise(self, dist):
        if dist < MIN_DIST or not self.library:
            return
        me = Profile("now", self.points)
        best = None
        for past in self.library:
            if past.length < dist:
                continue
            diff, spread = compare(me, past, dist)
            if diff is None or spread < MIN_SPREAD:
                return                           # too flat so far to tell routes apart
            if diff <= MAX_DIFF:
                best = past                      # keep going: the most recent match wins
        self.match = best

    def gap(self):
        """(seconds, metres) versus the ghost; negative seconds = ahead. None if no ghost."""
        if not self.match or not self.points:
            return None
        d, t, _ = self.points[-1]
        ghost_t = self.match.time_at(d)
        if ghost_t is None:
            return None                          # past the end of the ghost's ride
        # Metres: where the ghost was at our current time.
        i = bisect.bisect_right(self.match.t, t) - 1
        ghost_d = self.match.d[max(0, min(i, len(self.match.d) - 1))]
        return round(t - ghost_t), round(d - ghost_d)

    def status(self):
        g = self.gap()
        if not self.match:
            return None
        return {"vs": self.match.name, "seconds": g[0] if g else None, "metres": g[1] if g else None}
