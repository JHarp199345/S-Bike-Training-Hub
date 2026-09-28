"""Fitness/fatigue/form: NP, TSS and the 42/7-day curves against known values."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import csv, datetime as dt, math, tempfile
import fitness


def ride_file(path, start, watts_fn, secs):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time", "power_w", "cadence_rpm"])
        for s in range(secs):
            w.writerow([(start + dt.timedelta(seconds=s)).isoformat(timespec="seconds"), watts_fn(s), 80])


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    const = [(t, 200.0) for t in range(600)]
    check(f"NP of steady 200 W is 200 ({fitness.normalized_power(const):.1f})", abs(fitness.normalized_power(const) - 200) < 0.01)
    surgy = [(t, 300.0 if (t // 60) % 2 else 100.0) for t in range(3600)]
    np_ = fitness.normalized_power(surgy)
    check(f"NP of 1-min 100/300 W surges is well above their 200 W average ({np_:.0f})", 225 < np_ < 260)

    tmp = pathlib.Path(tempfile.mkdtemp()); rides = tmp / "rides"; rides.mkdir()
    prof = {"ftp": 200, "ftp_source": "test", "history": []}
    ride_file(rides / "ride_a.csv", dt.datetime(2026, 9, 1, 8), lambda s: 200, 3600)
    r = fitness.ride_load(rides / "ride_a.csv", prof)
    check(f"an hour at exactly FTP is a load of 100 ({r['tss']})", abs(r["tss"] - 100) < 0.5)
    ride_file(rides / "ride_b.csv", dt.datetime(2026, 9, 2, 8), lambda s: 140, 3600)
    r = fitness.ride_load(rides / "ride_b.csv", prof)
    check(f"an hour at 70% of FTP is ~49 ({r['tss']})", abs(r["tss"] - 49) < 0.5)
    ride_file(rides / "ride_c.csv", dt.datetime(2026, 9, 3, 8), lambda s: 0, 30)
    check("a few seconds of nothing isn't a ride", fitness.ride_load(rides / "ride_c.csv", prof) is None)

    old = {"ftp": 250, "ftp_source": "test", "history": [{"ftp": 200, "source": "x", "until": "2026-09-10"}]}
    check("rides before an FTP change use the FTP of their day",
          fitness.ftp_on(old, dt.date(2026, 9, 1)) == 200 and fitness.ftp_on(old, dt.date(2026, 9, 12)) == 250)

    start = dt.date(2026, 1, 1)
    daily = [{"date": (start + dt.timedelta(days=i)).isoformat(), "tss": 100} for i in range(42)]
    days = fitness.chart(daily, today=start + dt.timedelta(days=41), ahead=14)
    d42 = days[41]
    want = 100 * (1 - math.exp(-1)); wanta = 100 * (1 - math.exp(-42 / 7))
    check(f"42 days of 100: fitness ~63 ({d42['ctl']}), fatigue ~100 ({d42['atl']})", abs(d42["ctl"] - want) < 0.5 and abs(d42["atl"] - wanta) < 0.5)
    check(f"...so form is negative while training ({d42['tsb']})", d42["tsb"] < -30)
    rest = days[41 + 7]
    check(f"after a week of rest, fatigue falls faster than fitness and form turns positive "
          f"(fitness {rest['ctl']}, fatigue {rest['atl']}, form {rest['tsb']})", rest["tsb"] > 0 and rest["atl"] < rest["ctl"])
    check("the rest days after today are marked as projection", days[-1]["future"] and not d42["future"])
    check("advice for very tired", "rest" in fitness.advice({"tsb": -40, "ctl": 50}))
    check("advice for fresh", "hard effort" in fitness.advice({"tsb": 12, "ctl": 50}))
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
