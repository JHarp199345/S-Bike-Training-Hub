"""live.py - the last ten minutes of the ride, second by second, and calories.

The bike reports a few times a second, unevenly. This keeps one point per
second (watts, cadence, speed, grade, gear) for the live graph, and adds up
the work done: joules = watts x seconds.

Calories come from that work. Pedalling turns about 24% of the food energy
burned into work at the pedals (gross efficiency; 20-25% for most riders), so
    kcal = kJ / 4.184 / 0.24  (~ 1 kcal per kJ)
It uses measured watts - not heart rate, weight or guesses - so it is about
as good as a calorie number gets, and a lot better than most watch estimates.
"""
import collections
import csv
import datetime as dt

WINDOW = 600            # seconds of history kept (the graph shows ten minutes)
EFFICIENCY = 0.24
MAX_GAP = 5.0           # a longer silence (bike asleep) adds no work


def kcal_from_kj(kj):
    return kj / 4.184 / EFFICIENCY


class Live:
    def __init__(self):
        self.points = collections.deque(maxlen=WINDOW)   # (epoch s, watts, rpm, km/h, grade %, gear)
        self.kj = 0.0
        self.moving_s = 0                                # seconds with the pedals turning (watts > 0)
        self._last_t = None
        self._last_w = 0.0

    def add(self, t, watts, rpm, kmh, grade, gear):
        """One reading from the bike, at wall-clock time t (epoch seconds)."""
        if self._last_t is not None:
            gap = t - self._last_t
            if 0 < gap <= MAX_GAP:
                self.kj += (self._last_w + watts) / 2 * gap / 1000     # trapezoid between readings
        self._last_t, self._last_w = t, watts
        sec = int(t)
        p = (sec, round(watts), round(rpm), round(kmh, 1), round(grade, 1), gear)
        if self.points and self.points[-1][0] == sec:
            self.points[-1] = p                                        # latest reading of this second
        elif not self.points or sec > self.points[-1][0]:
            self.points.append(p)
            if watts > 0:
                self.moving_s += 1

    @property
    def kcal(self):
        return kcal_from_kj(self.kj)

    def kcal_per_min(self, now):
        """From the last minute's average watts (seconds without a reading count as zero)."""
        recent = [p[1] for p in self.points if now - p[0] <= 60]
        if not recent:
            return 0.0
        watts = sum(recent) / 60 if len(recent) < 60 else sum(recent) / len(recent)
        return kcal_from_kj(watts * 60 / 1000)

    def since(self, t):
        return [list(p) for p in self.points if p[0] > t]

    def status(self, now):
        return {"kj": round(self.kj, 1), "kcal": round(self.kcal), "kcal_min": round(self.kcal_per_min(now), 1)}

    def load_ride(self, csv_path):
        """After a restart mid-ride: the work so far and the last ten minutes, from the ride file."""
        try:
            with open(csv_path, newline="") as f:
                for r in csv.DictReader(f):
                    try:
                        t = dt.datetime.fromisoformat(r["time"]).timestamp()
                        self.add(t, float(r["power_w"] or 0), float(r["cadence_rpm"] or 0),
                                 float(r.get("virtual_speed_kmh") or r.get("bike_speed_kmh") or 0),
                                 float(r.get("grade_pct") or 0), int(float(r.get("gear") or 0)))
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError:
            pass
        self._last_t = None                                            # the gap while down adds nothing
