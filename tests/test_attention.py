"""The check-in attention list (the rider's design, 2026-10-03): what the assistant goes through with the athlete
at every check-in, most urgent first, each with the lightest fix. The hub only lists; it never rewrites the plan."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import copy
from unittest.mock import patch
import attention
import coach
import coaching_review

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


TODAY = "2026-07-06"
LOOK = {"sessions": [{"date": "2026-07-08", "name": "Long run", "status": "conflict", "sport": "run"},
                     {"date": "2026-07-09", "name": "Swim", "status": "within_projected_limits", "sport": "swim"}],
        "training_rules": [{"rule": "hard_after_legs", "severity": "breaks", "dates": ["2026-07-07", "2026-07-08"], "why": "legs"},
                           {"rule": "runs_back_to_back", "severity": "caution", "dates": ["2026-07-10", "2026-07-11"], "why": "block"}],
        "running_progression": {"status": "over_target", "advice": "shorten", "target_blocks": [0.3, 0.4],
                                "deload": {"status": "deload", "why": ["2026-07-05: legs 6/10 in the morning"], "ends": "no sooner than 2026-07-12"},
                                "whole_body_warning": "Short of breath: ease all training."}}


def run(look=LOOK, d=None):
    d = d or {"plans": {}, "checkins": {}}
    with patch.object(coaching_review, "outlook", return_value=copy.deepcopy(look)), \
         patch.object(coach, "missed_days", return_value={"2026-07-04": [{"name": "Swim", "reason": None}]}):
        return attention.items(d, {"activities": []}, {}, [], TODAY)


out = run()
kinds = [x["kind"] for x in out["items"]]
check(f"most urgent first ({kinds})", kinds == ["warning", "rule", "forecast", "deload", "missed", "caution"])
check("each item says what and the lightest fix", all(x["what"] and x["fix"] for x in out["items"]))
check("a missed session without a reason asks why", any(x["kind"] == "missed" and x["tool"] == "record_missed_session" for x in out["items"]))
check("the routine is spelled out for the assistant", "preview" in out["routine"] and "agrees" in out["routine"])
calm = run({"sessions": [], "training_rules": [], "running_progression": {"status": "on_target"}})
with patch.object(coaching_review, "outlook", return_value={"sessions": [], "training_rules": [], "running_progression": {"status": "on_target"}}), \
     patch.object(coach, "missed_days", return_value={}):
    calm = attention.items({"plans": {}, "checkins": {}}, {"activities": []}, {}, [], TODAY)
check(f"nothing to change: the plan stands ({calm['summary']})", not calm["items"] and "stands" in calm["summary"])
stop = run({"sessions": [], "training_rules": [], "running_progression": {"status": "stop", "advice": "Stop running and have it assessed."}})
check("two weeks of negative reports puts 'stop' first", stop["items"][0]["kind"] == "stop")
plans = {"2026-07-01": {"test": "run_calibration", "sessions": [{"sport": "run", "name": "Running calibration", "minutes": 60}]}}
with patch.object(coaching_review, "outlook", return_value={"sessions": [], "training_rules": [], "running_progression": {}}), \
     patch.object(coach, "missed_days", return_value={}):
    cal = attention.items({"plans": plans, "checkins": {}}, {"activities": [{"sport": "run", "date": "2026-07-01", "minutes": 35}]}, {}, [], TODAY)
check("a calibration stopped short asks why", [x["kind"] for x in cal["items"]] == ["calibration"] and "stopped at 35" in cal["items"][0]["what"])
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
