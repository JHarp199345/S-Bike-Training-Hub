"""Today's focus: a cadence range and a watt range per day, from the coach plan to auto-shift, the ride view
and the ride's story."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, datetime as dt
import coach, focus
from pathlib import Path
from test_hills import make_bridge


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    f = focus.resolve("cadence", 180)
    check(f"cadence habit at FTP 180: 65-80 rpm, zone 2 = {f['watts']} W", f["rpm"] == [65, 80] and f["watts"] == [101, 135])
    g = focus.resolve("grit", 180)
    check(f"grit: lower cadence, more watts ({g['rpm']} rpm, {g['watts']} W)", g["rpm"][1] <= 65 and g["watts"][0] > f["watts"][1])
    check("leg speed: faster and lighter", focus.resolve("speed", 180)["rpm"][0] >= 85)
    check("the watts follow FTP", focus.resolve("cadence", 200)["watts"] == [112, 150])
    check("'off' keeps the cadence range and drops the watts", focus.resolve("off", 180)["watts"] is None)
    check("no focus set: cadence habit; a rest day that's ridden anyway: recovery",
          focus.resolve(None, 180)["key"] == "cadence" and focus.resolve(None, 180, verdict="rest")["key"] == "recovery")
    check("the rider's own cadence range carries into cadence habit", focus.resolve("cadence", 180, (70, 85))["rpm"] == [70, 85])
    c = focus.check({"name": "Hill grind", "rpm": [55, 68], "watts": [140, 170]})
    check(f"a custom focus is kept as given ({focus.resolve(c, 180)})", focus.resolve(c, 180)["watts"] == [140, 170])
    cp = focus.resolve(focus.check({"name": "Tempo", "rpm": [80, 90], "pct": [0.8, 0.9]}), 180)
    check(f"...or in % of FTP ({cp['watts']})", cp["watts"] == [144, 162])
    for bad in ("sprint", {"rpm": [80, 60]}, {"rpm": [60, 62]}, {"rpm": [60, 80], "watts": [5, 900]}):
        try:
            focus.check(bad); check(f"refuses {bad}", False)
        except focus.BadFocus:
            check(f"refuses {bad}", True)

    t = focus.Tracker()
    for cad, w in [(75, 120)] * 30 + [(60, 120)] * 10 + [(75, 150)] * 10 + [(0, 0)] * 20:
        t.add(f, cad, w)
    st = t.status(f, 75, 150)
    check(f"time in range counts pedalling seconds only ({st['seconds']} s: {st['in_range']})",
          st["seconds"] == 50 and st["in_range"] == {"rpm": 80, "watts": 80, "both": 60})
    check(f"hints: over the watts -> '{st['hint']}'", st["hint"] == "ease off a touch" and st["watts_ok"] is False)
    check("on a climb it can't fix, it says so", "climb" in t.status(f, 72, 170, limited="easiest")["hint"])
    check("under the cadence range: spin faster", t.status(f, 58, 100)["hint"] == "spin a little faster")

    # the plan -> the bridge -> auto-shift, and the event that the ride's story reads back
    br = make_bridge()
    rides = Path(br.csv_path).parent
    d = coach.load(coach.file_for(rides))
    coach.set_plan(d, coach.today(), "easy", focus_="grit"); coach.save(d)
    br.refresh_focus(force=True)
    check(f"the bridge picks up today's plan: {br.focus['name']}, auto-shift {br.auto.low:.0f}-{br.auto.high:.0f} rpm, "
          f"{br.auto.watt_band}", br.focus["key"] == "grit" and (br.auto.low, br.auto.high) == (55, 65) and br.auto.watt_band)   # grit step 1 on its ladder
    check("the ride view gets it in the status", br.status()["focus"]["name"] == "Grit / force")
    ev = [e for e in br.events if "Focus -" in e]
    check(f"it's written to the ride's events ({ev[0].split('  ', 1)[-1] if ev else None})", ev)
    coach.set_plan(d, coach.today(), focus_=""); coach.save(d)
    br.refresh_focus(force=True)
    check("clearing it goes back to the default (cadence habit on an easy day)", br.focus["key"] == "cadence")
    try:
        coach.set_plan(d, coach.today(), focus_="warp"); check("a bad focus is refused by the plan", False)
    except focus.BadFocus:
        check("a bad focus is refused by the plan", True)

    t0 = dt.datetime(2026, 9, 28, 9)
    rows = [{"t": t0 + dt.timedelta(seconds=s), "power": 120.0 if s < 400 else 170.0, "cadence": 75.0, "erg": None}
            for s in range(600)]
    events = [(t0.isoformat(), "Focus - Cadence habit: 65-80 rpm, 101-135 W")]
    r = focus.for_ride(rows, events)
    check(f"the ride's story: {r}", r["both_pct"] == 67 and r["rpm_pct"] == 100 and r["minutes"] == 10)
    check("a ride with no focus event has no focus line", focus.for_ride(rows, []) is None)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
