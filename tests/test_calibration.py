"""Calibration: each capacity from tests and training with a fading confidence; tests as plan items; the test week
(a recovery week that peaks on test day, then rest); swims scored against CSS; the running block grown by tests."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt, tempfile
import calibration, coach, damage, loads


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    E = lambda date, kind, v: {"date": date, "kind": kind, "value": v}
    e = calibration.estimate([E("2026-09-01", "test", 200), E("2026-09-20", "training", 220)], 42, "2026-09-28")
    check(f"a test anchors it, training since nudges it 30% of the way ({e['value']:.0f} W, {e['source']})",
          abs(e["value"] - 206) < 0.5 and e["source"] == "test + training")
    check(f"confidence fades with the test's age ({e['confidence']}) and the next test comes due ({e['due_in_days']} days)",
          0.6 < e["confidence"] < 0.8 and e["due_in_days"] == 15)
    old = calibration.estimate([E("2026-06-01", "test", 200)], 42, "2026-09-28")
    check(f"a stale test: low confidence ({old['confidence']}), due now", old["confidence"] <= 0.3 and old["due_in_days"] == 0)
    check("a manual setting wins like a test", calibration.estimate([E("2026-09-01", "test", 200), E("2026-09-10", "manual", 190)], 42, "2026-09-28")["value"] == 190)
    check("a starting guess until there's anything better", calibration.estimate([E("2026-09-26", "model", 180)], 42, "2026-09-28")["source"] == "model")
    prof = {"ftp": 186, "ftp_source": "ramp test (2026-10-03)", "history": [{"ftp": 180, "source": "COROS estimate (2026-09-26)"}]}
    fe = calibration.ftp_entries(prof)
    check(f"FTP history: the ramp test is a test, the watch's estimate a guess ({[(x['date'], x['kind'], x['value']) for x in fe]})",
          ("2026-10-03", "test", 186.0) in [(x["date"], x["kind"], x["value"]) for x in fe])

    check("CSS from a 400 m in 8:00 and a 200 m in 3:40: 2:10 per 100 m", calibration.css_from_times(480, 220) == 130)
    try:
        calibration.css_from_times(300, 220); check("impossible times refused", False)
    except ValueError:
        check("impossible times refused", True)
    swim = {"id": "s", "source": "watch", "start": 0, "sport": "swim", "minutes": 45, "distance_m": 2000, "descent_m": 0, "records": []}
    p = {"weight_kg": 100, "hr_rest": 60, "hr_max": 185, "ftp": 180}
    s1 = loads.score(swim, dict(p, swim_css=130), 1.2)
    check(f"a swim is scored against CSS: 2 km in 45 min at CSS 2:10 -> {s1['engine']:.0f} (hours x (CSS/pace)^3 x 100)",
          abs(s1["engine"] - 0.75 * (130 / 135) ** 3 * 100) < 0.1)
    check("...and from heart rate when there's no CSS yet", loads.score(swim, p, 1.2)["engine"] == 0)

    # ── the benchmark run: graded, predicted, diminishing returns, results overrule the curve ──
    clean = {"2026-10-02": {"feet": 2, "legs": 3}, "2026-10-03": {"feet": 1, "legs": 2}}
    std = lambda hr: {"impact": 200, "km": 3.22, "minutes": 32, "descent_m": 5, "avg_hr": hr}
    def bench(date, run, prior, rpe=None, pain=False, checkins=None, d=None):
        d = d if d is not None else {"plans": {}}
        if rpe is not None or pain:
            calibration.benchmark_report(d, date, rpe, pain)
        return calibration.block_test(d, date, run, checkins if checkins is not None else clean, prior), d
    b, _ = bench("2026-10-01", 300, 223.6)
    check(f"no feel, no heart rate, clean mornings: a cautious middle grade ({b['gain_pct']}%)",
          b["result"] == "grew" and 3 <= b["gain_pct"] <= 5)
    easy, _ = bench("2026-10-01", std(140), 223.6, rpe=2)
    hard, _ = bench("2026-10-01", std(140), 223.6, rpe=8)
    check(f"felt like nothing grows more than felt like a fight ({easy['gain_pct']}% vs {hard['gain_pct']}%)",
          easy["gain_pct"] > hard["gain_pct"] > 0)
    check("the mornings not in yet: wait", calibration.block_test({"plans": {}}, "2026-10-01", 300, {}, 223.6) is None)
    sore = {"2026-10-02": {"feet": 5, "legs": 3}, "2026-10-03": {"feet": 2, "legs": 2}}
    half, _ = bench("2026-10-01", std(140), 223.6, rpe=2, checkins=sore)
    check(f"feet at 5/10 the morning after: half the growth ({half['gain_pct']}% vs {easy['gain_pct']}%)",
          abs(half["gain_pct"] - easy["gain_pct"] / 2) <= 0.2)
    ouch, dd = bench("2026-10-01", std(140), 223.6, rpe=4, pain=True)
    check("anything hurt: no growth - repeat it", ouch["result"] == "repeat" and not dd.get("calibration"))
    bad = {"2026-10-02": {"feet": 7, "legs": 3}, "2026-10-03": {"feet": 4, "legs": 2}}
    rep_, _ = bench("2026-10-01", std(140), 223.6, rpe=3, checkins=bad)
    check("a 7/10 morning after: repeat", rep_["result"] == "repeat")
    again, d1 = bench("2026-10-01", std(140), 223.6, rpe=2)
    check("graded once", calibration.block_test(d1, "2026-10-01", std(140), clean, 223.6) is None)
    # a history of standard benchmarks -> a prediction; beating it grows more and moves the curve
    def history(hrs):
        d = {"plans": {}}
        for i, h in enumerate(hrs):
            day = f"2026-1{i}-01"
            c = {f"2026-1{i}-02": {"feet": 2, "legs": 2}, f"2026-1{i}-03": {"feet": 2, "legs": 2}}
            calibration.benchmark_report(d, day, 3)
            calibration.block_test(d, day, std(h), c, 223.6)
        return d
    c9 = {"2026-12-02": {"feet": 2, "legs": 2}, "2026-12-03": {"feet": 2, "legs": 2}}
    ex = calibration.benchmark_expectation(history([140, 140]), "2026-12-01", 223.6)
    check(f"two standard benchmarks make a prediction ({ex['predicted_eff']} m/min per beat)", ex["predicted_eff"] and ex["from_benchmarks"] == 2)
    dm = history([140, 140]); calibration.benchmark_report(dm, "2026-12-01", 3)
    match = calibration.block_test(dm, "2026-12-01", std(140), c9, 223.6)
    db = history([140, 140]); calibration.benchmark_report(db, "2026-12-01", 3)
    blew = calibration.block_test(db, "2026-12-01", std(125), c9, 223.6)
    ds = history([140, 140]); calibration.benchmark_report(ds, "2026-12-01", 3)
    short = calibration.block_test(ds, "2026-12-01", std(150), c9, 223.6)
    check(f"as predicted {match['gain_pct']}%, beat the prediction (HR 125 vs 140) {blew['gain_pct']}%, fell short {short['gain_pct']}%",
          blew["gain_pct"] > match["gain_pct"] > short["gain_pct"])
    check(f"...and beating it shifts the curve up for next time (rate {match['grade']['rate']} -> {blew['grade']['rate']}); "
          f"falling short shifts it down ({short['grade']['rate']})",
          blew["grade"]["rate"] > match["grade"]["rate"] > short["grade"]["rate"])
    near = calibration.benchmark_expectation({"benchmarks": {"start_block": 100}}, "2026-12-01", 450)
    start = calibration.benchmark_expectation({"benchmarks": {"start_block": 100}}, "2026-12-01", 100)
    check(f"diminishing returns: at 1x the curve offers {start['growth_if_as_predicted']:.1%}, at 4.5x only {near['growth_if_as_predicted']:.1%}",
          start["growth_if_as_predicted"] >= 0.09 and near["growth_if_as_predicted"] < 0.02)
    dx = {"plans": {}, "benchmarks": {"start_block": 100, "rate": 1.0, "runs": {
        "2026-11-01": {"result": "grew", "eff": 0.7, "standard": True}, "2026-11-15": {"result": "grew", "eff": 0.7, "standard": True}}}}
    calibration.benchmark_report(dx, "2026-12-01", 2)
    vet = calibration.block_test(dx, "2026-12-01", std(115), c9, 480)
    check(f"...but a veteran at 4.8x who blows past the prediction still grows ({vet['gain_pct']}%) - results overrule the curve",
          vet["gain_pct"] >= 3)
    off = calibration.block_test({"plans": {}}, "2026-10-01", {**std(140), "km": 5.0}, clean, 223.6)
    check("a 5 km run isn't the standard benchmark: no prediction compared", off["standard"] is False and off["vs_prediction"] is None)
    r = damage.remodeling_response(["2026-10-05"], [246.0], block=246.0)
    check("a calibrated block sizes the running load (one of its runs = 1 block)", r["history"][0]["score"] == 1.0)

    d = coach.load(pathlib.Path(tempfile.mkdtemp()) / "coach.json")
    days = calibration.plan_test_week(d, "2026-10-26", ["ftp", "css", "diagnostic"])
    k = sorted(days)
    check(f"the test week: easy Mon-Wed, CSS Thu, diagnostic Fri, TEST DAY Sat, off Sun "
          f"({[(x[5:], days[x].get('sport'), days[x].get('test')) for x in k]})",
          [days[x].get("sport") for x in k] == ["ride", "swim", "ride", "swim", "ride", "test", "rest"]
          and days[k[3]]["test"] == "css" and days[k[4]]["test"] == "diagnostic" and days[k[5]]["test"] == "ftp"
          and days[k[5]]["note"].startswith("TEST DAY") and all(days[x]["minutes"] <= 30 for x in k[:3]))
    check("test day goes on Coming Up", any(e["name"].startswith("Test day") for e in d["events"]))
    bg = calibration.plan_test_week(d, "2026-12-07", ["big_gear"])
    check("FTP not due: the big-gear test takes Saturday; no CSS: an easy swim Thursday",
          bg["2026-12-12"]["test"] == "big_gear" and bg["2026-12-12"].get("focus", {}).get("rpm") == [50, 60] and "test" not in bg["2026-12-10"])
    try:
        calibration.plan_test_week(d, "2026-10-27"); check("a test week starts on a Monday", False)
    except ValueError:
        check("a test week starts on a Monday", True)
    check(f"next test week: six weeks after the last ({calibration.next_test_week(d, '2026-11-02')})",
          calibration.next_test_week(d, "2026-11-02") == "2026-12-07")
    check("never tested: next Monday", calibration.next_test_week({"plans": {}}, "2026-09-28") == "2026-10-05")
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
