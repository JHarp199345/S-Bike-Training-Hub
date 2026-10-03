"""mcp_server.py - the bike hub as MCP tools, so Claude can coach from any chat.

A Model Context Protocol server over stdio (JSON-RPC 2.0, one message per
line), written without extra packages. Every tool calls the bridge's own API
on this Mac (http://127.0.0.1:8729), the same one the pages and `hub` use -
the bridge must be running. An external AI receives the training context returned by these tools under its own service policies.

Registered with Claude Desktop (claude_desktop_config.json) and Claude Code
(`claude mcp add`) as "s-bike-hub".
"""
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

BASE = __import__("os").environ.get("S29_HUB_URL", "http://127.0.0.1:8729")   # tests point this at a scratch server
VERSION = "1.5.0"


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
    out = call("/api/coach/today" + _q(_date(a)))
    try:
        recent = call("/api/coach/recent-weeks?weeks=3&date=" + _date(a))
        out["recent_weeks"] = recent["weeks"]
        out["coaching_review"] = recent.get("coaching_review")
    except HubError:
        pass
    if out.get('training_block'):
        out['training_block'] = {k:v for k,v in out['training_block'].items() if k not in ('load_outlooks','load_history','swim_outlooks','weeks')}
        out['training_block']['detail_hint'] = 'Use get_training_block for weekly details; use preview_program for a focused draft forecast.'
    return out


def t_checkins(a):
    return call(f"/api/coach/history?days={int(a.get('days', 14))}")


def t_checkin(a):
    body = {k: a[k] for k in ("date", "legs", "feet", "shoulders", "hops", "hops_left", "hops_right", "journal", "breathing", "sleep", "motivation", "hr90", "hr120", "hr_after", "gut", "note") if k in a}
    return call("/api/coach/checkin", body)


def t_flag(a):
    return call("/api/coach/flag" + (f"?date={a['date']}" if a.get("date") else ""), {"id": a["id"], "action": a["action"]})


def t_plan(a):
    body = {k: a[k] for k in ("date", "verdict", "note", "focus", "sport", "minutes", "sessions") if k in a}
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


def t_programming(a):
    q = f"/api/coach/programming?sport={a.get('sport', 'swim')}" + (f"&date={a['date']}" if a.get("date") else "")
    if a.get("swim_profile"): q += "&swim_profile=" + a["swim_profile"]
    return call(q)


def t_swim_settings(a):
    return call("/api/coach/programming/swim", {k: a[k] for k in ("mix", "drill_share", "follow_event", "profile_id") if k in a})


def t_weekly(a):
    return call("/api/coach/weekly", {k: a[k] for k in ("sunday", "legs", "feet", "hops_left", "hops_right", "shoulders", "lift", "week", "note", "progress", "run_response") if k in a})


def t_block(a):
    return call("/api/coach/block", {k: v for k, v in {"weeks": a.get("weeks", 4), "start_date": a.get("start_date")}.items() if v is not None}) if a.get("start") else call("/api/coach/block")


def t_lifting(a):
    return call("/api/coach/lifting")


def t_lift_plan(a):
    return call("/api/coach/lifting/plan", {k: a[k] for k in ("date", "lifts", "name", "minutes", "index", "note", "override") if k in a})


def t_lift_eval(a):
    return call("/api/coach/lifting/evaluate", {"lifts": a["lifts"]})


def t_lift_log(a):
    return call("/api/coach/lifting/log", {k: a[k] for k in ("date", "done", "rpe", "wellness", "session_index", "compare_last", "override") if k in a})


def t_lift_follow(a):
    return call("/api/coach/lifting/followup", {k: a[k] for k in ("log_date", "ratings", "compare", "note") if k in a})


def t_lift_rule(a):
    return call("/api/coach/lifting/rules", {k: a[k] for k in ("text", "note", "remove") if k in a})


def t_swim_activity(a):
    return call("/api/load/swim-activity", {k: a[k] for k in ("activity_id", "paddles", "pull_buoy", "swim_rpe", "fins", "snorkel", "fins_fraction", "snorkel_fraction", "fin_type", "kick_rpe", "fin_kick_factor") if k in a})


def t_morning(a):
    return call("/api/morning", {"days": a["days"]})


def t_skills(a):
    return call("/api/coach/today").get("skills")


def t_set_skill(a):
    return call("/api/coach/skill", {k: a[k] for k in ("skill", "level", "why") if k in a})


def t_event(a):
    body = {k: a[k] for k in ("date", "name", "kind", "sport", "note", "remove") if k in a}
    det = {k: a[v] for k, v in (("type", "event_type"), ("distance", "distance"), ("strokes", "strokes")) if v in a}
    if det:
        body["detail"] = det
    return call("/api/coach/event", body)


def t_calibration(a):
    return call("/api/coach/today").get("calibration")


def t_schedule_test(a):
    return call("/api/coach/test", {"test": a["test"], **({"date": a["date"]} if a.get("date") else {})})


def t_record_test(a):
    return call("/api/calibration", {k: a[k] for k in ("capacity", "value", "kind", "date", "note", "t400", "t200",
                                                        "benchmark", "rpe", "pain", "calibration_run", "reason", "was_test") if k in a})


def t_test_week(a):
    return call("/api/coach/testweek", {"monday": a["monday"]} if a.get("monday") else {})


def t_aerobic(a):
    return call("/api/load").get("aerobic")


def t_insights(a):
    out = call("/api/load").get("insights") or {}
    if a.get("sport") and out.get("activities"):
        want = {"ride": "bike"}.get(a["sport"], a["sport"])
        out = out | {"activities": [r for r in out["activities"] if r["sport"] == want]}
    return out


def t_transfer(a):
    return call("/api/load").get("transfer")


def t_diagnostic(a):
    return call("/api/coach/test/start", {})


def _program_summary(out, a):
    """Keep calculations in the Hub; give the model decision evidence and bounded detail."""
    view = {k:v for k,v in out.items() if k not in ('starter','weeks')}
    view['weeks'] = [{k:w.get(k) for k in ('week','start','end','purpose','minutes')} for w in out.get('weeks',[])]
    for brief,w in zip(view['weeks'],out.get('weeks',[])):
        brief['sessions'] = [{'date':x.get('date'),'sport':x.get('sport'),'source':x.get('source')} for x in w.get('slots',[])]
    starter = out.get('starter') or {}
    if starter:
        view['starter'] = {k:v for k,v in starter.items() if k not in ('plans','display_plans','candidates')}
        view['starter']['candidates'] = []
        for c in starter.get('candidates',[]):
            brief = {k:c.get(k) for k in ('level','journey','summary','unknown_metrics','total_minutes','added_minutes')}
            flags=c.get('limit_flags',[]); by={}
            for f in flags:
                item=by.setdefault(f['metric'],{'metric':f['metric'],'days_over_limit':0,'first_date':f['date'],'peak':f['after'],'limit':f['limit']})
                item['days_over_limit']+=1
                if f['after'] is not None and (item['peak'] is None or f['after']>item['peak']):item['peak']=f['after']
            brief['limit_flags'] = list(by.values());brief['flagged_metric_days']=len(flags)
            view['starter']['candidates'].append(brief)
        if a.get('detail_start'):
            start=dt.date.fromisoformat(a['detail_start']); days=int(a.get('detail_days',7))
            if not 1<=days<=7:raise ValueError('detail_days must be 1–7')
            dates=[(start+dt.timedelta(days=i)).isoformat() for i in range(days)]
            selected=next((c for c in starter.get('candidates',[]) if c['level']==starter.get('selected')), {})
            view['starter']['detail']={date:{'plan':(selected.get('display_plans') or {}).get(date),
                'metrics':[{k:r.get(k) for k in ('key','name','unit','before','session_dose','dose_unit','after','expected','goal','method','limit','over_limit')} for r in (selected.get('projection',{}).get(date) or {}).get('metrics',[])]} for date in dates}
        view['detail_hint']='Pass detail_start YYYY-MM-DD and detail_days 1–7 to preview_program for selected-scenario sessions and daily forecast metrics.'
    return view


def t_program(a):
    return _program_summary(call('/api/coach/program-builder'),a)

def t_program_preview(a):
    fields=a.get('fields')
    if not isinstance(fields,dict) or not fields:raise ValueError('Provide program fields after reading get_program; include sport, priorities and the requested horizon.')
    out=call('/api/coach/program-builder', {**fields,'action':'preview'})
    if not (out.get('draft') or {}).get('id'):raise HubError('Update the Hub app to the MCP 1.3 release before reviewing or applying programs; this app does not support reviewed drafts.')
    return _program_summary(out,a)

def t_program_apply(a):
    if not a.get('draft_id'):raise ValueError('Preview first, then apply its draft_id. Field-only Apply is refused.')
    if not call('/api/coach/program-builder').get('capabilities',{}).get('reviewed_drafts'):raise HubError('Update the Hub app to the MCP 1.3 release before applying; the installed app does not support exact reviewed drafts.')
    return _program_summary(call('/api/coach/program-builder', {'draft_id':a['draft_id'],'action':'accept'}),a)

def t_calendar(a):
    from urllib.parse import urlencode
    return call('/api/coach/calendar?'+urlencode({'date':_date(a),'days':a.get('days',7)}))

def t_reading(a):
    from urllib.parse import urlencode
    return call('/api/coach/reading-evidence?'+urlencode({'date':_date(a),'metric':a['metric']}))

def t_coaching_review(a):
    return call('/api/coach/coaching-review?days='+str(a.get('days',14)))

def t_coaching_preview(a):
    return call('/api/coach/coaching-review',{**a,'action':'preview'})

def t_coaching_apply(a):
    return call('/api/coach/coaching-review',{**a,'action':'apply'})

def t_adaptation(a):
    return call('/api/coach/progression')


def _trim_packets(packets, per_char=24):
    out, seen = [], {}
    for pk in packets or []:
        seen[pk["char"]] = seen.get(pk["char"], 0) + 1
        if seen[pk["char"]] <= per_char:
            out.append(pk)
    return {"shown": out, "total_by_characteristic": seen}


def t_missed(a):
    return call("/api/coach/missed", {"date": a["date"], "index": int(a.get("index", 0)), "reason": a["reason"],
                                      "note": a.get("note", "")})["missed"]


def t_recent_weeks(a):
    return call(f"/api/coach/recent-weeks?weeks={int(a.get('weeks', 4))}&date={_date(a)}")


def t_bike_request(a):
    out = call("/api/bike/request")
    st = call("/api/bike/status")
    out["active_bike"] = st.get("active")
    r = out.get("request")
    if r:
        r = dict(r)
        if r.get("inspection"):
            r["inspection"] = dict(r["inspection"], packets=_trim_packets(r["inspection"].get("packets")))
        r["captures"] = [dict(c, packets=_trim_packets(c.get("packets"))) for c in r.get("captures", [])]
        r["proposals"] = r.get("proposals", [])[-2:]
        out["request"] = r
    return out


def t_bike_capture(a):
    out = call("/api/bike/capture", {"seconds": a.get("seconds", 10), "label": a.get("label", "")})
    out["capture"]["packets"] = _trim_packets(out["capture"]["packets"], 40)
    return out


def t_bike_propose(a):
    return call("/api/bike/propose", {"profile": a["profile"], "note": a.get("note", "")})


def t_bike_check(a):
    return call("/api/bike/check", {"athlete_ready": a.get("athlete_ready") is True})


def t_bike_feel(a):
    return call("/api/bike/feel", {"felt": a["felt"], "note": a.get("note", "")})


def t_bike_activate(a):
    return call("/api/bike/activate", {"share": bool(a.get("share"))})


def t_progress_evidence(a):
    return call('/api/coach/progress-evidence')

S = lambda **p: {"type": "object", "properties": p, "additionalProperties": False}
INT = lambda d, lo=None, hi=None: {"type": "integer", "description": d, **({"minimum": lo} if lo is not None else {}),
                                   **({"maximum": hi} if hi is not None else {})}
STR = lambda d, **k: {"type": "string", "description": d, **k}
DATE = STR("Day as YYYY-MM-DD (default: today)")
LIFTS = {"type": "array", "description": "The exercises, in order", "items": {"type": "object", "properties": {
    "name": {"type": "string"}, "how": {"type": "string", "description": "One line on how to do it"},
    "equipment": {"type": "string"},
    "kind": {"type": "string", "enum": ["barbell", "dumbbell", "kettlebell", "machine", "cable", "band", "medicine_ball", "power", "bodyweight", "other"], "description": "power = fast rotational swings, chops and throws (not judged against a one-rep max)"},
    "style": {"type": "string", "enum": ["restorative", "build"], "description": "restorative = controlled mild stress (holds, slow tempo, hangs, loaded stretching); build = progressive strength"},
    "sets": {"type": "integer", "minimum": 1, "maximum": 20}, "reps": {"type": "integer", "minimum": 1, "maximum": 100},
    "seconds": {"type": "integer", "minimum": 1, "maximum": 600}, "weight": {"type": "number", "minimum": 0},
    "unit": {"type": "string", "enum": ["lb", "kg"]}, "per_side": {"type": "boolean"},
    "tempo": {"type": "string", "description": "Seconds down-pause-up, e.g. '3-0-3' (slower = more strain per rep)"},
    "regions": {"type": "object", "description": "How the whole movement's strain is shared across body regions (from get_lifting), as percentages adding to ~100, e.g. deadlift {lower_back: 30, glutes: 25, hamstrings: 20, quads: 15, forearms: 10}",
                "additionalProperties": {"type": "number", "minimum": 0}}},
    "required": ["name", "kind", "sets", "regions"]}}

PROGRAM_FIELDS = {'type':'object','description':'Program fields: start YYYY-MM-DD, optional target date, horizon_days (default84), hours, sport (general/ride/swim/run/gym), priorities {sport:improve/maintain/pause}, assessment week/existing, optional reviewed phases, schedule_options {available_days, rest_days (0=Mon), first_sport, allow_doubles, lift_split: full_body/upper_lower/push_pull/push_pull_legs/lower_push_pull/four_way (the athlete chooses: ask), max_lift_days_in_row 1-5}, starter_enabled, starter_level easy/moderate/higher, starter_equipment basic/barbell, strength_anchors [{name,weight,unit,reps,rir}], neutral_forecast. Read get_program first; preserve the full reviewed payload when applying.','additionalProperties':True}
PROGRAM_FIELDS['properties'] = {
    'start':DATE, 'target':STR('Optional event/peak date YYYY-MM-DD'),
    'horizon_days':INT('Ongoing horizon; default 84, starter detail capped at 84',1,366),
    'goal':STR('Athlete goal'), 'outcome':STR('Desired result'), 'hours':{'type':'number','minimum':0.5,'maximum':40},
    'sport':STR('Goal sport',enum=['general','ride','swim','run','gym','tri']),
    'priorities':{'type':'object','additionalProperties':{'type':'string','enum':['improve','maintain','pause']}},
    'assessment':STR('Initial familiarization week or reported existing tests',enum=['week','existing']),
    'starter_enabled':{'type':'boolean'},'starter_level':STR('Workload scenario',enum=['easy','moderate','higher']),
    'starter_equipment':STR('Starter lifting equipment',enum=['basic','barbell']),
    'strength_anchors':{'type':'array','items':{'type':'object','properties':{'name':STR('Exact lift name'),'weight':{'type':'number','minimum':0},'unit':STR('Unit',enum=['lb','kg']),'reps':INT('Comfortable set repetitions',3,15),'rir':INT('Repetitions left',0,5)},'required':['name','weight','unit','reps','rir']}},
    'phases':{'type':'array','description':'Complete reviewed contiguous phases; read the saved phases first','items':{'type':'object'}},
    'schedule_options':{'type':'object'},'neutral_forecast':{'type':'boolean'}
}
TOOLS = [
    ('get_coaching_review','Read the next 1–14 days of running/lifting outlook, forecast conflicts, holds, symptoms and evidence-based capacity review candidates. Does not save or clear holds.',S(days=INT('Days ahead, including today',1,14)),t_coaching_review),
    ('preview_coaching_change','Preview calendar replacements or an evidence-supported capacity recalibration. Stores a six-hour review draft, without changing training records. Calendar changes replace all sessions on each specified uncompleted date in the next 14 days. Capacity target is running_block or lift_<region>; evidence determines direction and a provisional bounded step, never an arbitrary requested increase.',S(kind=STR('Review type',enum=['calendar','capacity']),target=STR('Capacity target: running_block or lift_<region>'),changes={'type':'array','minItems':1,'maxItems':14,'items':{'type':'object','required':['date','sessions'],'properties':{'date':DATE,'sessions':{'type':'array','items':{'type':'object'}}}}},note=STR('Why this change serves the program')),t_coaching_preview),
    ('apply_coaching_change','Apply the exact reviewed coaching draft after explicit athlete approval. Rejects stale state, forecast violations and unresolved restrictions. Read back get_coaching_review and the calendar; this never grants running clearance.',S(draft_id=STR('ID returned by preview_coaching_change'),approved={'type':'boolean','description':'True only after athlete approval'}),t_coaching_apply),
    ("get_recent_weeks", "The athlete's response to the plan, week by week: planned vs done minutes against their "
     "available time, each week's phase and shape (build, consolidation, peak_volume, peak_performance, taper, race), "
     "hard sessions, and every missed session with its reason. Read it before deciding whether to build, hold, recover "
     "or taper next week. Does not change anything.",
     S(weeks=INT("Weeks back to include (1-12, default 4)", 1, 12), date=DATE), t_recent_weeks),
    ("record_missed_session", "Record why a planned session didn't happen, in the athlete's words (busy, sick, sore, "
     "tired, travel, weather, other). Shown on their calendar and used when you plan the following weeks: illness or "
     "soreness argue for holding the build; busy weeks argue for a lighter, more realistic plan.",
     S(date=DATE, index=INT("Which session that day (0 = first)", 0, 9),
       reason=STR("Why", enum=["busy", "sick", "sore", "tired", "travel", "weather", "other"]), note=STR("Their words")), t_missed),
    ("get_bike_setup_request", "When the athlete says 'get my bike working' (or their bike won't connect to the hub): "
     "read the bike setup request they queued from the hub's welcome page - the bike's Bluetooth name, services, "
     "readable values and data packets captured while they pedaled - plus step-by-step instructions, safety rules and "
     "the profile format. Start here and follow its what_to_do steps. Does not change anything.", S(), t_bike_request),
    ("capture_bike_data", "Record the bike's data packets for a few seconds while the athlete pedals as you asked "
     "(e.g. label 'steady 60 rpm', then 'steady 90 rpm') so you can see which bytes follow cadence and power. "
     "Listen-only: nothing is sent to the bike. Tell the athlete what to do first.",
     S(seconds=INT("3-30 seconds", 3, 30), label=STR("What the athlete is doing, e.g. 'steady 90 rpm'")), t_bike_capture),
    ("propose_bike_profile", "Propose how the hub should talk to the bike: a profile (data, never code) in the "
     "profile_format from get_bike_setup_request. The hub validates it and decodes every captured packet with it, "
     "returning averages, ranges and warnings - fix warnings before checking.",
     S(profile={"type": "object", "description": "The bike profile (see profile_format)"},
       note=STR("Your reasoning in a sentence or two, kept with the request")), t_bike_propose),
    ("run_bike_check", "Run the hub's guided check with the latest proposed profile: ~40 s while the athlete pedals "
     "steadily. It listens, then (if the profile has resistance control) nudges resistance up a few levels in small "
     "steps and back down, through the hub's safety rules. ONLY after telling the athlete to pedal steadily and getting "
     "their OK. Then ask whether it got harder in the middle.",
     S(athlete_ready={"type": "boolean", "description": "true only after the athlete said they're pedaling steadily and ready"}),
     t_bike_check),
    ("record_bike_feel", "Record what the athlete felt during the guided check, in their words: harder (the pedals got "
     "harder in the middle), no_change, or unsure.",
     S(felt=STR("What they said", enum=["harder", "no_change", "unsure"]), note=STR("Anything else they said")), t_bike_feel),
    ("activate_bike_profile", "Make the checked profile the hub's bike - only after the check passed, the athlete "
     "felt the resistance change, and they agree. share=true returns a pre-filled GitHub link so they can share the "
     "profile and the next owner of this bike needs no assistant (ask them first).",
     S(share={"type": "boolean", "description": "Return a link to share the profile (athlete's choice)"}), t_bike_activate),
    ('get_training_calendar','Read 1–14 days of saved workout prescriptions, actual completions, reports, phase context and projected load readings. Stable session IDs change when prescriptions change. Does not save or modify training.',S(date=DATE,days=INT('Window length',1,14)),t_calendar),
    ('explain_training_reading','Investigate a reading: implemented formula, constants, source hash, profile inputs, baseline, recorded contributors, planned doses and assumptions. Unknown is not zero; these models are provisional.',S(date=DATE,metric=STR('Metric key: cardio_fatigue, cardio_conditioning, impact_fatigue, muscle_fatigue, run_mechanical, run_recent, swim_recovery, strength, mechanical or lift_<region>')),t_reading),
    ('get_adaptation_review','Read progression policy, recent decisions and unresolved localized symptoms before changing workloads. Does not change anything.',S(),t_adaptation),
    ('get_program','Read the saved macro program, phases and weekly placements. Does not change anything.',S(),t_program),
    ('preview_program','Preview a draft and optionally compare three starter workload scenarios and forecasts. Does not save or replace the active program.',S(fields=PROGRAM_FIELDS,detail_start=DATE,detail_days=INT('Focused detail window, at most one week',1,7)),t_program_preview),
    ('apply_program','Save the exact reviewed preview by draft_id, only with athlete approval. A changed athlete state or expired draft is rejected; retries are idempotent while the draft remains available. Read back get_program and get_training_calendar afterward.',S(draft_id=STR('ID returned by preview_program; expires after six hours')),t_program_apply),
    ('get_progress_evidence','Read measured training responses and evidence for improvement; modeled conditioning is not a guaranteed performance gain.',S(),t_progress_evidence),
    ("get_today", "Today's coaching picture: the rider's check-in and morning diagnostic (heart rate at 90 W / 120 W / "
     "60 s later, legs, breathing, sleep, gut call), the verdict with reasons, their normal (baseline), the plan "
     "already set, FTP, and the workout list. Start every coaching conversation here.", S(date=DATE), t_today),
    ("get_checkins", "Recent daily check-ins, diagnostics, verdicts and plans - the trend over days.",
     S(days=INT("How many days back (default 14)", 1, 120)), t_checkins),
    ("record_checkin", "Record or update a day's check-in for the rider (when they tell you in chat). Legs/breathing/sleep "
     "1-10 (legs: 1 fresh, 10 wrecked; feet = feet & bones, 1 fine, 10 very sore); hops = the single-leg hop "
     "test, pain-free hops on the worse leg (10 clears running after a block; a poor count past halfway through the "
     "plateau adds time); gut is go/easy/no; heart rates in bpm. Returns the verdict.",
     S(date=DATE, legs=INT("1-10", 1, 10), feet=INT("Feet & bones 1-10", 1, 10), shoulders=INT("Shoulders 1-10", 1, 10),
       hops=INT("Pain-free single-leg hops, worse leg (or give each leg)", 0, 100),
       hops_left=INT("Pain-free hops, left leg", 0, 100), hops_right=INT("Pain-free hops, right leg", 0, 100),
       journal=STR("Their journal entry, in their words - kept, not scored"), breathing=INT("1-10", 1, 10), sleep=INT("1-10", 1, 10),
       motivation=INT("1-10", 1, 10), hr90=INT("HR at the end of the 90 W stage", 40, 220),
       hr120=INT("HR at the end of the 120 W push", 40, 220), hr_after=INT("HR 60 s after the push", 30, 220),
       gut=STR("Their own call", enum=["go", "easy", "no"]), note=STR("Anything they said")), t_checkin),
    ("settle_journal_flag", "Settle a flag the journal raised (get_checkins shows each day's flags: bone, muscle, "
     "illness, better). ONLY on their say-so in chat - never decide it for them. confirm = it's real, count it (bone/muscle "
     "read as 6/10 on their slider that day; illness makes heart & lungs easy); dismiss = it's fine; reopen = undo.",
     S(date=DATE, id=STR("The flag id", enum=["bone", "muscle", "illness", "better"]),
       action=STR("What they said", enum=["confirm", "dismiss", "reopen"])), t_flag),
    ("set_plan", "Write today's plan onto the Coach page: the verdict (go/easy/rest), your coaching note to them "
     "(plain, specific: what to ride, how it should feel, when to stop), and optionally the workout to ride "
     "(workout_id from list_workouts or a create tool).",
     S(date=DATE, verdict=STR("go, easy or rest", enum=["go", "easy", "rest"]), note=STR("Your note to them"),
       workout_id=STR("Workout to ride today (empty string clears it)"),
       sport=STR("The day's marker on the Coach page's week: ride, swim, run, walk, gym, test, rest, other "
                 "(swims can't go on the COROS calendar - this is where they live)",
                 enum=["ride", "swim", "run", "walk", "gym", "test", "rest", "other", ""]),
       minutes=INT("The time goal for the day's session", 0, 600),
       sessions={"description": "Optional ordered sessions for this day, each {sport, minutes, name, steps: [set or interval descriptions], note, workout, swim_profile, swim_plan: {stroke_mix, work_mix, purpose, why} (swim sessions)}. Replaces the day's sessions; use two or more for a double-session day. Check recovery before scheduling.",
                 "type": "array", "items": {"type": "object"}},
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
    ("list_workouts", "His workouts with ids, notes, time/load/calories at his FTP, and their blocks.", S(), t_workouts),
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
     "acute:chronic ratio and provisional zone, this week's used load versus the current estimated capacity, "
     "and a weakest-link readiness verdict with what's limiting. These zones are planning heuristics, not "
     "validated injury-risk thresholds. Use this before set_plan.", S(), t_load),
    ("get_programming", "Programming a swim, bike or run session: the phase (counted back from the next race: base, "
     "build, peak, taper, recovery), the rider's load state for that sport (fresh, moderate, heavy but ready, not ready), "
     "the tier cap and the suggested tier (easy, moderate, hard, very hard), and the nearest templates from the "
     "research-backed library, filled with the rider's paces (critical swim speed, FTP, a recent 5K) - each with what "
     "it trains, what it doesn't, and sources. For swimming also the stroke mix for this block (four strokes out of "
     "100, from the race or the rider's dials), eight reusable swim_profiles with eligibility reasons, selected profile, "
     "main-set work ratios, equipment and weekly sequence context. Use swim_profile to preview another eligible module. "
     "Profiles are provisional coaching defaults; respect blocked choices. Record swim_profile and the returned swim_plan "
     "snapshot on planned swim sessions; adapt its why to the actual goal and projected load. When the sport isn't a good idea today it says why "
     "and offers mobility or another sport. Use it before writing any swim, bike or run session; adapt the template, "
     "don't invent one; keep the week's core sessions the same for 4-6 weeks and progress them. Lifting uses get_lifting.",
     S(sport=STR("swim, bike or run", enum=["swim", "bike", "run"]), date=DATE,
       swim_profile=STR("Swim profile to preview for this session; does not change saved settings", enum=["auto","balanced","event-technique","event-endurance","race-pace","speed-skills","maintenance","kick-emphasis","recovery"])), t_programming),
    ("set_swim_settings", "The rider's swim dials: the stroke mix (free, back, breast, fly out of 100), the drill "
     "share (15-30%), and whether the mix follows their race (follow_event, default true) or their dials.",
     S(mix={"type": "object", "description": "{free, back, breast, fly} - normalised to 100",
            "additionalProperties": {"type": "number", "minimum": 0}},
       drill_share=INT("Percent of the session that is drill-then-swim", 15, 30), follow_event={"type": "boolean"},
       profile_id=STR("Preferred reusable swim profile; auto chooses by phase, load, recent work and Sunday response", enum=["auto","balanced","event-technique","event-endurance","race-pace","speed-skills","maintenance","kick-emphasis","recovery"])), t_swim_settings),
    ("record_weekly_checkin", "The Sunday check-in (get_today shows 'weekly' when it's due - Sunday through Tuesday): a "
     "look back at the week, asking only about what it held. legs (after riding), feet and hops per leg (after running), "
     "shoulders (after swimming), each muscle group the week's lifting worked (lift: {region: 1-10}), and the week "
     "overall (1 easy, 10 too much), comparable-session progress (better, same, worse) by sport, and, for a running goal, "
     "whether the lower-leg pulling resolved, persisted or was not retested. During a mechanical plateau that report "
     "can hold a running session but does not move the accumulated-load curve. "
     "It's the calibration anchor: the running, swim and lifting fits "
     "weight it most.",
     S(sunday=STR("The Sunday (YYYY-MM-DD; default: the open one)"), legs=INT("1-10", 1, 10), feet=INT("1-10", 1, 10),
       hops_left=INT("Pain-free hops, left leg", 0, 100), hops_right=INT("Pain-free hops, right leg", 0, 100),
       shoulders=INT("1-10", 1, 10), week=INT("The week overall, 1 easy - 10 too much", 1, 10), note=STR("Their words"),
       lift={"type": "object", "description": "{region: 1-10}", "additionalProperties": {"type": "integer", "minimum": 1, "maximum": 10}},
       progress={"type": "object", "description": "Compared with similar work this week: {bike|run|swim|gym: better|same|worse}",
                 "additionalProperties": {"type": "string", "enum": ["better", "same", "worse"]}},
       run_response=STR("Lower-leg pulling since last week, without provoking a hop just to answer", enum=["resolved", "pulling", "not_tested"])),
     t_weekly),
    ("get_training_block", "Read the persistent four-to-six-week block, all scheduled sessions including two-a-days, "
     "cross-sport demanding-session count, planned versus completed minutes and Sunday advance/repeat/hold/reduce reviews. "
     "Set start=true to create a block from an already scheduled week; start_date may name a future Monday. Existing future plans are preserved. "
     "Forecast minutes are planning proxies, not measured tissue damage or injury predictions.",
     S(start={"type": "boolean"}, start_date=DATE, weeks=INT("Block duration when starting", 4, 6)), t_block),
    ("get_lifting", "Lifting and functional strength. Read before planning or scoring a gym session: the rider's RULES "
     "(never plan what a 'No ...' rule excludes; use favourites), the coaching GUIDANCE, the STEER (restorative or build, "
     "the suggested restorative share of the session and why, from the load the rider carries), sessions the rider built "
     "that are waiting for you to score (unscored_sessions), the exercise library, estimated one-rep maxes, recent "
     "sessions, the follow-up that's due, and each region's recovery block. Units: the rider's (lb or kg). All load "
     "numbers are estimates.", S(), t_lifting),
    ("plan_lift_session", "Put a scored gym session on a day's plan - one you designed from the rider's goals, rules and "
     "the steer (search the web for exercises when you can), or the rider's own draft that you're scoring. Each exercise: "
     "name, how (one line), kind, style (restorative/build), sets, reps OR seconds, weight (omit for bodyweight), tempo, "
     "per_side, and regions: how the whole movement's strain is shared, as percentages. Replaces the day's gym session "
     "(or the one at index); a session already checked off is recalculated. If the rider chose something other than the "
     "steer, pass their reason as override. Returns the plan and its evaluation.",
     S(date=DATE, name=STR("Session name, e.g. 'Rotational core'"), minutes=INT("Minutes (estimated if left out)", 5, 240),
       index=INT("Which of the day's sessions to replace (default: the first gym session, or add one)", 0, 4),
       note=STR("A short note for the rider"), override=STR("The rider's call when it departs from the steer, in their words"),
       lifts=LIFTS), t_lift_plan),
    ("evaluate_lift_session", "Score a lift session before it's done: points per exercise (intensity against the estimated "
     "one-rep max, or effort for throws/bands/holds, times tempo), shared across regions, the restorative share against "
     "the steer (fits_steer), against the rider's usual, and what each region is already carrying. Use it to judge and "
     "adjust; nothing is saved.", S(lifts=LIFTS), t_lift_eval),
    ("log_lift_session", "The check-off after a gym session, from what the rider tells you: one entry per planned lift, in "
     "order ({done, weight, reps, sets, why} - leave out what went as planned). If they lifted LESS weight than planned, "
     "ask why and pass why = too_heavy (the load stays as planned; the strength estimate comes down) or chose (the load "
     "is what they lifted). More weight = more load. rpe = session effort 1-10, wellness = how they feel after 1-10. "
     "These reports also tune the steer.",
     S(date=DATE, rpe=INT("Session effort 1-10", 1, 10), wellness=INT("How they feel after, 1-10", 1, 10),
       session_index=INT("Which of the day's gym sessions (default the first)", 0, 4),
       compare_last=STR("How it felt against their last lift session", enum=["easier", "same", "harder"]),
       override=STR("If they overrode the steer, their reason"),
       done={"type": "array", "description": "One per planned lift, in order", "items": {"type": "object", "properties": {
           "done": {"type": "boolean"}, "weight": {"type": "number"}, "reps": {"type": "integer"}, "sets": {"type": "integer"},
           "why": {"type": "string", "enum": ["too_heavy", "chose"]}}}}), t_lift_log),
    ("record_lift_followup", "Two to four days after a lift session (get_lifting shows when one is due): how each region "
     "it worked feels now, 1-10 (1 fine, 10 very sore), and how the session compared with the one before. This refits "
     "each region's recovery block and tunes the steer.",
     S(log_date=STR("The date of the lift session (YYYY-MM-DD)"), ratings={"type": "object", "description": "{region: 1-10}",
       "additionalProperties": {"type": "integer", "minimum": 1, "maximum": 10}},
       compare=STR("Against the session before", enum=["easier", "same", "harder"]), note=STR("Anything they said")), t_lift_follow),
    ("set_lift_rule", "Add one of the rider's lifting rules, in their words (\"No squats\", \"Favorite lift: incline "
     "dumbbell press\", \"Nothing heavy overhead - left shoulder\"), or remove one (remove = the rule's text, or the "
     "exercise it excludes). 'No ...' / 'never ...' rules are enforced: plans with those exercises are refused. Every AI "
     "the rider uses reads these rules.",
     S(text=STR("The rule"), note=STR("Why, if they said"), remove=STR("A rule to remove")), t_lift_rule),
    ("record_swim_activity", "Attach the rider's report to one imported pool swim: whether paddles or a pull buoy "
     "were used and how hard the swim felt. Use get_load for swim activity IDs, then record_checkin with a "
     "shoulders rating for how the shoulders feel. This updates provisional swim recovery blocks.",
     S(activity_id=STR("Imported swim activity ID"), paddles={"type": "boolean"},
       pull_buoy={"type": "boolean"}, swim_rpe=INT("Swim effort 1-10", 1, 10), fins={"type":"boolean"}, snorkel={"type":"boolean"}, fins_fraction={"type":"number","minimum":0,"maximum":1}, snorkel_fraction={"type":"number","minimum":0,"maximum":1}, fin_type=STR("Reported fin type"), kick_rpe=INT("Reported kick effort",1,10), fin_kick_factor={"type":"number","minimum":1,"maximum":2,"description":"Explicitly reviewed provisional fin factor; not measured force"}), t_swim_activity),
    ("import_activities", "Import watch activity files into the hub so every sport counts: pass the https download "
     "links for .fit files (e.g. from the COROS tool queryActivityFitFileDownloadUrls, one activity at a time).",
     S(urls={"type": "array", "items": {"type": "string"}, "description": "https links to .fit or .tcx files"}), t_import),
    ("set_capacity", "Tune a body system's usual week (engine, impact or muscle, in load points) from how the rider's "
     "body actually responded - e.g. they handled 416 engine points like easy work (raise engine), or their feet feel "
     "overdone at 79 impact (lower impact so 79 reads 'caution'). The zones, ratio and weekly budget then use it. "
     "Say why in the note. usual_week null clears it back to the model.",
     S(system=STR("engine, impact or muscle", enum=["engine", "impact", "muscle"]),
       usual_week={"type": ["number", "null"]}, note=STR("Why: what the rider reported")), t_capacity),
    ("record_steps", "Record the rider's daily step counts from the watch (e.g. from the COROS tool "
     "queryDailyHealthData): {\"YYYY-MM-DD\": steps}. Walking outside runs counts toward the feet's accumulated "
     "load above a daily allowance (free steps from conditioning - the bigger of running (the block) and walking woken up fine from - shrinking as the load rises; only steps over them count). Sync the last week "
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
       event_type=STR("What kind of race (sets the programming)", enum=["triathlon", "swim_meet", "run_race", "lift_meet", "other"]),
       distance=STR("Triathlon: sprint, olympic, 70.3, ironman; run race: km"),
       strokes={"type": "array", "description": "Swim meet events", "items": {"type": "object", "properties": {
           "stroke": {"type": "string", "enum": ["free", "back", "breast", "fly", "im"]}, "m": {"type": "integer"}}}},
       remove=STR("An event id to remove")), t_event),
    ("get_calibration", "The rider's capacities, each from tests and training with a confidence that fades after the "
     "last test: FTP (ramp test; 20-min bests between), heart rate at 90 W (morning diagnostic), big-gear 3 min (big-gear "
     "test; grit rides between), critical swim speed (400 m + 200 m time trial), and the running block (a benchmark run "
     "taken well can grow it, 10% a test). Plus which tests are coming due - put them on the calendar with schedule_test.",
     S(), t_calibration),
    ("schedule_test", "Put a test on the calendar (a plan item, not a button): ftp, diagnostic, big_gear, css, "
     "benchmark_run. Sets the day's marker, time, how-to note, and for big_gear the focus that runs it; the bike tests "
     "start from the Coach page's Ride it row. Keep the two days before an FTP or big-gear test easy.",
     S(test=STR("Which test", enum=["ftp", "diagnostic", "big_gear", "css", "benchmark_run", "run_calibration"]), date=DATE), t_schedule_test),
    ("schedule_test_week", "Plan a test week - the rider's way (from their high-school lifting program): it's also "
     "the recovery week. Easy, reduced sessions Mon-Wed so they peak on test day; swim CSS test Thu if due; morning "
     "diagnostic Fri then rest; TEST DAY Sat (FTP ramp test, or the big-gear test - one leg test a day); Sun off; "
     "training resumes Monday. Every 6 weeks; no monday = the next one due. Overwrites that week's plan.",
     S(monday=DATE), t_test_week),
    ("get_aerobic", "The aerobic engine ride by ride, from the watch's ride files (the bridge is its power meter, so "
     "power and heart rate together): efficiency factor (normalized watts per beat - rises with fitness), aerobic "
     "decoupling (watts per beat, first half vs second - under 5% stayed aerobic; judged only on 40+ min steady rides), "
     "and heart rate at the same 100-120 W (falls as the heart gets fitter), with trends. Import the watch's ride "
     "files first (import_activities).", S(), t_aerobic),
    ("get_insights", "The rest of what the watch recorded, cross-referenced. Signals and flags only - nothing here "
     "scores the rider or changes a load model; ask the rider each flag's question rather than judging. "
     "SWIM, per set: SWOLF (seconds + strokes per length), strokes, stroke rate, pace, and how the stroke changed - "
     "held / gradual (slow fade: ordinary fatigue) / sudden (a step between neighbouring lengths - even a small one is "
     "the more telling strain signal) - plus how far in it first broke down. swim.session_length reads that across "
     "swims: use it to decide how long swims should be. Heart-rate drop in the rests is a wrist reading in water: rough. "
     "RUN: laps and 5-minute splits of power, cadence, heart rate, pace, vertical oscillation/ratio, step length, "
     "ground contact; form drift is flagged only when the pace matched. "
     "RIDE: work in kJ, heart rate in the opening minutes against the usual at those watts, heart-rate recovery in the "
     "minute after hard efforts, and (from get_aerobic) drift; ride.work_vs_legs fits kJ to the next morning's legs, "
     "ride.leg_check asks whether cadence and heart rate show the running load, ride.climbs compares each climb to the "
     "last time up. ALL: pauses mid-workout (count, time) - many of them is a question, not a fault. "
     "Trends say when they have too little data.",
     S(sport=STR("Only this sport: swim, run, ride, gym or walk (optional)")), t_insights),
    ("get_transfer", "How much each sport carries over to the others for this rider, learned from their data: "
     "fitness carry-over (from -> to, relative to training the target sport itself; e.g. bike -> run 0.5 means an "
     "hour on the bike builds running fitness like half an hour of running) and how much each sport tires the legs "
     "relative to running. Starts at the literature (Millet 2002, Tanaka 1994, 2026 meta-analysis) and each value "
     "has an 80% interval and a status: prior / learning / learned. Only running builds feet and bones.", S(), t_transfer),
    ("record_test", "Record a result the hub can't see: a swim CSS test ({t400, t200} seconds - from the rider or the "
     "watch's laps), or any capacity by hand ({capacity: ftp|engine_hr90|legs_3min|swim_css|block, value, kind: "
     "test|manual|training, note}), or how a benchmark run felt ({benchmark: its date, rpe 1-10, pain: true if "
     "anything hurt}) - the benchmark is graded once the two mornings after are in. Swims are then scored against CSS. "
     "A running calibration stopped short of the hour: {calibration_run: its planned date, reason: time|tired|form|pain|interrupted} "
     "- ask the athlete why; interrupted voids the test (retry when 100% again). A run within two days of a planned "
     "calibration (none on the day itself): ask whether it was the test and record {calibration_run: planned date, "
     "was_test: true|false}.",
     S(t400={"type": "number"}, t200={"type": "number"}, benchmark=DATE, rpe=INT("Benchmark feel, 1 nothing - 10 a fight", 1, 10),
       pain={"type": "boolean", "description": "Anything hurt on the benchmark"},
       calibration_run=DATE, reason=STR("Why the running calibration stopped early", enum=["time", "tired", "form", "pain", "interrupted"]),
       was_test={"type": "boolean", "description": "Whether the run near a planned calibration day was the test"},
       capacity=STR("Capacity", enum=["ftp", "engine_hr90", "legs_3min", "swim_css", "block"]),
       value={"type": "number"}, kind=STR("test, manual or training", enum=["test", "manual", "training"]),
       date=DATE, note=STR("Where it came from")), t_record_test),
    ("start_workout", "Start a workout on the bike NOW in ERG (only when he asks, e.g. he's on the bike).",
     S(workout_id=STR("Workout id")), t_start),
    ("start_diagnostic", "Start the 6-minute morning diagnostic on the bike NOW (only when he asks and is on the bike).",
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
    if name in ("plan_lift_session", "evaluate_lift_session"):
        schema["required"] = ["lifts"]
    if name == "log_lift_session":
        schema["required"] = ["rpe", "wellness"]
    if name == "record_lift_followup":
        schema["required"] = ["log_date", "ratings"]
    if name in ("set_capacity",):
        schema["required"] = ["system", "usual_week"]
for name, _, schema, _ in TOOLS:
    if name=='preview_program':schema['required']=['fields']
    if name=='preview_coaching_change':schema['required']=['kind']
    if name=='apply_coaching_change':schema['required']=['draft_id','approved']
    if name=='apply_program':schema['required']=['draft_id']
    if name=='explain_training_reading':schema['required']=['metric']
    if name=='propose_bike_profile':schema['required']=['profile']
    if name=='record_bike_feel':schema['required']=['felt']
    if name=='run_bike_check':schema['required']=['athlete_ready']
    if name=='record_missed_session':schema['required']=['date','reason']
BY_NAME = {t[0]: t for t in TOOLS}
INSTRUCTIONS = ("Before placing or increasing running or lifting, read get_coaching_review and inspect the next two weeks, including openers after peak weeks. Repair forecast conflicts by shortening, spacing, replacing affected work or resting, then preview_coaching_change(kind=calendar) and compare the whole sequence. Preserve recovery/taper purpose and cross-sport overlap. Repeated matched prediction errors or a completed benchmark with delayed recovery may produce a capacity candidate; preview_coaching_change(kind=capacity) proposes an increase or decrease, not a guaranteed increase. Never schedule a benchmark inside a running hold, or use competition performance alone as proof of recovery tolerance. Apply only approved drafts using apply_coaching_change, then read back the outlook and saved calendar. Existing doses and forecasts remain recorded. Optional exercise tempo/range descriptions are estimates; do not invent force or work from machine-labelled pounds. " + "A bike, run, and swim training companion (built on a Merach S29 smart bike). If the athlete says "
                "'get my bike working' (or anything like it: their bike won't connect, the hub doesn't recognize "
                "it), call get_bike_setup_request first and follow its steps; never ask them to paste anything. "
                "Otherwise start with get_today "
                "and recent check-ins and activity, then set a concrete day plan. Keep an explicit planning checklist: goal/date, phase purpose, available time, sport priorities, current holds, calibration gaps and projected limit flags. Re-read relevant data before writing after a long discussion. Read get_program before changing the macro program; use preview_program to compare drafts and starter forecasts, and apply_program only for athlete-approved reviewed changes. Request detail_start and detail_days for focused preview evidence rather than repeating the full horizon. Explain assumptions separately from measured inputs, and retain unresolved limits in the recommendation. After applying, call get_program and get_today for the affected day to verify the saved program and session. Apply saves the exact draft_id returned by preview. Draft conflicts require a fresh preview and approval. Use get_training_calendar for saved prescriptions and projections, explain_training_reading to inspect formula/input evidence, and get_adaptation_review for unresolved symptoms and progression context. Never interpret a falling conditioning score alone as lost performance or an easy recovery session as permission to increase load.  You are the planner. The hub records, organizes and calculates the athlete's state (loads, readiness, check-ins, journal, completions, missed sessions and why); you turn that into the plan with them, so they only have to do the training. Decide when to build, hold, recover, peak and taper from the evidence, not the calendar alone: read get_today (it includes recent_weeks) and get_recent_weeks, then revise upcoming weeks with set_plan or preview_program/apply_program. Missed sessions are information - ask why if no reason is recorded (record_missed_session), and plan the next week around what actually happened rather than repeating what was missed. The hub's starter program is a draft skeleton to adapt: when something in it doesn't make sense for this athlete (a session too long for their level, a phase timed wrong for their event, a test they don't need, too little or too much of a sport for their goal), fix it with them and say why, rather than following it to the letter. Program shape: available weekly hours are the most a week may use, not the starting dose. Start around half of them (an optional test week lighter still), build through the foundation and development phases, and plan two DIFFERENT peaks: PEAK VOLUME weeks at the end of development (the most hours and sessions, 80-95% of available time, mostly aerobic with one quality session per sport) and PEAK PERFORMANCE weeks in event preparation (slightly less volume, race-specific intensity: race-pace intervals, and bricks for triathletes). Then taper (less volume, short race-pace openers) and a light race week (openers two days out, rest the day before). Every fourth building week consolidates. Progress RUNNING LOAD, not just hours: running is measured in blocks carried on run days, and 1.5 is the hard limit. get_coaching_review's outlook.running_progression gives the current target and status. While running is building, hold it in 0.8-1.5 and wave it week to week (light 0.8-1.0, middle 1.0-1.2, heavy 1.2-1.45) so the build can last; space the runs so each lands in the target rather than stacking small ones. When running isn't the focus, keep a third of the middle (about 0.4) for maintenance, short but with a little intensity (strides). The hub deloads running automatically on negative reports (tightness or pain in a run report, a run that felt too hard, legs or feet 6+ in the morning, a hop-test drop): the target becomes 0.4, then 0.1 if reports stay negative past a week, and after at least a week and two clean mornings running comes back in at 0.8. Reschedule runs to match with the athlete's approval; preview rejects runs over a deload target. Shortness of breath or a heart-rate issue is a whole-body warning: ease all training and suggest a doctor if it's unusual or persists. Two weeks of negative reports means stop running and get it assessed. CALIBRATING the block: the best measure is the running calibration (schedule_test run_calibration): up to 60 min in zone 2 on a day they feel their best, then 8 days without running; on day 9 the hub sets the block to that run's load x 0.8-1.5 by heart-rate drift, mornings and hop tests. The starter test week includes it; offer it again whenever the block is only an estimate. When a run is imported on or near a calibration day, check with the athlete that it was the test (record_test was_test), and if it was under an hour ask why they stopped (record_test reason); if it wasn't the test, put the calibration back on a day they feel 100%. Planned weekly running load may rise at most 15% over the most of the last three weeks, whatever the block says. The block adapts weekly by itself: a week whose in-band runs were absorbed more easily than predicted (mornings, pace per heartbeat, heart-rate drift, hop test, the run report) grows it 1-10%; a rough run shrinks it at once. So ask for run reports, and never push a run beyond the target to 'find out' the block. EMPHASIS PHASES for several goals: build one or two sports at a time in their bands while the others hold about a third for maintenance, then rotate, and use running's deload or maintenance weeks to build the bike or swim. Shared tissue competes: running and leg lifting share the legs (never peak both the same week), swimming and upper-body lifting share the shoulders (pair leg-focused strength with a swim build, or keep swimming to technique volume in an upper-body block); cycling and lifting coexist best. Swim and lifting loads clear in a few days, running in a week or more: plan around that. FREQUENCY comes from each sport's recovery, not fixed counts: swims may fall on consecutive days (hard swims about 48 h apart, the shoulder rating governs); runs go back to back only when the block's target allows it; rides can be daily with about 80% easy and hard rides about 48 h apart, never hard the day after a leg-lifting session or long run; lifting follows the athlete's split (ask which they prefer: full body needs 48 h between sessions, splits rotate focuses up to their days-in-a-row limit, and each region needs 48-72 h before it is trained hard again; training each region twice a week beats once, and splits work equally when volume is equal). A second session the same day should load different tissue (swim with a run, a ride with upper-body lifting); lift first when strength is the priority, or six hours apart. TRAINING RULES: get_coaching_review's outlook.training_rules lists any pattern in the next two weeks that breaks a rule (a hard ride or run the day after leg lifting, same-tissue doubles, full-body lifting under 48 h apart, a region trained hard two days running, two hard sessions of a sport within 48 h, more lifting days in a row than the split allows, a run in a calibration's eight-day watch) or needs care (back-to-back runs, legs or shoulders peaking in two sports the same week, more than eight weeks without a check week). A preview that introduces a breaking pattern can't be applied; cautions are yours to weigh with the athlete. CHECK WEEKS are a few deloads that retest everything (2 in a 12-week program, 3 in 16, 8 in a year with the last three close together before the peak); the block's automatic growth adds at most 30% between measurements. Each session's shape field (test, build, consolidation, peak_volume, peak_performance, taper, race) says which kind of week it belongs to; keep that shape when revising, and let check-ins, missed sessions and load flags hold the build back. A day can contain ordered ride and "
                "swim sessions with intervals or drills; consider both shared cardiovascular and sport-specific "
                "recovery before adding a second session. Running impact and swim recovery blocks are provisional "
                "planning estimates, not measured tissue damage or injury clearance. Reported pain and the athlete's "
                "own 'not today' outrank scores. After an imported swim, ask about shoulder response, paddles or buoy, "
                "and perceived effort, then record only what the athlete reports. get_insights holds what the watch "
                "saw beyond the loads (stroke breakdown, run form, ride recovery, pauses): ask its flags as questions, "
                "never as verdicts. Before writing a swim, bike or run session, read get_programming and adapt its "
                "nearest template. On Sundays (through Tuesday) ask the weekly check-in when get_today shows it due; "
                "then read its training-block review and compare plan, completion, symptoms and later performance "
                "before progressing. Gym sessions: read get_lifting first (the rider's rules, the coaching guidance, "
                "the steer, drafts waiting to be scored), plan or score with plan_lift_session, check off with "
                "log_lift_session (ask why when they lifted less), and ask the follow-up when it's due. If the rider "
                "says they have a plan, record it; if they ask you to consult, lead with the load numbers and the steer. "
                "Their call wins.")

PROMPTS = {"get-my-bike-working": ("Set up a bike the hub doesn't recognize yet",
                                   "Get my bike working. Read get_bike_setup_request and walk me through it.")}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None                                     # a notification (e.g. notifications/initialized)
    if method == "initialize":
        pv = (msg.get("params") or {}).get("protocolVersion") or "2025-06-18"
        return {"protocolVersion": pv, "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
                "serverInfo": {"name": "s-bike-hub", "version": VERSION}, "instructions": INSTRUCTIONS}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": s,
            "annotations": {"readOnlyHint": (n.startswith(('get_','list_','preview_','evaluate_','explain_')) and n not in ('get_training_block','get_today','get_skills','get_calibration','preview_program','preview_coaching_change')),
                            "openWorldHint": n in ('import_activities','plan_area_route','save_planned_route')}} for n, d, s, _ in TOOLS]}
    if method == "prompts/list":
        return {"prompts": [{"name": n, "description": d} for n, (d, _) in PROMPTS.items()]}
    if method == "prompts/get":
        name = (msg.get("params") or {}).get("name")
        if name not in PROMPTS:
            raise KeyError(f"unknown prompt {name}")
        d, text = PROMPTS[name]
        return {"description": d, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}
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
