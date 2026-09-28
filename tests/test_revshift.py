"""Rev-matched up-shifts, growing shift pacing, watts guard, descent gears handed back."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, time
import bridge as b
from autoshift import AutoShift
from test_hills import make_bridge


class Clock:
    t = 0.0
    def __call__(self): return self.t


def shifter(**kw):
    clk = Clock(); gear = [0]
    def shift(d, why): gear[0] += d; return True
    a = AutoShift(shift, low=65, high=80, up_hold=3, clock=clk, **kw)
    return a, clk, gear


def run(a, clk, cads, power=None):
    out = []
    for c in cads:
        clk.t += 1; r = a.update(c, power=power)
        if r: out.append((int(clk.t), r))
    return out


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    a, c, g = shifter(); run(a, c, [75] * 20)
    s = run(a, c, [92] * 4)
    check(f"revving to 92 rpm: shifts harder within ~2 s {s}", s and s[0][0] - 20 <= 3)
    a, c, g = shifter(); run(a, c, [75] * 20)
    s = run(a, c, [83] * 8)
    check(f"just over at 83 rpm: waits the normal ~3 s {s}", s and s[0][0] - 20 >= 4)
    a, c, g = shifter(); run(a, c, [75] * 20)
    s = run(a, c, [92] * 45)
    gaps = [y - x for (x, _), (y, _) in zip(s, s[1:])]
    check(f"holding 92: keeps shifting up, gaps grow like a car's gears {gaps}", len(s) >= 5 and gaps == sorted(gaps) and gaps[-1] > gaps[0])
    check("  ...and never more than one gear per shift", all(d == 1 for _, d in s))
    run(a, c, [75] * 10); s = run(a, c, [92] * 4)
    check(f"back in the band resets the pacing: next rev shifts quick again {s}", s and s[0][0] - c.t >= -3)
    a, c, g = shifter(power_cap=165); run(a, c, [75] * 20)
    check("pushing 170 W at 86 rpm: no more gears (guard)", run(a, c, [86] * 10, power=170) == [])
    check("pushing 170 W but really spinning, 92 rpm: gear allowed", run(a, c, [92] * 4, power=170) != [])
    a, c, g = shifter(); run(a, c, [75] * 20); a.hill_changed()
    s = run(a, c, [40] * 12)
    check(f"cadence collapses to 40 right after the road changed: drops two gears {s[:1]}", s and s[0][1] == -2)
    a, c, g = shifter(); run(a, c, [75] * 60)
    s = run(a, c, [60] * 12)
    check(f"a slow sag with no road change: still one gear at a time {s[:1]}", s and s[0][1] == -1)

    # In the bridge: the stacking scenario.
    br = make_bridge()
    class CP: uuid = b.CONTROL
    def hill(g): br.on_write(CP(), b"\x11\x00\x00" + int(g * 100).to_bytes(2, "little", signed=True) + b"\x28\x33")
    hill(0); br.shift(+1)                              # a gear he earned on the flat
    hill(-4)
    for _ in range(5): br.shift(+1, "Auto: cadence 92 rpm, over 80")
    check(f"spinning down a -4% descent: 5 gears gained, counted as descent gears ({br.descent_gears})", br.descent_gears == 5 and br.gear == 6)
    hill(6)
    check(f"road turns up to +6%: the 5 descent gears go back, the flat one stays (gear {br.gear:+d})", br.gear == 1 and br.descent_gears == 0)
    check(f"climb starts at a sane level ({br.target_level}), not ~12", br.target_level <= 9)
    hill(-4)
    for _ in range(3): br.shift(+1, "Auto: x")
    br.shift(-1)
    check(f"a hand shift easier on the descent comes off the count ({br.descent_gears})", br.descent_gears == 2)
    hill(0); br.descent_left_at = time.monotonic() - 61; hill(0.5); hill(5)
    check("after a minute on the flat, descent gears are the rider's to keep", br.descent_gears == 0 and br.gear == 3)
    br.gear = -1
    check("a two-gear drop at gear -1 stops at the floor (-2)", br.shift(-2, "Auto: collapse") and br.gear == -2)
    check("  ...and a further drop is refused", br.shift(-2, "Auto: collapse") is False)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
