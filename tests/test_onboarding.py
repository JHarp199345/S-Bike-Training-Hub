"""The welcome page's orientation: starting numbers from the rider's answers (onboarding.py)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import json, tempfile
from pathlib import Path
import coach, lifting, onboarding


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    base = Path(tempfile.mkdtemp())
    check("an empty folder is a first run", onboarding.first_run(base))
    out = onboarding.apply(base, {"unit": "lb", "weight": 180, "age": 30, "hr_rest": 58, "sports": ["run", "swim", "lift"],
                                  "experience": {"run": "new", "swim": "regular", "lift": "returning"}, "start": "fresh",
                                  "css": "1:55", "run5k": "27:30", "rules": ["No barbell squats", "Favorite lift: incline press"]})
    p = json.loads((base / "profile.json").read_text())
    check(f"weight in kg, max heart rate from age ({p['weight_kg']} kg, {p['hr_max']})", abs(p["weight_kg"] - 81.6) < 0.1 and p["hr_max"] == 187)
    cal = p["load_calibration"]
    check(f"starting usual weeks: engine from the best sport, impact from running, legs from running/lifting ({ {k: v['usual_week'] for k, v in cal.items()} })",
          cal["engine"]["usual_week"] == 400 and cal["impact"]["usual_week"] == 40 and cal["muscle"]["usual_week"] == 100)
    d = coach.load(base / "coach.json")
    check("swim pace recorded as the rider's own number", d["calibration"]["swim_css"][0]["value"] == 115 and d["calibration"]["swim_css"][0]["kind"] == "manual")
    check("rules land on the Rules tab", [r["text"] for r in lifting.rules(d)] == ["No barbell squats", "Favorite lift: incline press"])
    check("no longer a first run", not onboarding.first_run(base))
    b2 = Path(tempfile.mkdtemp())
    out2 = onboarding.apply(b2, {"unit": "kg", "weight": 70, "sports": ["run"], "experience": {"run": "regular"}, "start": "loaded"})
    p2 = json.loads((b2 / "profile.json").read_text())
    check(f"loaded starts 30% more cautious ({p2['load_calibration']['impact']['usual_week']})", p2["load_calibration"]["impact"]["usual_week"] == 112)
    check("...and asks for the hop test before the first run", out2["next"][0].startswith("Before your first run: the hop test"))
    try:
        onboarding.apply(Path(tempfile.mkdtemp()), {"weight": 900, "sports": ["run"]}); bad = False
    except ValueError:
        bad = True
    check("an impossible weight is refused", bad)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
