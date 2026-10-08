"""energy.py - one metabolic energy estimate per session, from the source least dependent on heart rate.

  Cycling with power: mechanical work in kJ, read as kcal. Gross cycling efficiency is about 20-25% and
      1 kcal = 4.184 kJ, so mechanical kJ is close to metabolic kcal (Ettema & Loras 2009).
  Running and walking with distance: body mass x distance x the energy cost of locomotion at each stretch's
      gradient (Minetti et al. 2002; running scaled to 1 kcal/kg/km on the flat, Margaria et al. 1963), plus resting metabolism over the session so it is a gross total like the
      bike figure and the watch's. Stretches slower than 2.0 m/s use the walking curve, so run-walks aren't
      counted as continuous running.
  Everything else, or anything missing its inputs: the watch's calories (heart-rate based).

The watch's calories are always kept beside the primary estimate; a large gap is flagged, never averaged away.
"""
import math

KCAL_J = 4184
REST_KCAL_PER_KG_H = 1.0          # 1 MET = 3.5 ml O2/kg/min ~ 1 kcal/kg/h
WALK_RUN_MS = 2.0                 # below this a stretch is walking
SEGMENT_M = 25                    # gradient over 25 m stretches of smoothed altitude
SMOOTH_S = 15                     # altitude smoothing window, seconds
MAX_GRADE = 0.45                  # the measured range of Minetti et al. (2002)
GAP_RATIO = 1.3                   # watch vs primary beyond 30% either way is flagged


RUN_FLAT_J_PER_KG_M = 4.184   # 1 kcal/kg/km: the population average net cost of flat running (Margaria et al. 1963)


def run_cost(i):
    """Net energy cost of running, J/kg/m, at gradient i (rise/run). The shape across gradients is Minetti et al.
    (2002); it is scaled so flat running costs the population average of 1 kcal/kg/km, because Minetti's flat value
    (3.6 J/kg/m) came from trained mountain runners, who are more economical than most athletes."""
    return (155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3 + 46.3 * i**2 + 19.5 * i + 3.6) * RUN_FLAT_J_PER_KG_M / 3.6


def walk_cost(i):
    """Net energy cost of walking, J/kg/m, at gradient i. Minetti et al. 2002."""
    return 280.5 * i**5 - 58.7 * i**4 - 76.8 * i**3 + 51.9 * i**2 + 19.6 * i + 2.5


def power_kj(recs):
    """Mechanical work from power samples, kJ; None unless most of the moving time has power."""
    total, covered, moving, last = 0.0, 0.0, 0.0, None
    for r in recs:
        t, w = r.get("t"), r.get("w")
        if last is not None and t is not None:
            step = min(max(t - last, 0), 5)                 # a gap counts at most 5 s
            moving += step
            if w:
                total += w * step
                covered += step
        last = t if t is not None else last
    return round(total / 1000, 1) if moving and covered / moving >= 0.5 else None


def _smoothed(recs):
    """(t, distance, altitude) with altitude averaged over SMOOTH_S seconds; flat when there is no altitude."""
    pts = [(r["t"], r["d"], r.get("alt")) for r in recs if r.get("t") is not None and r.get("d") is not None]
    if not any(a is not None for _, _, a in pts):
        return [(t, d, 0.0) for t, d, _ in pts]
    out, lo, hi = [], 0, 0
    for t, d, _ in pts:
        while lo < len(pts) and pts[lo][0] < t - SMOOTH_S / 2:
            lo += 1
        while hi < len(pts) and pts[hi][0] <= t + SMOOTH_S / 2:
            hi += 1
        near = [a for _, _, a in pts[lo:hi] if a is not None]
        out.append((t, d, sum(near) / len(near) if near else (out[-1][2] if out else 0.0)))
    return out


def motion_kcal(recs, mass_kg, seconds=None):
    """Gross energy of a run or walk from distance, gradient and body mass, kcal; None without distance or mass."""
    if not mass_kg:
        return None
    pts = _smoothed(recs)
    if len(pts) < 2 or pts[-1][1] - pts[0][1] < 200:
        return None
    net_j, (t0, d0, a0) = 0.0, pts[0]
    for t, d, a in pts[1:]:
        dist = d - d0
        if dist < SEGMENT_M and (t, d, a) != pts[-1]:
            continue
        if dist > 0:
            grade = max(-MAX_GRADE, min(MAX_GRADE, (a - a0) / dist))
            speed = dist / (t - t0) if t > t0 else 0
            net_j += (run_cost(grade) if speed >= WALK_RUN_MS else walk_cost(grade)) * mass_kg * dist
        t0, d0, a0 = t, d, a
    duration_h = (seconds if seconds else pts[-1][0] - pts[0][0]) / 3600
    return round(net_j / KCAL_J + REST_KCAL_PER_KG_H * mass_kg * duration_h, 1)


def estimate(sport, recs, mass_kg, watch_kcal, seconds=None):
    """The session's energy: {energy_kcal, energy_source, estimates, gap_flag}."""
    est = {"watch_kcal": watch_kcal}
    if sport == "bike":
        est["power_kj"] = power_kj(recs)
    if sport in ("run", "walk"):
        est["motion_kcal"] = motion_kcal(recs, mass_kg, seconds)
    primary, source = None, None
    if est.get("power_kj") is not None:
        primary, source = est["power_kj"], "power"
    elif est.get("motion_kcal") is not None:
        primary, source = est["motion_kcal"], "motion"
    elif watch_kcal is not None:
        primary, source = watch_kcal, "watch"
    gap = None
    if source in ("power", "motion") and watch_kcal and primary:
        ratio = watch_kcal / primary
        if ratio > GAP_RATIO or ratio < 1 / GAP_RATIO:
            gap = round(ratio, 2)
    return {"energy_kcal": primary, "energy_source": source, "estimates": est, "gap_ratio": gap}
