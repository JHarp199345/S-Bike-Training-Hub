"""Cross-sport carry-over: starts at the literature, learns this rider's ratios from their markers and check-ins,
and says how sure it is."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt, math, random
import transfer


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    m = [[4.0, 1, 0], [1, 3, 1], [0, 1, 2]]
    inv = transfer._inv(m)
    prod = [[sum(m[i][k] * inv[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    check("the small matrix inverse works", all(abs(prod[i][j] - (i == j)) < 1e-9 for i in range(3) for j in range(3)))

    # 20 weeks alternating bike-heavy, swim-heavy and run-heavy blocks
    d0, n = dt.date(2026, 5, 1), 140
    days, rnd = [], random.Random(3)
    for i in range(n):
        blk = (i // 14) % 3
        load = {"bike": 60 if blk == 0 else 15, "swim": 60 if blk == 1 else 10, "run": 50 if blk == 2 else 10}
        if i % 7 == 6:
            load = {s: 0 for s in load}
        days.append({"date": (d0 + dt.timedelta(days=i)).isoformat(), "sports": {s: {"engine": v} for s, v in load.items()}})
    empty = transfer.analyse(days, [], marker_data={"swim": [], "bike": [], "run": []})
    br = empty["fitness"]["run"]["from"]["bike"]
    check(f"no measurements: the research's numbers, marked as such (bike -> run {br['ratio']}, {br['status']})",
          br["status"] == "prior" and abs(br["ratio"] - 0.5) < 0.1)
    # the truth for this rider: an hour on the bike builds running like 0.9 h of running (the research says 0.5)
    loads = transfer.daily_loads(days)
    fit = {s: transfer.ewma(loads[s], 42) for s in transfer.SPORTS}
    run_marker = [(days[i]["date"], 3.0 + 0.01 * (fit["run"][i] + 0.9 * fit["bike"][i] + 0.2 * fit["swim"][i]) + rnd.gauss(0, 0.02))
                  for i in range(30, n, 2)]
    t = transfer.analyse(days, [], marker_data={"swim": [], "bike": [], "run": run_marker})
    br = t["fitness"]["run"]["from"]["bike"]
    check(f"with {len(run_marker)} run measurements it learns bike -> run is higher for this rider "
          f"({br['ratio']}, 80% {br['lo']}-{br['hi']}, {br['status']})", br["ratio"] > 0.65 and br["status"] in ("learning", "learned"))
    check("a ratio it wasn't shown anything about stays near the research's", abs(t["fitness"]["bike"]["from"]["run"]["ratio"] - 0.6) < 0.15)
    # legs: this rider's legs feel the bike as much as a run
    checkins = {}
    for i in range(2, n, 3):
        x = {s: days[i - 1]["sports"][s]["engine"] + 0.5 * days[i - 2]["sports"][s]["engine"] for s in transfer.SPORTS}
        checkins[days[i]["date"]] = {"legs": round(2 + 0.04 * (x["run"] + 1.0 * x["bike"] + 0.05 * x["swim"]) + rnd.gauss(0, 0.3), 1)}
    lg = transfer.analyse(days, [], checkins=checkins, marker_data={"swim": [], "bike": [], "run": []})["legs"]["from"]["bike"]
    check(f"legs check-ins teach how much the bike tires the legs next to running ({lg['ratio']}, {lg['status']})",
          lg["ratio"] > 0.75 and lg["status"] != "prior")
    check("no carry-over is ever negative", all(v["lo"] is None or v["lo"] >= 0 for s in t["fitness"].values() for v in s["from"].values()))
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
