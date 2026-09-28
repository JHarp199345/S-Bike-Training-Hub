"""mcp_server.py - the bike hub as MCP tools, so Claude can coach from any chat.

A Model Context Protocol server over stdio (JSON-RPC 2.0, one message per
line), written without extra packages. Every tool calls the bridge's own API
on this Mac (http://127.0.0.1:8729), the same one the pages and `hub` use -
nothing leaves the Mac, and the bridge must be running.

Registered with Claude Desktop (claude_desktop_config.json) and Claude Code
(`claude mcp add`) as "s-bike-hub".
"""
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

BASE = __import__("os").environ.get("S29_HUB_URL", "http://127.0.0.1:8729")   # tests point this at a scratch server
VERSION = "1.0.0"


class HubError(Exception):
    pass


def call(path, body=None):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            raise HubError(json.loads(e.read()).get("error") or str(e))
        except ValueError:
            raise HubError(str(e))
    except OSError:
        raise HubError("The bike bridge isn't running on the Mac. Start it from the 🚲 menu icon or the Desktop "
                       "launcher (S-Bike Hub.command), then try again.")


def _date(a):
    return a.get("date") or dt.date.today().isoformat()


def _q(date):
    return f"?date={date}"


# ── tools ────────────────────────────────────────────────────────────────────

def t_today(a):
    return call("/api/coach/today" + _q(_date(a)))


def t_checkins(a):
    return call(f"/api/coach/history?days={int(a.get('days', 14))}")


def t_checkin(a):
    body = {k: a[k] for k in ("date", "legs", "breathing", "sleep", "motivation", "hr90", "hr120", "hr_after", "gut", "note") if k in a}
    return call("/api/coach/checkin", body)


def t_plan(a):
    body = {k: a[k] for k in ("date", "verdict", "note") if k in a}
    if "workout_id" in a:
        body["workout"] = a["workout_id"]
    return call("/api/coach/plan", body)


def t_rides(a):
    d = call("/api/fitness")
    since = (dt.date.today() - dt.timedelta(days=int(a.get("days", 7)))).isoformat()
    return [r for r in d["rides"] if r["date"] >= since]


def t_story(a):
    s = call(f"/api/posts/{a['ride']}")
    keep = ("ride", "title", "stats", "zones", "highlights", "best_efforts", "compare", "streak", "week", "fitness",
            "route", "ghost", "workout", "ftp_test", "adherence")
    return {k: s.get(k) for k in keep}


def t_fitness(a):
    d = call("/api/fitness")
    return {k: d[k] for k in ("ftp", "ftp_source", "today", "advice", "week")} | {"last_14_days": d["days"][-14:]}


def t_milestones(a):
    d = call("/api/milestones")
    return {k: d[k] for k in ("totals", "streaks", "next", "equivalents")} | {"earned": [e["name"] for e in d["earned"]]}


def t_status(a):
    s = call("/status")
    return {k: s.get(k) for k in ("bike", "power", "cadence", "speed", "gear", "erg", "workout", "ftp", "ftp_source",
                                  "bests", "kcal", "distance", "route", "events")}


def t_workouts(a):
    d = call("/api/workouts")
    return [{"id": w["id"], "name": w["name"], "note": w.get("note"), "stats": w["stats"], "blocks": w["blocks"]} for w in d["workouts"]]


def t_timed(a):
    T, n = float(a["total_minutes"]), int(a.get("intervals", 3))
    ip, rp = int(a.get("interval_pct", 75)), int(a.get("rest_pct", 50))
    shares = [("warmup", "Warm-up", 15), ("ramp", "Ramp", 15)]
    for i in range(n):
        shares.append(("interval", f"Interval {i + 1}", 40 / n))
        if i < n - 1:
            shares.append(("rest", f"Rest {i + 1}", 20 / max(1, n - 1)))
    shares.append(("cooldown", "Cool-down", 10))
    tot = sum(x[2] for x in shares)
    parts = []
    for kind, label, sh in shares:
        p = {"kind": kind, "label": label, "minutes": T * sh / tot}
        if kind == "ramp":
            p.update({"from": 50, "to": min(ip, 75)})
        else:
            p["pct"] = {"warmup": 50, "interval": ip, "rest": rp, "cooldown": 45}[kind]
        parts.append(p)
    name = a.get("name") or f"{T:.0f} min · {n}× at {ip}%"
    return call("/api/coach/split/save", {"name": name, "parts": parts, "plan": bool(a.get("make_today_plan")),
                                          "date": a.get("date")})


def t_create(a):
    d = call("/api/workouts/save", {"name": a["name"], "note": a.get("note", ""), "blocks": a["blocks"]})
    if a.get("make_today_plan"):
        call("/api/coach/plan", {"date": _date(a), "workout": d["id"]})
    return d


def t_start(a):
    return call(f"/api/workouts/start/{a['workout_id']}", {})


def t_diagnostic(a):
    return call("/api/coach/test/start", {})


S = lambda **p: {"type": "object", "properties": p, "additionalProperties": False}
INT = lambda d, lo=None, hi=None: {"type": "integer", "description": d, **({"minimum": lo} if lo is not None else {}),
                                   **({"maximum": hi} if hi is not None else {})}
STR = lambda d, **k: {"type": "string", "description": d, **k}
DATE = STR("Day as YYYY-MM-DD (default: today)")

TOOLS = [
    ("get_today", "Today's coaching picture: the rider's check-in and morning diagnostic (heart rate at 90 W / 120 W / "
     "60 s later, legs, breathing, sleep, gut call), the verdict with reasons, their normal (baseline), the plan "
     "already set, FTP, and the workout list. Start every coaching conversation here.", S(date=DATE), t_today),
    ("get_checkins", "Recent daily check-ins, diagnostics, verdicts and plans - the trend over days.",
     S(days=INT("How many days back (default 14)", 1, 120)), t_checkins),
    ("record_checkin", "Record or update a day's check-in for the rider (when they tell you in chat). Legs/breathing/sleep "
     "1-10 (legs: 1 fresh, 10 wrecked); gut is go/easy/no; heart rates in bpm. Returns the verdict.",
     S(date=DATE, legs=INT("1-10", 1, 10), breathing=INT("1-10", 1, 10), sleep=INT("1-10", 1, 10),
       motivation=INT("1-10", 1, 10), hr90=INT("HR at the end of the 90 W stage", 40, 220),
       hr120=INT("HR at the end of the 120 W push", 40, 220), hr_after=INT("HR 60 s after the push", 30, 220),
       gut=STR("Their own call", enum=["go", "easy", "no"]), note=STR("Anything they said")), t_checkin),
    ("set_plan", "Write today's plan onto the rider's Coach page: the verdict (go/easy/rest), your coaching note to them "
     "(plain, specific: what to ride, how it should feel, when to stop), and optionally the workout to ride "
     "(workout_id from list_workouts or a create tool). They see it on their phone with a Ride button.",
     S(date=DATE, verdict=STR("go, easy or rest", enum=["go", "easy", "rest"]), note=STR("Your note to the rider"),
       workout_id=STR("Workout to ride today (empty string clears it)")), t_plan),
    ("get_rides", "Recent rides: date, start, minutes, average and normalized watts, intensity (IF), training load.",
     S(days=INT("How many days back (default 7)", 1, 120)), t_rides),
    ("get_ride_story", "Everything about one ride (ride id like ride_2026-09-27_0959 from get_rides): stats, "
     "time in power zones, highlights, best efforts, records, workout adherence grades per part, streak, fitness.",
     S(ride=STR("Ride id, e.g. ride_2026-09-27_0959")), t_story),
    ("get_fitness", "Fitness (42-day load), fatigue (7-day), form, advice, the last 7 days' totals and the last "
     "14 days day by day. From power, bike rides only - check COROS for runs, swims and sleep.", S(), t_fitness),
    ("get_milestones", "Streaks (days, weeks on goal), lifetime totals, milestones earned and next up.", S(), t_milestones),
    ("get_status", "The bridge right now: bike connected, live watts/cadence/gear, ERG/workout running, FTP, "
     "personal bests (5 s / 1 / 5 / 20 min), this ride's calories and distance, recent events.", S(), t_status),
    ("list_workouts", "The workouts with ids, notes, time/load/calories at the rider's FTP, and their blocks.", S(), t_workouts),
    ("create_timed_workout", "Make a standard timed workout: warm-up 15%, ramp 15%, intervals 40% (split evenly), "
     "rests 20%, cool-down 10% of total_minutes. Intensities in % of FTP. Optionally make it today's ride.",
     S(total_minutes={"type": "number", "minimum": 10, "maximum": 180}, intervals=INT("Number of intervals", 1, 10),
       interval_pct=INT("Interval target, % of FTP (base phase: 70-80)", 30, 150),
       rest_pct=INT("Rest target, % of FTP", 30, 80), name=STR("Name"), make_today_plan={"type": "boolean"}, date=DATE),
     t_timed),
    ("create_workout", "Make any workout from blocks, each one of: {type:'steady', minutes, pct|watts, label?}, "
     "{type:'ramp', minutes, from, to, label?} (pct of FTP), {type:'intervals', times, on:{minutes,pct}, "
     "off:{minutes,pct}}. Optionally make it today's ride.",
     S(name=STR("Name"), note=STR("What it's for"), blocks={"type": "array", "items": {"type": "object"}},
       make_today_plan={"type": "boolean"}, date=DATE), t_create),
    ("start_workout", "Start a workout on the bike NOW in ERG (only when the rider asks, e.g. they're on the bike).",
     S(workout_id=STR("Workout id")), t_start),
    ("start_diagnostic", "Start the 6-minute morning diagnostic on the bike NOW (only when the rider asks and is on the bike).",
     S(), t_diagnostic),
]
for name, _, schema, _ in TOOLS:
    if name in ("get_ride_story",):
        schema["required"] = ["ride"]
    if name in ("create_timed_workout",):
        schema["required"] = ["total_minutes"]
    if name in ("create_workout",):
        schema["required"] = ["name", "blocks"]
    if name in ("start_workout",):
        schema["required"] = ["workout_id"]
BY_NAME = {t[0]: t for t in TOOLS}
INSTRUCTIONS = ("An indoor smart-bike training hub (built on a Merach S29). Coach the rider day by day: start "
                "with get_today, look at recent check-ins and rides, then set_plan with a verdict, a short plain "
                "note, and a workout if they're riding. Their legs and their own 'not today' outrank the numbers. "
                "Heart rate on the bike comes only from the morning diagnostic (read off their watch).")


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None                                     # a notification (e.g. notifications/initialized)
    if method == "initialize":
        pv = (msg.get("params") or {}).get("protocolVersion") or "2025-06-18"
        return {"protocolVersion": pv, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "s-bike-hub", "version": VERSION}, "instructions": INSTRUCTIONS}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s, _ in TOOLS]}
    if method == "tools/call":
        p = msg.get("params") or {}
        tool = BY_NAME.get(p.get("name"))
        if not tool:
            raise KeyError(f"unknown tool {p.get('name')}")
        try:
            out = tool[3](p.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}]}
        except HubError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except (KeyError, ValueError, TypeError) as e:
            return {"content": [{"type": "text", "text": f"Bad arguments: {e}"}], "isError": True}
    raise LookupError(method)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            res = handle(msg)
            if res is not None:
                out = {"jsonrpc": "2.0", "id": msg["id"], "result": res}
            else:
                continue
        except LookupError as e:
            out = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32601, "message": f"Method not found: {e}"}}
        except Exception as e:
            out = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
