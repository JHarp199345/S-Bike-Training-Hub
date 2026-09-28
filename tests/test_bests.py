"""Personal bests: best averages from ride files, no averaging across a stop,
live records called once then settled, records saved, FTP only raised."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import csv, datetime as dt, tempfile
import bests


def write_ride(path, watts_by_second, start=dt.datetime(2026, 9, 20, 9, 0, 0), per_second=3):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "power_w", "cadence_rpm"])
        for s, watts in watts_by_second:
            for _ in range(per_second):                        # the bike reports several times a second
                w.writerow([(start + dt.timedelta(seconds=s)).isoformat(timespec="seconds"), watts, 80])


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    tmp = pathlib.Path(tempfile.mkdtemp())
    bests.FILE = tmp / "bests.json"
    rides = tmp / "rides"; rides.mkdir()

    # Ride 1: 25 min at 150 W with a 5-min block at 220 W, a 1-min 300 W, and one 3-s 600 W spike.
    r1 = [(s, 150) for s in range(1500)]
    for s in range(300, 600): r1[s] = (s, 220)
    for s in range(900, 960): r1[s] = (s, 300)
    for s in range(1200, 1203): r1[s] = (s, 600)
    write_ride(rides / "ride_2026-09-20_0900.csv", r1)
    b = bests.best_efforts(bests.ride_seconds(rides / "ride_2026-09-20_0900.csv"))
    check(f"5-min best is the 220 W block ({b[300][0]:.0f})", round(b[300][0]) == 220)
    check(f"1-min best is the 300 W minute ({b[60][0]:.0f})", round(b[60][0]) == 300)
    check(f"5-s best includes the 3-s spike: (3x600+2x150)/5 = 420 ({b[5][0]:.0f})", round(b[5][0]) == 420)
    want20 = (300 * 220 + 60 * 300 + 3 * 600 + 837 * 150) / 1200
    check(f"20-min best found ({b[1200][0]:.1f} vs {want20:.1f})", abs(b[1200][0] - want20) < 1.5)

    # Ride 2: two 3-min efforts at 250 W with a 2-minute stop between: no 5-min best across the stop.
    r2 = [(s, 250) for s in range(180)] + [(s, 250) for s in range(300, 480)]
    write_ride(rides / "ride_2026-09-21_0900.csv", r2, start=dt.datetime(2026, 9, 21, 9))
    b2 = bests.best_efforts(bests.ride_seconds(rides / "ride_2026-09-21_0900.csv"))
    check("no 5-min effort averaged across a 2-minute stop", 300 not in b2)
    r3 = [(s, 200) for s in range(400) if s not in (100, 101, 102)]          # a 3-s dropout
    write_ride(rides / "ride_2026-09-22_0900.csv", r3, start=dt.datetime(2026, 9, 22, 9))
    b3 = bests.best_efforts(bests.ride_seconds(rides / "ride_2026-09-22_0900.csv"))
    check(f"a 3-s Bluetooth dropout is bridged, not a stop ({round(b3.get(300, (0,))[0])} W)", round(b3[300][0]) == 200)

    d = bests.load()
    new = bests.scan_rides(d, rides)
    check(f"scanning past rides sets the records ({d['records']['60']['watts']} W 1-min)", d["records"]["60"]["watts"] == 300)
    check("each ride is read once", bests.scan_rides(d, rides) == [])
    bests.save(d)

    # Live: a 1-min effort at 320 W beats the 300 W record.
    calls = []
    tr = bests.Tracker(bests.load(), "ride_live", lambda *a: calls.append(a))
    t = 1_800_000_000.0
    for s in range(400):
        w = 320 if 200 <= s < 290 else 140
        for k in range(4):
            tr.add(t + s + k * 0.25, w)
    news = [c for c in calls if c[0] == "new" and c[1] == 60]
    finals = [c for c in calls if c[0] == "final" and c[1] == 60]
    check(f"a new 1-min record is called out once, not every second ({len(news)})", len(news) == 1)
    check(f"...and settled once with the peak ({finals[0][2] if finals else None} W, was {finals[0][3] if finals else None})",
          len(finals) == 1 and finals[0][2] == 320 and finals[0][3] == 300)
    check("the new record is saved", bests.load()["records"]["60"]["watts"] == 320)
    st = {x["secs"]: x for x in tr.status()}
    check(f"status shows this ride's best and the record ({st[60]['ride']} / {st[60]['best']})", st[60]["ride"] == 320 and st[60]["best"] == 320)
    check("an easy effort sets no record", not [c for c in calls if c[1] == 300])

    # A gap during a live ride: no 5-s effort straddles it.
    calls.clear()
    tr2 = bests.Tracker(bests.load(), "ride_gap", lambda *a: calls.append(a))
    tr2.add(t, 900); tr2.add(t + 1, 900); tr2.add(t + 2, 900)
    tr2.add(t + 60, 900); tr2.add(t + 61, 900); tr2.add(t + 62, 0)
    check("live: a 5-s best can't be made of two bursts either side of a stop", not [c for c in calls if c[1] == 5])

    # FTP from the 20-min best, via the bridge's rule
    d = bests.load()
    check(f"20-min record {d['records']['1200']['watts']} W -> FTP would be {round(d['records']['1200']['watts'] * 0.95)} W",
          round(d["records"]["1200"]["watts"] * bests.FTP_FROM_20MIN) == round(d["records"]["1200"]["watts"] * 0.95))
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
