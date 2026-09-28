"""Route engine: distance -> position, heading, smoothed grade; stats; GPX import."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import random, tempfile
import routes as R


def synthetic(noise=2.0):
    """North from 45.0N 1.0E: 1 km at +5%, 1 km flat, 0.5 km at -4%, points every ~20 m, noisy elevation."""
    random.seed(4)
    pts, ele, d = [], 100.0, 0.0
    step_deg = 20 / 111_195                     # ~20 m of latitude
    lat = 45.0
    while d <= 2500:
        g = 5 if d < 1000 else 0 if d < 2000 else -4
        pts.append((lat, 1.0, ele + random.uniform(-noise, noise)))
        lat += step_deg; d += 20; ele += g / 100 * 20
    return R.Route(pts, "Test hill")


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    r = synthetic()
    check(f"length ~2.5 km ({r.length:.0f} m)", abs(r.length - 2500) < 30)
    import statistics as st
    for name, lo, hi, want in (("climb", 150, 850, 5), ("flat", 1150, 1850, 0), ("descent", 2150, 2400, -4)):
        gs = [r.grade_at(d) for d in range(lo, hi, 10)]
        check(f"{name} ({want:+d}%) through ±2 m noise: averages {st.fmean(gs):+.1f}%, every point within "
              f"{max(abs(x - want) for x in gs):.1f}%", abs(st.fmean(gs) - want) <= 0.5 and max(abs(x - want) for x in gs) <= 2.0)
    raw = [(r.points[i + 1][2] - r.points[i][2]) / 20 * 100 for i in range(10, 40)]
    check(f"(raw point-to-point grade would have jumped {min(raw):.0f}% to {max(raw):.0f}%)", max(raw) - min(raw) > 15)
    lat, lon, hd = r.position_at(1000)
    check(f"position 1 km in: {lat:.5f}, {lon:.5f}, heading {hd:.0f}° (north)", abs(lat - 45.009) < 0.001 and (hd < 1 or hd > 359))
    check("past the end stays at the end (no crash)", r.position_at(99999)[0] == r.points[-1][0])
    s = r.stats()
    check(f"stats: {s}", s["km"] == 2.5 and 40 <= s["climb_m"] <= 70 and s["max_grade"] >= 4.5)
    flat = R.Route([(45 + i * 0.0002, 1, 100) for i in range(60)], "Flat")
    check(f"a flat route is labelled easy ({flat.stats()['kind']}), the test hill is not ({s['kind']})",
          flat.stats()["kind"] == "easy" and s["kind"] != "easy")
    spike = R.Route([(45 + i * 0.0002, 1, 100 if i != 30 else 160) for i in range(60)], "Spike")
    check(f"a bad elevation spike is capped at {R.MAX_GRADE}% ({max(abs(spike.grade_at(d)) for d in range(0, 1300, 10)):.0f}%)",
          max(abs(spike.grade_at(d)) for d in range(0, 1300, 10)) <= R.MAX_GRADE)
    folder = tempfile.mkdtemp(); r.save(folder)
    back = R.load(r.id, folder)
    check("save and load round-trip", back.name == "Test hill" and abs(back.length - r.length) < 1)
    check("route list shows it with stats", R.list_routes(folder)[0]["name"] == "Test hill")
    gpx = """<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Loire loop</name><trkseg>
      <trkpt lat="47.39" lon="0.68"><ele>50</ele></trkpt><trkpt lat="47.40" lon="0.68"><ele>55</ele></trkpt>
      <trkpt lat="47.41" lon="0.69"><ele>60</ele></trkpt></trkseg></trk></gpx>"""
    g = R.from_gpx(gpx)
    check(f"GPX import: '{g.name}', {len(g.points)} points, {g.length:.0f} m", g.name == "Loire loop" and len(g.points) == 3)
    ride = R.RouteRide(r, start_distance=500)
    st = ride.status(1500)
    check(f"riding it: 1 km along, grade {st['grade']}%, elevation {st['elevation']} m", st["done_m"] == 1000)
    check("finished flag at the end", ride.status(500 + r.length + 1)["finished"])
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
