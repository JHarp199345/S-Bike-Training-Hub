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
weekly = [x for x in learned["block_learning"] if x.get("score") is not None]
check(f"weeks of too-easy runs grow the block week by week ({base['reference_points']} -> {learned['reference_points']})",
      learned["reference_points"] > base["reference_points"] and len(weekly) >= 2)
check("…by 1-10% a week, scored on how easily the runs were absorbed",
      all(1.0 <= 100 * (x["to"] / x["from"] - 1) <= 10.05 and 0 <= x["score"] <= 1 for x in weekly))
check("each step says why", learned["block_learning"] and all(s["why"] and s["to"] != s["from"] for s in learned["block_learning"]))
check("the first run's easy heart rate is evidence", "heart-rate reserve" in learned["block_learning"][0]["why"])

hard = damage.remodeling_response(dates, doses(), feet_reports=reports(), runs=runs(hrr=0.9))
check("a first run near the top of the heart-rate reserve isn't evidence of spare capacity",
      not any("heart-rate reserve" in s["why"] for s in hard["block_learning"]))

rough = damage.remodeling_response(dates, doses(), feet_reports=reports(rough_after=10), runs=runs())
steps = rough["block_learning"]
k = next((n for n, s in enumerate(steps) if "rough" in s["why"]), None)
check("rough mornings after a run shrink the block", k is not None and steps[k]["to"] < steps[k]["from"])
check("…and it can't grow past its earlier size until two clean runs in a row confirm it",
      k is not None and len(steps) > k + 1 and steps[k + 1]["to"] <= steps[k]["from"])

one = damage.learn_block(dates, [30.0 if i in (0, 9) else 0 for i in range(len(dates))], reports(), runs(), 30.0)[1]
check("one in-band run in a week grows it at most 5%",
      all(x["to"] / x["from"] <= 1.0501 for x in one if x.get("score") is not None))
feel = damage.learn_block(dates, doses(), reports(), {d: {"hrr": None, "eff": None} for d in dates}, 30.0)[1]
check("feelings without heart-rate evidence grow it at most 3% a week",
      feel and all(x["to"] / x["from"] <= 1.035 for x in feel if x.get("score") is not None))
light = [3.0 if i in RUNS else 0 for i in range(len(dates))]
check("runs below the band (0.8 blocks) aren't evidence",
      not [x for x in damage.learn_block(dates, light, reports(), runs(), 30.0)[1] if x.get("score") is not None])
weekly_runs = [20.0 if i in (0, 7, 14, 21) else 0 for i in range(len(dates))]     # 0.85-0.97 blocks carried, a week apart
as_said = damage.learn_block(dates, weekly_runs, reports(feet=3, legs=3), runs(hrr=0.9), 30.0)[1]
check("a week that felt as predicted holds", not [x for x in as_said if x.get("score") is not None])
drifty = {d: {**v, "drift": 9.0, "minutes": 40} for d, v in runs().items()}
check("heart-rate drift of 8% or more holds growth",
      not [x for x in damage.learn_block(dates, doses(), reports(), drifty, 30.0)[1] if x.get("score") is not None])
said = {d: {**v, "effort": "too_easy"} for d, v in runs().items()}
mid = reports(feet=3, legs=3)
check("the athlete saying 'too easy' counts when the mornings are only a little better than predicted",
      len([x for x in damage.learn_block(dates, [20.0 if i in RUNS else 0 for i in range(len(dates))], mid, said, 30.0)[1] if x.get("score") is not None])
      >= len([x for x in damage.learn_block(dates, [20.0 if i in RUNS else 0 for i in range(len(dates))], mid, runs(), 30.0)[1] if x.get("score") is not None]))

slow = damage.remodeling_response(dates, doses(), feet_reports=reports(), runs=runs(slower_from=10))
check("running slower at the same heart rate shrinks it too", any("slowed" in s["why"] for s in slow["block_learning"]))

# Calibration from completed training: clean run/walks the starting block reads as piling up
WARM = {0, 4, 7, 11, 14, 18, 21, 25}
warm = [33.0 if i in WARM else 0 for i in range(len(dates))]
ev = {dates[i]: {"hrr": 0.62, "eff": 0.11} for i in WARM}
cal = damage.remodeling_response(dates, warm, feet_reports=reports(), block=33.0, runs=ev)
uncal = damage.remodeling_response(dates, warm, feet_reports=reports(), block=33.0)
check(f"clean training the block reads as piling up recalibrates it ({uncal['score']} -> {cal['score']} blocks, block "
      f"{cal['reference_points']} pts)", any(x.get("calibration") for x in cal["block_learning"]) and uncal["score"] > 10)
check("…so the training the athlete absorbed sits back under the line, not past the cliff",
      max(c["after_blocks"] for c in cal["components"]) < 1.5)
sore = damage.remodeling_response(dates, warm, feet_reports=reports(feet=4, legs=3), block=33.0, runs=ev)
check("not when the mornings weren't clean", not any(x.get("calibration") for x in sore["block_learning"]))
hop = {**reports(), dates[2]: {"feet": 2, "legs": 3, "hops": 20}, dates[5]: {"feet": 2, "legs": 3, "hops": 16}}
hop_steps = damage.remodeling_response(dates, warm, feet_reports=hop, block=33.0, runs=ev)["block_learning"]
check("not within two weeks of a hop-test drop", not any(x.get("calibration") and x["date"] <= dates[5 + 14] for x in hop_steps))

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
