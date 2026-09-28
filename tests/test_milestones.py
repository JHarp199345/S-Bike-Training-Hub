"""Streaks and milestones: day and week streaks (the current week is in progress,
not a break), each milestone credited to the ride that earned it, a gap breaks
a streak, the ride in progress can be left out, fun equivalents."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import csv, datetime as dt, tempfile
import milestones as M


def ride(folder, day, minutes, watts=150, grade=0.0, hour=9, events=()):
    start = dt.datetime.combine(day, dt.time(hour, 0))
    stem = f"ride_{start:%Y-%m-%d_%H%M}"
    with open(folder / f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "power_w", "cadence_rpm", "bike_speed_kmh", "bike_distance_m", "resistance",
                    "virtual_speed_kmh", "virtual_distance_m", "grade_pct", "gear", "hill_shift", "erg_w"])
        d = 0.0
        for s in range(int(minutes * 60)):
            d += 30 / 3.6                                          # 30 km/h
            w.writerow([(start + dt.timedelta(seconds=s)).isoformat(timespec="seconds"), watts, 80, 30, d, 5,
                        30, round(d, 1), grade, 0, 0, ""])
    if events:
        with open(folder / f"{stem}_events.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["time", "event"])
            for e in events:
                w.writerow([start.isoformat(), e])
    return stem


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    tmp = pathlib.Path(tempfile.mkdtemp()); rides = tmp / "rides"; rides.mkdir()
    mon = dt.date(2026, 9, 7)                                       # a Monday
    stems = {}
    # week 1: Mon, Tue, Wed (3 rides of 30 min) - goal met
    for i in range(3):
        stems[f"w1d{i}"] = ride(rides, mon + dt.timedelta(days=i), 30)
    # week 2: Mon, Wed, Fri - goal met; the Mon ride is a 60-min climb with a route
    stems["w2mon"] = ride(rides, mon + dt.timedelta(days=7), 60, grade=5.0,
                          events=["Route started: x at 0 m - Hill, 30.0 km, 400 m of climbing"])
    stems["w2wed"] = ride(rides, mon + dt.timedelta(days=9), 30)
    stems["w2fri"] = ride(rides, mon + dt.timedelta(days=11), 30)
    # week 3 (the current week): Mon and Tue so far
    stems["w3mon"] = ride(rides, mon + dt.timedelta(days=14), 30)
    stems["w3tue"] = ride(rides, mon + dt.timedelta(days=15), 30)
    today = mon + dt.timedelta(days=15)

    d = M.compute(rides, weekly_goal=3, today=today)
    t, s = d["totals"], d["streaks"]
    check(f"8 rides, 4.5 h ({t['rides']}, {t['hours']})", t["rides"] == 8 and abs(t["hours"] - 4.5) < 0.05)
    check(f"distance adds up: 8 rides at 30 km/h = 135 km ({t['km']})", abs(t["km"] - 135) < 1)
    check(f"day streak today is 2 (Mon, Tue) ({s['days']})", s["days"] == 2 and s["rode_today"])
    check(f"best day streak is 3 (week 1) ({s['best_days']})", s["best_days"] == 3)
    check(f"weeks on goal: 2, the current week in progress doesn't break it ({s['weeks']})", s["weeks"] == 2)
    check(f"this week: 2 of 3 ({s['this_week']}/{s['goal']})", s["this_week"] == 2 and s["goal"] == 3)
    who = {e["key"]: e["ride"] for e in d["earned"]}
    check("'First ride' goes to the very first ride", who["rides:1"] == stems["w1d0"])
    check("'5 rides' goes to the fifth ride", who["rides:5"] == stems["w2wed"])
    check("'100 km ridden' goes to the ride that crossed it (45+30+15 = 90, then Friday)", who["km:100"] == stems["w2fri"])
    check("'1 h ride' goes to the 60-min ride", who["long:60"] == stems["w2mon"])
    check("'Eiffel Tower' climbing (330 m) comes from the climb", who["climb:330"] == stems["w2mon"])
    check("first route ride is credited", who["first_route"] == stems["w2mon"])
    check("'3-day streak' earned on the third day", who["daystreak:3"] == stems["w1d2"])
    check("'2 weeks on goal' earned when week 2's goal was met", who["weekstreak:2"] == stems["w2fri"])
    check("next-up has progress for unearned milestones", all(0 < b["progress"] < 1 for b in d["next"]))

    # a day off breaks the day streak (Wednesday not ridden, look from Thursday)
    d2 = M.compute(rides, weekly_goal=3, today=today + dt.timedelta(days=2))
    check(f"a missed day ends the day streak ({d2['streaks']['days']})", d2["streaks"]["days"] == 0)
    # a whole week missed ends the week streak
    d3 = M.compute(rides, weekly_goal=3, today=today + dt.timedelta(days=13))
    check(f"a missed week ends the week streak ({d3['streaks']['weeks']})", d3["streaks"]["weeks"] == 0)
    # leaving the ride in progress out
    d4 = M.compute(rides, weekly_goal=3, today=today, exclude=stems["w3tue"])
    check("the ride in progress can be left out of the totals", d4["totals"]["rides"] == 7)
    check("a lower weekly goal counts more weeks", M.compute(rides, weekly_goal=2, today=today)["streaks"]["weeks"] == 3)
    eq = M.equivalents({"climb_m": 1200, "km": 200, "kcal": 1000})
    check(f"equivalents: {eq}", eq[0].startswith("Alpe d'Huez ×1.1") and "LA to San Diego ✓" in eq and "4 donuts 🍩" in eq)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
