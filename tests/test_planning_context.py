import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import planning_context as C
import program_builder as B

today = "2026-10-11"
acts = [  # oldest week heavy, then lighter: the four weekly totals keep that shape
    {"date": "2026-09-15", "sport": "run", "minutes": 60, "km": 8},
    {"date": "2026-09-17", "sport": "run", "minutes": 50, "km": 7},
    {"date": "2026-10-06", "sport": "run", "minutes": 55, "km": 5.0},
    {"date": "2026-10-09", "sport": "run", "minutes": 39, "km": 3.0},
    {"date": "2026-10-09", "sport": "swim", "minutes": 50, "km": 2.0},
    {"date": "2026-10-08", "sport": "gym", "minutes": 34},
    {"date": "2026-10-08", "sport": "bike", "minutes": 40, "km": 0},
    {"date": "2025-01-01", "sport": "run", "minutes": 99, "km": 20},       # far outside every window
    {"date": "bad", "sport": "run", "minutes": 10},
]
v = C.volume(acts, today)
assert set(v) == {"run", "swim", "lift", "bike"}
run = v["run"]
assert [w["sessions"] for w in run["last_28_days_by_week"]] == [2, 0, 0, 2]
assert run["last_28_days_by_week"][-1]["to"] == today and run["last_week"]["km"] == 8.0
assert run["best_week"]["km"] == 15 and run["average_week"]["km"] == round((15 + 8.0) / 4, 2)
assert run["longest_session_28d"] == {"minutes": 60.0, "km": 8.0} and len(run["trend_13_weeks"]) == 13

# reports: a 45-day half-life, and only the last 7 days verbatim
d = {"checkins": {"2026-10-11": {"hooper_fatigue": 6, "journal": "a chill", "pain": {"knee": 3}},
                  "2026-08-27": {"hooper_fatigue": 2},            # 45 days earlier: half the weight
                  "2026-06-01": {"hooper_fatigue": 7}},           # outside the 90 days
     "training_feedback": {"a": {"date": "2026-10-09", "sport": "run", "effort": "too_hard", "note": "slower"},
                           "b": {"date": "2026-09-20", "sport": "run", "effort": "as_intended"}}}
r = C.reports(d, today)
f = r["trend"]["hooper_fatigue"]
assert f["reports"] == 2 and f["latest"] == 6 and abs(f["weighted_average"] - (6 + 0.5 * 2) / 1.5) < 0.01
assert r["trend"]["pain_knee"]["latest"] == 3
recent = r["last_7_days"]
assert [c["date"] for c in recent["checkins"]] == ["2026-10-11"] and recent["checkins"][0]["journal"] == "a chill"
assert [x["note"] for x in recent["session_reports"]] == ["slower"]

# calibration: numbers only, a when for the best, at least one part
e = C.set_baseline(d, "swim", {"now": {"session_minutes": 60, "session_km": 2.3}, "best": {"session_km": 3.66, "when": "college"}}, today)
assert e["best"]["when"] == "college" and d["sport_baselines"]["swim"]["now"]["session_km"] == 2.3
for bad in ({"now": {"weekly_km": -1}}, {"now": {"weekly_km": True}}, {}, {"now": "x"}):
    try:
        C.set_baseline(d, "run", bad, today); raise AssertionError(bad)
    except ValueError:
        pass
try:
    C.set_baseline(d, "rowing", {"now": {"weekly_km": 1}}, today); raise AssertionError("rowing")
except ValueError:
    pass

# context: both scopes, the playbook and the how-to
ctx = C.context(d, acts, today, "program")
assert ctx["scope"] == "program" and "Pass 1" in ctx["how_to_plan"] and ctx["playbook"] and ctx["calibration"]["swim"]
assert C.context(d, acts, today, "week")["program"]["week"]["from"] == today
try:
    C.context(d, acts, today, "month"); raise AssertionError("scope")
except ValueError:
    pass

# the mirror describes a draft week against recent weeks
m = C.mirror(acts, today, {"2026-10-13": [{"sport": "run", "minutes": 30, "km": 3}], "2026-10-15": [{"sport": "run", "minutes": 30, "km": 3}, {"sport": "swim", "minutes": 45, "swim_recipe": {"total_distance_m": 2000}}]})
assert m["by_sport"]["run"]["planned"] == {"sessions": 2, "minutes": 60.0, "km": 6.0}
assert m["by_sport"]["run"]["km_vs_average_pct"] == round(6 / run["average_week"]["km"] * 100)
assert m["by_sport"]["swim"]["planned"]["km"] == 2.0 and m["by_sport"]["lift"]["planned"]["sessions"] == 0

# pass 1 slots keep their role, minutes band and lifting groups
assert B.slot_detail({"sport": "gym", "role": "maintain", "minutes": [30, 40], "lift_groups": ["lower", "upper"]}) == {"role": "maintain", "minutes": [30, 40], "lift_groups": ["upper", "lower"]}
assert B.slot_detail({"sport": "run", "role": "rest", "minutes": [40, 20], "lift_groups": ["upper"]}) == {}
print("PASS planning context: weekly volume, report trend, calibration, mirror, pass 1 slots")

# efficiency: runs and swims per heartbeat, rides from aerobic.py, matched by similar duration
state = {"activities": [
    {"date": "2026-09-05", "sport": "run", "minutes": 40, "km": 5.0, "avg_hr": 150},
    {"date": "2026-10-09", "sport": "run", "minutes": 41, "km": 5.2, "avg_hr": 146, "drift_pct": 6},
    {"date": "2026-10-11", "sport": "run", "minutes": 26, "km": 3.4, "avg_hr": 140},
    {"date": "2026-10-10", "sport": "run", "minutes": 5, "km": 0.5, "avg_hr": 120},          # too short to judge
    {"date": "2026-10-08", "sport": "swim", "minutes": 30, "km": 1.0, "avg_hr": None}],     # no heart rate
    "aerobic": {"rides": [{"date": "2026-10-05", "minutes": 27, "np": 128, "avg_hr": 120, "ef": 1.06, "decoupling_pct": 25.2, "hr_at_band": 118}]}}
e = C.efficiency(state, today)["by_sport"]
assert set(e) == {"run", "bike"}
runs = {c["session"]["date"]: c for c in e["run"]["matched_comparisons"]}
assert runs["2026-10-09"]["match"]["date"] == "2026-09-05"               # 39 min matches 40 min
assert runs["2026-10-09"]["avg_hr_change"] == -4 and runs["2026-10-09"]["efficiency_change_pct"] > 0
assert runs["2026-10-11"]["match"] is None                               # 26 min has no earlier similar run
assert e["run"]["trend"]["sessions"] == 2 and e["run"]["trend"]["previous_sessions"] == 1 and "change_pct" in e["run"]["trend"] and e["bike"]["sessions_90_days"][0]["hr_at_110w"] == 118
assert abs(e["run"]["sessions_90_days"][-1]["efficiency"] - 3400 / 26 / 140) < 0.001
assert C._match([{"date": "2026-10-01", "minutes": 30}, {"date": "2026-10-05", "minutes": 30}], {"date": "2026-10-09", "minutes": 30})["date"] == "2026-10-05"
assert "efficiency" in C.context({}, state["activities"], today, "week", state=state)
print("PASS planning context efficiency: per-heartbeat efficiency, matched comparisons, trend")
