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
    body = {k: a[k] for k in ("date", "verdict", "note", "focus", "sport", "minutes") if k in a}
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


def t_load(a):
    d = call("/api/load")
    return {k: d.get(k) for k in ("systems", "readiness", "sports_last7", "calibration", "history_days", "profile")} | \
           {"last_14_days": [{"date": r["date"], **{x: r[x]["load"] for x in ("engine", "impact", "muscle")}}
                             for r in d.get("days", [])[-14:]], "activities_last_14": [x for x in d.get("activities", [])
                                                                                      if x["date"] >= (dt.date.today() - dt.timedelta(days=14)).isoformat()]}


def t_import(a):
    return call("/api/activities/import", {"urls": a["urls"]})


def t_capacity(a):
    return call("/api/load/capacity", {"system": a["system"], "usual_week": a.get("usual_week"), "note": a.get("note")})


def t_steps(a):
    return call("/api/steps", {"steps": a["steps"]})


def t_area(a):
    body = {k: a[k] for k in ("center", "radius_km", "minutes", "focus") if k in a}
    d = call("/api/plan/area", body)
    return {"focus": d.get("focus"), "center": d.get("center"), "radius_km": d.get("radius_km"), "minutes": d.get("minutes"),
            "note": d.get("note"),
            "routes": [{"cid": r["cid"], "name": r["name"], **r["stats"], "fit": r["fit"]} for r in d.get("routes", [])]}


def t_save_route(a):
    d = call("/api/route/save", {"cid": a["cid"], "name": a.get("name")})
    if a.get("ride_now") and d.get("id"):
        call(f"/api/route/start/{d['id']}", {})
        d["riding"] = True
    return d


def t_routes(a):
    return [{k: r.get(k) for k in ("id", "name", "km", "climb_m", "max_grade", "kind")} for r in call("/api/routes")]


def t_climbs(a):
    return call(f"/api/route/{a['route_id']}/climbs")


def t_session(a):
    body = {"route_id": a.get("route_id"), "segments": a.get("segments") or []}
    if a.get("date"):
        body["date"] = a["date"]
    return call("/api/coach/session", body)


def t_climb_history(a):
    q = f"?route_id={a['route_id']}" if a.get("route_id") else ""
    return call("/api/climbs" + q)


def t_rate(a):
    return call("/api/coach/rate", {k: a[k] for k in ("ride", "rpe") if k in a})


def t_morning(a):
    return call("/api/morning", {"days": a["days"]})


def t_skills(a):
    return call("/api/coach/today").get("skills")


def t_set_skill(a):
    return call("/api/coach/skill", {k: a[k] for k in ("skill", "level", "why") if k in a})


def t_event(a):
    return call("/api/coach/event", {k: a[k] for k in ("date", "name", "kind", "sport", "note", "remove") if k in a})


def t_calibration(a):
    return call("/api/coach/today").get("calibration")


def t_schedule_test(a):
    return call("/api/coach/test", {"test": a["test"], **({"date": a["date"]} if a.get("date") else {})})


def t_record_test(a):
    return call("/api/calibration", {k: a[k] for k in ("capacity", "value", "kind", "date", "note", "t400", "t200") if k in a})


def t_test_week(a):
    return call("/api/coach/testweek", {"monday": a["monday"]} if a.get("monday") else {})


def t_aerobic(a):
    return call("/api/load").get("aerobic")


def t_transfer(a):
    return call("/api/load").get("transfer")


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
       workout_id=STR("Workout to ride today (empty string clears it)"),
       sport=STR("The day's marker on the Coach page's week: ride, swim, run, walk, gym, test, rest, other "
                 "(swims can't go on the COROS calendar - this is where they live)",
                 enum=["ride", "swim", "run", "walk", "gym", "test", "rest", "other", ""]),
       minutes=INT("The time goal for the day's session", 0, 600),
       focus={"description": "What the ride is coaching for - a cadence range plus a watt range that auto-shift "
              "steers toward: 'cadence' (65-80 rpm, zone 2: builds the cadence habit), 'grit' (50-65 rpm, 76-90% FTP: "
              "force; loads the leg muscles more - not when legs are tired), 'speed' (85-100 rpm, 50-67% FTP), "
              "'recovery' (70-85 rpm, 40-55% FTP), 'off' (cadence only), or custom {name, rpm:[lo,hi], "
              "watts:[lo,hi] or pct:[lo,hi]}. Empty string clears it (default: cadence; recovery on rest days).",
              "anyOf": [{"type": "string"}, {"type": "object"}]}), t_plan),
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
    ("get_load", "Training load by body system across ALL sports (runs, swims, gym, rides): ENGINE (heart/lungs; "
     "watts on the bike, heart rate calibrated to watts elsewhere), IMPACT (feet/bones; running and walking x body "
     "weight), MUSCLE (leg force; pedal torque, gym effort, running). Each has fitness, fatigue, form, the "
     "acute:chronic ratio and zone (0.8-1.3 sweet spot, >1.5 danger for impact/muscle), this week's used load vs "
     "budget, and a weakest-link readiness verdict with what's limiting. Use this before set_plan.", S(), t_load),
    ("import_activities", "Import watch activity files into the hub so every sport counts: pass the https download "
     "links for .fit files (e.g. from the COROS tool queryActivityFitFileDownloadUrls, one activity at a time).",
     S(urls={"type": "array", "items": {"type": "string"}, "description": "https links to .fit or .tcx files"}), t_import),
    ("set_capacity", "Tune a body system's usual week (engine, impact or muscle, in load points) from how the rider's "
     "body actually responded - e.g. they handled a big engine week like easy work (raise engine), or their feet feel "
     "overdone at a given impact week (lower impact so that week reads 'caution'). The zones, ratio and weekly budget then use it. "
     "Say why in the note. usual_week null clears it back to the model.",
     S(system=STR("engine, impact or muscle", enum=["engine", "impact", "muscle"]),
       usual_week={"type": ["number", "null"]}, note=STR("Why: what the rider reported")), t_capacity),
    ("record_steps", "Record the rider's daily step counts from the watch (e.g. from the COROS tool "
     "queryDailyHealthData): {\"YYYY-MM-DD\": steps}. Walking outside runs counts toward the feet's accumulated "
     "load above a daily allowance (a normal day, 6,000 steps, shrinking as the load rises). Sync the last week "
     "whenever coaching; today's count is partial.",
     S(steps={"type": "object", "additionalProperties": {"type": "integer"}, "description": "date -> steps"}), t_steps),
    ("plan_area_route", "Find ride routes inside an area for today's focus (the cadence and watt ranges from set_plan): "
     "loops inside a circle, each judged on TIME (minutes at the focus's middle watts, climbs slowing it), HOLDABLE "
     "(share of the ride where auto-shift's easiest gear keeps the watts at or under the range - walls aren't) and "
     "TERRAIN (gentle for cadence/speed/recovery days, steady climbing for grit). Best fit first, with the reasons. "
     "No center: uses the last area the rider circled on the planner. Pick one and save it with save_planned_route.",
     S(center={"type": "array", "items": {"type": "number"}, "description": "[lat, lon] of the circle's middle"},
       radius_km={"type": "number", "description": "circle radius, 1-40 km"},
       minutes=INT("How long the ride should be (default 45)", 15, 240),
       focus={"description": "override today's focus (a preset name or custom) for this search",
              "anyOf": [{"type": "string"}, {"type": "object"}]}), t_area),
    ("save_planned_route", "Save a route from plan_area_route (by its cid) so it's in the rider's list; ride_now starts "
     "it on the bike at once (only when the rider asks, e.g. they're on the bike).",
     S(cid=INT("The route's cid from plan_area_route"), name=STR("A name for it"), ride_now={"type": "boolean"}),
     t_save_route),
    ("get_routes", "The rider's saved routes: id, name, km, climbing, steepest grade, easy/mixed/hilly.", S(), t_routes),
    ("get_route_climbs", "A saved route's climbs, numbered from 1: where each starts and ends (m along the route), "
     "length, gain, average and max grade - for placing climb goals and efforts with set_route_session.",
     S(route_id=STR("Route id from get_routes or save_planned_route")), t_climbs),
    ("set_route_session", "Attach training to places on a route for a day (default today): when the rider starts that "
     "route the bridge runs it, steering auto-shift and shifting for the efforts. Segments (use climb numbers from "
     "get_route_climbs, or metres along the route): {type:'climb_time', climb:2, seconds:600, rpm?:[lo,hi]} - get up it "
     "in that time: the pace becomes a watt target, re-worked every second from what's left; {type:'efforts', climb:1 "
     "or at_m, count:3, on_s:15, off_s:180, watts:200, rpm?:[55,70]} - efforts in a big gear, shifted into at the start "
     "of each; {type:'focus', climb:3 or start_m+end_m, focus:'grit'} - a different focus for part of the route. "
     "Empty segments clear it. Results land in get_ride_story and get_climb_history.",
     S(route_id=STR("Route id"), segments={"type": "array", "items": {"type": "object"}}, date=DATE), t_session),
    ("get_climb_history", "Every climb the rider has ridden on a route (or all): date, climb number, length, grade, "
     "time, average and max watts, cadence, km/h, VAM (m climbed per hour), gears used - to see progress on the same "
     "climb and set the next goal.", S(route_id=STR("Only this route (optional)")), t_climb_history),
    ("rate_ride", "Record how hard the rider said a ride felt, 1-10 (session RPE: 1 very easy, 3 comfortable, 5 working, "
     "7 hard, 9 near max, 10 all out). Default: their latest ride. It shows in the ride story and on the Coach page.",
     S(rpe=INT("1-10", 1, 10), ride=STR("Ride id (default: the latest)")), t_rate),
    ("record_morning", "Record overnight readiness from the watch (COROS: querySleepHrv for HRV + its normal range "
     "and baseline, queryRestingHeartRate, queryDailyHealthData for sleep). {\"YYYY-MM-DD\": {hrv, hrv_low, hrv_high, "
     "hrv_baseline, resting_hr, sleep_min, deep_min, rem_min}} - dates are wake-up days. HRV under its normal range, "
     "resting HR 5+ over its two-week median, or under 5 h of sleep make the engine 'easy' (worse: 'rest'). Sync the "
     "last few days whenever coaching, before get_today.",
     S(days={"type": "object", "additionalProperties": {"type": "object"}}), t_morning),
    ("get_skills", "The rider's place on each skill ladder (progressions and regressions): cadence habit (rpm "
     "range), leg speed, grit (big-gear sets), climb pace (goal time vs their best), running return (walk/jog steps). "
     "Each: step n of N, what it is, today's step (one down on a day the watch or check-in says easy), the next step, "
     "recent moves and why. Steps move on their own with the evidence: up after two good sessions, down after two "
     "poor ones; running drops to walking while it's on rest. Use the steps when writing plans.", S(), t_skills),
    ("set_skill_level", "Move a skill ladder by hand (the coach's call): skill cadence/speed/grit/climbing/running, "
     "level 1..N, and why.", S(skill=STR("Skill", enum=["cadence", "speed", "grit", "climbing", "running"]),
                             level=INT("Step, from 1", 1, 6), why=STR("Why")), t_set_skill),
    ("set_event", "Add a date to plan backward from - an FTP test, a race, a goal ({date, name, kind: test|race|goal, "
     "sport: bike|run|swim|tri|other, note}) - or {remove: id}. get_today lists upcoming ones with days to go and "
     "notes (easy days before a test, taper before a race, and for running events whether the load model will have "
     "running cleared by then). Plan the days before each one around it.",
     S(date=DATE, name=STR("What it is"), kind=STR("test, race or goal", enum=["test", "race", "goal"]),
       sport=STR("bike, run, swim, tri or other", enum=["bike", "run", "swim", "tri", "other"]), note=STR("Anything else"),
       remove=STR("An event id to remove")), t_event),
    ("get_calibration", "The rider's capacities, each from tests and training with a confidence that fades after the "
     "last test: FTP (ramp test; 20-min bests between), heart rate at 90 W (morning diagnostic), big-gear 3 min (big-gear "
     "test; grit rides between), critical swim speed (400 m + 200 m time trial), and the running block (a benchmark run "
     "taken well can grow it, 10% a test). Plus which tests are coming due - put them on the calendar with schedule_test.",
     S(), t_calibration),
    ("schedule_test", "Put a test on the calendar (a plan item, not a button): ftp, diagnostic, big_gear, css, "
     "benchmark_run. Sets the day's marker, time, how-to note, and for big_gear the focus that runs it; the bike tests "
     "start from the Coach page's Ride it row. Keep the two days before an FTP or big-gear test easy.",
     S(test=STR("Which test", enum=["ftp", "diagnostic", "big_gear", "css", "benchmark_run"]), date=DATE), t_schedule_test),
    ("schedule_test_week", "Plan a test week - it doubles as the recovery week."
     " Easy, reduced sessions Mon-Wed so they peak on test day; swim CSS test Thu if due; morning "
     "diagnostic Fri then rest; TEST DAY Sat (FTP ramp test, or the big-gear test - one leg test a day); Sun off; "
     "training resumes Monday. Every 6 weeks; no monday = the next one due. Overwrites that week's plan.",
     S(monday=DATE), t_test_week),
    ("get_aerobic", "The aerobic engine ride by ride, from the watch's ride files (the bridge is its power meter, so "
     "power and heart rate together): efficiency factor (normalized watts per beat - rises with fitness), aerobic "
     "decoupling (watts per beat, first half vs second - under 5% stayed aerobic; judged only on 40+ min steady rides), "
     "and heart rate at the same 100-120 W (falls as the heart gets fitter), with trends. Import the watch's ride "
     "files first (import_activities).", S(), t_aerobic),
    ("get_transfer", "How much each sport carries over to the others for this rider, learned from their data: "
     "fitness carry-over (from -> to, relative to training the target sport itself; e.g. bike -> run 0.5 means an "
     "hour on the bike builds running fitness like half an hour of running) and how much each sport tires the legs "
     "relative to running. Starts at the literature (Millet 2002, Tanaka 1994, 2026 meta-analysis) and each value "
     "has an 80% interval and a status: prior / learning / learned. Only running builds feet and bones.", S(), t_transfer),
    ("record_test", "Record a result the hub can't see: a swim CSS test ({t400, t200} seconds - from the rider or the "
     "watch's laps), or any capacity by hand ({capacity: ftp|engine_hr90|legs_3min|swim_css|block, value, kind: "
     "test|manual|training, note}). Swims are then scored against CSS.",
     S(t400={"type": "number"}, t200={"type": "number"},
       capacity=STR("Capacity", enum=["ftp", "engine_hr90", "legs_3min", "swim_css", "block"]),
       value={"type": "number"}, kind=STR("test, manual or training", enum=["test", "manual", "training"]),
       date=DATE, note=STR("Where it came from")), t_record_test),
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
    if name in ("import_activities",):
        schema["required"] = ["urls"]
    if name in ("set_capacity",):
        schema["required"] = ["system", "usual_week"]
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
