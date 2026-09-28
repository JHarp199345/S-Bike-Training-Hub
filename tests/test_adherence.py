"""Workout adherence: part-by-part scores and grades from a ride that follows a
workout imperfectly; stopping early counts as missed; the diagnostic is graded;
the report gets the pie, the radar and the table."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import csv, datetime as dt, tempfile
import adherence, workouts


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    tmp = pathlib.Path(tempfile.mkdtemp()); rides = tmp / "rides"; rides.mkdir()
    ftp = 180
    blocks = [{"type": "steady", "minutes": 5, "pct": 50},                                  # 90 W
              {"type": "ramp", "minutes": 5, "from": 50, "to": 75},                         # 90 -> 135 W
              {"type": "intervals", "times": 3, "on": {"minutes": 4, "pct": 80}, "off": {"minutes": 3, "pct": 50}},
              {"type": "steady", "minutes": 5, "pct": 45}]                                  # cool-down 81 W
    wl = [{"name": "Test 3x4", "blocks": blocks}]
    start = dt.datetime(2026, 10, 1, 7, 0, 0)
    stem = "ride_2026-10-01_0700"
    # what the rider rode: warm-up and ramp on target; efforts 1-2 on target (144 W); effort 3 fades to 110 W;
    # recoveries on target; they stop 3 minutes before the end of the cool-down
    plan_w = []
    for s in range(300): plan_w.append(90)
    for s in range(300): plan_w.append(90 + 45 * (s + 0.5) / 300)
    for k in range(3):
        for s in range(240): plan_w.append(144 if k < 2 else 110)
        if k < 2:
            for s in range(180): plan_w.append(90)
    for s in range(120): plan_w.append(81)                                                  # 2 of 5 min of cool-down
    with open(rides / f"{stem}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time", "power_w", "cadence_rpm"])
        for s, watts in enumerate(plan_w):
            w.writerow([(start + dt.timedelta(seconds=s)).isoformat(timespec="seconds"), round(watts), 85])
    with open(rides / f"{stem}_events.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time", "event"])
        w.writerow([start.isoformat(timespec="seconds"), "Workout started: Test 3x4 (at FTP 180 W)"])
    a = adherence.for_ride(rides / f"{stem}.csv", wl)
    parts = {p["label"]: p for p in a["parts"]}
    check(f"parts: steady, ramp, efforts, recoveries, cool-down ({list(parts)})", len(parts) == 5)
    check(f"shares add up to the whole workout ({sum(p['share'] for p in a['parts']):.3f})", abs(sum(p["share"] for p in a["parts"]) - 1) < 1e-9)
    warm, ramp = a["parts"][0], a["parts"][1]
    check(f"warm-up held: A ({warm['grade']} {warm['score']})", warm["grade"] == "A")
    check(f"ramp followed: A ({ramp['grade']} {ramp['score']})", ramp["grade"] == "A")
    eff = next(p for p in a["parts"] if p["kind"] == "effort")
    check(f"efforts: 2 of 3 on target -> 67%, grade D ({eff['score']}, {eff['grade']})", abs(eff["score"] - 2 / 3) < 0.01 and eff["grade"] == "D")
    rec = next(p for p in a["parts"] if p["kind"] == "rest")
    check(f"recoveries held: A ({rec['grade']})", rec["grade"] == "A")
    cool = a["parts"][-1]
    check(f"stopping 3 min early: cool-down 40% completed, grade F ({cool['completed']}, {cool['grade']})",
          abs(cool["completed"] - 0.4) < 0.01 and cool["grade"] == "F")
    check(f"overall is time-weighted ({a['score']}, {a['grade']})", 0.7 < a["score"] < 0.85)
    html = adherence.report_html(a)
    check("the report has the pie, the radar and the table", html.count("<svg") == 2 and "<polygon" in html and "<table>" in html)
    (tmp / "adherence.html").write_text(f"<body style='background:#0b0f14;color:#eef1f5;font-family:-apple-system'>{html}</body>")
    print("   report preview:", tmp / "adherence.html")

    # the morning diagnostic, ridden well
    d2 = "ride_2026-10-02_0700"; s2 = dt.datetime(2026, 10, 2, 7)
    ws = [60] * 120 + [90] * 120 + [120] * 60 + [30] * 60
    with open(rides / f"{d2}.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time", "power_w", "cadence_rpm"])
        for s, watts in enumerate(ws):
            w.writerow([(s2 + dt.timedelta(seconds=s)).isoformat(timespec="seconds"), watts, 85])
    with open(rides / f"{d2}_events.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time", "event"])
        w.writerow([s2.isoformat(timespec="seconds"), "Morning diagnostic started: 2 min 60 W, ..."])
    a2 = adherence.for_ride(rides / f"{d2}.csv", [])
    check(f"the diagnostic is graded too ({[p['label'] for p in a2['parts']]}, {a2['grade']})",
          a2["grade"] == "A" and a2["parts"][1]["label"] == "Steady 90 W")
    check("a ride without a workout has no adherence", adherence.for_ride(rides / "nope.csv", []) is None)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
