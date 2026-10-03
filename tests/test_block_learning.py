"""Block learning (the rider's design, 2026-10-03): the size of a running block comes from evidence -
how hard the first run was for the athlete, and whether runs that land inside an earlier run's plateau
or decline are carried without rough mornings or slower running. The curve's shape doesn't change."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import damage
import loads

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


D0 = dt.date(2026, 5, 4)
dates = [(D0 + dt.timedelta(days=i)).isoformat() for i in range(28)]
RUNS = (0, 3, 7, 10, 14, 17, 21)


def doses(dose=30.0):
    return [dose if i in RUNS else 0.0 for i in range(len(dates))]


def reports(feet=2, legs=3, rough_after=None):
    out = {d: {"feet": feet, "legs": legs} for d in dates}
    if rough_after is not None:
        for j in (rough_after + 1, rough_after + 2):
            out[dates[j]] = {"feet": 7, "legs": 4}
    return out


def runs(hrr=0.62, eff=0.11, slower_from=None):
    return {dates[i]: {"hrr": hrr, "eff": eff * (0.9 if slower_from is not None and i >= slower_from else 1)} for i in RUNS}



check("protected and legacy recovery cannot automatically rescale blocks", not loads.automatic_run_learning({}) and not loads.automatic_run_learning({'return_to_run':True}))
check("existing recovery protocol remains protected despite fresh setup", not loads.automatic_run_learning({'return_to_run':False,'_protected_run_recovery':True}))
check("reviewed recovery cannot automatically rescale blocks", not loads.automatic_run_learning({'return_to_run':False},[{'action':'begin_decline'}]))
check("ordinary training can use evidence learning", loads.automatic_run_learning({'return_to_run':False}))
middling = damage.remodeling_response(dates, doses(), feet_reports=reports(feet=4,legs=4), runs=runs())
check("middling mornings do not count as clean first-run capacity evidence", not any('heart-rate reserve' in x['why'] for x in middling['block_learning']))


anchored = damage.remodeling_response(dates, doses(), feet_reports=reports(), block=200.0, runs=runs(), learn_since=dates[9])
check("after a reviewed capacity change, learning continues from the reviewed block using only later runs",
      anchored["reference_points"] >= 200.0 and all(s["date"] > dates[9] for s in anchored["block_learning"]))
base = damage.remodeling_response(dates, doses(), feet_reports=reports())
learned = damage.remodeling_response(dates, doses(), feet_reports=reports(), runs=runs())
check(f"without run evidence nothing changes (reference {base['reference_points']}, {base['score']} blocks)",
      base["block_learning"] == [])
check(f"easy runs carried well grow the block ({base['reference_points']} -> {learned['reference_points']})",
      learned["reference_points"] > 2 * base["reference_points"])
check(f"…so the same training sits under the 1.5-block line ({base['score']} -> {learned['score']} blocks)",
      base["score"] >= 1.5 > learned["score"])
check("each step says why", learned["block_learning"] and all(s["why"] and s["to"] != s["from"] for s in learned["block_learning"]))
check("the first run's easy heart rate is evidence", "heart-rate reserve" in learned["block_learning"][0]["why"])

hard = damage.remodeling_response(dates, doses(), feet_reports=reports(), runs=runs(hrr=0.9))
check("a first run near the top of the heart-rate reserve isn't evidence of spare capacity",
      not any("heart-rate reserve" in s["why"] for s in hard["block_learning"]))

rough = damage.remodeling_response(dates, doses(), feet_reports=reports(rough_after=10), runs=runs())
check(f"rough mornings after a run shrink the block ({learned['reference_points']} vs {rough['reference_points']})",
      rough["reference_points"] < learned["reference_points"] and any("rough" in s["why"] for s in rough["block_learning"]))

slow = damage.remodeling_response(dates, doses(), feet_reports=reports(), runs=runs(slower_from=10))
check("running slower at the same heart rate shrinks it too", any("slowed" in s["why"] for s in slow["block_learning"]))

check("the plateau rule is unchanged: 5 days per block added", all(
    abs(e["plateau_days"] - max(1, 5 * e["added_blocks"])) < 0.2 or e["before_blocks"] > 0 for e in learned["components"]))
top = damage.remodeling_response(dates, [300.0 if i in RUNS else 0 for i in range(len(dates))], feet_reports=reports(),
                                 runs=runs(hrr=0.5))
check("growth is bounded (at most 6x the evidence-free block)",
      top["reference_points"] <= 6.01 * damage.remodeling_response(dates, [300.0 if i in RUNS else 0 for i in range(len(dates))],
                                                                     feet_reports=reports())["reference_points"])

# the careful return-to-run protocol only for athletes coming back from a running injury
import json, tempfile, loads
for flag, expect in ((False, None), (True, "protocol"), (None, "protocol")):
    base_dir = pathlib.Path(tempfile.mkdtemp())
    (base_dir / "rides").mkdir(); (base_dir / "activities").mkdir()
    prof = {"weight_kg": 75, "hr_rest": 58, "hr_max": 184, "ftp": 180}
    if flag is not None:
        prof["return_to_run"] = flag
    (base_dir / "profile.json").write_text(json.dumps(prof))
    (base_dir / "coach.json").write_text(json.dumps({"checkins": {}, "plans": {}}))
    rp = loads.summary(base_dir).get("run_progression")
    label = {False: "said no", True: "said yes", None: "installed before the question"}[flag]
    check(f"return-to-run protocol when the athlete {label}: {'on' if expect else 'off'}", (rp is not None) == bool(expect))

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
