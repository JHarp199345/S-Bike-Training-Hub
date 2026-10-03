"""Running load targets in the coaching outlook (the rider's design, 2026-10-03): build running in 0.8-1.5 blocks,
waved light/middle/heavy week to week; keep a third (0.4) for maintenance when running isn't the focus;
negative reports deload to 0.4 automatically, then 0.1 if they persist, and come back in at 0.8; and the
planned weekly running load can't jump more than 15% over recent weeks."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
from unittest.mock import patch
import coaching_review as C
import progression

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


TODAY = "2026-07-06"
OPEN = {"status": "open_for_review", "reasons": []}
day = lambda n: (dt.date(2026, 7, 6) + dt.timedelta(days=n)).isoformat()


def coach(run_days=(0, 2, 4), **extra):
    d = {"plans": {day(n): {"sessions": [{"sport": "run", "minutes": 30, "name": "Easy run"}]} for n in run_days},
         "program_goal": {"start": "2026-06-29"}, "checkins": {}, "training_feedback": {}}
    d.update(extra)
    return d


def daily(*after, dose=0.3):
    return [{"date": day(n), "readings": [{"key": "run_mechanical", "after": b, "session_dose": dose, "limit": 1.5}]}
            for n, b in enumerate(after)]


def reading(d, peaks, phase="build", purpose="aerobic", gate=OPEN, symptoms=(), load=None):
    with patch.object(progression, "context", return_value={"phase": phase, "purpose": purpose}), \
         patch.object(progression, "active_symptoms", return_value=list(symptoms)):
        return C.running_progression(d, load or {}, TODAY, daily(*peaks), gate)


# build: the wave
r = reading(coach(), (0.4, 0, 0.5, 0, 0.45))
check(f"a build week whose runs land at 0.5 blocks is under target ({r['mode']}, {r['target_blocks']})",
      r["status"] == "under_target" and r["planned_week_peak_blocks"] == 0.5 and r["mode"].startswith("build"))
waves = []
for monday in ("2026-07-06", "2026-07-13", "2026-07-20"):
    waves.append(C._wave(coach(), monday))
check(f"build weeks wave light, middle, heavy ({waves})", sorted(waves) == ["heavy", "light", "middle"])
check("the wave stays inside 0.8-1.5", all(C.RUN_BAND[0] <= lo < hi <= C.RUN_BAND[1] for lo, hi in C.RUN_WAVE.values()))
check("only the load on run days counts (a carried peak on a rest day isn't a run at that load)",
      reading(coach(run_days=(0,)), (0.9, 1.4))["planned_week_peak_blocks"] == 0.9)
check("one-third maintenance when running isn't the focus", reading(coach(), (0.4, 0, 0.4), purpose="maintain")["status"] == "on_target"
      and C.RUN_TARGETS["maintain"] == (.3, .5))
check("taper doesn't ask for more", reading(coach(), (0.5,), phase="taper")["status"] == "on_target")
check("a running hold means no added load", reading(coach(), (0.3,), gate={"status": "hold", "reasons": ["x"]})["status"] == "held")
check("an unresolved symptom means no added load", reading(coach(), (0.3,), symptoms=[{"regions": ["calves"]}])["status"] == "held")

# automatic deload
sore = {"2026-07-04:0": {"date": "2026-07-04", "sport": "run", "symptoms": [{"location": "calf_belly", "severity": 4}], "effort": "as_intended"}}
r = reading(coach(training_feedback=sore), (0.9, 0, 0.8))
check(f"calf tightness in a run report deloads running to 0.4 automatically ({r['mode']}, {r['target_blocks']})",
      r["deload"] and r["deload"]["status"] == "deload" and r["target_blocks"] == [0.3, 0.4] and r["status"] == "over_target")
awful = {"2026-07-05:0": {"date": "2026-07-05", "sport": "run", "symptoms": [], "effort": "too_hard"}}
check("a run that felt awful deloads too", reading(coach(training_feedback=awful), (0.3,))["deload"]["status"] == "deload")
check("legs 6/10 in the morning deloads too",
      reading(coach(checkins={"2026-07-05": {"legs": 6, "feet": 3}}), (0.3,))["deload"]["status"] == "deload")
check("a hop-test drop deloads too",
      reading(coach(checkins={"2026-07-01": {"hops": 20}, "2026-07-05": {"hops": 15}}), (0.3,))["deload"]["status"] == "deload")
breath = reading(coach(checkins={"2026-07-05": {"legs": 6, "breathing": 7}}), (0.3,))
check("shortness of breath is a whole-body warning, not just a running one", "doctor" in breath.get("whole_body_warning", ""))
persist = {f"2026-06-{n}": {"legs": 6, "feet": 4} for n in (24, 27, 30)} | {"2026-07-03": {"legs": 6, "feet": 4}}
check("still negative after a week at 0.4: deeper, to 0.1",
      reading(coach(checkins=persist), (0.2,))["deload"]["status"] == "deep_deload")
long_ = {f"2026-06-{n}": {"legs": 6, "feet": 4} for n in (20, 23, 26, 29)} | {"2026-07-02": {"legs": 6, "feet": 4}, "2026-07-05": {"legs": 6, "feet": 4}}
check("two weeks of negative reports: stop running and get assessed", reading(coach(checkins=long_), (0.2,))["status"] == "stop")
back = {"2026-06-26": {"legs": 6, "feet": 3}, "2026-06-28": {"legs": 2, "feet": 2}, "2026-06-29": {"legs": 2, "feet": 2},
        "2026-07-01": {"legs": 2, "feet": 2}}
r = reading(coach(checkins=back), (0.85,))
check(f"after a week and two clean mornings, running comes back in at 0.8 ({r['mode']})", r["mode"] == "re_entry" and r["status"] == "on_target")
early = {"2026-07-02": {"legs": 6, "feet": 3}, "2026-07-03": {"legs": 2, "feet": 2}, "2026-07-04": {"legs": 2, "feet": 2}}
check("…but not before the week is up, however good the mornings", reading(coach(checkins=early), (0.3,))["deload"]["status"] == "deload")
check("clean reports: no deload", reading(coach(checkins={"2026-07-05": {"legs": 3, "feet": 2}}), (0.9,))["deload"] is None)

# weekly cap on absolute running load
hist = {"days": [{"date": day(-n), "sports": {"run": {"impact": 30 if n in (2, 5, 9, 12, 16, 19) else 0}}} for n in range(1, 22)],
        "systems": {"impact": {"tissue": {"remodeling": {"reference_points": 60}}}}}
r = reading(coach(), (0.9, 0, 1.0, 0, 1.1), load=hist)
check(f"the weekly cap is 15% over the most of the last three weeks ({r['prior_weeks_blocks']} -> cap {r['weekly_cap_blocks']})",
      r["weekly_cap_blocks"] == round(1.0 * 1.15, 2))
big = reading(coach(), (0.9, 0, 1.0, 0, 1.1, 0, 1.2), load=hist)       # 7 days x 0.3 blocks of running = 2.1
check(f"a week planning more than the cap says spread the increase ({big['planned_week_blocks']} > {big['weekly_cap_blocks']})",
      big["planned_week_blocks"] > big["weekly_cap_blocks"] and "spread the increase" in big["advice"])
small = reading(coach(), (0.9,), load=hist)
check("a week under the cap doesn't", "cap" not in small["advice"])

held, _ = C.run_hold({"status": "hold", "reasons": ["hop test first: 10 pain-free single-leg hops on the worse leg clears you to run"]}, TODAY)
check("a due hop test holds only today's run (the athlete hops that morning)", held(TODAY) and not held("2026-07-08"))
held, clear = C.run_hold({"status": "hold", "reasons": ["mechanical running load 1.70 blocks exceeds the 1.5-block planning limit",
                                                         "hop test first: 10 hops"], "model_days": 3}, TODAY)
check(f"load plus a due hop test: held until the projected clear date ({clear})", held("2026-07-08") and not held("2026-07-09"))
held, _ = C.run_hold({"status": "hold", "reasons": ["hop test: 6 pain-free hops - 10 clears you to run"]}, TODAY)
check("a failed hop test holds every run until reviewed", held("2026-07-19"))
check("an open gate holds nothing", not C.run_hold({"status": "open_for_review"}, TODAY)[0](TODAY))
cal = coach(run_days=(0, 2))
cal["plans"][day(0)]["test"] = "run_calibration"
r = reading(cal, (1.3, 0, 0.9))
check(f"a running calibration (about one block on purpose) isn't judged against the target ({r['planned_week_peak_blocks']})",
      r["planned_week_peak_blocks"] == 0.9)

# a calibration run is a measurement: the forecast limit doesn't judge it
import coaching_review as CR, training_block as TB
calib = {"plans": {day(1): {"test": "run_calibration", "sessions": [{"sport": "run", "minutes": 60, "name": "Running calibration"}]}},
         "checkins": {}, "training_feedback": {}}
over = {day(1): {"date": day(1), "metrics": [{"key": "run_mechanical", "before": 0.4, "after": 1.9, "limit": 1.5}]}}
with patch.object(TB, "projected_loads", return_value=over), patch.object(TB, "running_gate", return_value=OPEN), \
     patch.object(progression, "context", return_value={"phase": "build", "purpose": "aerobic"}), \
     patch.object(progression, "active_symptoms", return_value=[]):
    rows = CR.outlook(calib, {}, {}, [], TODAY, 3)["sessions"]
check(f"a calibration run forecast over the line is a test, not a conflict ({[r['status'] for r in rows]})",
      [r["status"] for r in rows] == ["test"])

# the target and the runs it judges are the same calendar week (no flip-flop across the week boundary)
with patch.object(progression, "context", return_value={"phase": "build", "purpose": "aerobic"}), \
     patch.object(progression, "active_symptoms", return_value=[]):
    sat = C.running_progression(coach(), {}, "2026-07-11", [], OPEN)
    tue = C.running_progression(coach(), {}, "2026-07-07", [], OPEN)
check(f"from the weekend on, next week is judged ({sat['week']})", sat["week"] == ["2026-07-13", "2026-07-19"])
check(f"midweek, the rest of this week ({tue['week']})", tue["week"] == ["2026-07-07", "2026-07-12"])
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
