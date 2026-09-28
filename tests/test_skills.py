"""Progressions and regressions: skill ladders that move on the evidence - two good sessions up, two poor down,
a step down for the day when not recovered, running back to walking while it's on rest."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt, json, tempfile
import coach, focus, skills

HDR = "time,power_w,cadence_rpm,bike_speed_kmh,bike_distance_m,resistance,virtual_speed_kmh,virtual_distance_m,grade_pct,gear,hill_shift,erg_w\n"


def ride(rides, day, hour, in_range, focus_line="Focus - Cadence habit: 65-80 rpm, 101-135 W", minutes=30):
    """A ride of `minutes`, with `in_range` of the seconds at 72 rpm / 120 W and the rest at 58 rpm."""
    t0 = dt.datetime.fromisoformat(f"{day}T{hour:02d}:00:00")
    stem = f"ride_{day}_{hour:02d}00"
    n = minutes * 60
    rows = []
    for s in range(n):
        cad = 72 if s < in_range * n else 58
        rows.append(f"{(t0 + dt.timedelta(seconds=s)).isoformat()},120,{cad},25,0,5,25,{s * 7},0,0,0,\n")
    (rides / f"{stem}.csv").write_text(HDR + "".join(rows))
    (rides / f"{stem}_events.csv").write_text(f"time,event\n{t0.isoformat()},{focus_line}\n")
    return stem


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    rides = pathlib.Path(tempfile.mkdtemp()) / "rides"; rides.mkdir()
    d = coach.load(coach.file_for(rides))
    check("everyone starts on step 1: cadence 65-80", skills.levels_for(d)["cadence"]["rpm"] == [65, 80])
    ride(rides, "2026-09-20", 9, 0.9)
    check("one good ride isn't enough", skills.evaluate(d, rides, today="2026-09-20") == [])
    ride(rides, "2026-09-21", 9, 0.85)
    ch = skills.evaluate(d, rides, today="2026-09-21")
    check(f"two good rides earn the next step ({ch[0]['step'] if ch else None}: {ch[0]['why'] if ch else ''})",
          ch and ch[0]["skill"] == "cadence" and ch[0]["to"] == 1)
    check("...and today's cadence focus uses it", focus.resolve("cadence", 180, levels=skills.levels_for(d))["rpm"] == [70, 85])
    check("the same rides don't count again for the next step", skills.evaluate(d, rides, today="2026-09-21") == [])
    ride(rides, "2026-09-22", 9, 0.3); ride(rides, "2026-09-23", 9, 0.35)
    ch = skills.evaluate(d, rides, today="2026-09-23")
    check(f"two poor rides drop a step ({ch[0]['why'] if ch else None})", ch and ch[0]["to"] == 0)
    ride(rides, "2026-09-24", 9, 0.95); ride(rides, "2026-09-25", 9, 0.95)
    d["ratings"]["ride_2026-09-25_0900"] = {"rpe": 9}
    check("good numbers but it felt 9/10: no step up", skills.evaluate(d, rides, today="2026-09-25") == [])
    skills.set_level(d, "cadence", 2, "test")
    d["checkins"]["2026-09-26"] = {"verdict": "easy"}
    step = skills.step_today(d, "2026-09-26")
    check(f"not recovered today: one step down for the day ({skills.levels_for(d, step)['cadence']['rpm']}) without losing the place",
          step == -1 and skills.levels_for(d, step)["cadence"]["rpm"] == [70, 85] and skills.state(d)["cadence"]["level"] == 2)
    check("...a low-HRV morning does the same", skills.step_today(d, "2026-09-27", "easy") == -1 and skills.step_today(d, "2026-09-27", "go") == 0)
    g = focus.resolve("grit", 180, levels=skills.levels_for(d))
    check(f"grit step 1: {skills.describe('grit', 0)} -> {g['rpm']} rpm, {g['watts']} W", g["rpm"] == [55, 65] and g["watts"] == [137, 153])

    # running: walking while it's on rest; up a step once cleared and the last run went down well
    skills.set_level(d, "running", 2, "test")
    ch = skills.evaluate(d, rides, running_verdict="rest", today="2026-09-26")
    check(f"running on rest: back to walking only ({ch[-1]['step'] if ch else None})", skills.state(d)["running"]["level"] == 0)
    d["checkins"].update({"2026-10-02": {"feet": 2, "legs": 3}, "2026-10-03": {"feet": 2, "legs": 2}})
    ch = skills.evaluate(d, rides, running_verdict="go", last_run="2026-10-01", today="2026-10-03")
    check(f"cleared, and two good mornings after the last run: next step ({skills.describe('running', 1)})",
          skills.state(d)["running"]["level"] == 1)
    check("...once per run", skills.evaluate(d, rides, running_verdict="go", last_run="2026-10-01", today="2026-10-04") == [])

    # climbing: climb goals from route sessions
    for i, made in enumerate((True, True)):
        (rides / f"ride_2026-09-2{7 + i}_1000_session.json").write_text(json.dumps({"results": [
            {"type": "climb_time", "name": "Climb 1", "goal_s": 600, "took_s": 590 if made else 700, "made": made}]}))
    ch = skills.evaluate(d, rides, today="2026-09-28")
    check(f"two climb goals made: climb pace up ({skills.summary(d)['climbing']['now']})", skills.state(d)["climbing"]["level"] == 1)
    s = skills.summary(d, -1)
    check("the summary says where you are, today's step and the next", s["cadence"]["level"] == 3 and s["cadence"]["stepped_down_today"]
          and s["cadence"]["next"] == "80-95 rpm")
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
