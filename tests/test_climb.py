"""Climbing mode: standing, big gear, 30-45 rpm - by button or by shifting harder on a hill."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio
import bridge as b
from test_hills import make_bridge


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    br = make_bridge()
    t = [0.0]; br.auto.clock = lambda: t[0]
    class CP: uuid = b.CONTROL
    def hill(g): br.on_write(CP(), b"\x11\x00\x00" + int(g * 100).to_bytes(2, "little", signed=True) + b"\x28\x33")
    def pedal(rpm, secs):
        shifts = []
        for _ in range(secs):
            t[0] += 1
            r = br.auto.update(rpm)
            if r: shifts.append((int(t[0]), r))
        return shifts
    pedal(75, 20)
    hill(6); pedal(75, 8)
    # The 04:37 ride: hand shifts harder on the climb, then grinds at ~50 rpm standing.
    br.shift(+1); br.shift(+1)
    check("hand shift harder on a +6% climb turns climbing mode on", br.auto.climbing and br.auto.climb_auto)
    s = pedal(50, 90)
    check(f"standing at 50 rpm for 90 s: no down-shift this time {s}", all(d > 0 for _, d in s) or s == [])
    s = pedal(40, 60)
    check(f"40 rpm in climbing mode: left alone {s}", s == [])
    s = pedal(27, 12)
    check(f"27 rpm (about to stall): shifts easier {s[:1]}", s and s[0][1] == -1)
    hill(0.5)
    check("over the top: climbing mode ends by itself", not br.auto.climbing)
    check(f"band back to normal {br.auto.low:.0f}-{br.auto.high:.0f}", (br.auto.low, br.auto.high) == br.auto.normal_band)
    hill(0); br.shift(+1)
    check("hand shift harder on the flat does NOT start climbing mode", not br.auto.climbing)
    hill(5); br.shift(+1); br.shift(-1)
    check("hand shift easier ends automatic climbing mode", not br.auto.climbing)
    br.climbing(True); hill(0)
    check("climbing mode from the button stays on over the top", br.auto.climbing)
    br.climbing(False)
    check("button off: normal band", not br.auto.climbing and (br.auto.low, br.auto.high) == br.auto.normal_band)
    check("status reports it", br.status()["climbing"] is False and br.status()["band"] == list(br.auto.normal_band))
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
