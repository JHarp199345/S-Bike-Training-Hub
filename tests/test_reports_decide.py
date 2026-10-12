"""The athlete's reports set the daily verdicts; model readings (load ratios, blocks, lifting carry-over) are evidence."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import loads
assert loads.REPORTS_DECIDE

heavy = {"systems": {"impact": {"tissue": {"remodeling": {"score": 2.4, "phase": "plateau", "threshold_blocks": 1.5,
                                                           "hops": {"last": 4, "needed": 10, "fresh": True}},
                                           "event": {"score": 1.2}}, "acwr": None},
                     "engine": {"acwr": 1.6, "tuned": True, "form": -40, "last7": 3, "prev7": 1},
                     "muscle": {"acwr": 1.7, "tuned": True, "form": 0, "last7": 3, "prev7": 1}},
         "days": [], "history_days": 30, "swim_recovery": {"score": 2.0, "threshold_blocks": 1.5},
         "lifting": {"regions": {"quads": {"name": "Quads", "blocks": 2.0}, "shoulders": {"name": "Shoulders", "blocks": 2.0}}}}

r = loads.readiness(heavy, {"feet": 2, "legs": 2, "breathing": 2, "shoulders": 1})
assert r["verdict"] == "go" and r["running"]["verdict"] == "go" and r["swimming"]["verdict"] == "go", r
assert any("blocks" in w for w in r["running"]["why"] if w.startswith("evidence to weigh")), "the blocks still show, as evidence"
assert any(w.startswith("evidence to weigh") for w in r["swimming"]["why"]) and r["evidence"]
assert r["systems"]["impact"]["model_level"] == "rest", "the model's own reading is kept for reference"

# what the athlete reports still decides
assert loads.readiness(heavy, {"feet": 8})["running"]["verdict"] == "rest"
assert loads.readiness(heavy, {"legs": 6})["verdict"] == "easy"
assert loads.readiness(heavy, {"shoulders": 8})["swimming"]["verdict"] == "rest"
assert loads.readiness(heavy, {"breathing": 8})["verdict"] == "rest"
print("PASS reports decide: model readings and blocks are evidence; feet, legs, shoulders and breathing reports set the verdict")
