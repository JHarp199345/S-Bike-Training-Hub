"""Energy from the least heart-rate-dependent source, and reports frozen with the work context they were made in."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import copy, datetime as dt
import energy, work_rate, report_snapshots


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    # ── energy ──
    flat = [{"t": i, "d": 3.0 * i, "alt": 100.0} for i in range(1668)]                # 5 km at 3 m/s
    k = energy.motion_kcal(flat, 70)
    check(f"flat 5 km run at 70 kg = 1 kcal/kg/km net + resting ({k} kcal)", abs(k - (350 + 70 * 1668 / 3600)) < 3)
    up = [{"t": i, "d": 3.0 * i, "alt": 100 + 0.05 * 3.0 * i} for i in range(1668)]
    check(f"a 5% climb costs ~1.3x flat on the running part (Minetti) ({energy.motion_kcal(up, 70)})", 1.2 < energy.motion_kcal(up, 70) / k < 1.35)
    walk = [{"t": i, "d": 1.4 * i, "alt": 0} for i in range(1668)]
    run_same = [{"t": i * 1.4 / 3.0, "d": 1.4 * i, "alt": 0} for i in range(1668)]
    check("walking stretches use the walking curve (cheaper per metre than running)",
          energy.motion_kcal(walk, 70) - 70 * (1668 / 3600) < energy.motion_kcal(run_same, 70))
    noisy = [{"t": i, "d": 3.0 * i, "alt": 100 + (1.5 if i % 2 else -1.5)} for i in range(1668)]
    check("altitude noise is smoothed, not counted as climbing", abs(energy.motion_kcal(noisy, 70) - k) / k < 0.03)
    check("no distance or mass: no motion estimate", energy.motion_kcal([{"t": 0, "d": None}], 70) is None and energy.motion_kcal(flat, None) is None)
    ride = [{"t": i, "w": 200} for i in range(3601)]
    check("power: 200 W for an hour = 720 kJ", energy.power_kj(ride) == 720.0)
    check("sparse power (<50% of the time) is not trusted", energy.power_kj([{"t": i, "w": 200 if i < 600 else 0} for i in range(3601)]) is None)
    e = energy.estimate("bike", ride, 70, 650)
    check("bike: power is primary, watch kept beside it", e["energy_source"] == "power" and e["estimates"]["watch_kcal"] == 650 and e["gap_ratio"] is None)
    e = energy.estimate("run", flat, 70, 520)
    check(f"run: motion primary; a watch 50%+ higher is flagged ({e['gap_ratio']})", e["energy_source"] == "motion" and e["gap_ratio"])
    e = energy.estimate("swim", [], 70, 600)
    check("swim: the watch's calories, labelled as the watch", e["energy_source"] == "watch" and e["energy_kcal"] == 600)

    # ── ledger and snapshots ──
    def act(i, date, start, sport, kcal, source="watch"):
        return {"id": f"a{i}", "source": "watch", "sport": sport, "date": date, "start": start, "minutes": 40,
                "duration_seconds": 2400, "calories_kcal": kcal, "energy_kcal": kcal, "energy_source": source}
    load = {"activities": [act(1, "2026-10-05", "08:00", "swim", 600), act(2, "2026-10-06", "07:00", "run", 500, "motion"),
                           act(3, "2026-10-07", "06:00", "bike", 300, "power"), act(4, "2026-10-07", "18:00", "run", 400, "motion")]}
    w = work_rate.build(load, [], today="2026-10-07")
    check("swim work counts in cardio beside run and bike", w["windows"]["3"]["cardio"]["sport_j"].get("swim") == 600 * 4184)
    snap = work_rate.snapshot(load, [], {}, "2026-10-07", cutoff="09:00")
    check("a 9:00 check-in excludes the 18:00 run that day", snap["context_3_days"]["cardio"]["recorded_sessions"] == 3)
    fb = {"2026-10-07:0": {"date": "2026-10-07", "rpe": 6, "actual_minutes": 40}}
    s2 = work_rate.snapshot(load, [], fb, "2026-10-07")
    check("session effort x minutes recorded beside joules (6 x 40 = 240 AU)", s2["context_3_days"]["session_load"]["srpe_au"] == 240)

    d = {"checkins": {"2026-10-06": {"legs": 4}, "2026-10-07": {"legs": 5}}, "weekly": {},
         "training_feedback": {"2026-10-06:0": {"date": "2026-10-06", "rpe": 7, "actual_minutes": 40, "activity_id": "a2"}},
         "journal_entries": [{"date": "2026-10-07", "saved_at": "2026-10-07T09:58:00-07:00"}], "lifting": {}}
    p = report_snapshots.preview(d, load, [])
    check(f"preview finds every unfrozen report ({p['count']})", p["count"] == 3)
    ck = next(r for r in p["records"] if r["key"] == "2026-10-07")
    check("a rebuilt check-in uses its saved time (09:58) as the cutoff", ck["cutoff"] == "09:58" and ck["snapshot"]["context_3_days"]["cardio"]["recorded_sessions"] == 3)
    before = copy.deepcopy(d)
    try:
        report_snapshots.apply(d, load, [], "stale"); check("a stale token is refused", False)
    except ValueError:
        check("a stale token is refused and nothing is written", d == before)
    r = report_snapshots.apply(d, load, [], p["token"])
    check(f"apply writes exactly the preview ({r['applied']})", r["applied"] == 3 and all(
        x["snapshot"]["recorded"] == "rebuilt" for x in (d["checkins"]["2026-10-06"], d["checkins"]["2026-10-07"], d["training_feedback"]["2026-10-06:0"])))
    check("no existing field changed", all({k: v for k, v in d["checkins"][k2].items() if k != "snapshot"} == before["checkins"][k2] for k2 in before["checkins"]))
    check("apply is idempotent", report_snapshots.preview(d, load, [])["count"] == 0 and report_snapshots.apply(d, load, [], report_snapshots.preview(d, load, [])["token"])["applied"] == 0)
    frozen = d["checkins"]["2026-10-06"]["snapshot"]["context_3_days"]["cardio"]["known_j"]
    load2 = copy.deepcopy(load); load2["activities"][0]["energy_kcal"] = 900          # a later formula change
    w2 = work_rate.build(load2, [], checkins=d["checkins"], feedback=d["training_feedback"], today="2026-10-07")
    rep = next(x for x in w2["reports"] if x["kind"] == "Daily check-in" and x["date"] == "2026-10-06")
    check("a frozen report keeps its context when formulas change later", rep["context_3_days"]["cardio"]["known_j"] == frozen and rep["context_basis"] == "rebuilt")
    old = {"legs": 2, "snapshot": {"version": work_rate.SNAPSHOT, "recorded": "rebuilt", "context_3_days": {"cardio": {}}}}
    kept = {"legs": 2, "snapshot": {"version": work_rate.SNAPSHOT, "recorded": "at_report", "context_3_days": {"cardio": {}}}}
    check("an older rebuilt snapshot is topped up; one frozen at save never is", not report_snapshots.current(old["snapshot"]) and report_snapshots.current(kept["snapshot"]))
    snapd = work_rate.snapshot(load, [], {}, "2026-10-07")["context_3_days"]["cardio"]
    check(f"the biggest day is recorded beside the average ({snapd['peak_day']['date']}, {round(snapd['peak_day']['j']/4184)} kcal)",
          snapd["peak_day"]["date"] == "2026-10-07" and round(snapd["peak_day"]["j"] / 4184) == 700 and snapd["training_days"] == 3)
    rec = {"legs": 3}
    report_snapshots.freeze(rec, load, [], {}, "2026-10-07", "checkin", now=dt.datetime(2026, 10, 7, 12, 0))
    check("a new check-in freezes 'at_report' with its time as the cutoff", rec["snapshot"]["recorded"] == "at_report" and rec["snapshot"]["cutoff"] == "12:00")
    import rider, tempfile, json
    tmp = pathlib.Path(tempfile.mkdtemp()) / "profile.json"; tmp.write_text(json.dumps({"weight_kg": 80.0}))
    prof = rider.set_weight(rider.load(tmp), 90.0, "2026-10-07")
    check("a new weight keeps the old one for earlier dates", rider.weight_on(prof["weight_kg"], prof["weight_history"], "2026-10-06") == 80.0
          and rider.weight_on(prof["weight_kg"], prof["weight_history"], "2026-10-07") == 90.0)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
