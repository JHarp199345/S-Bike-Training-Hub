"""Live graph history and calories: work adds up correctly from uneven readings,
a sleeping bike adds nothing, one point per second, ten minutes kept, and a
restarted bridge picks up the calories and graph from the ride file."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import csv, datetime as dt, random, tempfile
import live


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    L, t = live.Live(), 1_800_000_000.0
    random.seed(3)
    while t < 1_800_000_000.0 + 3600:              # an hour at 200 W, readings every 0.2-0.6 s
        L.add(t, 200, 80, 30, 1.0, 0); t += random.uniform(0.2, 0.6)
    check(f"an hour at 200 W is 720 kJ ({L.kj:.1f})", abs(L.kj - 720) < 1)
    check(f"720 kJ is ~717 kcal at 24% efficiency ({L.kcal:.0f})", abs(L.kcal - 717) < 2)
    check(f"kcal per minute at 200 W is ~12 ({L.kcal_per_min(t):.1f})", abs(L.kcal_per_min(t) - 11.95) < 0.2)
    check(f"only ten minutes are kept, one point per second ({len(L.points)})", len(L.points) == 600)
    secs = [p[0] for p in L.points]
    check("points are whole seconds, each once, in order", secs == sorted(set(secs)))
    before = L.kj
    L.add(t + 120, 200, 80, 30, 1.0, 0)                # bike asleep for two minutes
    check(f"a 2-minute silence adds no work ({L.kj - before:.2f} kJ)", L.kj - before == 0)
    check("history since a time gives only newer points", all(p[0] > secs[-5] for p in L.since(secs[-5])))
    check("status carries kJ, kcal and kcal/min", set(L.status(t)) == {"kj", "kcal", "kcal_min"})

    # A ride file, as the bridge writes it, read back after a restart.
    f = pathlib.Path(tempfile.mkdtemp()) / "ride.csv"
    start = dt.datetime(2026, 9, 27, 9, 0, 0)
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "power_w", "cadence_rpm", "bike_speed_kmh", "bike_distance_m", "resistance",
                    "virtual_speed_kmh", "virtual_distance_m", "grade_pct", "gear", "hill_shift", "erg_w"])
        for s in range(1200):                          # 20 min at 150 W, one row a second
            w.writerow([(start + dt.timedelta(seconds=s)).isoformat(timespec="seconds"), 150, 75, 20, 0, 5,
                        25.5, s * 7, 2.0 if s > 600 else 0.0, 1 if s > 900 else 0, 0, ""])
    R = live.Live(); R.load_ride(f)
    check(f"after a restart: 20 min at 150 W = 180 kJ recovered ({R.kj:.1f})", abs(R.kj - 180) < 0.5)
    check(f"after a restart: the graph has the last ten minutes ({len(R.points)} points)", len(R.points) == 600)
    check("after a restart: grade and gear come back in the graph", R.points[-1][4] == 2.0 and R.points[-1][5] == 1)
    check("after a restart: virtual speed is what the graph shows", R.points[-1][3] == 25.5)
    before = R.kj
    R.add(R.points[-1][0] + 3, 150, 75, 25, 0, 0)
    check("the downtime before the first new reading adds no work", R.kj == before)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
