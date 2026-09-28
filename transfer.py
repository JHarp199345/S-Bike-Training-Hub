"""transfer.py - how much each sport carries over to the others, learned from this rider.

The rider's idea (2026-09-28): the sports are a semi-shared resource - running costs the
others most, cycling next, swimming least - and the ratios should be learned from the
tests, the performances and the reports. The literature gives the starting point:

  Millet et al. 2002 (elite triathletes, a Banister model per sport): cycling training
  carried over to running performance; nothing carried over into swimming.
  Tanaka 1994 (review): running carries to cycling better than cycling to running;
  swimming carries least.  A 2026 meta-analysis: replacing 20-50% of running with cycling
  (often 2 min of bike per min of run) didn't cost VO2max or 1-mile-5K times.
  Bone and tendon: cycling and swimming don't load them - only running builds them.

THE MODEL (a Banister model per sport, with carry-over, fitted the Bayesian way):
  For each sport s with a performance marker y_s (its efficiency: bike watts per beat,
  swim metres per minute per beat, run metres per minute per beat):
      y_s(t) = p0 + sum_u a_u * fitness_u(t) - sum_u b_u * fatigue_u(t)
  fitness_u is the 42-day average of sport u's load, fatigue_u the 7-day average. The
  carry-over u -> s is a_u / a_s: how much a unit of u training builds s, next to s
  training itself. The priors are the literature values above; every measurement updates
  them (Bayesian linear regression - the same answer a Kalman filter reaches one
  measurement at a time; Kolossa 2017, Swartz et al. 2023), and each ratio carries an
  80% interval. With little data the answer IS the prior, and says so.

  LEGS: the next morning's legs check-in against the day before's load in each sport -
  how much each sport tires the legs, relative to running.

It needs weeks where the mix changes (a swim-heavy week after a bike-heavy one) to tell
the sports apart; test weeks anchor it.
"""
import datetime as dt
import math
import random
import statistics

SPORTS = ("swim", "bike", "run")
PRIOR = {                     # PRIOR[from][to]: carry-over of fitness, relative to training `to` itself
    "swim": {"swim": 1.0, "bike": 0.2, "run": 0.2},
    "bike": {"swim": 0.1, "bike": 1.0, "run": 0.5},
    "run": {"swim": 0.1, "bike": 0.6, "run": 1.0},
}
PRIOR_LEGS = {"run": 1.0, "bike": 0.6, "swim": 0.1}   # how much each tires the legs, relative to running
A0, B0 = 0.5, 0.3             # prior size of the own-sport fitness and fatigue effects (standardised units)


# ── small linear algebra (the matrices are 7 x 7 at most) ────────────────────
def _inv(m):
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        piv = a[c][c]
        if abs(piv) < 1e-12:
            raise ValueError("singular")
        a[c] = [x / piv for x in a[c]]
        for r in range(n):
            if r != c and a[r][c]:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [row[n:] for row in a]


def _chol(m):
    n = len(m)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = m[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            L[i][j] = math.sqrt(max(s, 1e-12)) if i == j else s / L[j][j]
    return L


def bayes_regression(X, y, prior_mean, prior_sd, noise_sd=1.0):
    """Posterior mean and covariance of w in y = X w + e, w ~ N(prior_mean, diag(prior_sd^2))."""
    k = len(prior_mean)
    P = [[(1 / prior_sd[i] ** 2 if i == j else 0.0) for j in range(k)] for i in range(k)]
    s2 = noise_sd ** 2
    A = [[P[i][j] + sum(x[i] * x[j] for x in X) / s2 for j in range(k)] for i in range(k)]
    b = [P[i][i] * prior_mean[i] + sum(x[i] * yy for x, yy in zip(X, y)) / s2 for i in range(k)]
    cov = _inv(A)
    mean = [sum(cov[i][j] * b[j] for j in range(k)) for i in range(k)]
    return mean, cov


def _ratio(mean, cov, i, j, n=3000, seed=7):
    """Median and 80% interval of w_i / w_j by sampling the posterior."""
    L = _chol(cov)
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        z = [rnd.gauss(0, 1) for _ in mean]
        w = [mean[r] + sum(L[r][c] * z[c] for c in range(len(mean))) for r in range(len(mean))]
        if w[j] > 1e-3:
            out.append(w[i] / w[j])
    if len(out) < n * 0.5:
        return None
    out.sort()
    q = lambda p: out[min(len(out) - 1, int(p * len(out)))]
    return {"ratio": round(max(0.0, q(0.5)), 2), "lo": round(max(0.0, q(0.1)), 2), "hi": round(max(0.0, q(0.9)), 2)}   # no negative carry-over


# ── the data: loads per sport per day, and each sport's efficiency marker ────
def daily_loads(days):
    """{sport: [load per day]} from loads.analyse days (engine points per sport)."""
    return {s: [((r.get("sports") or {}).get(s) or {}).get("engine", 0.0) for r in days] for s in SPORTS}


def ewma(xs, tau):
    k, out, v = 1 - math.exp(-1 / tau), [], 0.0
    for x in xs:
        v += (x - v) * k
        out.append(v)
    return out


def markers(acts, aerobic_rides):
    """{sport: [(date, efficiency)]}: bike watts per beat; swim and run metres per minute per beat."""
    out = {s: [] for s in SPORTS}
    for r in aerobic_rides or []:
        if r.get("ef"):
            out["bike"].append((r["date"], r["ef"]))
    for a in acts:
        if a["sport"] not in ("swim", "run") or a["minutes"] < 15 or a["distance_m"] <= 0:
            continue
        hrs = [x["hr"] for x in a["records"] if x.get("hr")]
        if len(hrs) < 300:
            continue
        out[a["sport"]].append((dt.date.fromtimestamp(a["start"]).isoformat(),
                                a["distance_m"] / a["minutes"] / statistics.fmean(hrs)))
    return out


def _status(n, r):
    if n < 5 or r is None:
        return "prior"
    return "learning" if r["hi"] - r["lo"] > 0.6 else "learned"


def analyse(days, acts, aerobic_rides=None, checkins=None, marker_data=None):
    """The carry-over table for fitness, and how much each sport tires the legs - each with an 80% interval and
    whether it's still the prior, learning, or learned."""
    if not days:
        return None
    dates = [r["date"] for r in days]
    idx = {d: i for i, d in enumerate(dates)}
    loads = daily_loads(days)
    scale = statistics.fmean([sum(loads[s][i] for s in SPORTS) for i in range(len(dates))]) or 1.0
    fit = {s: [v / scale for v in ewma(loads[s], 42)] for s in SPORTS}
    fat = {s: [v / scale for v in ewma(loads[s], 7)] for s in SPORTS}
    mk = marker_data if marker_data is not None else markers(acts, aerobic_rides)
    fitness = {}
    for to in SPORTS:
        obs = [(idx[d], v) for d, v in mk[to] if d in idx]
        if len(obs) >= 2:
            vals = [v for _, v in obs]
            mu, sd = statistics.fmean(vals), (statistics.pstdev(vals) or 1.0)
            y = [(v - mu) / sd for _, v in obs]
        else:
            y = []
        X = [[1.0] + [fit[u][i] for u in SPORTS] + [-fat[u][i] for u in SPORTS] for i, _ in obs] if y else []
        pm = [0.0] + [A0 * PRIOR[u][to] for u in SPORTS] + [B0 * PRIOR[u][to] for u in SPORTS]
        ps = [1.0] + [A0 * 0.6 + 0.05 for _ in SPORTS] + [B0 + 0.05 for _ in SPORTS]
        mean, cov = bayes_regression(X, y, pm, ps)
        own = 1 + SPORTS.index(to)
        row = {}
        for u in SPORTS:
            if u == to:
                continue
            r = _ratio(mean, cov, 1 + SPORTS.index(u), own)
            row[u] = {"prior": PRIOR[u][to], **(r or {"ratio": PRIOR[u][to], "lo": None, "hi": None}),
                      "status": _status(len(y), r)}
        fitness[to] = {"from": row, "measurements": len(y)}
    # legs: the next morning's rating against yesterday's (and the day before's) load in each sport
    legs_obs = []
    for d, c in (checkins or {}).items():
        i = idx.get(d)
        if c.get("legs") is None or i is None or i < 2:
            continue
        x = [(loads[u][i - 1] + 0.5 * loads[u][i - 2]) / scale for u in SPORTS]
        legs_obs.append((x, float(c["legs"])))
    if len(legs_obs) >= 2:
        mu = statistics.fmean(v for _, v in legs_obs)
        X = [[1.0] + x for x, _ in legs_obs]
        y = [v - mu for _, v in legs_obs]
    else:
        X, y = [], []
    pm = [0.0] + [PRIOR_LEGS[u] for u in SPORTS]
    mean, cov = bayes_regression(X, y, pm, [1.5] + [0.8 for _ in SPORTS], noise_sd=1.5)
    legs = {}
    for u in SPORTS:
        if u == "run":
            continue
        r = _ratio(mean, cov, 1 + SPORTS.index(u), 1 + SPORTS.index("run"))
        legs[u] = {"prior": PRIOR_LEGS[u], **(r or {"ratio": PRIOR_LEGS[u], "lo": None, "hi": None}),
                   "status": _status(len(y), r)}
    return {"fitness": fitness, "legs": {"relative_to": "run", "from": legs, "measurements": len(y)},
            "markers": {s: len(mk[s]) for s in SPORTS}}
