"""Load-guided planning: starting capacities, session energy, phase targets and flags, report-gated build steps,
the bad-report protocol (evening + morning re-checks) and sessions that went well."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import planning_load as pl, report_protocol as rp


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    s = pl.starting({"weight_kg": 100, "experience": {"run": "new"}})
    check(f"new athlete starts at 150 min/week x 4 METs x 100 kg ({round(s['daily_j']/4184)} kcal/day)", round(s["daily_j"] / 4184) == round(150 / 60 * 4 * 100 / 7))
    s2 = pl.starting({"weight_kg": 100, "experience": {"run": "new"}, "vo2max": 42})
    check("a wearable VO2max sets the intensity (60% of 42 = 7.2 METs)", "7.2 METs" in s2["basis"] and s2["daily_j"] > s["daily_j"])
    e, basis = pl.session_energy({"sport": "ride", "bike_plan": {"power_steps": [{"watts": 150, "minutes": 40}]}}, {}, s)
    check("a planned ride uses its planned power (150 W x 40 min = 360 kJ ~ kcal)", e == 360 and basis == "planned power")
    e, basis = pl.session_energy({"sport": "swim", "minutes": 30}, {"swim": {"kcal_per_min": 10, "sessions": 4}}, s)
    check("other sessions use your own median kcal/min", e == 300 and "median" in basis)

    today = dt.date(2026, 10, 14)
    acts = [{"id": f"a{i}", "source": "watch", "sport": "run", "date": (today - dt.timedelta(days=i)).isoformat(),
             "minutes": 40, "energy_kcal": 500} for i in range(1, 28, 2)]                      # every other day
    d = {"events": [], "plans": {}, "checkins": {}, "training_feedback": {}}
    plan_day = (today + dt.timedelta(days=1)).isoformat()
    d["plans"][plan_day] = {"sessions": [{"sport": "run", "name": "Long run", "minutes": 120}]}
    o = pl.outlook(d, {"activities": acts}, {"weight_kg": 100}, today, horizon=7)
    check(f"reference = your 28-day daily average ({round(o['reference_rate_j_per_day']/4184)} kcal/day)", o["history_days"] >= 14 and abs(o["reference_rate_j_per_day"] - 14 * 500 * 4184 / 28) < 1)
    big = next(r for r in o["days"] if r["date"] == plan_day)
    check("a stacked long run is flagged as an over-big day", any("biggest day" in f for f in big["flags"]))
    check("planned sessions carry their estimate and basis", big["planned"][0]["kcal"] > 0 and big["planned"][0]["basis"])

    good = pl.progression_step({"checkins": {today.isoformat(): {"legs": 3, "feet": 2, "pain": {}}}}, today)
    check("settled reports: a full 10% step", good["step"] == 0.10)
    mild = pl.progression_step({"checkins": {today.isoformat(): {"legs": 3, "pain": {"feet": 3}}}}, today)
    check("mild pain: a small step", 0 < mild["step"] < 0.10)
    bad = pl.progression_step({"checkins": {today.isoformat(): {"pain": {"feet": 6}}}}, today)
    check("pain of 5 or more: no increase", bad["step"] == 0)

    # ── bad-report protocol ──
    d = {"checkins": {"2026-10-12": {"pain": {"feet": 1}, "legs": 3, "feet": 3}}}
    for i in range(5, 13):
        d["checkins"][f"2026-10-0{i}" if i < 10 else f"2026-10-{i}"] = d["checkins"].get(f"2026-10-{i}") or {"legs": 3, "feet": 3}
    check("ordinary report is not bad", rp.assess(d, "checkin", {"pain": {}, "legs": 3, "feet": 3}, "2026-10-13") == [])
    check("pain 5+ is bad", rp.assess(d, "checkin", {"pain": {"feet": 5}}, "2026-10-13"))
    check("pain worse than last report is bad", any("worse" in x for x in rp.assess(d, "checkin", {"pain": {"feet": 3}}, "2026-10-13")))
    check("soreness well above usual is bad", any("above your usual" in x for x in rp.assess(d, "checkin", {"pain": {}, "legs": 7}, "2026-10-13")))
    r = rp.on_report(d, "checkin", "2026-10-13", {"pain": {"feet": 6}}, "2026-10-13", now=dt.datetime(2026, 10, 13, 8, 0))
    check("a bad report schedules an evening and a next-morning re-check", [x["slot"] for x in r["due"]] == ["evening", "morning"]
          and r["due"][0]["at"].endswith("19:00") and r["due"][1]["at"] == "2026-10-14T08:00")
    check("running is held and the next increase waits", rp.holds(d, "2026-10-13")["impact_held"] and rp.holds(d, "2026-10-13")["increase_waits"])
    check("only one open re-check at a time", rp.on_report(d, "checkin", "2026-10-13", {"pain": {"legs": 7}}, "2026-10-13")["id"] == r["id"])
    late = rp.on_report({}, "checkin", "x", {"pain": {"feet": 6}}, "2026-10-13", now=dt.datetime(2026, 10, 13, 21, 0))
    check("a late report re-checks in about three hours", late["due"][0]["at"] == "2026-10-14T00:00")
    rp.answer(d, r["id"], {"slot": "evening", "pain": {"feet": 4}}, now=dt.datetime(2026, 10, 13, 19, 5))
    check("the evening answer waits for the morning", r["outcome"]["result"] == "waiting" and r["status"] == "open")
    rp.answer(d, r["id"], {"slot": "morning", "pain": {"feet": 1}, "stiffness": 1}, now=dt.datetime(2026, 10, 14, 8, 5))
    check("settled by morning: resume, re-check closed", r["outcome"]["result"] == "settled" and r["status"] == "closed")
    d2 = {}; r2 = rp.on_report(d2, "checkin", "k", {"pain": {"feet": 6}}, "2026-10-13", now=dt.datetime(2026, 10, 13, 8))
    rp.answer(d2, r2["id"], {"slot": "morning", "pain": {"feet": 4}}, now=dt.datetime(2026, 10, 14, 8))
    check("improving but not settled: another morning re-check", r2["outcome"]["result"] == "improving" and len(r2["due"]) == 3)
    rp.answer(d2, r2["id"], {"slot": "morning", "pain": {"feet": 7}}, now=dt.datetime(2026, 10, 15, 8))
    check("worse: step back", r2["outcome"]["result"] == "step_back" and r2["status"] == "closed")
    d3 = {}; r3 = rp.on_report(d3, "checkin", "k", {"pain": {"feet": 6}}, "2026-10-13", now=dt.datetime(2026, 10, 13, 8))
    rp.answer(d3, r3["id"], {"slot": "evening", "pain": {"feet": 2}, "red_flags": ["swelling"]}, now=dt.datetime(2026, 10, 13, 19))
    check("a red flag means stop and see a professional", r3["outcome"]["result"] == "stop")

    fb = {"2026-10-10:0": {"date": "2026-10-10", "sport": "swim", "session_name": "Easy swim", "effort": "as_intended", "symptoms": [],
                           "snapshot": {"context_3_days": {"cardio": {"j_per_day": 2e6}}}},
          "2026-10-11:0": {"date": "2026-10-11", "sport": "run", "session_name": "Run", "effort": "too_hard", "symptoms": []},
          "2026-10-12:0": {"date": "2026-10-12", "sport": "run", "session_name": "Run 2", "effort": "as_intended", "symptoms": [{"severity": 4}]}}
    w = pl.well_tolerated({"training_feedback": fb}, today)
    check("sessions that went well: as intended, no pain 3+, with the rate they were done at", len(w) == 1 and w[0]["name"] == "Easy swim" and w[0]["at_rate3_j_per_day"] == 2e6)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
