"""The run-walk test at 60% of a running plateau: run-walk, then walking, then stairs (recovery.py)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import recovery as R

D0 = dt.date(2026, 10, 28)
REM = {"phase": "plateau", "plateau_days": 50, "plateau_remaining_days": 20, "score": 13.0, "threshold_blocks": 1.5}   # 60% served


def day(n): return D0 + dt.timedelta(days=n)


def athlete(**c):
    base = {"hops_left": 10, "hops_right": 10, "feet": 2, "legs": 2}
    base.update(c)
    return {"checkins": {D0.isoformat(): base}}


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    early = dict(REM, plateau_remaining_days=30)
    st = R.run_test_status(athlete(), early, D0)
    check(f"before 60%: not due, and it says when ({st['checkpoint_date']})", st["stage"] == "not_due" and st["checkpoint_date"] == day(10).isoformat())
    check("at 60% with good check-in: ready", R.run_test_status(athlete(), REM, D0)["stage"] == "ready")
    miss = R.run_test_status(athlete(hops_left=7, feet=5), REM, D0)["missing"]
    check(f"ready, but says what's missing ({miss})", any("hops" in m for m in miss) and any("feet" in m for m in miss))
    try:
        R.record_run_test(athlete(), "run_walk", {"brisk_walk_ok": False, "completed": True, "pain_max": 1}, REM, D0); refused = False
    except ValueError as e:
        refused = "brisk 30-minute walk" in str(e)
    check("no run-walk without the pain-free brisk walk first", refused)
    d = athlete()
    R.record_run_test(d, "run_walk", {"brisk_walk_ok": True, "completed": True, "pain_max": 1}, REM, D0)
    st = R.run_test_status(d, REM, D0)
    check("day 1 recorded: walking is next, tomorrow", st["stage"] == "in_progress" and st["next_step"] == "walk" and st["next_date"] == day(1).isoformat())
    try:
        R.record_run_test(d, "walk", {"walk_feel": 1, "morning_pain": False, "night_pain": False}, REM, D0); same_day = False
    except ValueError:
        same_day = True
    check("walking is checked the day after, not the same day", same_day)
    R.record_run_test(d, "walk", {"walk_feel": 1, "morning_pain": False, "night_pain": False}, REM, day(1))
    R.record_run_test(d, "stairs", {"used_stairs": True, "stairs_feel": 2, "pain_lasting": False}, REM, day(2))
    t = d["run_progression"]["run_tests"][-1]
    check(f"comfortable all three days: good ({t['why'][0]})", t["verdict"] == "good")
    s = R.status(d, dict(REM, plateau_remaining_days=18), day(2))
    check("a good test offers the reviewed early decline (not automatic)", s["review_eligible"] and not (d["run_progression"].get("reviews")))
    r = R.approve_decline(d, dict(REM, plateau_remaining_days=18), day(2), "test passed")
    check("...and the athlete's confirmation records it", r["action"] == "begin_decline")
    d2 = athlete()
    R.record_run_test(d2, "run_walk", {"brisk_walk_ok": True, "completed": True, "pain_max": 2}, REM, D0)
    R.record_run_test(d2, "walk", {"walk_feel": 3, "morning_pain": True, "night_pain": False}, REM, day(1))
    t2 = d2["run_progression"]["run_tests"][-1]
    check(f"morning pain the next day: retry in a week ({t2['why']})", t2["verdict"] == "retry" and t2["retry_from"] == day(8).isoformat())
    st2 = R.run_test_status(d2, REM, day(3))
    check("no new test before the retry date", st2["stage"] == "retry_wait" and st2["retry_from"] == day(8).isoformat())
    d3 = athlete()
    R.record_run_test(d3, "run_walk", {"brisk_walk_ok": True, "completed": False, "pain_max": 5}, REM, D0)
    check("pain reaching 5/10 during the run-walk ends the test there", d3["run_progression"]["run_tests"][-1]["verdict"] == "retry")
    d4 = athlete()
    R.record_run_test(d4, "run_walk", {"brisk_walk_ok": True, "completed": True, "pain_max": 0}, REM, D0)
    R.record_run_test(d4, "walk", {"walk_feel": 1, "morning_pain": False, "night_pain": False}, REM, day(1))
    R.record_run_test(d4, "stairs", {"used_stairs": False, "stairs_feel": 4, "pain_lasting": False}, REM, day(2))
    t4 = d4["run_progression"]["run_tests"][-1]
    check(f"no stairs: walking counts instead, and 4/10 two days on is a retry ({t4['why']})", t4["verdict"] == "retry" and "walking felt 4/10" in t4["why"][0])
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
