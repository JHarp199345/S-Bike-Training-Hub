"""Critical power and W': the best-effort curve, the 2-parameter fit (trusted only when the efforts were real),
live W' balance with matches, "can I do that?", the fastest climb you could hold, and swim D'."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt, tempfile
import cp

HDR = "time,power_w,cadence_rpm,bike_speed_kmh,bike_distance_m,resistance,virtual_speed_kmh,virtual_distance_m,grade_pct,gear,hill_shift,erg_w\n"


def ride(folder, day, parts):
    """parts: [(seconds, watts)] ridden back to back."""
    t0 = dt.datetime.fromisoformat(f"{day}T09:00:00")
    rows, s = [], 0
    for secs, w in parts:
        for _ in range(secs):
            rows.append(f"{(t0 + dt.timedelta(seconds=s)).isoformat()},{w},80,25,0,5,25,0,0,0,0,\n"); s += 1
    (folder / f"ride_{day}_0900.csv").write_text(HDR + "".join(rows))


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    real = pathlib.Path(tempfile.mkdtemp())
    for i, t in enumerate((180, 300, 600, 900, 1200)):            # all-out efforts on a CP 200 W, W' 15 kJ rider
        ride(real, f"2026-09-{10 + i:02d}", [(600, 100), (t, round(200 + 15000 / t)), (600, 100)])
    curve = cp.best_curve(real, today=dt.date(2026, 9, 30))
    f = cp.fit(curve)
    # within ~8%: in-between durations are slices of longer efforts, not all-out ones, which pulls W' a little low
    check(f"the fit recovers CP and W' from real efforts (CP {f['cp']:.0f} W, W' {f['w_prime'] / 1000:.1f} kJ)",
          abs(f["cp"] - 200) < 4 and abs(f["w_prime"] - 15000) < 1200)
    e = cp.estimate(curve, 200)
    check("...and it's trusted (CP close to FTP)", e["source"] == "your best efforts")
    easy = pathlib.Path(tempfile.mkdtemp())
    for i in range(5):
        ride(easy, f"2026-09-{10 + i:02d}", [(2400, 120 - i * 3)])
    ee = cp.estimate(cp.best_curve(easy, today=dt.date(2026, 9, 30)), 180)
    check(f"easy rides only: CP = FTP and a typical W', the fit shown as a floor ({ee['source'][:60]}...)",
          ee["cp"] == 180 and ee["w_prime"] == cp.W_PRIOR and "at least" in ee["source"] or "not enough" in ee["source"])
    w = cp.WBal(200, 15000)
    for _ in range(60):
        w.add(300)
    check(f"a minute at 300 W on CP 200 spends 6 kJ ({w.status()['bal_kj']} of 15 left)", w.status()["bal_kj"] == 9.0)
    for _ in range(300):
        w.add(100)
    check(f"five minutes easy refill most of it ({w.status()['bal_kj']} kJ) and it counted a match", w.status()["bal_kj"] > 13 and w.matches == 1)
    check("200 W for 15 s: easily", cp.feasible(200, 15, 180, 12000)["ok"])
    bad = cp.feasible(230, 600, 180, 12000)
    check(f"230 W for 10 min on CP 180: no ({bad['note']})", not bad["ok"] and bad["lasts_s"] == 240)
    check("under CP: sustainable", cp.feasible(170, 1800, 180, 12000)["ok"])
    fast = cp.fastest_climb(1800, 8, 126.6, 180, 12000)
    import session
    check(f"the fastest you could hold up 1.8 km at 8%: {fast // 60}:{fast % 60:02d} - it spends about 90% of W'",
          fast and cp.feasible(session.watts_for(1800 / fast, 8, 126.6), fast, 180, 12000)["ok"])
    check(f"swim D' from a 400 in 8:00 and a 200 in 3:40: {cp.swim_d_prime(480, 220)} m", abs(cp.swim_d_prime(480, 220) - 30.8) < 0.1)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
