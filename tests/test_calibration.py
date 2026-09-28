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

    d = {"checkins": {"2026-10-02": {"feet": 2, "legs": 3}, "2026-10-03": {"feet": 1, "legs": 2}}, "plans": {}}
    b = calibration.block_test(d, "2026-10-01", 300, d["checkins"], 223.6)
    check(f"a benchmark run taken well grows the block - by at most 10% ({b['value'] if b else None})", b and b["value"] == 246.0)
    d2 = {"checkins": {"2026-10-02": {"feet": 5}, "2026-10-03": {"feet": 2}}, "plans": {}}
    check("feet at 5/10 the morning after: no growth", calibration.block_test(d2, "2026-10-01", 300, d2["checkins"], 223.6) is None)
    check("the mornings not in yet: wait", calibration.block_test({"plans": {}}, "2026-10-01", 300, {}, 223.6) is None)
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
