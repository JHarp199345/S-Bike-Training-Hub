"""The aerobic engine from power and heart rate together: watts per beat, decoupling (judged only on long steady
rides), and heart rate at the same watts - and their trends."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import aerobic


def ride(day, minutes, watts, hr_start, hr_drift, wobble=0):
    t0 = int(dt.datetime.fromisoformat(f"{day}T09:00:00").timestamp())
    n = minutes * 60
    recs = [{"t": t0 + s, "w": watts + (wobble if (s // 60) % 2 else -wobble), "hr": hr_start + hr_drift * s / n,
             "rpm": 75, "d": None, "alt": None} for s in range(n)]
    return {"id": day, "sport": "bike", "start": t0, "records": recs}


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    steady = aerobic.ride(ride("2026-10-01", 50, 110, 115, 2))
    check(f"a steady 50 min at 110 W with heart rate flat: aerobic (decoupling {steady['decoupling_pct']}%)",
          steady["judged"] and steady["aerobic"] and steady["decoupling_pct"] < 5)
    drift = aerobic.ride(ride("2026-10-02", 50, 110, 115, 15))
    check(f"the same watts with heart rate drifting up 15: above the aerobic threshold ({drift['decoupling_pct']}%)",
          drift["judged"] and drift["aerobic"] is False and drift["decoupling_pct"] > 5)
    short = aerobic.ride(ride("2026-10-03", 30, 110, 115, 15))
    check("30 minutes: shown, but not judged", short["judged"] is False and short["aerobic"] is None)
    hilly = aerobic.ride(ride("2026-10-04", 50, 110, 115, 2, wobble=60))
    check(f"a surging ride (VI {hilly['vi']}): not judged", hilly["judged"] is False)
    check(f"watts per beat ({steady['ef']}) and heart rate at 100-120 W ({steady['hr_at_band']})",
          0.9 < steady["ef"] < 1.0 and 115 <= steady["hr_at_band"] <= 117)
    check("no heart rate: nothing", aerobic.ride({**ride("2026-10-05", 50, 110, 0, 0), "records": [
        {"t": 0, "w": 110, "hr": None, "rpm": 75} for _ in range(3000)]}) is None)
    acts = [ride("2026-09-20", 45, 110, 125, 3), ride("2026-09-27", 45, 110, 120, 3), ride("2026-10-04", 45, 110, 114, 3)]
    tr = aerobic.summary(acts, today=dt.date(2026, 10, 5))["trend"]
    check(f"the trend: heart rate at the same watts falling {tr['hr_at_band']['per_week']} bpm a week, watts per beat rising",
          tr["hr_at_band"]["per_week"] < -2 and tr["ef"]["per_week"] > 0)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
