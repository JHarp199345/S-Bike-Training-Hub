"""Area mode: routes inside a circle, judged for today's focus - time at the focus's watts, how much of the ride
auto-shift can hold in range, and whether the terrain suits the day. Uses stand-in roads (no route server)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import math, tempfile
import areaplan, focus, planner, routes


def line(km, grade_at=lambda d: 0.0, start=(45.9, 6.1)):
    """A straight road east with elevation from a grade function (d in m -> %), a point every 25 m."""
    pts, e = [], 200.0
    for i in range(int(km * 40) + 1):
        d = i * 25
        if i:
            e += grade_at(d) / 100 * 25
        lat, lon = planner._offset(start, d, 90)
        pts.append((lat, lon, e))
    return routes.Route(pts, "test")


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    t = areaplan.Terrain()
    check(f"same grade -> level mapping as the bridge: flat {t.level(0, 0)}, +6% {t.level(6, 0):.2f} (test_hills: level 7)",
          t.level(0, 0) == 4.75 and round(t.level(6, 0)) == 7)
    fl = [round(t.floor_watts(g, 65)) for g in (0, 6, 12, 15)]
    check(f"the fewest watts auto-shift leaves you climbs with the grade ({fl} W at 65 rpm)", fl == sorted(fl) and fl[0] < 101 < fl[-1])

    cad, grit = focus.resolve("cadence", 180), focus.resolve("grit", 180)
    flat, hilly = line(15), line(15, lambda d: 5.0 if (d // 1000) % 2 else -5.0)
    wall = line(15, lambda d: 15.0 if 6000 <= d < 7000 else 0.0)
    jf, jh, jw = (areaplan.judge(r, cad, t, 40) for r in (flat, hilly, wall))
    check(f"15 km flat at ~118 W takes {jf['minutes']} min; the same 15 km up and down takes longer ({jh['minutes']})",
          30 <= jf["minutes"] <= 45 and jh["minutes"] > jf["minutes"])
    check(f"flat: holdable the whole way ({jf['holdable_pct']}%)", jf["holdable_pct"] == 100)
    check(f"a 15% wall on an easy day: not all holdable ({jw['holdable_pct']}%) and it says where ({jw['why'][-1]})",
          jw["holdable_pct"] < 100 and "km 6" in jw["why"][-1])
    check(f"an easy day prefers the flat road ({jf['score']} vs {jh['score']})", jf["score"] > jh["score"])
    gf, gh = areaplan.judge(flat, grit, t, 60), areaplan.judge(hilly, grit, t, 60)
    check(f"a grit day prefers the climbs (terrain {gh['terrain_fit']} vs {gf['terrain_fit']})", gh["terrain_fit"] > gf["terrain_fit"])
    check("time fit: 10% off the asked-for minutes still scores 0.8",
          abs(areaplan.judge(flat, cad, t, jf["minutes"] / 1.1)["time_fit"] - 0.8) < 0.05)

    centre = (45.9, 6.1)
    check("inside: a road that stays in the circle counts; one that runs 15 km out doesn't",
          areaplan.inside(line(3, start=centre), centre, 5000) == 1 and areaplan.inside(line(15, start=centre), centre, 5000) < 0.5)

    # the route server, stood in for: straight roads between the waypoints, flat
    real = planner._request
    def fake(points, alt=0, profile=None, timeout=90):
        pts = []
        for a, b in zip(points, points[1:]):
            n = max(2, int(planner._apart(a, b) / 25))
            pts += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, 200.0) for i in range(n)]
        return routes.Route(pts + [(points[-1][0], points[-1][1], 200.0)], "route")
    planner._request = fake
    try:
        found = areaplan.plan_area(centre, 6, 45, cad, t, tries=6)
        mins = [j["minutes"] for _, j in found]
        check(f"loops inside a 6 km circle, timed for 45 min ({mins}), best first", found and all(38 <= m <= 52 for m in mins)
              and [j["score"] for _, j in found] == sorted((j["score"] for _, j in found), reverse=True))
        check("...and they stay in the circle", all(areaplan.inside(r, centre, 6000) >= 0.9 for r, _ in found))
        small = areaplan.plan_area(centre, 1.5, 90, cad, t, tries=4)
        check(f"a 90-minute ride in a tiny circle does what it can and says so in the time ({[j['minutes'] for _, j in small]})",
              small and all(j["time_fit"] < 0.8 for _, j in small))
    finally:
        planner._request = real

    tmp = pathlib.Path(tempfile.mkdtemp())
    areaplan.save_area(tmp, (45.9, 6.1), 7)
    check("the last area drawn is remembered for the coach", areaplan.last_area(tmp) == ((45.9, 6.1), 7.0))
    check("no area yet: None", areaplan.last_area(pathlib.Path(tempfile.mkdtemp())) is None)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
