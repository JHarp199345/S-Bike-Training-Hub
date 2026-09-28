"""Resistance ramps one level at a time and ignores a flickering grade."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from test_hills import make_bridge


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    br = make_bridge()
    t = [0.0]
    def run(secs):
        sent = []
        for _ in range(int(secs / 0.2)):
            t[0] += 0.2
            cmd = br.ramp_step(t[0])
            if cmd: sent.append((round(t[0], 1), int.from_bytes(cmd[1:3], "little") // 10))
        return sent
    def target(level):
        br.set_level(level, "test"); br.target_since = t[0]
    target(5); s = run(1)
    check(f"first command after connecting goes straight to the level {s}", s == [(0.2, 5)])
    target(10); s = run(10)
    levels = [l for _, l in s]
    check(f"5 -> 10 walks up one level at a time {levels}", levels == [6, 7, 8, 9, 10])
    gaps = [round(b - a, 1) for (a, _), (b, _) in zip(s, s[1:])]
    check(f"steps are at least 1.2 s apart {gaps}", all(g >= 1.2 for g in gaps))
    check("first step waits for the target to hold still (0.8 s)", s[0][0] >= 0.8)
    sent = []
    for i in range(20):                       # grade flickering: target 9, 10, 9, 10 ... every 0.4 s
        target(9 if i % 2 else 10); sent += run(0.4)
    check(f"flickering target: bike holds still {sent}", sent == [])
    target(3); s = run(15)
    check(f"big drop 10 -> 3 also steps down one at a time {[l for _, l in s]}", [l for _, l in s] == [9, 8, 7, 6, 5, 4, 3])
    br.level_sent = None; target(3); s = run(1)
    check(f"after the bike reconnects, the level is re-sent at once {s}", s and s[0][1] == 3)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    import asyncio; sys.exit(0 if asyncio.run(main()) else 1)
