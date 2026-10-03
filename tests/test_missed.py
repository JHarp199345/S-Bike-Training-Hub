"""Missed sessions: a past planned session with nothing recorded is missed (not today's, not a done one);
the athlete's reason is kept; the recent-weeks summary and the MCP tools give the coach the picture."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, datetime as dt, json, os, subprocess, tempfile, threading, types
from unittest.mock import patch
import coach

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


TODAY = "2026-11-12"   # a Thursday
d = {"plans": {
    "2026-11-09": {"sessions": [{"sport": "ride", "minutes": 45, "name": "Sweet-spot intervals", "shape": "build"},
                                 {"sport": "run", "minutes": 20, "name": "Brick run", "shape": "build"}]},
    "2026-11-10": {"sessions": [{"sport": "swim", "minutes": 30, "name": "Swim: steady 100s"}]},
    "2026-11-11": {"sessions": [{"sport": "rest", "minutes": 0, "name": "Rest"}]},
    "2026-11-12": {"sessions": [{"sport": "ride", "minutes": 40, "name": "Easy endurance ride"}]},
    "2026-11-14": {"sessions": [{"sport": "run", "minutes": 30, "name": "Steady run"}]}},
    "checkins": {}}
done = {"2026-11-09": [{"sport": "bike", "minutes": 44}]}

with patch.object(coach, "today", return_value=TODAY):
    wk = {x["date"]: x for x in coach.week(d, TODAY, done)}
    mon = wk["2026-11-09"]["sessions"]
    check("a done ride is completed, not missed", mon[0].get("completion") and not mon[0].get("missed"))
    check("the run after it, never recorded, is missed", mon[1].get("missed"))
    check("a past swim with nothing recorded is missed", wk["2026-11-10"]["sessions"][0].get("missed"))
    check("a rest day is never missed", not wk["2026-11-11"]["sessions"][0].get("missed"))
    check("today's session isn't missed yet", not wk["2026-11-12"]["sessions"][0].get("missed"))
    check("a future session isn't missed", not wk["2026-11-14"]["sessions"][0].get("missed"))
    e = coach.record_missed(d, "2026-11-10", 0, "sick", "head cold")
    wk = {x["date"]: x for x in coach.week(d, TODAY, done)}
    check("the athlete's reason is kept with the session", wk["2026-11-10"]["sessions"][0]["missed_reason"]["reason"] == "sick")
    bad = []
    for args in (("2026-11-10", 0, "lazy"), ("2026-11-10", 5, "busy"), ("2026-11-14", 0, "busy")):
        try:
            coach.record_missed(d, *args)
            bad.append(False)
        except ValueError:
            bad.append(True)
    check("unknown reasons, wrong indexes and future sessions are refused", all(bad))
    md = coach.missed_days(d, "2026-11-01", "2026-11-30", done)
    check("missed_days lists them for the program calendar", set(md) == {"2026-11-09", "2026-11-10"}
          and md["2026-11-10"][0]["reason"] == "sick")

# the coach's view, over HTTP and MCP (no ride files on this scratch hub, so Monday's ride is missed there too)
import panel
tmp = pathlib.Path(tempfile.mkdtemp())
(tmp / "rides").mkdir()
d2 = json.loads(json.dumps(d)) | {"program_goal": {"goal": "Sprint tri", "sport": "tri", "hours": 4, "start": "2026-10-05"}}
coach.save = coach.save  # (writes beside the scratch rides)
(tmp / "coach.json").write_text(json.dumps(d2))


class FakeBridge:
    profile = {"ftp": 180, "ftp_source": "test"}
    csv_path = tmp / "rides" / "ride_x.csv"
    workouts = []
    args = types.SimpleNamespace(no_bike=True)
    def event(self, m): pass


coach_file = coach.file_for(tmp / "rides")
coach_file.write_text(json.dumps(d2))
loop = asyncio.new_event_loop()
with patch.object(coach, "today", return_value=TODAY):
    loop.run_until_complete(panel.serve(FakeBridge(), 18771, lan=False))
    threading.Thread(target=loop.run_forever, daemon=True).start()
    import urllib.request
    rw = json.loads(urllib.request.urlopen(f"http://127.0.0.1:18771/api/coach/recent-weeks?weeks=2&date={TODAY}").read())
    this = next(w for w in rw["weeks"] if w["when"] == "this week")
    check("recent weeks: this week's planned vs available time and its missed sessions with reasons",
          this["available_minutes"] == 240 and this["planned_minutes"] == 165
          and {m["session"] for m in this["missed"]} == {"Sweet-spot intervals", "Brick run", "Swim: steady 100s"}
          and next(m for m in this["missed"] if m["session"].startswith("Swim"))["reason"] == "sick")
    check("…and next week is included for planning ahead", any(w["when"] == "next week" for w in rw["weeks"]))
    r = urllib.request.Request("http://127.0.0.1:18771/api/coach/missed", method="POST",
                               data=json.dumps({"date": "2026-11-09", "index": 1, "reason": "busy", "note": "work ran late"}).encode())
    check("the page can record a reason", json.loads(urllib.request.urlopen(r).read())["missed"]["reason"] == "busy")
    cal = json.loads(urllib.request.urlopen("http://127.0.0.1:18771/api/coach/missed?start=2026-11-01&end=2026-11-30").read())
    check("the program calendar gets the missed days", cal["missed"]["2026-11-09"][1]["reason"] == "busy")

    env = {**os.environ, "S29_HUB_URL": "http://127.0.0.1:18771"}
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_recent_weeks", "arguments": {"weeks": 2, "date": TODAY}}}]
    out = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "mcp_server.py")],
                         input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, env=env, timeout=60)
    res = [json.loads(l) for l in out.stdout.splitlines() if l.strip()]
    instr = res[0]["result"]["instructions"]
    check("the assistant is told it is the planner and to plan around what actually happened",
          "You are the planner" in instr and "Missed sessions are information" in instr and "peak" in instr.lower())
    weeks = json.loads(res[1]["result"]["content"][0]["text"])["weeks"]
    check("get_recent_weeks gives the assistant the same picture", any(w["missed"] for w in weeks))
loop.call_soon_threadsafe(loop.stop)

html = (pathlib.Path(__file__).resolve().parent.parent / "web" / "coach.html").read_text()
check("the Coach page draws a red cross on missed sessions in the week strip, calendar and program calendar",
      all(x in html for x in ("missx", "hasmissed", "missed-day", "data-miss-reason", "/api/coach/missed")))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
