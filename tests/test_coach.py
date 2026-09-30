"""Coach: diagnostic verdicts against the rider's own baseline, the sliding bar chart keeps
the total and the others' ratios, time-split workouts with watt targets, and the
hub command end to end against a real (scratch) server."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, io, json, contextlib, tempfile, threading
import coach, workouts


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    tmp = pathlib.Path(tempfile.mkdtemp())
    d = coach.load(tmp / "coach.json")

    c = coach.record(d, "2026-10-01", {"legs": 3, "gut": "go", "hr90": 110, "hr120": 125, "hr_after": 100})
    check(f"first test: go, and it says the baseline is still building ({c['why']})",
          c["verdict"] == "go" and any("building" in w for w in c["why"]))
    check("recovery = end of the push minus 60 s later", c["hrr"] == 25)
    for day, hr in (("2026-10-02", 112), ("2026-10-03", 108)):
        coach.record(d, day, {"legs": 3, "gut": "go", "hr90": hr, "hr120": hr + 15, "hr_after": hr - 10})
    b = coach.baseline(d, "2026-10-04")
    check(f"baseline after 3 tests: HR@90W median 110, recovery 25 ({b})", b["hr90"] == 110 and b["hrr"] == 25)
    c = coach.record(d, "2026-10-04", {"legs": 4, "gut": "go", "hr90": 117, "hr120": 130, "hr_after": 108})
    check(f"HR 7 above normal -> easy ({c['verdict']}: {c['why']})", c["verdict"] == "easy" and any("+7" in w for w in c["why"]))
    c = coach.record(d, "2026-10-05", {"legs": 4, "gut": "go", "hr90": 111, "hr120": 124, "hr_after": 107})
    check(f"slow recovery (17 vs 25) -> easy ({c['why']})", c["verdict"] == "easy" and any("recovery" in w for w in c["why"]))
    c = coach.record(d, "2026-10-06", {"legs": 7, "gut": "go", "hr90": 100})
    check(f"HR 10 below normal with heavy legs -> rest (deep fatigue) ({c['why']})", c["verdict"] == "rest")
    c = coach.record(d, "2026-10-07", {"legs": 2, "gut": "no"})
    check("the rider's own 'not today' is always respected -> rest", c["verdict"] == "rest")
    c = coach.record(d, "2026-10-08", {"legs": 8, "gut": "go"})
    check("legs 8/10 -> rest even if they want to go", c["verdict"] == "rest")
    c = coach.record(d, "2026-10-09", {"legs": 3, "gut": "go", "hr90": 111, "hr120": 126, "hr_after": 101})
    check(f"normal numbers, fresh legs -> go ({c['why']})", c["verdict"] == "go" and "everything looks normal" in c["why"])
    try:
        coach.record(d, "2026-10-10", {"legs": 15}); check("out-of-range input refused", False)
    except ValueError:
        check("out-of-range input refused", True)

    # the sliding bar chart
    mins = [4.5, 4.5, 4, 3, 4, 3, 4, 3]                 # 30 min
    out = coach.rebalance(mins, 2, 8, 30)
    others_before = [m for i, m in enumerate(mins) if i != 2]
    others_after = [m for i, m in enumerate(out) if i != 2]
    ratios = [a / b for a, b in zip(others_after, others_before)]
    check(f"dragging one bar keeps the total ({sum(out):.3f} min)", abs(sum(out) - 30) < 1e-9 and out[2] == 8)
    check(f"...and the others keep their ratios (all scaled by {ratios[0]:.3f})", max(ratios) - min(ratios) < 1e-9)
    out = coach.rebalance(mins, 0, 29.9, 30)
    check(f"no bar is squeezed below 15 s ({min(out):.2f} min), total still 30", min(out) >= 0.25 - 1e-9 and abs(sum(out) - 30) < 1e-6)
    shape = coach.split_parts(3)
    check("the standard shape: warm-up, ramp, 3 intervals with 2 rests, cool-down",
          [p["kind"] for p in shape] == ["warmup", "ramp", "interval", "rest", "interval", "rest", "interval", "cooldown"])
    blocks = coach.split_to_blocks([{"kind": "warmup", "minutes": 5, "pct": 50}, {"kind": "ramp", "minutes": 5, "from": 50, "to": 75},
                                    {"kind": "interval", "minutes": 0.05, "watts": 230}, {"kind": "rest", "minutes": 2, "watts": 60}])
    steps = workouts.flatten(blocks)
    check("watt targets survive into the ERG steps (230 W for 3 s, then 60 W)",
          {"minutes": 0.05, "watts": 230} in steps and {"minutes": 2, "watts": 60} in steps)
    st = workouts.stats(steps, 180)
    check(f"stats handle watt steps ({st['minutes']} min, avg {st['avg_w']} W)", st["minutes"] > 12)

    # the hub command against a real scratch server
    import panel, bridge as b_mod
    workouts.FOLDER = tmp / "workouts"; workouts.FOLDER.mkdir()
    class FakeBridge:
        profile = {"ftp": 180, "ftp_source": "test"}
        csv_path = tmp / "rides" / "ride_2026-10-01_0700.csv"
        workouts = []
        started = []
        def reload_workouts(self): self.workouts = [{"id": w["id"], "name": w["name"]} for w in workouts.list_all(180, workouts.FOLDER)]
        def workout_start_id(self, wid): self.started.append(wid); return True
        def coach_test_start(self): self.started.append("diagnostic")
        def event(self, m): pass
    (tmp / "rides").mkdir()
    fb = FakeBridge()
    loop = asyncio.new_event_loop()
    srv = loop.run_until_complete(panel.serve(fb, 18731, lan=False))
    threading.Thread(target=loop.run_forever, daemon=True).start()
    import hub
    hub.BASE = "http://127.0.0.1:18731"
    def run(*args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hub.main(list(args))
        return buf.getvalue()
    out = run("checkin", "--date", "2026-10-01", "--legs", "3", "--gut", "go", "--hr90", "110")
    check(f"hub checkin records and shows a verdict", "verdict: GO" in out)
    out = run("plan", "--date", "2026-10-01", "--verdict", "easy", "--note", "Legs still heavy from Friday: 30 min spin, 85+ rpm.")
    check("hub plan writes the coach's note", "note: Legs still heavy" in out)
    out = run("split", "--total", "30", "--intervals", "3", "--interval-pct", "75", "--plan", "--name", "Easy 3x")
    check(f"hub split saves a timed workout and makes it today's ride ({out.strip()})",
          "saved as easy-3x" in out and (workouts.FOLDER / "easy-3x.json").exists())
    w = json.loads((workouts.FOLDER / "easy-3x.json").read_text())
    check(f"the split workout is 30 min ({sum(s['minutes'] for s in w['steps']):.2f})", abs(sum(s["minutes"] for s in w["steps"]) - 30) < 0.01)
    out = run("today", "--date", "2026-10-01")
    check("hub today shows the check-in, plan and note", "HR@90W 110" in out and "plan: easy" in out and "Legs still heavy" in out)
    out = run("diagnostic")
    check("hub diagnostic starts the test on the bridge", "diagnostic" in fb.started)
    check("the coach file is the scratch one, not the real one", (tmp / "coach.json").exists())
    loop.call_soon_threadsafe(srv.close)

    # one-tap effort rating: the last real ride, a 1-10 rating kept with the plan
    import tempfile as _tf, pathlib as _pl
    rd = _pl.Path(_tf.mkdtemp()) / "rides"; rd.mkdir()
    hdr = "time,power_w,cadence_rpm\n"
    (rd / "ride_2026-09-28_0900.csv").write_text(hdr + "".join(f"2026-09-28T09:{m:02d}:{s:02d},120,80\n" for m in range(10) for s in range(60)))
    (rd / "ride_2026-09-28_1200.csv").write_text(hdr + "".join(f"2026-09-28T12:00:{s:02d},0,0\n" for s in range(60)))
    (rd / "ride_2026-09-28_0900_events.csv").write_text("time,event\n")
    lr = coach.last_ride(rd)
    check(f"the last ride is the latest with 5+ minutes of pedalling ({lr})", lr and lr["id"] == "ride_2026-09-28_0900" and lr["minutes"] == 10)
    plan30 = {"plans": {"2026-09-30": {"sport": "ride", "minutes": 30}}}
    check("an attempt cut short is not the day's ride: 5 of a planned 30 minutes doesn't count, nor 12; 15 does",
          not coach.counts(plan30, "2026-09-30", "bike", 5.4) and not coach.counts(plan30, "2026-09-30", "bike", 12)
          and coach.counts(plan30, "2026-09-30", "bike", 15))
    check("nothing planned: it counts from 10 minutes", coach.counts({"plans": {}}, "2026-09-30", "bike", 11)
          and not coach.counts({"plans": {}}, "2026-09-30", "bike", 9))
    (rd / "ride_2026-09-30_0322.csv").write_text(hdr + "".join(f"2026-09-30T03:{22 + m:02d}:{s:02d},110,70\n" for m in range(5) for s in range(60)))
    lr2 = coach.last_ride(rd, d=plan30)
    check(f"...and it isn't the ride offered for rating ({lr2 and lr2['id']})", lr2 and lr2["id"] == "ride_2026-09-28_0900")
    (rd / "ride_2026-09-30_0400.csv").write_text(hdr + "".join(f"2026-09-30T04:{m:02d}:{s:02d},110,70\n" for m in range(25) for s in range(60)))
    lr3 = coach.last_ride(rd, d=plan30)
    check(f"stopped then picked up again: the two pieces are one 30-minute ride ({lr3})",
          lr3 and lr3["date"] == "2026-09-30" and lr3["minutes"] == 30 and lr3["id"] == "ride_2026-09-30_0400")
    (rd / "ride_2026-09-30_0400.csv").unlink(); (rd / "ride_2026-09-30_0322.csv").unlink()
    dd = coach.load(coach.file_for(rd))
    check("a rating is kept", coach.rate(dd, lr["id"], 6)["rpe"] == 6 and dd["ratings"][lr["id"]]["rpe"] == 6)
    for bad in ((lr["id"], 11), ("../x", 5)):
        try:
            coach.rate(dd, *bad); check(f"refuses {bad}", False)
        except ValueError:
            check(f"refuses {bad}", True)

    # dates to plan backward from
    ev = coach.add_event(dd, "2026-10-03", "FTP ramp test", "test", "bike")
    coach.add_event(dd, "2026-11-08", "Hometown 5K", "race", "run")
    up = coach.upcoming(dd, "2026-10-01", running_cleared_in=117)
    check(f"soonest first, with days to go ({[(e['name'], e['days']) for e in up]})", [e["days"] for e in up] == [2, 38])
    check(f"a test two days out: easy from here ({up[0]['notes'][0]})", "easy" in up[0]["notes"][0])
    check(f"a 5K before running is cleared says so ({up[1]['notes'][-1][:60]}...)", "heads-up" in up[1]["notes"][-1])
    check("a passed event drops off", [e["name"] for e in coach.upcoming(dd, "2026-10-05")] == ["Hometown 5K"])
    check("remove by id", coach.remove_event(dd, ev["id"]) and len(dd["events"]) == 1)
    try:
        coach.add_event(dd, "soon", "x"); check("bad date refused", False)
    except ValueError:
        check("bad date refused", True)

    # the week's markers: what to do and for how long, and what was done
    coach.set_plan(dd, "2026-09-29", "easy", "Easy swim", sport="swim", minutes=60)
    coach.set_plan(dd, "2026-10-03", sport="test", minutes=25)
    wk = coach.week(dd, "2026-10-01", {"2026-09-29": [{"sport": "swim", "minutes": 58}]})
    check(f"Monday to Sunday, with markers and what was done ({[(w['date'][5:], w['sport'], w['minutes']) for w in wk if w['sport']]})",
          len(wk) == 7 and wk[0]["date"] == "2026-09-28" and wk[1]["sport"] == "swim" and wk[1]["minutes"] == 60
          and wk[1]["done"][0]["minutes"] == 58 and wk[5]["sport"] == "test")
    coach.set_sessions(dd, "2026-09-30", [
        {"sport": "swim", "minutes": 35, "name": "Technique", "steps": ["6 x 50 easy drill"]},
        {"sport": "ride", "minutes": 25, "name": "Easy spin", "steps": ["5 min warm-up", "20 min easy"]}])
    wed = coach.week(dd, "2026-09-30")[2]
    check("two sports and their sets stay on one day", len(wed["sessions"]) == 2
          and wed["sessions"][0]["steps"] == ["6 x 50 easy drill"] and wed["sessions"][1]["sport"] == "ride")
    try:
        coach.set_plan(dd, "2026-09-30", sport="skydive"); check("unknown sports refused", False)
    except ValueError:
        check("unknown sports refused", True)
    import tempfile as _t
    dj = coach.load(pathlib.Path(_t.mkdtemp()) / "coach.json")
    cj = coach.record(dj, "2026-09-30", {"hops_left": 4, "hops_right": 2, "journal": "  calves tight, hamstrings worse  "})
    check(f"the hop test leg by leg: the worse leg is the number ({cj['hops']})", cj["hops"] == 2)
    cj = coach.record(dj, "2026-09-30", {"hops_right": 6})
    check(f"...update one leg and it re-takes the worse ({cj['hops']})", cj["hops"] == 4)
    check("the journal is kept in the rider's words, trimmed", cj["journal"] == "calves tight, hamstrings worse")
    check("...and an empty one clears it", coach.record(dj, "2026-09-30", {"journal": " "})["journal"] is None)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
