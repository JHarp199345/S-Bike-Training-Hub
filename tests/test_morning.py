"""Morning readiness from the watch: HRV against its own normal range, resting HR against two weeks, sleep."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt, tempfile
import loads, morning


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    base = pathlib.Path(tempfile.mkdtemp())
    norm = {f"2026-09-{d:02d}": {"hrv": 40, "hrv_low": 32, "hrv_high": 44, "resting_hr": 60, "sleep_min": 420} for d in range(10, 25)}
    morning.record(base, norm)
    D = lambda s: dt.date.fromisoformat(s)
    check("a normal night: go", morning.assess(morning.load(base), D("2026-09-24"))["level"] == "go")
    morning.record(base, {"2026-09-25": {"hrv": 28, "hrv_low": 32, "hrv_high": 44}})
    a = morning.assess(morning.load(base), D("2026-09-25"))
    check(f"HRV under its normal range: easy ({a['why']})", a["level"] == "easy")
    morning.record(base, {"2026-09-26": {"hrv": 27, "hrv_low": 32, "hrv_high": 44}})
    check("...two mornings running: rest", morning.assess(morning.load(base), D("2026-09-26"))["level"] == "rest")
    morning.record(base, {"2026-09-27": {"hrv": 40, "hrv_low": 32, "hrv_high": 44, "resting_hr": 66}})
    a = morning.assess(morning.load(base), D("2026-09-27"))
    check(f"resting HR 6 over its two-week normal: easy ({a['why']})", a["level"] == "easy")
    morning.record(base, {"2026-09-28": {"resting_hr": 69, "hrv": 40, "hrv_low": 32, "hrv_high": 44}})
    check("...9 over: rest", morning.assess(morning.load(base), D("2026-09-28"))["level"] == "rest")
    morning.record(base, {"2026-09-29": {"sleep_min": 158, "hrv": 40, "hrv_low": 32, "hrv_high": 44, "resting_hr": 60}})
    a = morning.assess(morning.load(base), D("2026-09-29"))
    check(f"2h38 of sleep: easy, said plainly ({a['why']})", a["level"] == "easy" and "2h38" in a["why"][0])
    check("no data this morning: yesterday's read, or nothing", morning.assess(morning.load(base), D("2026-09-30"))["date"] == "2026-09-29"
          and morning.assess(morning.load(base), D("2026-10-05")) is None)
    try:
        morning.record(base, {"today": {"hrv": 40}}); check("bad dates refused", False)
    except ValueError:
        check("bad dates refused", True)
    st = {"systems": {x: {"acwr": 0.9, "tuned": True, "form": 0, "last7": 1, "prev7": 1} for x in loads.SYSTEMS},
          "days": [], "history_days": 30, "morning": {"date": "2026-09-26", "level": "rest", "why": ["HRV 27 ms..."]}}
    st["systems"]["impact"]["tissue"] = None
    rd = loads.readiness(st, {})
    check(f"a rest morning sets the bike verdict ({rd['verdict']}: {rd['systems']['engine']['why']}) and benches running ({rd['running']['verdict']})",
          rd["verdict"] == "rest" and rd["running"]["verdict"] == "rest")
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
