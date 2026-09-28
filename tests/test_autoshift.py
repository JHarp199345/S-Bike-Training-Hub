"""Auto-shift: the rider's rule - under 70 rpm easier, held over 80 harder."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from autoshift import AutoShift


class Clock:
    t = 0.0
    def __call__(self): return self.t


def run(a, clk, cads, hr=None):
    out = []
    for c in cads:
        clk.t += 1; r = a.update(c, hr)
        if r: out.append((int(clk.t), r))
    return out


def fresh(limit=(-99, 99)):
    clk = Clock(); gear = [0]
    def shift(d, why):
        if not limit[0] <= gear[0] + d <= limit[1]: return False
        gear[0] += d; return True
    return AutoShift(shift, clock=clk), clk, gear


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    ramp = [25, 30, 35, 42, 42, 45, 48, 48, 50, 55, 58, 62, 66, 70, 72, 74, 75] + [76] * 40
    cases = [
        ("steady 75 rpm for 3 min: no shifts", lambda a, c, g: run(a, c, [75] * 180) == []),
        ("above 80 for only 10 s: nothing yet", lambda a, c, g: run(a, c, [75] * 20 + [84] * 10) == []),
        ("held above 80 for 15 s: one harder", lambda a, c, g: [d for _, d in run(a, c, [75] * 20 + [84] * 20)] == [1]),
        ("below 70: easier", lambda a, c, g: [d for _, d in run(a, c, [75] * 20 + [66] * 12)][:1] == [-1]),
        ("drops hard to 52: easier quickly", lambda a, c, g: (lambda s: s and s[0][1] == -1 and s[0][0] <= 30)(run(a, c, [75] * 20 + [52] * 10))),
        ("slow start ramp (17:57 ride): no shift", lambda a, c, g: run(a, c, ramp) == []),
        ("restart but stays at 62: shifts after grace", lambda a, c, g: [d for _, d in run(a, c, [75] * 20 + [0] * 20 + [40, 55, 60, 62] + [62] * 30)][:1] == [-1]),
        ("ragged 60/85 pattern: easier", lambda a, c, g: [d for _, d in run(a, c, [75] * 20 + [60, 85] * 25)][:1] == [-1]),
        ("new hill: grace, then judges", lambda a, c, g: (run(a, c, [75] * 20), a.hill_changed(), run(a, c, [64] * 6) == [] and run(a, c, [64] * 8) != [])[-1]),
        ("hand shift: auto waits 30 s", lambda a, c, g: (run(a, c, [75] * 20), a.manual_shift(), run(a, c, [60] * 28) == [])[-1]),
        ("auto off: never shifts", lambda a, c, g: (setattr(a, 'enabled', False), run(a, c, [50] * 60) == [])[-1]),
        ("at the gear limit: no phantom shifts", lambda a, c, g: run(a, c, [75] * 20 + [60] * 40) == [] if a.shift.__closure__ else True),
    ]
    for name, f in cases[:-1]:
        a, c, g = fresh(); check(name, f(a, c, g))
    def rider_rule():                       # the bridge's settings since 2026-09-26
        clk = Clock(); gear = [0]
        def shift(d, why): gear[0] += d; return True
        return AutoShift(shift, low=65, high=80, up_hold=3, clock=clk), clk, gear
    a, c, g = rider_rule(); s = run(a, c, [75] * 20 + [86] * 6)
    check(f"the band rule: over 80 shifts harder within ~5 s {s}", s and s[0][1] == 1 and s[0][0] - 20 <= 5)
    a, c, g = rider_rule(); s = run(a, c, [75] * 20 + [88] * 20)
    check(f"still over 80 after going harder: next up-shift ~6 s later {s}", len(s) >= 2 and s[1][0] - s[0][0] <= 11)
    a, c, g = rider_rule(); check("68 rpm is fine now (down-shift only under 65)", run(a, c, [75] * 20 + [68] * 60) == [])
    a, c, g = rider_rule(); s = run(a, c, [75] * 20 + [62] * 12)
    check(f"under 65: easier {s}", s and s[0][1] == -1)
    a, c, g = fresh(limit=(0, 0)); check("at the gear limit: no phantom shifts", run(a, c, [75] * 20 + [60] * 40) == [] and g[0] == 0)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
