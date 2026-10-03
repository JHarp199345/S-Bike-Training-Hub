"""The coaching outlook says when a plan doesn't challenge running: the coming week's forecast peak (in blocks)
against the phase's band. A plan that never reaches the band never teaches the block anything."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
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


def daily(*peaks):
    return [{"date": f"2026-07-{6 + n:02d}", "readings": [{"key": "run_mechanical", "after": b, "limit": 1.5}]}
            for n, b in enumerate(peaks)]


def reading(phase, peaks, gate=OPEN, symptoms=()):
    with patch.object(progression, "context", return_value={"phase": phase}), \
         patch.object(progression, "active_symptoms", return_value=list(symptoms)):
        return C.running_progression({}, {}, TODAY, daily(*peaks), gate)


r = reading("build", (0.3, 0.5, 0.4))
check(f"a build week peaking at 0.5 blocks is under target ({r['status']}, band {r['target_blocks']})",
      r["status"] == "under_target" and r["planned_week_peak_blocks"] == 0.5 and "Lengthen" in r["advice"])
check("build reaching the band is on target", reading("build", (0.6, 1.3))["status"] == "on_target")
check("past the band says shorten or space", reading("build", (1.48,))["status"] == "over_target")
check("base asks for less than build", C.RUN_TARGETS["base"][1] < C.RUN_TARGETS["build"][1])
check("taper doesn't ask for more", reading("taper", (0.5,))["status"] == "on_target")
check("a running hold means no added load", reading("build", (0.3,), gate={"status": "hold", "reasons": ["x"]})["status"] == "held")
check("an unresolved symptom means no added load", reading("build", (0.3,), symptoms=[{"regions": ["calves"]}])["status"] == "held")
check("only the coming week counts", reading("build", (0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 1.4))["status"] == "under_target")
held, _ = C.run_hold({"status": "hold", "reasons": ["hop test first: 10 pain-free single-leg hops on the worse leg clears you to run"]}, TODAY)
check("a due hop test holds only today's run (the athlete hops that morning)", held(TODAY) and not held("2026-07-08"))
check("…so it doesn't stop the plan from progressing running",
      reading("build", (0.3,), gate={"status": "hold", "reasons": ["hop test first: 10 hops"]})["status"] == "under_target")
held, clear = C.run_hold({"status": "hold", "reasons": ["mechanical running load 1.70 blocks exceeds the 1.5-block planning limit",
                                                         "hop test first: 10 hops"], "model_days": 3}, TODAY)
check(f"load plus a due hop test: held until the projected clear date ({clear})", held("2026-07-08") and not held("2026-07-09"))
held, _ = C.run_hold({"status": "hold", "reasons": ["hop test: 6 pain-free hops - 10 clears you to run"]}, TODAY)
check("a failed hop test holds every run until reviewed", held("2026-07-19"))
check("an open gate holds nothing", not C.run_hold({"status": "open_for_review"}, TODAY)[0](TODAY))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
