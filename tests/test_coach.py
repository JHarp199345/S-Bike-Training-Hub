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
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
