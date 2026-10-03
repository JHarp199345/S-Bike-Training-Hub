"""The running start from setup (the rider's design, 2026-10-03), until a calibration run measures the block:
a new runner picks how much they'd like (40 min is about one good run) and starts below it; someone who already
runs gives their usual week and number of runs and continues it, held two weeks. A niggle halves it. The
starting block keeps those runs below the cliff: a new runner's run is about 0.4 blocks; a current runner's
usual week carries at most about one block over two months on the recovery curve."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import damage
import loads
import onboarding as O
import program_builder as B
import starter_programs as S

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


rs = lambda **f: O.running_start({"run_minutes": 40, **f})
check("new runner, 20 min: one 10-minute run", (rs(run_minutes=20)["runs"], rs(run_minutes=20)["per_run"]) == (1, 10))
check("new runner, 30 min: two 10-minute runs", (rs(run_minutes=30)["runs"], rs(run_minutes=30)["per_run"]) == (2, 10))
check("new runner, 40 min (one good run): two 15-minute runs", (rs()["runs"], rs()["per_run"]) == (2, 15))
check("new runner: no hold", rs()["hold_weeks"] == 0)
cur = rs(runs_now=True, run_minutes=120, runs_per_week=3)
check(f"already runs 120 min in 3: continues 3 x 40, held two weeks ({cur['runs']} x {cur['per_run']})",
      (cur["runs"], cur["per_run"], cur["hold_weeks"]) == (3, 40, 2) and cur["good_runs"] == 3.0)
check("a niggle halves the run", rs(runs_now=True, run_minutes=120, runs_per_week=3, run_niggles=True)["per_run"] == 20)
check("no running answer: nothing set", O.running_start({}) is None)

# starting block
prof = lambda r: {"running_start": r}
new = loads.start_block(prof(rs()), [])
check(f"new runner: block is 2.5 x one starting run ({new} = 2.5 x 15 min x 2 pts/min)", new == 75.0)
blk = loads.start_block(prof(cur), [])
def peak_over(weeks):
    dates = [(dt.date(2026, 1, 5) + dt.timedelta(days=i)).isoformat() for i in range(7 * weeks)]
    doses = [80.0 if i % 7 in (0, 2, 5) else 0 for i in range(7 * weeks)]      # 3 x 40 min at 2 pts/min
    return max(c["after_blocks"] for c in damage.remodeling_response(dates, doses, block=blk)["components"])
check(f"current runner: their usual week carries at most one block over two months ({blk} pts -> {peak_over(8)})",
      0.9 <= peak_over(8) <= 1.05)
check(f"…and less in the first month ({peak_over(4)})", peak_over(4) <= peak_over(8))
own = [{"sport": "run", "minutes": 20, "impact": 33.0}]
check("points per minute come from their own runs when there are any", loads.start_block(prof(rs()), own) == round(2.5 * 33 / 20 * 15, 1))

# the starter follows it
f = {"start": "2026-10-05", "target": "2026-12-27", "sport": "tri", "hours": 5, "goal": "Sprint", "assessment": "week",
     "starter_level": "moderate", "priorities": {"ride": "improve", "swim": "improve", "run": "improve", "gym": "maintain"}}
p = B.propose({"plans": {}}, f, "2026-10-05", {"status": "open_for_review"})
plans = S.build({"plans": {}}, p, {"running_start": rs(run_minutes=20)}, today="2026-10-05")["candidates"][1]["plans"]
weeks = {}
for k, v in plans.items():
    mon = (dt.date.fromisoformat(k) - dt.timedelta(days=dt.date.fromisoformat(k).weekday())).isoformat()
    for s in v["sessions"]:
        if s["sport"] == "run" and "calibration" not in s["name"].lower() and "brick" not in s["name"].lower():
            weeks.setdefault(mon, []).append(s["minutes"])
first = weeks[sorted(weeks)[0]]
check(f"a 20-minute new runner gets one 10-minute run a week to start ({first})", first == [10])
check("…then up to 10% a week, never jumping", all(max(weeks[b]) <= max(weeks[a]) * 1.1 + 5 for a, b in zip(sorted(weeks), sorted(weeks)[1:])))
held = S.build({"plans": {}}, p, {"running_start": cur}, today="2026-10-05")["candidates"][1]["plans"]
two = sorted({k for k, v in held.items() if any(s["sport"] == "run" for s in v["sessions"])})
check("a current runner's runs a week never exceed what they do", all(
    sum(1 for k, v in held.items() if any(s["sport"] == "run" for s in v["sessions"])
        and (dt.date.fromisoformat(k) - dt.timedelta(days=dt.date.fromisoformat(k).weekday())).isoformat() == m) <= 3
    for m in {(dt.date.fromisoformat(k) - dt.timedelta(days=dt.date.fromisoformat(k).weekday())).isoformat() for k in two}))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
