"""Hill shifting: resistance must never drop as the hill gets steeper."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, types, os, tempfile
import bridge as b


class FakeBike:
    is_connected = True
    def __init__(s): s.sent = []
    async def write_gatt_char(s, u, v, response=True): s.sent.append(bytes(v))


ARGS = dict(wheel=2096, broadcast="SBike Hub", base_level=None, per_percent=None, weight=80.0, bike_mass=10.0,
            bike_speed=False, no_auto=False, cadence_low=70, cadence_high=80, up_hold=15, min_gear=-2, upshift_cap_w=165,
            hill_shift_every=3.0, watch_ftms=False, ramp=1.2)


def make_bridge():
    cwd = os.getcwd(); os.chdir(tempfile.mkdtemp())
    br = b.Bridge(types.SimpleNamespace(**ARGS)); os.chdir(cwd)
    br.push = lambda *a, **k: None
    br.static[b.FEATURE] = bytes.fromhex("0b50000004000000")          # S29: resistance only
    br.static[b.RES_RANGE] = (10).to_bytes(2, 'little') + (160).to_bytes(2, 'little') + (10).to_bytes(2, 'little')
    br.describe_features(); br.bike = FakeBike(); br.have_control = True
    return br


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    br = make_bridge()
    class CP: uuid = b.CONTROL
    def hill(g): br.on_write(CP(), b"\x11\x00\x00" + int(g * 100).to_bytes(2, 'little', signed=True) + b"\x28\x33")
    grades = [x / 2 for x in range(-20, 25)]                                   # -10% .. +12% in 0.5% steps
    levels = []
    for g in grades:
        hill(g); await asyncio.sleep(0.005); levels.append(br.target_level)
    print("  levels -10%..+12%:", levels)
    check("resistance never drops as the hill gets steeper", all(x <= y for x, y in zip(levels, levels[1:])))
    check("flat is level 5", levels[grades.index(0)] == 5)
    check("+6% is harder than flat but pedalable (level 7)", levels[grades.index(6)] == 7)
    check("+3% shifts one gear easier at the bottom", round(br.hill_shift) == -4 and (hill(3) or True))
    await asyncio.sleep(0.005)
    check("  (after +3%: hill shift -1)", round(br.hill_shift) == -1)
    hill(0); await asyncio.sleep(0.005)
    check("cresting to 0% gives the gears back", br.hill_shift == 0 and br.target_level == 5)
    hill(-6); await asyncio.sleep(0.005)
    check("-6% descent shifts 2 harder", round(br.hill_shift) == 2)
    hill(6); br.gear = -1; hill(6.5); await asyncio.sleep(0.005)
    check("auto/hand gear stacks on the hill shift", br.target_level == round(4.75 + 0.75 * 6.5 - 6.5 / 3 - 1))
    br.gear = -2
    check("auto floor (-2) holds with a hill shift active", br.shift(-1, "Auto: test") is False and br.gear == -2)
    bad = [x for x in br.bike.sent if x[0] == 4 and not 10 <= int.from_bytes(x[1:3], 'little') <= 160]
    check("no out-of-range level ever sent", not bad)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
