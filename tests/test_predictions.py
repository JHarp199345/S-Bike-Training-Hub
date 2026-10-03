"""Race predictions (the rider's design, 2026-10-03): the assistant predicts from the hub's numbers, the hub keeps
every prediction, says when one is due again and grades them all against the result."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import predictions as P

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


d = {"events": [{"id": "2026-09-20-sprint-tri", "date": "2026-09-20", "name": "Sprint tri", "kind": "race", "sport": "tri"}]}
check("times read as seconds, m:ss or h:mm:ss", P.seconds("1:27:30") == 5250 and P.seconds("12:05") == 725 and P.seconds(90) == 90)
for bad in ("1:xx", "-5", 0):
    try:
        P.seconds(bad); check(f"'{bad}' is refused", False)
    except ValueError:
        check(f"'{bad}' is refused", True)
v = P.view(d, "2026-06-29")["races"][0]
check(f"a race without a prediction is due ({v['why_due']})", v["due"] and v["why_due"] == "no prediction yet")
try:
    P.save(d, "2026-09-20", "1:27:00", "1:30:00", "1:25:00", today="2026-06-29"); check("a backwards range is refused", False)
except ValueError:
    check("a backwards range is refused", True)
try:
    P.save(d, "2026-10-01", 1, 1, 1); check("a race not on the calendar is refused", False)
except ValueError:
    check("a race not on the calendar is refused", True)
P.save(d, "2026-09-20", "1:31:00", "1:24:00", "1:40:00", {"swim": "12:30", "bike": "45:00", "run": "29:00"},
       "FTP 180 W, CSS 2:05, block 72", ["run block", "+10 W"], today="2026-06-29")
v = P.view(d, "2026-07-02")["races"][0]
check("a fresh prediction isn't due", not v["due"] and v["predictions"][0]["likely"] == "1:31:00")
d["calibration"] = {"ftp": [{"date": "2026-08-17", "kind": "test", "value": 192}]}
v = P.view(d, "2026-08-18")["races"][0]
check(f"a test since the last prediction makes it due ({v['why_due']})", v["due"] and "ftp" in v["why_due"])
P.save(d, "2026-09-20", "1:27:00", "1:23:30", "1:31:00", basis="FTP 192 W", today="2026-08-18")
v = P.view(d, "2026-08-19")["races"][0]
check(f"the log shows how it moved and narrowed ({v['moved']})", "1:31:00 -> 1:27:00" in v["moved"] and "16:00 wide -> 7:30 wide" in v["moved"])
v = P.view(d, "2026-09-10")["races"][0]
check(f"three weeks without one makes it due ({v['why_due']})", v["due"] and "21+" in v["why_due"])
P.result(d, "2026-09-20-sprint-tri", "1:26:10", {"run": "27:40"})
v = P.view(d, "2026-09-21")["races"][0]
check(f"the result grades every prediction ({v['grade']})", v["grade"].startswith("2 of 2") and v["predictions"][-1]["off_by_s"] == -50)
check("a raced event is never due", "due" not in v)
from unittest.mock import patch
import attention, coach, coaching_review
d2 = {"plans": {}, "checkins": {}, "events": d["events"]}
with patch.object(coaching_review, "outlook", return_value={"sessions": [], "training_rules": [], "running_progression": {}}), \
     patch.object(coach, "missed_days", return_value={}):
    items = attention.items(d2, {"activities": []}, {}, [], "2026-07-06")["items"]
check(f"a due prediction is on the check-in list ({[x['kind'] for x in items]})",
      [x["kind"] for x in items] == ["prediction"] and items[0]["tool"] == "save_race_prediction")
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
