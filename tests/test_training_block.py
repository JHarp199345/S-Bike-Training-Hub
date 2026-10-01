"""The weekly program uses the existing Sunday check-in and all scheduled sessions."""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import coach
import training_block as B
import weekly


def main():
    d = {"plans": {}, "weekly": {}, "events": [], "checkins": {}}
    coach.set_sessions(d, "2026-09-28", [
        {"sport": "ride", "minutes": 40, "name": "Easy ride"},
        {"sport": "swim", "minutes": 30, "name": "Easy swim"}])
    coach.set_sessions(d, "2026-09-30", [{"sport": "run", "minutes": 20, "name": "Easy run"}])
    coach.set_sessions(d, "2026-10-12", [{"sport": "swim", "minutes": 35, "name": "Coach override"}])
    B.create(d, "2026-09-30")
    f = B.forecast(d, "2026-09-30")
    assert len(f["weeks"]) == 4
    assert [w["total_minutes"] for w in f["weeks"]] == [90, 90, 55, 90]
    assert len(d["plans"]["2026-10-05"]["sessions"]) == 2
    assert d["plans"]["2026-10-12"]["sessions"][0]["name"] == "Coach override"
    done = {"2026-09-28": [{"sport": "bike", "minutes": 40}, {"sport": "swim", "minutes": 30}],
            "2026-09-30": [{"sport": "run", "minutes": 20}]}
    d["weekly"]["2026-10-04"] = {"week": 3, "legs": 3, "shoulders": 3, "feet": 3,
                                   "progress": {"bike": "same", "swim": "same", "run": "better"}}
    r = B.review(d, "2026-10-04", done)
    assert r["decision"] == "advance" and r["adherence"] == 1
    assert r["by_sport"] == {"ride": "advance", "swim": "advance", "run": "advance"}
    del d["weekly"]["2026-10-04"]["progress"]
    assert B.review(d, "2026-10-04", done)["decision"] == "hold"
    d["weekly"]["2026-10-04"]["progress"] = {"bike": "same", "swim": "same", "run": "better"}
    # Extra unplanned cycling cannot disguise an uncompleted run.
    done["2026-09-30"] = [{"sport": "bike", "minutes": 200}]
    r = B.review(d, "2026-10-04", done)
    assert r["by_sport"]["run"] == "repeat" and r["decision"] != "advance"
    d["weekly"]["2026-10-04"]["feet"] = 8
    r = B.review(d, "2026-10-04", done)
    assert r["decision"] == "reduce" and r["by_sport"]["run"] == "reduce"
    future = {"plans": {}, "events": []}
    coach.set_sessions(future, "2026-10-05", [{"sport": "swim", "minutes": 40, "name": "Easy swim"}])
    B.create(future, "2026-09-30", start_date="2026-10-05")
    assert future["training_block"]["start"] == "2026-10-05"
    try:
        B.create({"plans": {"2026-10-06": {"sport": "swim", "minutes": 40}}}, "2026-09-30", start_date="2026-10-06")
        assert False, "non-Monday start was accepted"
    except ValueError:
        pass
    paused = {"events": [{"kind": "race", "sport": "run", "date": "2027-01-17"}], "lifting": {}}
    prompts = [q["key"] for q in weekly.questions(paused, __import__("datetime").date(2026, 10, 11), {})["questions"]]
    assert "feet" in prompts and "hops" not in prompts
    load = {"headline": {"mechanical": {"remodeling_blocks": 13.25, "block_limit": 1.5}}}
    gate = B.running_gate({"training_block": {"hop_status": "unresolved"}}, load)
    assert gate["status"] == "hold" and "mechanical running load" in gate["reasons"][0]
    blocked = {"plans": {}, "events": []}
    coach.set_sessions(blocked, "2026-10-05", [{"sport": "run", "minutes": 20, "name": "Easy run"}])
    try:
        B.create(blocked, "2026-09-30", start_date="2026-10-05", run_gate=gate)
        assert False, "run week repeated despite mechanical hold"
    except ValueError as e:
        assert "mechanical running load" in str(e)
    assert "2026-10-12" not in blocked["plans"]
    d["weekly"]["2026-10-04"]["feet"] = 3
    r = B.review(d, "2026-10-04", done, gate)
    assert r["by_sport"]["run"] == "hold" and r["decision"] == "hold"
    import copy
    forecast_plan={"plans":{"2026-10-01":{"sessions":[{"sport":"swim","name":"Planned swim","minutes":30,"swim_profile":"balanced","swim_plan":{"stroke_mix":{"free":100},"work_mix":{"swim":100},"why":"Maintain aerobic work"}}]},
                            "2026-10-02":{"sessions":[{"sport":"swim","name":"Second swim","minutes":30}]}}}
    load={"swim_recovery":{"recent":.5,"history_component":.1,"reference_units":1000,"threshold_blocks":1.5},
          "activities":[{"sport":"swim","date":"2026-09-29","minutes":30,"engine":20,"swim_exposure":{"units":300,"by_stroke":{"freestyle":300}}}]}
    original=copy.deepcopy(forecast_plan)
    estimates=B.swim_plan_forecast(forecast_plan,"2026-09-30",load)
    first=estimates[("2026-10-01",0)];second=estimates[("2026-10-02",0)]
    assert first["raw_blocks"]==.3 and first["after_blocks"]>first["before_blocks"] and first["cardio_points"]==20
    assert first["why"]=="Maintain aerobic work" and first["stroke_mix"]=={"free":100}
    alone=copy.deepcopy(forecast_plan);del alone["plans"]["2026-10-01"]
    assert second["before_blocks"]>B.swim_plan_forecast(alone,"2026-09-30",load)[("2026-10-02",0)]["before_blocks"]
    assert forecast_plan==original
    unknown=B.swim_plan_forecast(forecast_plan,"2026-09-30",{})[("2026-10-01",0)]
    assert unknown["after_blocks"] is None and unknown["cardio_points"] is None
    completed={"2026-10-01":[{"sport":"swim","minutes":30}]}
    assert ("2026-10-01",0) not in B.swim_plan_forecast(forecast_plan,"2026-10-01",load,completed)
    clean={"plans":{}};coach.set_sessions(clean,"2026-10-01",forecast_plan["plans"]["2026-10-01"]["sessions"])
    assert clean["plans"]["2026-10-01"]["sessions"][0]["swim_plan"]["why"]=="Maintain aerobic work"
    # Solid history comes only from recorded model values, never from forecasts.
    recorded={"days":[{"date":"2026-09-29","engine":{"fatigue":37.5,"fitness":17.2},
                       "impact":{"fatigue":14},"muscle":{"fatigue":11.2}},
                      {"date":"2026-09-30","engine":{"fatigue":99}},
                      {"date":"2026-10-01","engine":{"fatigue":123}}],
              "systems":{"impact":{"tissue":{"remodeling":{"history":[{"date":"2026-09-29","score":13.25}],
                                                                  "projection":[{"date":"2026-10-01","score":10}]}}}},
              "swim_recovery":{"history":[{"date":"2026-09-29","score":.53}]}}
    snapshot=copy.deepcopy(recorded)
    hist=B.recorded_load_history(recorded,"2026-09-30")
    assert len(hist)==1 and hist[0]["date"]=="2026-09-29"
    metrics={m["key"]:m["after"] for m in hist[0]["metrics"]}
    assert metrics["cardio_fatigue"]==37.5 and metrics["run_mechanical"]==13.25
    assert metrics["swim_recovery"]==.53 and "strength" not in metrics
    assert recorded==snapshot and B.recorded_load_history({},"2026-09-30")==[]
    assert B.forecast({"plans":{},"checkins":{}},"2026-09-30")["load_history"]==[]
    print("training block PASS\nALL PASS")


if __name__ == "__main__":
    main()
