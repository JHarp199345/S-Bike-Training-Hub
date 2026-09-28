"""cp.py - critical power, W', and how much of W' is left right now.

CP is the power you can keep up for a long time; W' ("W prime") is a fixed store of
work you can spend above it - kilojoules, not days. Every second above CP draws it
down; every second below refills it, faster the further below you are. Empty means
you have to back off. So W' answers "can I do that effort?" and "how many more?".

  THE CURVE    your best average power for 1 min ... 40 min, from every ride in the last
               90 days (the bridge's own files - bests.ride_seconds).
  THE FIT      the 2-parameter model: work = CP x time + W', fitted to the 3-20 min bests
               (GoldenCheetah's estimator uses 4-60 min weekly bests the same way).
               Easy rides don't show your limits (they make a tidy curve well under them),
               so a fit is only trusted when CP reaches 85-130% of FTP and W' is 3-40 kJ;
               until then CP = FTP and W' = 12 kJ, a typical figure, with the fit shown as
               a floor - a hard effort or a test replaces them.
  W' BALANCE   live, the differential model (Froncioni/Clarke; Skiba 2015):
               above CP  W'bal -= (P - CP) each second
               below CP  W'bal += (CP - P) x (W' - W'bal) / W'
               A "match" is a bout above CP that spent more than 2 kJ.
"""
import datetime as dt
from pathlib import Path

DURATIONS = [60, 120, 180, 300, 480, 600, 720, 900, 1200, 1800, 2400]
FIT_RANGE = (180, 1200)
W_PRIOR = 12000.0          # J - a typical W' until your own efforts show it
MATCH_J = 2000.0


def best_curve(rides_dir, days=90, today=None):
    """{seconds: (watts, ride)} - the best average for each duration over the last `days`."""
    import bests
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=days)).isoformat()
    curve = {}
    for p in sorted(Path(rides_dir).glob("ride_*.csv")):
        if p.stem.count("_") != 2 or p.stem[5:15] < since:
            continue
        try:
            secs = bests.ride_seconds(p)
        except (OSError, ValueError, KeyError):
            continue
        runs, cur = [], []
        for x in secs:                               # a None is a break: no best averages across one
            if x is None:
                if cur:
                    runs.append(cur); cur = []
            else:
                cur.append(x[1])
        if cur:
            runs.append(cur)
        for w in runs:
            for d in DURATIONS:
                if len(w) < d:
                    continue
                s = sum(w[:d]); best = s
                for i in range(d, len(w)):
                    s += w[i] - w[i - d]
                    best = max(best, s)
                avg = best / d
                if d not in curve or avg > curve[d][0]:
                    curve[d] = (round(avg, 1), p.stem)
    return dict(sorted(curve.items()))


def fit(curve):
    """work = CP x t + W' by least squares over the 3-20 min bests. None with fewer than 3 points."""
    pts = [(t, w * t) for t, (w, _) in curve.items() if FIT_RANGE[0] <= t <= FIT_RANGE[1]]
    if len(pts) < 3:
        return None
    n = len(pts)
    mt, mw = sum(t for t, _ in pts) / n, sum(w for _, w in pts) / n
    sxx = sum((t - mt) ** 2 for t, _ in pts)
    cp_ = sum((t - mt) * (w - mw) for t, w in pts) / sxx
    wp = mw - cp_ * mt
    ss_tot = sum((w - mw) ** 2 for _, w in pts) or 1
    r2 = 1 - sum((w - (cp_ * t + wp)) ** 2 for t, w in pts) / ss_tot
    return {"cp": cp_, "w_prime": wp, "r2": r2, "points": n}


def estimate(curve, ftp):
    """CP and W' to use: the fit when it's plausible, otherwise FTP and a typical W' - with the fit as a floor.
    Easy rides make a tidy curve that sits well under your limits (a 0.99 fit of rides that were never hard), so
    the fit is only trusted when its CP reaches 85% of FTP: then the efforts were real ones."""
    f = fit(curve)
    if f and 0.85 * ftp <= f["cp"] <= 1.3 * ftp and 3000 <= f["w_prime"] <= 40000:
        return {"cp": round(f["cp"]), "w_prime": round(f["w_prime"]), "source": "your best efforts", "fit": f, "floor": None}
    floor = {"cp": round(f["cp"]), "w_prime": round(f["w_prime"])} if f and f["cp"] > 0 and f["w_prime"] > 0 else None
    why = (f"your rides show at least CP {floor['cp']} W - they were easy, so the real number is higher" if floor
           else "not enough hard efforts yet")
    return {"cp": round(ftp), "w_prime": W_PRIOR, "source": f"FTP and a typical W' ({why})", "fit": f, "floor": floor}


class WBal:
    """W' balance, second by second (the differential model)."""
    def __init__(self, cp, w_prime):
        self.cp, self.w = float(cp), float(w_prime)
        self.bal, self.low, self.matches = self.w, self.w, 0
        self._bout = 0.0                      # W' spent in the current bout above CP

    def add(self, power):
        p = float(power or 0)
        if p > self.cp:
            spend = p - self.cp
            self.bal -= spend
            self._bout += spend
        else:
            if self._bout > MATCH_J:
                self.matches += 1
            self._bout = 0.0
            self.bal += (self.cp - p) * (self.w - self.bal) / self.w
        self.bal = max(-self.w, min(self.w, self.bal))
        self.low = min(self.low, self.bal)

    def status(self):
        return {"cp": round(self.cp), "w_prime_kj": round(self.w / 1000, 1), "bal_kj": round(self.bal / 1000, 1),
                "pct": round(100 * self.bal / self.w), "low_pct": round(100 * self.low / self.w), "matches": self.matches}


def feasible(watts, seconds, cp, w_prime):
    """Can `watts` be held for `seconds`? Below CP: yes (for up to about an hour); above: only while W' lasts."""
    if watts <= cp:
        return {"ok": True, "needs_kj": 0.0, "note": f"{watts:.0f} W is under your CP ({cp:.0f} W) - sustainable"}
    needs = (watts - cp) * seconds
    lasts = w_prime / (watts - cp)
    ok = needs <= 0.9 * w_prime
    return {"ok": ok, "needs_kj": round(needs / 1000, 1), "lasts_s": round(lasts),
            "note": (f"{watts:.0f} W for {seconds / 60:.1f} min spends {needs / 1000:.1f} of your {w_prime / 1000:.0f} kJ W'"
                     + ("" if ok else f" - too much: {watts:.0f} W lasts about {lasts / 60:.1f} min"))}


def fastest_climb(length_m, grade_pct, mass_kg, cp, w_prime, from_s=60):
    """The quickest time up a climb you could hold: the time whose watts spend ~90% of W' (or CP, if that's longer)."""
    import session
    best = None
    t = max(from_s, 30)
    while t <= 7200:
        w = session.watts_for(length_m / t, grade_pct, mass_kg)
        if w <= cp or (w - cp) * t <= 0.9 * w_prime:
            best = t
            break
        t += 5
    return best


def swim_d_prime(t400, t200):
    """D' for swimming (metres you can swim beyond CSS pace) from the same 400/200 test: D' = 400 - CS x t400."""
    t400, t200 = float(t400), float(t200)
    cs = 200 / (t400 - t200)
    return round(400 - cs * t400, 1)
