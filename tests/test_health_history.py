import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import health_history as H

today = "2026-10-11"
d = {}
base = {k: False for k, _, _ in H.SCREENING}; base["intensity"] = "moderate"
def outcome(**kw):
    return H.assess({**base, **kw})[0]
assert outcome() == "no_clearance_needed"                                            # inactive, healthy: start gradually
assert outcome(kidney_disease=True) == "clearance_before_starting"                   # inactive with known disease
assert outcome(active_now=True, kidney_disease=True) == "no_clearance_needed"         # active, moderate: continue
assert outcome(active_now=True, kidney_disease=True, intensity="vigorous") == "clearance_before_vigorous"
assert outcome(active_now=True, symptoms=True) == "stop_and_see_doctor"               # symptoms always
assert outcome(supervised_only=True) == "clearance_before_starting"                   # follow the doctor's advice
notes = H.assess({**base, "heart_rate_medication": True, "bone_joint": True, "pregnant": True})[1]
assert len(notes) == 4 and any("heart rate" in n for n in notes)                      # three extras plus "start light"
e = H.screen(d, {**base, "kidney_disease": True}, today, {"obtained": False, "note": "seeing my doctor Tuesday"})
assert e["result"] == "clearance_before_starting" and "doctor" in e["advice"] and e["clearance"]["obtained"] is False
for bad in ({"active_now": True}, {**base, "made_up": True}, {**base, "intensity": "max"}, {**base, "heart_disease": "yes"}, "no"):
    try:
        H.screen(d, bad, today); raise AssertionError(bad)
    except ValueError:
        pass

c = H.add(d, "condition", {"name": "Sciatica", "category": "nerve_or_back", "status": "current", "note": "Left leg, worse sitting long"}, today)
i = H.add(d, "injury", {"site": "Lower back", "when": "2024", "status": "flares", "aggravated_by": "heavy deadlifts"}, today)
m = H.add(d, "medication", {"name": "Metoprolol", "affects_heart_rate": True}, today)
g = H.add(d, "guidance", {"text": "No heavy spinal loading for now; walking and swimming encouraged.", "source": "physiotherapist"}, today)
for kind, bad in (("condition", {"name": ""}), ("condition", {"name": "x", "category": "aliens"}), ("injury", {"site": "knee", "status": "broken"}),
                  ("medication", {}), ("guidance", {"text": " "}), ("hobby", {"name": "x"})):
    try:
        H.add(d, kind, bad, today); raise AssertionError((kind, bad))
    except ValueError:
        pass

u = H.update(d, "injury", i["id"], {"status": "healed"}, "2026-11-01")
assert u["status"] == "healed" and u["id"] == i["id"] and u["site"] == "Lower back" and u["updated"] == "2026-11-01"
assert H.remove(d, "medication", m["id"]) == {"removed": m["id"]} and not d["health_history"]["medications"]
try:
    H.remove(d, "medication", m["id"]); raise AssertionError("removed twice")
except ValueError:
    pass

s = H.summary(d)
assert s["screening"]["result"] == "clearance_before_starting" and len(s["screening_questions"]) == 10
assert s["conditions"][0]["category"] == "nerve_or_back" and s["guidance"][0]["source"] == "physiotherapist"
assert s["heart_rate_note"] is None                            # the heart-rate medication was removed
H.add(d, "medication", {"name": "Propranolol", "affects_heart_rate": True}, today)
assert H.summary(d)["heart_rate_note"] and H.summary({})["screening"] is None

import planning_context as C
assert C.context(d, [], today, "program")["health_history"]["conditions"][0]["name"] == "Sciatica"
print("PASS health history: screening, records, summary, planning context")
