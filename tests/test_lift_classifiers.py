"""Lifting classifiers: type, duration, intensity (% of each lift's max or its last time), style, and the design context."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import lifting_framework as F

LB = 0.45359237
logs = [{"date": "2026-10-01", "lifts": [{"name": "Hip thrust machine", "weight": 200, "reps": 10, "sets": 3, "regions": {"glutes": 0.7, "hamstrings": 0.3}}]},
        {"date": "2026-10-05", "lifts": [{"name": "Lat pulldown", "weight": 100, "reps": 10, "sets": 3, "regions": {"lats": 0.6, "biceps": 0.4}}]}]
strength = {"hip thrust machine": {"e1rm_kg": 280 * LB}, "lat pulldown": {"e1rm_kg": 150 * LB}}

assert [F.style_of(*x) for x in ((3, 10), (2, 20), (6, 3), (2, 4))] == ["standard", "endurance", "power_explosive", "power_heavy"]
assert [F.load_level(p) for p in (45, 61, 75, 90, 106)] == ["light", "medium", "medium", "heavy", "maximal"]

# Type 2 (upper + trunk), Duration 1, medium, standard; each lift against its own last time
c = F.classify([{"name": "Hip thrust machine", "weight": 200, "reps": 10, "sets": 3, "regions": {"glutes": 0.7, "hamstrings": 0.3}},
                {"name": "Lat pulldown", "weight": 105, "reps": 10, "sets": 3, "regions": {"lats": 0.6, "biceps": 0.4}},
                {"name": "Dead bug", "section": "minor", "sets": 2, "reps": 8, "regions": {"abs": 1}}],
               logs, strength, "2026-10-12")
assert c["type"] == 2 and c["groups"] == ["upper", "trunk"] and c["duration"] == 1, c
assert c["intensity"] == "medium" and c["style"] == "standard" and c["minors"] == ["Dead bug"]
lat = next(x for x in c["exercises"] if x["name"] == "Lat pulldown")
assert lat["pct_of_estimated_max"] == 70 and lat["pct_of_last_time"] == 105 and lat["last_time"]["date"] == "2026-10-05"
assert c["label"] == "Type 2 · Duration 1 · Medium · Standard"

# no max known: intensity from what was moved last time
c2 = F.classify([{"name": "Hip thrust machine", "weight": 100, "reps": 10, "sets": 3, "regions": {"glutes": 1}}], logs, {}, "2026-10-12")
assert c2["exercises"][0]["pct_of_last_time"] == 50 and c2["intensity"] == "light" and c2["type"] == 1

# design context: rules respected, a target weight from the max, minors by sport and week
state = {"logs": logs, "strength": strength, "rules": [{"text": "No barbell deadlifts", "kind": "never", "excludes": "barbell deadlifts"}],
         "library": {"barbell deadlifts": {"name": "Barbell deadlifts", "shares": {"glutes": 0.5, "hamstrings": 0.5}}}}
ctx = F.design_context(state, ["trunk", "upper"], 2, "medium", "standard", "2026-10-12", ["swim"])
assert ctx["target"]["main_exercises"] == 4 and ctx["target"]["intensity"]["aim_pct"] == 70
names = [x["name"] for x in ctx["candidates_by_group"]["trunk"]]
assert "Hip thrust machine" in names and "Barbell deadlifts" not in names, "a 'No ...' rule removes the lift"
hip = ctx["candidates_by_group"]["trunk"][0]
assert hip["target_weight"] == 195 and hip["last_time"]["total"] == 6000
assert ctx["minors"]["sport_support"][0] == "Band external rotation" and ctx["minors"]["core"]["this_week"] in ("anti-rotation", "rotation")
for bad in ((["arms"], 1, "medium", "standard"), (["upper"], 1, "max", "standard"), (["upper"], 1, "light", "pump")):
    try:
        F.design_context(state, *bad, "2026-10-12"); raise AssertionError(bad)
    except ValueError:
        pass
# a lift logged twice in one session (warm-up, then working sets) counts as one last time, all of it
two = [{"date": "2026-10-08", "lifts": [{"name": "Hip thrust machine", "weight": 105, "reps": 12, "sets": 1},
                                         {"name": "Hip thrust machine", "weight": 195, "reps": 10, "sets": 2}]}]
lt = F.last_time("Hip thrust machine", two, "2026-10-12")
assert lt["total"] == 5160 and lt["weight"] == 195 and lt["sets"] == 3
print("PASS lift classifiers: type, duration, intensity by max or last time, style, rules respected, minors")

# recommending intensity from the phase and the athlete's own responses
state2 = {"logs": logs, "strength": strength, "followups": {}, "library": {}}
assert F.recommend(state2, {}, "build")["intensity"] == "medium"
fb_ok = {"a": {"sport": "gym", "date": "2026-10-01", "effort": "as_intended"}, "b": {"sport": "gym", "date": "2026-10-05", "effort": "as_intended"}}
up = F.recommend(state2, fb_ok, "build")
assert up["intensity"] == "heavy" and "stepped up" in up["why"][-1], up["why"]
assert F.recommend(state2, fb_ok, "maintain")["intensity"] == "medium", "no step up unless building"
sore = {**state2, "followups": {"2026-10-05": {"regions": {"lats": 7}, "compare": "worse"}}}
down = F.recommend(sore, fb_ok, "build")
assert down["intensity"] == "light" and "stepped down" in down["why"][-1]
tap = F.recommend(state2, {}, "taper")
assert tap["intensity"] == "light" and tap["volume"]["cut_range"] == [0.4, 0.6]
assert F.recommend(state2, {}, "build", {"legs": 7})["intensity"] == "light", "a sore check-in today eases it"
assert [r["date"] for r in up["past_responses"]] == ["2026-10-01", "2026-10-05"] and up["past_responses"][1]["label"]
print("PASS lift recommendation: phase start, stepped by the athlete's own responses and today's check-in")
rest = F.classify([{"name": "Medicine-ball lunge hold", "style": "restorative", "sets": 2, "weight": 20, "regions": {"quads": 0.5, "glutes": 0.5}},
                   {"name": "Deep squat hold", "style": "restorative", "sets": 1, "regions": {"glutes": 0.6, "adductors": 0.4}},
                   {"name": "Preacher curl", "style": "build", "sets": 2, "reps": 8, "weight": 50, "regions": {"biceps": 1}}], [], {}, "2026-10-12")
assert rest["style"] == "restorative" and rest["intensity"] == "light", rest["label"]
print("PASS a mostly-restorative session reads as restorative and light")
