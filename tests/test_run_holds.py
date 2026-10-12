"""Running holds come only from reports and the athlete's own choices; model readings and checklists are evidence."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import recovery

today = "2026-10-11"
s = recovery.status({"checkins": {}}, {"response_model": True}, today)
assert not s["run_hold_reasons"], s["run_hold_reasons"]
assert any("checks" in e for e in s["run_evidence"]), "the functional-check checklist is evidence"
legacy = recovery.status({"checkins": {}}, {"score": 3.0, "threshold_blocks": 1.5}, today)
assert any("Mechanical" in e for e in legacy["run_evidence"]) and not any("Mechanical" in h for h in legacy["run_hold_reasons"])
sore = recovery.status({"checkins": {today: {"feet": 7}}}, {"response_model": True}, today)
assert sore["run_hold_reasons"] == ["Today's check-in does not support progression"]
waits = recovery.status({"checkins": {}, "run_progression": {"minimum_run_days": 3}}, {"response_model": True, "last_run_date": "2026-10-10"}, today)
assert any("Personal minimum wait" in h for h in waits["run_hold_reasons"]), "the athlete's own wait holds"
print("PASS run holds: reports and the athlete's wait hold; model readings and checklists are evidence")
