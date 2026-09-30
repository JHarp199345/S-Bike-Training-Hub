"""Swim-specific recovery must respond to spacing and reports without distorting run load."""
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import bodymap
import swimload


def swims(days):
    out = []
    for i, day in enumerate(days):
        a = {"id": f"swim_{i}", "date": day, "sport": "swim", "minutes": 30,
             "distance_m": 900, "pool_length_m": 25,
             "swim_lengths": [{"length_type": 1, "total_strokes": 20,
                               "swim_stroke": 0, "avg_speed": 0.9} for _ in range(36)]}
        a["swim_exposure"] = swimload.dose(a)
        out.append(a)
    return out


today = dt.date(2026, 9, 30)
cluster = swimload.model(swims(["2026-09-26", "2026-09-27", "2026-09-28"]), {}, today)
spread = swimload.model(swims(["2026-09-12", "2026-09-20", "2026-09-28"]), {}, today)
assert cluster["score"] > spread["score"]
assert cluster["events"][2]["incoming_multiplier"] > 1
fatigued = swimload.model(swims(["2026-09-26", "2026-09-27", "2026-09-28"]), {}, today,
                         {"2026-09-29": {"shoulders": 8}})
assert fatigued["score"] > cluster["score"]
assert swimload.model([], {}, today)["score"] is None
assert swimload.model(swims(["2026-10-01"]), {}, today)["score"] is None
regional = bodymap.build(13.25, 0.5, 0.1)
assert regional["regions"]["shoulders"]["driver"] == "swim"
assert regional["regions"]["calves"]["driver"] == "impact"
print("PASS swim spacing, overlap, symptom response, future guard, and separate regional drivers")

# the block, fitted continuously to next-day shoulder reports
days = ["2026-09-%02d" % d for d in (10, 12, 14, 16, 18, 20, 22, 24)]
none = swimload.model(swims(days), {}, today)
assert none["reference_units"] == none["reference_initial"] and none["reference_interval"] is None
assert "no shoulder reports" in none["reference_from"]
nxt = lambda d: (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
easy = swimload.model(swims(days), {}, today, {nxt(d): {"shoulders": 1} for d in days})
rough = swimload.model(swims(days), {}, today, {nxt(d): {"shoulders": 7} for d in days})
assert easy["reference_units"] > none["reference_units"], "easy mornings: each swim is a smaller share of a block"
assert rough["reference_units"] < none["reference_units"], "rough mornings: each swim is a bigger share of a block"
assert rough["score"] > easy["score"], "...so the same swimming leaves more load for the rough-morning swimmer"
few = swimload.model(swims(days), {}, today, {nxt(d): {"shoulders": 7} for d in days[:2]})
width = lambda m: m["reference_interval"][1] / m["reference_interval"][0]
assert width(rough) < width(few), "more reports, a narrower interval"
assert few["shoulder_reports_used"] == 2 and rough["shoulder_reports_used"] == 8
print(f"PASS the block fits to shoulder reports: easy {easy['reference_units']} / none {none['reference_units']} / "
      f"rough {rough['reference_units']}; interval x{width(few):.2f} with 2 reports, x{width(rough):.2f} with 8")
print("ALL PASS")                      # what tests/run_all.sh looks for
