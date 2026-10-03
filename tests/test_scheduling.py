"""Scheduling rules by sport (the rider's design, 2026-10-03): runs never back to back in a starter; swims and
rides may repeat on consecutive days; lifting follows the athlete's split, rotating its focuses, full body 48 h
apart and splits up to their days-in-a-row limit; second sessions load different tissue; no hard ride or run
the day after a leg-lifting session."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import program_builder as PB
import starter_programs as S

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


START, END = dt.date(2026, 6, 1), dt.date(2026, 7, 13)
PHASE = [{"start": START.isoformat(), "end": END.isoformat(), "kind": "build", "stage": "build", "label": "Build",
          "modes": {"ride": "improve", "run": "improve", "swim": "improve", "gym": "improve"},
          "weights": {"gym": 3, "ride": 2, "run": 2, "swim": 2}}]


def slots(hours=7, **options):
    weeks = PB.macro_weeks(PHASE, START, END, "tri", "tri", False, hours, options={"rest_days": [], **options})
    return [x for w in weeks for x in w["slots"] if x["sport"] != "rest"]


def runs_of(sl, sport):
    days = sorted({dt.date.fromisoformat(x["date"]) for x in sl if x["sport"] == sport})
    best = cur = 1 if days else 0
    for a, b in zip(days, days[1:]):
        cur = cur + 1 if (b - a).days == 1 else 1
        best = max(best, cur)
    return best


for split in S.LIFT_SPLITS:
    check(f"lifting split '{split}' is accepted", PB.validate_options({"lift_split": split})["lift_split"] == split)
try:
    PB.validate_options({"lift_split": "bro_split"})
    check("an unknown split is refused", False)
except ValueError:
    check("an unknown split is refused", True)

full = slots()
check("runs are never on consecutive days", runs_of(full, "run") <= 1)
check("full-body lifting is never on consecutive days (48 h)", runs_of(full, "gym") <= 1)
four = slots(lift_split="four_way", max_lift_days_in_row=4)
focus = [x["lift_focus"] for x in four if x["sport"] == "gym"]
check(f"a four-way split rotates knee, hip, push, pull ({focus[:4]})", focus[:4] == ["knee", "hip", "upper_push", "upper_pull"])
two = slots(lift_split="upper_lower", max_lift_days_in_row=2)
check("a split never exceeds the athlete's lifting days in a row", runs_of(two, "gym") <= 2)

# sessions by focus
upper = S.workout("gym", 40, 2, "moderate", "returning", "basic", {}, lift_focus="upper_push")
names = [x["name"] for x in upper["lifts"]]
check(f"an upper-push session trains pressing, not legs ({names})",
      "Incline push-up" in names and "Pike push-up" in names and "Chair squat" not in names)
hip = S.workout("gym", 40, 2, "moderate", "returning", "barbell", {}, lift_focus="hip")
check("a hip-dominant barbell session hinges", "BB Romanian deadlift" in [x["name"] for x in hip["lifts"]])

# doubles load different tissue
dbl = slots(hours=8, allow_doubles=True)
by_day = {}
for x in dbl:
    by_day.setdefault(x["date"], []).append(x)
pairs = [v for v in by_day.values() if len(v) == 2]
check(f"second sessions load different tissue ({len(pairs)} doubles)",
      pairs and all(not (PB.tissue(a["sport"], a.get("lift_focus")) & PB.tissue(b["sport"], b.get("lift_focus"))) for a, b in pairs))

# no hard ride or run the day after a leg-lifting day, when the week has a fresher day for it
f = {"start": "2026-10-05", "horizon_days": 56, "sport": "general", "hours": 5,
     "priorities": {"ride": "improve", "swim": "maintain", "gym": "improve", "run": "pause"},
     "schedule_options": {"rest_days": [], "lift_split": "upper_lower", "max_lift_days_in_row": 2}}
prop = PB.propose({"plans": {}}, f, "2026-10-05", {"status": "hold"})
plans = S.build({"plans": {}}, prop, today="2026-10-05")["candidates"][1]["plans"]
bad, hard_rides = [], 0
for date, v in sorted(plans.items()):
    prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    legs = any(x["sport"] == "gym" and ("lower" in x["name"] or "full" in x["name"].lower() or x["name"].startswith("Basic"))
               for x in (plans.get(prev) or {}).get("sessions", []))
    for x in v["sessions"]:
        if x["sport"] in ("ride", "run") and x.get("tier") in ("moderate", "hard"):
            hard_rides += 1
            if legs:
                wk = dt.date.fromisoformat(date) - dt.timedelta(days=dt.date.fromisoformat(date).weekday())
                fresh = [d for d, w in plans.items() if wk.isoformat() <= d < (wk + dt.timedelta(days=7)).isoformat() and d > date
                         and any(y["sport"] == x["sport"] for y in w["sessions"])]
                if fresh:
                    bad.append(date)
check(f"hard rides and runs wait for a fresh day after leg lifting ({hard_rides} hard, misplaced: {bad})", hard_rides and not bad)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
