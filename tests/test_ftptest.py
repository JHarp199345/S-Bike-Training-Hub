"""FTP ramp test: measures a known rider's FTP within a few percent, end to end."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, tempfile
import bridge as b
import rider
from erg import Erg
from ftptest import RampTest
from test_erg import bike_power
from test_hills import make_bridge

rider.PATH = pathlib.Path(tempfile.mkdtemp()) / "profile.json"      # never touch the real profile


def ride_test(true_ftp, estimate=180, stop_at=None):
    """A simulated rider on the simulated S29, ERG holding the test's targets.
    The simulated rider can follow any target up to their max-minute power (1.33 x FTP, the ratio
    the 75% rule assumes); above it their cadence collapses."""
    t, level, e = 0.0, 5, Erg(min_cadence=45)       # as the bridge sets it for a test
    test = RampTest(estimate, t)
    e.set(test.target(t), "FTP test", t)
    mmp = 1.33 * true_ftp
    for _ in range(3600):
        t += 1
        tgt = test.target(t)
        if (tgt or 0) <= mmp:
            # Within their limit they hold ~82 rpm, and if the bike is already at its
            # hardest level they spin faster to make the watts (up to 100 rpm).
            cad = min(100.0, max(82.0, (tgt or 0) / bike_power(level, 1))) if level == 16 else 82.0
        else:
            cad = max(30.0, 82 - ((tgt or 0) - mmp) * 1.5)            # past their max: legs give out
        p = bike_power(level, cad)
        new = test.update(t, p, cad)
        if stop_at and test.phase == "ramp" and t - test.phase_at >= stop_at:
            test.finish(t, "stopped with the button")
        if new is None:
            break
        if new != e.target:
            e.target = new; e.samples.clear()
        level = max(1, min(16, level + e.update(p, cad, t)))
    return test


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    for true in (160, 200, 240):
        te = ride_test(true)
        err = (te.result - true) / true * 100 if te.result else 999
        check(f"rider with FTP {true} W measures {te.result} W ({err:+.0f}%), ended because: {te.reason}", abs(err) <= 8)
    te = ride_test(200, stop_at=None); check("test finishes with a cool-down, then hands control back", te.phase == "done")
    te = RampTest(180, 0); te.update(60, 90, 80); te.finish(60, "stopped with the button")
    check("stopped during warm-up: no FTP, straight to cool-down", te.result is None and te.phase == "cool-down")
    te = ride_test(200, stop_at=180)
    check(f"stopped after 3 min of ramp: too short, no result ({te.result})", te.result is None)
    te = ride_test(200, stop_at=420)
    check(f"stopped after 7 min of ramp: result from the best minute so far ({te.result} W)", te.result and te.result < 200)

    te = RampTest(180, 0); te.update(300, 90, 80)
    for t in range(301, 305): te.update(t, 0, 0)
    check("brief zero readings do not end the ramp", te.phase == "ramp")
    te.update(305, 100, 80)
    for t in range(306, 312): te.update(t, 0, 0)
    check("stopping completely for five seconds starts cool-down", te.phase == "cool-down" and "stopped" in te.reason)
    p = RampTest.preview(180)
    check("preview uses controller warm-up and first ramp step", p["warm_w"] == RampTest(180, 0).warm_w and p["start_w"] == RampTest(180, 0).start_w)
    te = RampTest(180, 0); te.phase, te.phase_at, te.best_1min = "ramp", 300, 264
    te.finish(600, "test limit")
    check("forecast frozen before test and compared with actual result", te.comparison()["prediction"]["predicted_ftp"] == 180 and te.comparison()["error_w"] == 18)

    # In the bridge: result is saved, workouts and the up-shift guard rescale.
    br = make_bridge(); br.profile = rider.load(); br.args.upshift_cap_w = None
    br.ftp_test_start()
    check("starting the test turns ERG on at the warm-up watts", br.erg.on and br.erg.source == "FTP test" and br.erg.target == br.test.warm_w)
    t0 = br.test.phase_at
    br.test.phase, br.test.phase_at = "ramp", t0 - 600          # 10 minutes into the ramp
    br.test.best_1min = 264.0
    br.test.finish(t0, "couldn't hold 190 W"); br.ftp_test_tick(t0 + 1, 100, 70)
    check(f"FTP saved to the profile: {br.profile['ftp']} W ({br.profile['ftp_source']})",
          br.profile["ftp"] == 198 and rider.load()["ftp"] == 198)
    check(f"old value kept in history ({br.profile['history'][-1]['ftp']} W)", br.profile["history"][-1]["ftp"] == rider.DEFAULT["ftp"])
    check(f"up-shift guard rescaled to 90% of the new FTP ({br.auto.power_cap:.0f} W)", round(br.auto.power_cap) == 178)
    br.workout_start(1)
    check(f"Zone 2 workout now rides at {br.erg.workout['steps'][1][1]:.0f} W (61% of 198)", br.erg.workout["steps"][1][1] == 120)
    check("status shows the new FTP", br.status()["ftp"] == 198)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
