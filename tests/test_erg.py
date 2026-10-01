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
            e.set(watts, "FTP test", t) if e.target != watts else None   # the tight controller (FTP test, Kinomap)
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
    check(f"tiring rider at 140 W: ERG backs off instead of grinding him to a stop (cadence ends {cads[-1]:.0f} rpm)", min(cads) >= 45)
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
    br.workout_start(0); t0 = br.erg.workout["started"]
    pedal = lambda a, b, rpm=80, on=True: [br.erg.tick_clock(t0 + s, rpm, on) for s in range(a, b + 1)]
    pedal(1, 200); st = br.erg.workout_status(t0 + 200)
    check(f"workout steps advance with pedalling time (200 s in: step {st['step']} at {st['watts']:.0f} W)", st["step"] == 2 and st["watts"] == 110)
    pedal(201, 320, rpm=0); st2 = br.erg.workout_status(t0 + 320)
    check(f"stopping pauses the workout clock (2 min stopped: still {st2['elapsed']:.0f} s in, auto-paused {st2['auto_paused']})",
          abs(st2["elapsed"] - st["elapsed"]) < 2 and st2["auto_paused"])
    pedal(321, 400, on=False); check("a dropped bike pauses it too", abs(br.erg.workout_status(t0 + 400)["elapsed"] - st["elapsed"]) < 2)
    br.erg.paused = True; pedal(401, 460)
    check("paused by hand: pedalling doesn't move it", abs(br.erg.workout_status(t0 + 460)["elapsed"] - st["elapsed"]) < 2)
    br.erg.paused = False; pedal(461, 461 + 420)
    br.erg._advance_workout(t0 + 881)
    check("workout ends by itself after its last step (of pedalling)", not br.erg.on)
    # resume: a workout that stopped before the end is picked up at the same block and second
    import tempfile, pathlib as _p, datetime as _dt
    br.resume_file = _p.Path(tempfile.mkdtemp()) / "resume.json"; br.resume = None
    br.workout_start(0); t0 = br.erg.workout["started"]; total = sum(d for d, _ in br.erg.workout["steps"])
    for s in range(1, 21): br.erg.tick_clock(t0 + s, 80, True); br.resume_tick()
    check("under 30 s of pedalling: nothing worth resuming yet", br.resume is None)
    for s in range(21, 201): br.erg.tick_clock(t0 + s, 80, True); br.resume_tick()
    was = br.erg.workout_status(t0 + 200)
    br.erg_set(None); br.resume_tick()                              # End (or the morning's reset)
    off = br.status()["resume"]
    check(f"ended early: the offer is there, and it survives on disk ({off})",
          off and abs(off["elapsed"] - 200) <= 5 and off["step"] == was["step"] and br.resume_file.exists())
    check("resuming starts at the same block, second and watts", br.workout_resume()
          and abs(br.erg.workout_status(0)["elapsed"] - 200) <= 5 and br.erg.target == int(was["watts"])
          and br.erg.workout_status(0)["step"] == was["step"])
    check("while it runs there is no offer", br.status()["resume"] is None)
    now = br.erg.workout["last"]
    for s in range(1, 61): br.erg.tick_clock(now + s, 0, True); br.resume_tick()
    check("the resumed clock waits for the pedals", abs(br.erg.workout_status(0)["elapsed"] - 200) <= 5 and br.erg.auto_paused)
    for s in range(61, 61 + int(total)): br.erg.tick_clock(now + s, 80, True); br.erg._advance_workout(now + s); br.resume_tick()
    br.resume_tick()
    check("finished by itself: nothing left to resume", not br.erg.on and br.resume is None and not br.resume_file.exists())
    br.resume = {"name": "Old", "steps": [[600, 100]], "active": 120.0, "date": (_dt.date.today() - _dt.timedelta(days=1)).isoformat(), "saved": 0}
    check("yesterday's unfinished workout is not offered", br.status()["resume"] is None)
    br.resume = None
    # workout ERG: zones, not a hair-trigger band (FTP tests, Kinomap and held watts keep the tight control above)
    from erg import Erg as ZErg
    def ride(watts, secs, target=150):
        e = ZErg(); e.set(target, "workout 'Z'", 0.0); moves = []
        for s in range(1, secs + 1):
            m = e.update(watts, 80, float(s))
            if m: moves.append((s, m))
        return moves
    check("green (100-120% of target): never shifts - 175 W on a 150 W block for 5 min", ride(175, 300) == [])
    yl = ride(125, 200)
    check(f"yellow under (83%): harder gear after a sustained 15-second shortfall ({yl})", yl and yl[0][1] == 1 and 15 <= yl[0][0] <= 20)
    rd = ride(110, 60)
    check(f"red under (73%): correction after 15 seconds ({rd[:1]})", rd and 15 <= rd[0][0] <= 20)
    bk = ride(270, 30)
    check(f"black over (180%): an easier gear after ~8 s ({bk[:1]})", bk and bk[0][1] == -1 and bk[0][0] <= 16)
    # look before shifting: at a high level one gear is a big jump - never shift the rider off the road
    def ride_at(watts, level, secs, target=150, gear=None):
        e = ZErg(); e.set(target, "workout 'Z'", 0.0)
        if gear: e.GEAR = gear
        return [(s, m) for s in range(1, secs + 1) if (m := e.update(watts, 80, float(s), level))]
    after = ZErg(); after.set(150, "workout 'Z'", 0.0)
    coarse = ZErg(); coarse.GEAR = (0.1, 0.6)          # a bike with big steps between gears
    jump = coarse.predict(125, 1, +1) / 150
    held = ride_at(125, 1, 300, gear=(0.1, 0.6))
    check(f"yellow under where one harder gear would overshoot to {jump:.0%} (off the road): it holds ({held})",
          jump > 1.4 and held == [])
    check(f"on the S29 one gear is at most ~{after.predict(100, 1, 1) / 100 - 1:.0%}, so from yellow the next gear stays on the road",
          after.predict(100, 1, 1) / 100 < 1.25)
    fine = ride_at(125, 10, 200)
    check(f"yellow under at a high gear, where the next lands in green ({after.predict(125, 10, 1) / 150:.0%}): it shifts ({fine[:1]})",
          fine and fine[0][1] == 1)
    rd2 = ride_at(100, 12, 60)
    check(f"red: shifts when the next gear gets closer ({rd2[:1]})", rd2 and rd2[0][1] == 1)
    e = ZErg(); e.set(150, "workout 'Z'", 0.0)
    bog = [s for s in range(1, 40) if e.update(150, 45, float(s))]
    check(f"legs bogging down (45 rpm) still gets an easier gear within seconds ({bog[:1]})", bog and bog[0] <= 16)
    e = ZErg(); e.set(90, "workout 'floor'", 0)
    moves = [(s, m) for s in range(1, 120) if (m := e.update(70 if (s // 8) % 2 else 76, 75, float(s), 2))]
    check(f"70–76 W fluctuations cannot cancel the 90 W floor upshift ({moves[:1]})",
          moves and moves[0][1] == 1 and moves[0][0] <= 20)
    check("85 W is below the 90 W floor and earns a harder gear", bool(ride_at(85, 2, 30, target=90)))
    for watts in (100, 110, 120):
        check(f"easy 90 W floor: {watts} W is accepted without downshifting", ride_at(watts, 3, 180, target=90) == [])
    e = ZErg(); e.set(90, "workout 'floor'", 0); e.GEAR = (.1, .4)
    moves = [(s, m) for s in range(1, 30) if (m := e.update(70, 75, float(s), 1))]
    check("a gear reaching 126 W wins over remaining at 70 W below a 90 W floor", moves and moves[0][1] == 1)

    e = ZErg(); e.set(80, "workout 'cooldown'", 0)
    for t in range(1, 18): e.update(70, 77, t, 2)
    before = len(e.samples)
    m = e.update(96, 77, 18, 3)
    check("manual shift to successful gear clears stale low readings and holds", before > 3 and m == 0 and len(e.samples) == 1)
    check("successful cooldown gear never triggers the logged harder shift", all(e.update(96, 77, t, 3) == 0 for t in range(19, 90)))
    e = ZErg(); e.set(115, "workout 'hold'", 0)
    moves = [e.update(113 if 20 <= t < 40 else 118, 80, t, 4) for t in range(1, 100)]
    check("temporary two-watt dip recovers without changing gear", not any(moves))
    e = ZErg(); e.set(90, "workout 'easiest'", 0)
    e.level_rates = {2:70/80, 3:110/80, 4:140/80}
    moves = [(t,m) for t in range(1, 70) if (m := e.update(140,80,t,4))]
    check("settled excess selects a measured easier gear that still meets goal", moves and moves[0][1] == -1)
    e = ZErg(); e.set(90, "workout 'easiest'", 0)
    e.level_rates = {2:70/80, 3:110/80}
    check("holds easiest successful gear when the next lower gear misses goal", all(e.update(110,80,t,3) == 0 for t in range(1,180)))

    adaptive = {"name": "Linked workout", "blocks": [{"type": "steady", "label": "Warm-up", "minutes":1}, {"type": "ramp", "minutes":1}],
                "steps": [{"minutes": 1, "watts": 90}, {"minutes": .5, "watts": 100},
                          {"minutes": .5, "watts": 110}, {"minutes": 1, "watts": 117},
                          {"minutes": 1, "watts": 81}]}
    e = ZErg(); e.start_workout(adaptive, 1)
    for s in range(2, 62): e.update(120 if s < 57 else 300, 75, float(s), 3)
    check("warm-up scaling is bounded to keep an easy peak at 75% FTP (135 W), ignoring a late spike",
          e.workout["steps"][3][1] == 135 and e.target == 115 and e.workout["scale"] == 135 / 117)
    check("ramp loosens cadence to 55–110 rpm while retaining its changing power floor",
          e.workout_status(62)["cadence_band"] == [55,110] and e.workout_status(62)["power_floor"] == 115)
    # A completed interval rebases cooldown from its actual sustained effort.
    e.workout["active"] = 179; e.workout["last"] = 200; e.workout["segment_index"] = 3; e.target = 156
    e.segment_samples.clear(); e.segment_samples.extend((t, 170, 75) for t in range(170, 201))
    e.update(170, 75, 201, 3)
    check("170 W interval finish scales the planned cooldown proportionally", e.target == round(81 * 170 / 117))
    saved = e.adaptive_state()
    e2 = ZErg(); e2.start_workout({"name": adaptive["name"], "steps": [{"minutes": d/60, "watts": p} for d, p in e.workout["steps"]]}, 300)
    e2.workout.update(saved); e2.workout["active"] = e.workout["active"]; e2._advance_workout(300)
    check("resume retains the adapted targets and immutable planned targets", e2.target == e.target and e2.workout["planned_steps"] == e.workout["planned_steps"])
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
