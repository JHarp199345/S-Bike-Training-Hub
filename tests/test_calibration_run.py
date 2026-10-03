"""The running calibration (the rider's design, 2026-10-03): one run of up to 60 minutes in zone 2, then eight
days without running. The block is that run's load times how well it was absorbed: heart-rate drift, the
mornings and the hop test. The starter program puts it in the test week and keeps the watch free of runs."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import calibration as C
import program_builder as B
import starter_programs as S

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


DAY = "2026-06-01"
after = lambda n: (dt.date(2026, 6, 1) + dt.timedelta(days=n)).isoformat()


def mornings(feet=2, legs=2, hops=None, n=8):
    out = {after(k): {"feet": feet, "legs": legs} for k in range(1, n + 1)}
    out["2026-05-31"] = {"feet": 2, "legs": 2, "hops": 20}
    if hops is not None:
        out[after(3)]["hops"] = hops
    return out


def grade(drift=2.0, checkins=None, today=after(9), others=(), pain=False, points=100.0):
    d = {}
    if pain:
        d = {"benchmarks": {"calibrations": {DAY: {"pain": True}}}}
    rec = C.run_calibration(d, DAY, {"impact": points, "drift_pct": drift, "minutes": 60},
                            mornings() if checkins is None else checkins, today, others)
    return rec, d


rec, d = grade(drift=2.0)
check(f"no drift and clean mornings: the block is 1.5x the run ({rec['block']})", rec["block"] == 150.0 and rec["multiplier"] == 1.5)
check("…recorded as a measured block", d["calibration"]["block"][-1]["kind"] == "test" and d["calibration"]["block"][-1]["value"] == 150.0)
check("drift 3-5%: 1.25x", grade(drift=4.2)[0]["multiplier"] == 1.25)
check("drift 5-8%: 1.0x", grade(drift=6.5)[0]["multiplier"] == 1.0)
check("drift 8%+: the run was more than a block (0.8x)", grade(drift=9.0)[0]["multiplier"] == 0.8)
check("heavy mornings (4-5): 1.0x however low the drift", grade(checkins=mornings(feet=4))[0]["multiplier"] == 1.0)
check("rough mornings (6+): 0.8x", grade(checkins=mornings(legs=6))[0]["multiplier"] == 0.8)
check("a hop-test drop: 0.8x", grade(checkins=mornings(hops=15))[0]["multiplier"] == 0.8)
check("it hurt: 0.8x", grade(pain=True)[0]["multiplier"] == 0.8)
check("no drift reading (short or unsteady run): one block, no headroom claimed", grade(drift=None)[0]["multiplier"] == 1.0)
check("ran again during the watch: no headroom claimed", grade(drift=2.0, others=[after(4)])[0]["multiplier"] == 1.0)
check("not graded before the eight days are over", grade(today=after(8))[0] is None)
check("not graded without enough mornings", grade(checkins=mornings(n=4))[0] is None)
check("…but graded on four once two weeks have passed", grade(checkins=mornings(n=4), today=after(15))[0] is not None)

# the starter program: the calibration in the test week, no running for eight days after
f = {"start": "2026-10-05", "target": "2026-12-27", "sport": "tri", "hours": 4, "goal": "Sprint", "assessment": "week",
     "starter_level": "moderate", "priorities": {"ride": "improve", "swim": "improve", "run": "improve", "gym": "maintain"}}
p = B.propose({"plans": {}}, f, "2026-10-05", {"status": "open_for_review"})
plans = S.build({"plans": {}}, p, today="2026-10-05")["candidates"][1]["plans"]
cal = [k for k, v in plans.items() if v.get("test") == "run_calibration"]
check(f"the test week has one running calibration ({cal})", len(cal) == 1 and cal[0] < "2026-10-12")
runs_in_watch = [k for k, v in plans.items() if cal and cal[0] < k <= (dt.date.fromisoformat(cal[0]) + dt.timedelta(days=8)).isoformat()
                 and any(s["sport"] == "run" for s in v["sessions"])]
check(f"no runs during its eight-day watch ({runs_in_watch})", cal and not runs_in_watch)
s = next(x for x in plans[cal[0]]["sessions"] if x["sport"] == "run")
check("it says up to 60 min in zone 2, stop early if form breaks down", s["minutes"] == 60 and "zone 2" in " ".join(s["steps"]))
held = S.build({"plans": {}}, {**p, "running_hold": True}, today="2026-10-05")["candidates"][1]["plans"]
check("never scheduled through a running hold", not any(v.get("test") == "run_calibration" for v in held.values()))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
