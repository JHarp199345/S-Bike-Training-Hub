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

# the test ends at an hour; stopped early, the reason caps what it can tell
def short(minutes, reason=None, drift=2.0, today=after(9)):
    d = {}
    if reason:
        C.calibration_stop(d, DAY, reason)
    return C.run_calibration(d, DAY, {"impact": 100.0, "drift_pct": drift, "minutes": minutes}, mornings(), today)
check("completed the hour: the full scale (x1.5)", short(60)["multiplier"] == 1.5 and short(60)["completed"])
check("past the hour only the first 60 minutes count", short(75)["points"] == 80.0)
check("stopped early with no reason yet: waits for the answer", short(35) is None)
check("ran out of time: at most x1.25, flagged as a short test", short(35, "time")["multiplier"] == 1.25 and "full hour" in short(35, "time")["why"])
check("too tired / form broke down: at most x1.0 - that was their limit", short(40, "tired")["multiplier"] == 1.0 and short(40, "form")["multiplier"] == 1.0)
check("something hurt: x0.8", short(40, "pain")["multiplier"] == 0.8)
v = short(25, "interrupted")
check(f"interrupted: the test is void, no block set ({v['why']})", v["result"] == "void" and "block" not in v)
check("no answer after two weeks: graded at most x1.0", short(35, today=after(15))["multiplier"] == 1.0)
try:
    C.calibration_stop({}, DAY, "bored")
    check("an unknown reason is refused", False)
except ValueError:
    check("an unknown reason is refused", True)

# done up to two days off the planned day: matched, then confirmed with the athlete
plan = {"plans": {DAY: {"test": "run_calibration", "sessions": []}}}
acts = {after(1): {"minutes": 60, "impact": 100.0, "drift_pct": 2.0}}
check("a run the day after a planned calibration is matched to it", C.match_runs(plan, acts) == {DAY: after(1)})
check("a run three days off is not", C.match_runs(plan, {after(3): acts[after(1)]}) == {DAY: None})
check("not when another run sits in between", C.match_runs(plan, {after(-1): {}, after(-2): acts[after(1)]})[DAY] == after(-1))
runs = C.calibration_runs(plan, acts)
check("a moved run asks whether it was the test", runs[0]["needs_confirm"] and runs[0]["moved"] and not runs[0]["needs_reason"])
moved = lambda **kw: C.run_calibration({**{"benchmarks": {"calibrations": {DAY: kw}}}} if kw else {}, DAY, acts[after(1)],
                                       {**mornings(), after(9): {"feet": 2, "legs": 2}}, kw.pop("today", after(10)), (), after(1))
check("…and waits for the answer", moved() is None)
check("confirmed: graded on the full scale from the day it was run", moved(confirmed=True)["multiplier"] == 1.5)
no = moved(confirmed=False)
check("an ordinary run: not the test, no block, schedule it again", no["result"] == "not_test" and "block" not in no)
late = C.run_calibration({}, DAY, acts[after(1)], {**mornings(), after(9): {"feet": 2, "legs": 2}}, after(16), (), after(1))
check("nobody answered in two weeks: measured anyway, no headroom claimed", late["multiplier"] == 1.0)

# the starter program: the calibration in the test week, no running for eight days after
f = {"start": "2026-10-05", "target": "2026-12-27", "sport": "tri", "hours": 4, "goal": "Sprint", "assessment": "week",
     "starter_level": "moderate", "priorities": {"ride": "improve", "swim": "improve", "run": "improve", "gym": "maintain"}}
p = B.propose({"plans": {}}, f, "2026-10-05", {"status": "open_for_review"})
plans = S.build({"plans": {}}, p, today="2026-10-05")["candidates"][1]["plans"]
cal = [k for k, v in plans.items() if v.get("test") == "run_calibration"]
check(f"the test week has a running calibration, and each check week another ({cal})", len(cal) >= 2 and cal[0] < "2026-10-12"
      and len([k for k in cal if k < "2026-10-12"]) == 1)
runs_in_watch = [k for c in cal for k, v in plans.items() if c < k <= (dt.date.fromisoformat(c) + dt.timedelta(days=8)).isoformat()
                 and any(s["sport"] == "run" for s in v["sessions"])]
check(f"no runs during any eight-day watch ({runs_in_watch})", cal and not runs_in_watch)
s = next(x for x in plans[cal[0]]["sessions"] if x["sport"] == "run")
check("it says up to 60 min in zone 2, stop early if form breaks down", s["minutes"] == 60 and "zone 2" in " ".join(s["steps"]))
held = S.build({"plans": {}}, {**p, "running_hold": True}, today="2026-10-05")["candidates"][1]["plans"]
check("never scheduled through a running hold", not any(v.get("test") == "run_calibration" for v in held.values()))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
