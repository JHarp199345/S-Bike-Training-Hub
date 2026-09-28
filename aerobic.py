"""aerobic.py - how the engine is doing, ride by ride, from power and heart rate together.

The watch records the ride with the bridge as its power meter, so its file has both
(GoldenCheetah's AerobicDecoupling and Efficiency Factor, done the same way):

  EF             efficiency factor: normalized power / average heart rate - watts per
                 beat. It rises as the aerobic engine improves.
  DECOUPLING     watts per beat in the first half vs the second (after a 5-min settle):
                 under 5% the ride stayed aerobic; over 5% it drifted above the aerobic
                 threshold (heart rate climbing for the same watts). Judged only on a ride
                 of 40+ minutes that was steady (normalized / average power under 1.10):
                 hills and short rides make the halves unequal and inflate it.
  HR AT 110 W    average heart rate over the steady stretches at 100-120 W (30-s power
                 inside the band) - the same watts every ride, so a falling number is a
                 fitter heart. The roadmap's "heart rate at the same watts".

These are daily signals of the engine for the cross-sport fitting to learn from.
"""
import datetime as dt
import statistics

SETTLE_S = 300          # heart rate lags the first minutes: left out of the halves
BAND = (100, 120)       # the fixed watts for "heart rate at the same watts"
DECOUPLED = 5.0         # % - the usual line for "this ride went above the aerobic threshold"
JUDGE_MIN = 40          # decoupling only means something on a long ride...
STEADY_VI = 1.10        # ...that's steady: normalized / average power under 1.10 (hills and surges inflate it)


def _np(watts):
    """Normalized power: the 4th-power mean of the 30-s rolling average."""
    if len(watts) < 30:
        return None
    roll, s = [], sum(watts[:30])
    for i in range(30, len(watts) + 1):
        roll.append(s / 30)
        if i < len(watts):
            s += watts[i] - watts[i - 30]
    return (sum(x ** 4 for x in roll) / len(roll)) ** 0.25


def ride(a):
    """One ride (loads.gather activity with records): EF, decoupling, HR at 110 W. None if it lacks both."""
    recs = [r for r in a["records"] if r.get("hr") and r.get("w") is not None]
    if len(recs) < 600:                                   # ten minutes of power with heart rate
        return None
    w = [r["w"] for r in recs]
    hr = [r["hr"] for r in recs]
    np_ = _np(w)
    ef = np_ / statistics.fmean(hr) if np_ else None
    body = recs[SETTLE_S:] if len(recs) > SETTLE_S + 600 else recs
    half = len(body) // 2
    ratio = lambda part: statistics.fmean(r["w"] for r in part) / statistics.fmean(r["hr"] for r in part)
    first, second = ratio(body[:half]), ratio(body[half:])
    dec = 100 * (first - second) / first if first else None
    avg_w = statistics.fmean(w)
    vi = np_ / avg_w if (np_ and avg_w) else None
    judged = len(recs) >= JUDGE_MIN * 60 and vi is not None and vi <= STEADY_VI
    # heart rate where the 30-s power sat in the band (after settling)
    steady, s30 = [], []
    for i, r in enumerate(recs):
        s30.append(r["w"])
        if len(s30) > 30:
            s30.pop(0)
        if i >= SETTLE_S and len(s30) == 30 and BAND[0] <= statistics.fmean(s30) <= BAND[1]:
            steady.append(r["hr"])
    return {"id": a["id"], "date": dt.date.fromtimestamp(a["start"]).isoformat(), "minutes": round(len(recs) / 60),
            "np": round(np_) if np_ else None, "avg_hr": round(statistics.fmean(hr)),
            "ef": round(ef, 2) if ef else None, "decoupling_pct": round(dec, 1) if dec is not None else None,
            "vi": round(vi, 2) if vi else None, "judged": judged,
            "aerobic": (dec < DECOUPLED) if (judged and dec is not None) else None,
            "hr_at_band": round(statistics.fmean(steady)) if len(steady) >= 120 else None,
            "band_minutes": round(len(steady) / 60, 1)}


def summary(acts, days=90, today=None):
    """Every bike ride with power and heart rate in the last `days`, and the trend of each number."""
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=days)).isoformat()
    rides = [x for x in (ride(a) for a in acts if a["sport"] == "bike") if x and x["date"] >= since]
    rides.sort(key=lambda x: x["date"])

    def trend(key):
        pts = [(dt.date.fromisoformat(r["date"]).toordinal(), r[key]) for r in rides if r[key] is not None]
        if len(pts) < 3:
            return None
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
        return {"per_week": round(slope * 7, 3), "latest": ys[-1], "first": ys[0], "rides": len(pts)}
    return {"band": list(BAND), "rides": rides, "trend": {"ef": trend("ef"), "hr_at_band": trend("hr_at_band"),
                                                          "decoupling_pct": trend("decoupling_pct")}}
