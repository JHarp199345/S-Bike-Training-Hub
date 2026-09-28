"""Virtual ERG: holds watts by moving resistance, never overrules a dying cadence."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json
import bridge as b
from erg import Erg
from test_hills import make_bridge


def bike_power(level, cadence):
    # Fitted to real S29 rides: L3@77rpm=95 W, L4@71=106 W, L9@52=116 W.
    return (0.72 + 0.17 * level) * cadence


def rider_cadence(level, tired=0.0):
    return max(35, 80 - 3 * (level - 4) - tired)


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    # 1. The controller alone, closed loop with the simulated bike and rider.
    def ride(target_steps, tired=lambda t: 0.0, start_level=5):
        e, level, t, log = Erg(), start_level, 0.0, []
        for secs, watts in target_steps:
            e.set(watts, "test", t) if e.target != watts else None
            for _ in range(int(secs)):
                t += 1
                cad = rider_cadence(level, tired(t)); p = bike_power(level, cad)
                level = max(1, min(16, level + e.update(p, cad, t)))
                log.append((t, watts, level, cad, p))
        return log
    log = ride([(120, 110)])
    last = log[-30:]; avg = sum(p for *_, p in last) / len(last)
    check(f"holds 110 W: last 30 s average {avg:.0f} W at level {last[-1][2]}, {last[-1][3]:.0f} rpm", abs(avg - 110) / 110 < 0.08)
    settle = next((t for t, w, l, c, p in log if abs(p - 110) / 110 < 0.07), None)
    check(f"gets there within 30 s from level 5 (took {settle} s)", settle is not None and settle <= 30)
    log = ride([(180, 80), (180, 110), (120, 140), (120, 80)])
    for lo, hi, w in ((150, 180, 80), (330, 360, 110), (450, 480, 140), (570, 600, 80)):
        seg = [p for t, *_, p in log if lo < t <= hi]; avg = sum(seg) / len(seg)
        check(f"  step {w} W: holding {avg:.0f} W", abs(avg - w) / w < 0.1)
    log = ride([(240, 140)], tired=lambda t: 0 if t < 60 else min(40, (t - 60) * 0.5))
    cads = [c for *_, c, p in log[-40:]]
    check(f"tiring rider at 140 W: ERG backs off instead of grinding them to a stop (cadence ends {cads[-1]:.0f} rpm)", min(cads) >= 45)
    check("no level ever outside 1-16", all(1 <= l <= 16 for _, _, l, _, _ in log))

    # 2. Inside the bridge.
    br = make_bridge()
    class CP: uuid = b.CONTROL
    def kinomap(hx): br.on_write(CP(), bytes.fromhex(hx))
    kinomap("11000000002833")
    br.erg_set(110)
    check("panel ERG on: auto-shift reports paused", br.status()["auto"] is False)
    before = br.target_level; kinomap("11000058022833")
    check("panel ERG: a Kinomap hill changes speed physics, not resistance", br.target_level == before and br.ride.grade == 6)
    br.erg_set(None)
    check(f"ERG off: back to the +6% hill level ({br.target_level})", br.target_level == round(4.75 + 0.75 * 6 - 6 / 3 + br.gear))
    kinomap("059600")
    check("Kinomap ERG (hold 150 W) is accepted and held by the bridge", br.erg.target == 150 and br.erg.source == "Kinomap")
    kinomap("11000000002833")
    check("Kinomap sending hills again ends its ERG", not br.erg.on)
    feat = br.on_read(type("C", (), {"uuid": b.FEATURE, "value": None})())
    tb = int.from_bytes(feat[4:8], "little")
    check("Kinomap is told: resistance, power target and hill simulation", tb >> 2 & 1 and tb >> 3 & 1 and tb >> 13 & 1)
    names = [w["name"] for w in br.workouts]
    check(f"{len(names)} workouts load, the presets among them: {names}", len(names) >= 5 and "ERG check (10 min)" in names)
    br.profile["ftp"] = 180                                   # the preset's % steps at a known FTP
    br.workout_start(0); st = br.erg.workout_status(br.erg.workout["started"] + 200)
    check(f"workout steps advance on time (200 s in: step {st['step']} at {st['watts']:.0f} W)", st["step"] == 2 and st["watts"] == 110)
    br.erg._advance_workout(br.erg.workout["started"] + 601)
    check("workout ends by itself after its last step", not br.erg.on)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
