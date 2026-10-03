"""Training rules (the rider's design, 2026-10-03): which patterns work together and which don't. Each breaking
pattern is caught, the allowed ones aren't flagged, generated starter programs come out clean, and a reviewed
change can't introduce a breaking pattern."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import collections
import datetime as dt
import program_builder as B
import starter_programs as S
import training_rules as R

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


D = lambda n: (dt.date(2026, 6, 1) + dt.timedelta(days=n)).isoformat()
run = lambda name="Easy run", tier="easy": {"sport": "run", "minutes": 30, "name": name, "tier": tier}
ride = lambda name="Easy endurance ride", tier="easy": {"sport": "ride", "minutes": 45, "name": name, "tier": tier}
swim = lambda name="Basic swim technique", tier="easy": {"sport": "swim", "minutes": 30, "name": name, "tier": tier}
gym = lambda focus="full", name=None: {"sport": "gym", "minutes": 40, "name": name or f"Strength: {focus}", "lift_focus": focus}


def rules(days, options=None):
    plans = {D(n): {"sessions": ss} for n, ss in days.items()}
    found = R.check({"plans": plans, "program_goal": {"schedule_options": options or {}}}, D(0), D(13))
    return {f["rule"] for f in found}, found


check("a hard run the day after leg lifting breaks a rule", "hard_after_legs" in rules({0: [gym("lower")], 1: [run("Steady run", "moderate")]})[0])
check("…an easy run after leg lifting is fine", "hard_after_legs" not in rules({0: [gym("lower")], 1: [run()]})[0])
check("…a hard ride after upper-body lifting is fine", "hard_after_legs" not in rules({0: [gym("upper")], 1: [ride("Tempo ride", "moderate")]})[0])
check("…a strength check (one comfortable set) doesn't count", "hard_after_legs" not in
      rules({0: [{**gym("full", "Strength check"), "shape": "check"}], 1: [run("Running calibration", "easy")]})[0])
check("two sessions on the same tissue the same day break a rule", "same_tissue_double" in rules({0: [swim(), gym("upper")]})[0])
check("…a swim with a run is fine", "same_tissue_double" not in rules({0: [swim(), run()]})[0])
check("…a brick (ride then run) is fine", "same_tissue_double" not in rules({0: [ride(), run("Brick run (straight off the bike)")]})[0])
check("full-body lifting two days running breaks a rule", "full_body_48h" in rules({0: [gym()], 1: [gym()]})[0])
check("…a split rotating focuses is fine", not {"full_body_48h", "region_48h"} & rules({0: [gym("upper_push")], 1: [gym("knee")]})[0])
lifted = lambda regions: {"sport": "gym", "minutes": 40, "name": "Custom", "lifts": [{"name": "x", "regions": {r: 50 for r in regions}}]}
check("a region trained two days running breaks a rule", "region_48h" in rules({0: [lifted(["quads"])], 1: [lifted(["quads", "glutes"])]})[0])
check("more lifting days in a row than the split allows breaks a rule",
      "lift_days_in_row" in rules({n: [gym(f)] for n, f in enumerate(["knee", "hip", "upper_push", "upper_pull", "knee"])}, {"max_lift_days_in_row": 4})[0])
check("two hard rides within 48 h break a rule", "hard_same_sport_48h" in rules({0: [ride("Tempo ride", "moderate")], 1: [ride("Interval ride", "hard")]})[0])
check("…hard days 48 h apart are fine", "hard_same_sport_48h" not in rules({0: [ride("Tempo ride", "moderate")], 2: [ride("Interval ride", "hard")]})[0])
cal = {0: [run("Running calibration (up to 60 min, zone 2)")], 4: [run()]}
plans = {D(n): {"sessions": ss} for n, ss in cal.items()}
plans[D(0)]["test"] = "run_calibration"
check("a run in a calibration's eight-day watch breaks a rule", "calibration_watch" in {f["rule"] for f in R.check({"plans": plans}, D(0), D(13))})
r, found = rules({0: [run()], 1: [run()]})
check("back-to-back runs are a caution, not a break (the block decides)", "runs_back_to_back" in r and
      all(f["severity"] == "caution" for f in found if f["rule"] == "runs_back_to_back"))
check("two hard runs and two leg sessions in a week: a caution",
      "legs_peak_together" in rules({0: [run("Steady run", "moderate")], 2: [gym("lower")], 4: [run("Race-pace run", "moderate")], 6: [gym("legs")]})[0])

# generated programs follow the rules
for hours, split in ((4, "full_body"), (7, "upper_lower"), (9, "four_way")):
    f = {"start": "2026-10-05", "target": "2026-12-27", "sport": "tri", "hours": hours, "goal": "Sprint", "assessment": "week",
         "starter_level": "moderate", "priorities": {"ride": "improve", "swim": "improve", "run": "improve", "gym": "improve"},
         "schedule_options": {"lift_split": split, "allow_doubles": True, "rest_days": []}}
    p = B.propose({"plans": {}}, f, "2026-10-05", {"status": "open_for_review"})
    breaks = collections.Counter(x["rule"] for c in S.build({"plans": {}}, p, today="2026-10-05")["candidates"]
                                 for x in c["training_rules"] if x["severity"] == "breaks")
    check(f"a {hours}-hour {split} starter program breaks no rule ({dict(breaks)})", not breaks)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
