"""Self-healing: watchdog decisions, crash snapshot + resume, supervised tasks."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, csv, os, tempfile, time, types
import bridge as b
from watchdog import Watchdog
from test_hills import ARGS


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    # ── watchdog ────────────────────────────────────────────────────────────
    d = Watchdog(); run = {"running": True}
    check("bridge answering: nothing to do", d.tick(0, True, run, True) is None)
    check("stopped on purpose (running=false): leave it off", d.tick(5, False, {"running": False}, False) is None)
    check("crashed (process gone): restart", d.tick(10, False, run, False) == "restart")
    check("...then leaves the new one 30 s to start up", d.tick(20, False, run, False) is None)
    d = Watchdog()
    check("alive but silent 10 s: still patient", d.tick(0, False, run, True) is None and d.tick(10, False, run, True) is None)
    check("alive but silent 20 s: frozen -> kill and restart", d.tick(20, False, run, True) == "kill_and_restart")
    d = Watchdog(grace=0)
    acts = [d.tick(t, False, run, False) for t in (0, 60, 120, 180)]
    check(f"a 4th crash within 10 min: stops restarting and says so {acts}", acts == ["restart"] * 3 + ["give_up"])
    d.reset(); check("starting it by hand resets the count", d.tick(200, False, run, False) == "restart")

    # ── crash snapshot + resume (throwaway folder and state file) ───────────
    work = pathlib.Path(tempfile.mkdtemp()); cwd = os.getcwd(); os.chdir(work)
    b.STATE = work / "state.json"
    try:
        br = b.Bridge(types.SimpleNamespace(**ARGS))
        br.csv.writerow(["2026-09-26T10:00:00", 120, 75, 20, 100, 5, 24.0, 1500.0, 2.0, 1, -0.7, ""])
        br.ride.vdistance, br.ride.grade, br.gear = 1500.0, 2.0, 1
        br.erg.start_workout({"name": "Zone 2 (45 min)", "steps": [{"minutes": 10, "watts": 85},
                              {"minutes": 25, "watts": 110}]}, time.monotonic() - 700)
        br.snapshot()
        st = b.read_state(); st["pid"] = 999999; b.write_state(st)     # as if the process died
        check("snapshot written while riding", st["running"] and st["ride"] == str(br.csv_path))
        br2 = b.Bridge(types.SimpleNamespace(**ARGS))
        check("a new bridge after the crash picks up the SAME ride file", br2.resumed and br2.csv_path == br.csv_path)
        br2.restore(br2.resumed)
        check(f"distance, grade and gear restored ({br2.ride.vdistance:.0f} m, {br2.ride.grade}%, gear {br2.gear:+d})",
              br2.ride.vdistance == 1500 and br2.ride.grade == 2.0 and br2.gear == 1)
        ws = br2.erg.workout_status(time.monotonic())
        check(f"ERG workout carries on where it was (step {ws['step']} at {ws['watts']:.0f} W)", ws["step"] == 2 and br2.erg.target == 110)
        br2.csv.writerow(["2026-09-26T10:00:30", 118, 74, 20, 110, 5, 24.0, 1700.0, 2.0, 1, -0.7, 110])
        rows = list(csv.reader(open(br.csv_path)))
        check(f"ride file appended, one header, both halves kept ({len(rows) - 1} rows)",
              sum(r[0] == "time" for r in rows) == 1 and len(rows) == 3)
        br2.snapshot(running=False)
        check("a clean stop is not resumed", b.resumable_state() is None)
        st = b.read_state(); st["running"] = True; st["pid"] = 999999; st["saved_at"] = time.time() - 20 * 60; b.write_state(st)
        check("a crash from over 15 minutes ago starts a fresh ride", b.resumable_state() is None)
        st["saved_at"] = time.time(); st["pid"] = os.getpid(); b.write_state(st)
        check("a state whose process is still alive is never resumed (no double riders)", b.resumable_state() is None)
    finally:
        os.chdir(cwd)

    # ── supervised tasks ────────────────────────────────────────────────────
    br.event = lambda m: None
    runs = []
    async def flaky():
        runs.append(1)
        if len(runs) < 3:
            raise RuntimeError("boom")
    await asyncio.wait_for(br.supervised("Test part", flaky), 5)
    check(f"a part that errors is restarted until it runs clean ({len(runs)} tries)", len(runs) == 3)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
