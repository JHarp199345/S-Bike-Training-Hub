"""The planning brief puts the obvious first and keeps detail one call away; guides and compact views lose nothing."""
import sys, pathlib, json; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import planning_context as C
import mcp_server as M

today = "2026-10-11"
acts = [{"date": "2026-10-06", "sport": "run", "minutes": 55, "km": 5.0}, {"date": "2026-10-09", "sport": "swim", "minutes": 50, "km": 2.0},
        {"date": "2026-10-08", "sport": "gym", "minutes": 34}, {"date": "2026-10-08", "sport": "bike", "minutes": 40, "km": 0}]
long_note = "felt fine " * 60
d = {"checkins": {"2026-10-11": {"hooper_fatigue": 6, "legs": 2, "journal": long_note},
                  "2026-09-20": {"hooper_fatigue": 2, "legs": 2}, "2026-09-10": {"hooper_fatigue": 2, "legs": 3}},
     "program_goal": {"goal": "Spring 10K", "target": "2027-03-01", "sport": "run", "hours": 5}}
gate = {"status": "open_for_review", "reasons": [], "evidence": ["hopping still pulls"]}

b = C.brief(d, acts, today, "program", gate=gate)
g = b["at_a_glance"]
assert g["goal"]["goal"] == "Spring 10K" and g["goal"]["days_to_event"] == 141
assert g["holds"]["running"] == "not held" and g["holds"]["evidence_to_weigh"] == ["hopping still pulls"]
assert any(f.startswith("hooper_fatigue: 6") for f in g["report_flags"]), g["report_flags"]
assert not any(f.startswith("legs") for f in g["report_flags"])
assert set(g["usual_week_by_sport"]) == {"run", "swim", "lift", "bike"}
assert g["health"]["status"] == "no health check recorded yet"
j = b["last_7_days"]["checkins"][0]["journal"]
assert j.endswith("…") and len(j) < 260, "journals are shortened in the brief"
assert all(not t.get("sports") for t in b["playbook"]), "the brief carries only the general playbook"
assert set(b["more"]) == set(C.SECTIONS) and "sport=" in b["more"]["volume"]["ask"]
full = C.context(d, acts, today, "program", gate=gate)
assert len(json.dumps(b)) < len(json.dumps(full)), "the brief is smaller than everything"

# sections: full detail, filtered to one sport where that makes sense
assert set(C.section(d, acts, today, "volume", "run", full=full)) == {"run"}
assert set(C.section(d, acts, today, "volume", full=full)) == {"run", "swim", "lift", "bike"}
swim_pb = C.section(d, acts, today, "playbook", "swim", full=full)
assert any(t["topic"] == "Swimming" for t in swim_pb) and not any(t["topic"] == "Lifting" for t in swim_pb)
assert C.section(d, acts, today, "reports", full=full)["last_7_days"]["checkins"][0]["journal"] == long_note, "reports in full keep the journal"
for bad in (("volume", "rowing"), ("nonsense", None)):
    try:
        C.section(d, acts, today, bad[0], bad[1], full=full); raise AssertionError(bad)
    except ValueError:
        pass

# guides: the core is short, every topic is named in it, and no topic is empty
assert len(M.INSTRUCTIONS) < 4000
for k, v in M.GUIDES.items():
    assert f"{k} (" in M.INSTRUCTIONS and len(v["text"]) > 100
assert M.t_guide({"topic": "lifting"})["guide"].startswith("Per-date responses") or "LIFTING SESSION" in M.t_guide({"topic": "lifting"})["guide"]
try:
    M.t_guide({"topic": "cooking"}); raise AssertionError("topic")
except ValueError:
    pass

# compact program and review views keep the decision facts and say where the rest is
program = {"goal": {"goal": "Spring 10K"}, "phases": [{"label": "Base", "start": "2026-10-12", "end": "2026-10-26", "days": 14,
           "weekly_pattern": [[{"sport": "rest"}]] * 7, "date_placements": {"2026-10-13": [{"sport": "run", "purpose": "Easy"}]}, "review_criteria": ["x"] * 50}],
           "weeks": [{"week": 1, "start": "2026-10-12", "slots": [{"sport": "run"}, {"sport": "rest"}, {"sport": "run"}]}], "capacity_review": {"notice": "n", "demands": [], "tolerance_trends": ["big"] * 100}}
c = M._program_compact(program)
assert c["phases"][0]["days_placed_by_hand"] == 1 and c["phases"][0]["weekly_template"] is False
assert c["weeks"][0]["sessions_by_sport"] == {"run": 2} and "detail=true" in c["detail"] and "tolerance_trends" not in json.dumps(c)
assert M._near({"after": 1.3, "limit": 1.5}) and not M._near({"after": 0.5, "limit": 1.5}) and M._near({"over_limit": True})
print("PASS planning brief: obvious first, sections by sport, short core with topic guides, compact program and review")
mech = M._reading({"key": "mechanical", "before": 1.7, "after": 1.5, "limit": 1, "over_limit": True, "unit": "× limit"})
assert mech["vs_usual_week"] == 1.5 and "not a limit" in mech["meaning"] and "limit" not in mech
assert M._reading({"key": "lift_trunk", "after": 1.4, "limit": 1.5})["limit"] == 1.5
print("PASS the mechanical reading is shown against the usual week, not as a limit")
