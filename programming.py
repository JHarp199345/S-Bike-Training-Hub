"""programming.py - templates and guidance for swim, bike and run sessions (the rider's design, 2026-09-30).

The AI plans sessions in the chat; this gives it (and the app's add-a-session buttons) the playbook:

  PHASE        counted back from the next race on the calendar: base (more than 12 weeks out), build (12-6),
               peak (6-2), taper (the last two weeks), recovery (the week after). No race: base.
  LOAD STATE   per sport, from the load models: fresh, moderate, heavy (still ready), not ready.
  TIER         how hard a session may be: easy, moderate, hard, very hard. The load state caps it (fresh -> very
               hard, moderate -> hard, heavy -> moderate, not ready -> none); the phase suggests the key session's
               tier. Most sessions stay easy or moderate either way (roughly 80/20: Seiler 2010; Stoggl & Sperlich 2014).
  SWIM MIX     the share of each stroke (free, back, breast, fly) out of 100, set by the event being trained for
               (a triathlon: ~90% freestyle; a swim meet: its stroke leads) or by the rider's four linked dials; and
               the drill share, 15-30% by level (newer swimmers more), always as drill-then-swim (part-whole practice).
  TEMPLATES    a library per sport; the best fit for (tier, phase, focus) is picked - the nearest template, not a
               perfect match - and filled with the rider's own paces (critical swim speed, FTP, a recent 5K).
Lifting has its own periodized plan (lifting.py) and isn't covered here.
"""
import copy
import datetime as dt
import math

TIERS = ("easy", "moderate", "hard", "very_hard")
STATES = ("fresh", "moderate", "heavy", "not_ready")
CAP = {"fresh": "very_hard", "moderate": "hard", "heavy": "moderate", "not_ready": None}
PHASE_TIER = {"base": "moderate", "build": "hard", "peak": "very_hard", "taper": "moderate", "recovery": "easy"}
STROKES = ("free", "back", "breast", "fly")
STROKE_OFFSET = {"free": 0, "back": 8, "fly": 8, "breast": 18, "mix": 8}   # s/100 slower than freestyle CSS (rough)
STROKE_REPS = {"fly": 0.6, "breast": 0.9}                                  # butterfly is heavy: fewer reps
STROKE_NAME = {"free": "freestyle", "back": "backstroke", "breast": "breaststroke", "fly": "butterfly", "mix": "IM order"}
DRILL_BY_LEVEL = {"new": 30, "returning": 22, "regular": 15}
SWIM_VOLUME = {"new": 1300, "returning": 1900, "regular": 2700}     # metres a session, before the tier adjusts it
EVENT_TYPES = ("triathlon", "swim_meet", "run_race", "lift_meet", "other")
SOURCES = {
    "css": "Wakayoshi et al. 1992 (critical swimming speed); Ginn 1993",
    "polarized": "Seiler 2010; Stoggl & Sperlich 2014 (intensity distribution)",
    "partwhole": "Motor learning: part-whole practice - a drill transfers best when full-stroke swimming follows it",
    "swim": "Maglischo, Swimming Fastest (set types and energy systems)",
    "run": "Daniels, Daniels' Running Formula (paces from a recent race)",
    "bike": "Coggan power zones (% of FTP); Friel, The Triathlete's Training Bible (base first)",
    "taper": "Mujika & Padilla 2003 (tapering: cut volume, keep intensity)",
}


# ── the goal and the phase ──────────────────────────────────────────────────
def goal(d, today):
    """The next race on the calendar (or the one just done, within a week, for recovery)."""
    evs = [e for e in d.get("events", []) if e.get("kind") == "race"]
    t = today.isoformat()
    past = [e for e in evs if e["date"] < t and (today - dt.date.fromisoformat(e["date"])).days <= 7]
    ahead = sorted((e for e in evs if e["date"] >= t), key=lambda e: e["date"])
    return (ahead[0] if ahead else None), (past[-1] if past else None)


def phase(d, today):
    ahead, past = goal(d, today)
    import phaseblend
    saved=phaseblend.active(d,today)
    if saved:
        ph='peak' if saved.get('stage')=='specific' else saved['kind']
        days=(dt.date.fromisoformat(ahead['date'])-today).days if ahead else None
        return {'phase':ph,'event':ahead,'weeks_to_event':round(days/7,1) if days is not None else None,
                'days_to_event':days,'why':'Saved program: '+saved['label'],'program_phase':saved['id']}
    if past and (not ahead or (dt.date.fromisoformat(ahead["date"]) - today).days > 14):
        return {"phase": "recovery", "event": past, "weeks_to_event": None, "why": f"the week after {past['name']}"}
    if not ahead:
        return {"phase": "base", "event": None, "weeks_to_event": None, "why": "no race on the calendar: general base"}
    days = (dt.date.fromisoformat(ahead["date"]) - today).days
    w = days / 7
    ph = "taper" if days <= 14 else "peak" if w <= 6 else "build" if w <= 12 else "base"
    return {"phase": ph, "event": ahead, "weeks_to_event": round(w, 1), "days_to_event": days,
            "why": f"{days} days to {ahead['name']}"}


# ── the load state per sport ────────────────────────────────────────────────
def load_state(sport, readiness, headline):
    """fresh / moderate / heavy / not_ready from the verdicts and the mechanical headline."""
    mech = (headline or {}).get("mechanical") or {}
    r = readiness or {}
    if sport == "run":
        v, why = (r.get("running") or {}).get("verdict"), (r.get("running") or {}).get("why") or []
        extra = max(mech.get("remodeling_ratio") or 0, (mech.get("impact_ratio") or 0) - 0.5)
    elif sport == "swim":
        v, why = (r.get("swimming") or {}).get("verdict"), (r.get("swimming") or {}).get("why") or []
        extra = mech.get("swim_ratio") or 0
    else:
        v, why = r.get("verdict"), r.get("limited_by") or []
        extra = (mech.get("muscle_ratio") or 0) - 0.3
    if v == "rest":
        return "not_ready", why
    if v == "easy":
        return "heavy", why
    if extra >= 0.5:
        return "moderate", why or ["some load still carried"]
    return "fresh", why or ["everything well under its limit"]


def tier_for(state, ph):
    """(the cap, the suggestion). Heavy but ready: easy, with moderate allowed if the rider feels good."""
    cap = CAP[state]
    if cap is None:
        return None, None
    sug = "easy" if state == "heavy" else PHASE_TIER[ph]
    return cap, TIERS[min(TIERS.index(cap), TIERS.index(sug))]


# ── the swim mix ────────────────────────────────────────────────────────────
def _norm(mix):
    mix = {s: max(0.0, float(mix.get(s, 0))) for s in STROKES}
    tot = sum(mix.values()) or 1
    out = {s: round(100 * v / tot) for s, v in mix.items()}
    out["free"] += 100 - sum(out.values())                      # rounding lands on freestyle
    return out


def event_mix(ev, ph):
    """The stroke mix a race calls for."""
    det = (ev or {}).get("detail") or {}
    kind = det.get("type") or {"tri": "triathlon", "swim": "swim_meet", "run": "run_race"}.get((ev or {}).get("sport"))
    if kind == "swim_meet" and det.get("strokes"):
        strokes = [x.get("stroke") for x in det["strokes"] if x.get("stroke") in STROKES + ("im",)]
        if "im" in strokes or len(set(strokes)) >= 3:
            return {"free": 25, "back": 25, "breast": 25, "fly": 25}, "individual medley: all four strokes evenly"
        lead = max(set(strokes), key=strokes.count) if strokes else "free"
        share = {"base": 40, "build": 50, "peak": 60, "taper": 55, "recovery": 30}[ph]
        if lead == "free":
            return _norm({"free": 70, "back": 10, "breast": 10, "fly": 10}), "freestyle events: freestyle leads, the others maintained"
        rest = 100 - share
        others = [s for s in STROKES if s not in (lead, "free")]
        mix = {lead: share, "free": rest * 0.4}                   # freestyle keeps the biggest maintenance share
        for s in others:
            mix[s] = rest * 0.6 / len(others)
        return _norm(mix), f"{STROKE_NAME[lead]} events: {STROKE_NAME[lead]} at {share}% this phase, the others maintained"
    return {"free": 90, "back": 4, "breast": 3, "fly": 3}, "triathlon: freestyle is the race stroke; a little of the others for balance and shoulder health"


def swim_settings(d, profile, ph_info):
    """The mix and drill share in force: the rider's dials if set to override, otherwise the event's."""
    s = (d.get("programming") or {}).get("swim") or {}
    level = ((profile or {}).get("experience") or {}).get("swim") or "returning"
    drill = int(s.get("drill_share") or DRILL_BY_LEVEL.get(level, 22))
    if s.get("mix") and not s.get("follow_event", True):
        return {"mix": _norm(s["mix"]), "drill_share": drill, "source": "your dials", "why": "set on the Rules tab", "level": level}
    ev = ph_info.get("event") or {}
    mix, why = event_mix(ev, ph_info["phase"])
    swim_race = (ev.get("detail") or {}).get("type") == "swim_meet"
    tri_race = (ev.get("detail") or {}).get("type") == "triathlon" or ev.get("sport") == "tri"
    return {"mix": mix, "drill_share": drill, "source": "your swim meet" if swim_race else "your triathlon" if tri_race else "the triathlon default",
            "why": why, "level": level}


def set_swim(d, mix=None, drill_share=None, follow_event=None, profile_id=None):
    if profile_id is not None and profile_id not in ("auto",) + SWIM_PROFILE_IDS:
        raise ValueError("Unknown swim profile")
    s = d.setdefault("programming", {}).setdefault("swim", {})
    if profile_id is not None:
        s["profile_id"] = profile_id
    if mix is not None:
        s["mix"] = _norm(mix)
    if drill_share is not None:
        s["drill_share"] = max(15, min(30, int(drill_share)))
    if follow_event is not None:
        s["follow_event"] = bool(follow_event)
    return s


# Profiles are coaching defaults, not research-established optimal percentages.
# work_mix is a share of MAIN-SET metres; drill_swim includes both halves of each rep.
SWIM_PROFILES = [
    {"id":"balanced", "name":"Balanced aerobic", "purpose":"Build general endurance while maintaining stroke variety",
     "phases":["base","build"], "tier":"moderate", "mix_mode":"baseline", "drill_share":22,
     "work_mix":{"drill_swim":22,"kick":10,"pull":0,"swim":68}, "volume_scale":1.0,
     "templates":["swim-aerobic-300s","swim-pyramid","swim-im-aerobic"]},
    {"id":"event-technique", "name":"Event technique", "purpose":"Practice the event stroke with drill-then-swim transfer",
     "phases":["base","build","peak","taper","recovery"], "tier":"easy", "mix_mode":"event", "drill_share":30,
     "work_mix":{"drill_swim":30,"kick":10,"pull":0,"swim":60}, "volume_scale":.8,
     "templates":["swim-drill-ladder","swim-tech-easy"]},
    {"id":"event-endurance", "name":"Event endurance", "purpose":"Hold event-stroke form over repeatable aerobic distances",
     "phases":["base","build"], "tier":"moderate", "mix_mode":"event", "drill_share":20,
     "work_mix":{"drill_swim":20,"kick":10,"pull":0,"swim":70}, "volume_scale":1.0,
     "templates":["swim-focus-aerobic","swim-tri-steady","swim-aerobic-300s"]},
    {"id":"race-pace", "name":"Race pace", "purpose":"Practice sustained event effort with repeatable pace and form",
     "phases":["build","peak"], "tier":"hard", "mix_mode":"event", "drill_share":15,
     "work_mix":{"drill_swim":15,"kick":0,"pull":0,"swim":85}, "volume_scale":.9,
     "templates":["swim-focus-threshold","swim-css-100s","swim-broken-400","swim-im-threshold"]},
    {"id":"speed-skills", "name":"Speed and skills", "purpose":"Short fast repetitions with full rest; turns and starts where appropriate",
     "phases":["build","peak"], "tier":"very_hard", "mix_mode":"event", "drill_share":20,
     "work_mix":{"drill_swim":20,"kick":5,"pull":0,"swim":75}, "volume_scale":.75,
     "templates":["swim-focus-speed","swim-vo2"]},
    {"id":"maintenance", "name":"Other-stroke maintenance", "purpose":"Keep non-event strokes practiced at easy effort",
     "phases":["base","build","peak","taper"], "tier":"easy", "mix_mode":"maintenance", "drill_share":25,
     "work_mix":{"drill_swim":25,"kick":10,"pull":0,"swim":65}, "volume_scale":.8,
     "templates":["swim-stroke-maint"]},
    {"id":"kick-emphasis", "name":"Kick emphasis", "purpose":"Develop kicking while reducing arm propulsion; legs must be ready",
     "phases":["base","build","peak","taper","recovery"], "tier":"easy", "mix_mode":"gentle", "drill_share":15,
     "work_mix":{"drill_swim":15,"kick":65,"pull":0,"swim":20}, "volume_scale":.65,
     "templates":["swim-kick-easy"]},
    {"id":"recovery", "name":"Easy recovery", "purpose":"Short comfortable swimming with lower total demand",
     "phases":["base","build","peak","taper","recovery"], "tier":"easy", "mix_mode":"gentle", "drill_share":15,
     "work_mix":{"drill_swim":15,"kick":10,"pull":0,"swim":75}, "volume_scale":.6,
     "templates":["swim-recovery","swim-tech-easy"]},
]
SWIM_PROFILE_IDS = tuple(p["id"] for p in SWIM_PROFILES)
SWIM_PROFILE_SOURCES = [
    {"title":"Swimming periodization systematic review", "url":"https://pubmed.ncbi.nlm.nih.gov/33952709/"},
    {"title":"Acute swim intensity and shoulder response", "url":"https://pubmed.ncbi.nlm.nih.gov/33176360/"},
    {"title":"Cumulative weekly swim load and wellness", "url":"https://pubmed.ncbi.nlm.nih.gov/34956735/"},
    {"title":"Tapering meta-analysis", "url":"https://pubmed.ncbi.nlm.nih.gov/17762369/"},
    {"title":"Training tasks aggravating painful swimmer shoulders", "url":"https://pubmed.ncbi.nlm.nih.gov/8427371/"},
]


def swim_profile_options(d, settings, ph, state, today, readiness=None, headline=None, activities=None):
    """Eligible modules plus auditable ordering context. Does not schedule or infer recovery from silence."""
    r, mech = readiness or {}, (headline or {}).get("mechanical") or {}
    legs_loaded = (mech.get("muscle_ratio", 0) >= 1 or mech.get("remodeling_ratio", 0) >= 1
                   or ((r.get("systems") or {}).get("muscle") or {}).get("level") in ("easy", "rest"))
    lo = (today - dt.timedelta(days=3)).isoformat()
    recent = [a for a in activities or [] if a.get("sport") == "swim" and lo <= a.get("date", "") <= today.isoformat()]
    planned = [{"date":date, "profile":s.get("swim_profile"), "name":s.get("name")}
               for date,p in (d.get("plans") or {}).items() if lo <= date <= today.isoformat()
               for s in p.get("sessions", []) if s.get("sport") == "swim"]
    demanding = any(s["profile"] in ("race-pace","speed-skills") for s in planned)
    demanding |= any(a.get("engine", 0) >= 60 for a in recent)  # provisional context flag, not a damage threshold
    reports = [(day,w) for day,w in d.get("weekly", {}).items()
               if (today-dt.timedelta(days=10)).isoformat() <= day <= today.isoformat()]
    latest = max(reports, default=(None,{}), key=lambda v:v[0] or "")[1]
    worsening = (latest.get("progress") or {}).get("swim") == "worse"
    cap = CAP[state]
    options = []
    for original in SWIM_PROFILES:
        p = copy.deepcopy(original); reasons=[]
        if ph["phase"] not in p["phases"]: reasons.append("Outside this profile's training phases")
        if cap is None or TIERS.index(p["tier"]) > TIERS.index(cap): reasons.append("Above today's swim load cap")
        if state == "heavy" and p["tier"] != "easy": reasons.append("Loaded swimming calls for easy work")
        if p["id"] == "kick-emphasis" and legs_loaded: reasons.append("Leg load rules out kick emphasis")
        if p["tier"] in ("hard","very_hard") and (demanding or worsening):
            reasons.append("Recent demanding work or worsening weekly response: choose easier work and review")
        p["eligible"] = not reasons; p["reasons"] = reasons
        mode=p["mix_mode"]
        event, _ = event_mix(ph.get("event"), ph["phase"])
        mix = dict(settings["mix"] if mode == "baseline" or settings["source"] == "your dials" else event)
        if mode == "gentle": mix={"free":70,"back":20,"breast":10,"fly":0}
        if mode == "maintenance":
            lead=max(event,key=event.get); mix={k:(10 if k==lead else 30) for k in STROKES}
        p["mix"]=_norm(mix)
        p["equipment"]={"paddles":False,"pull_buoy":False,"kick_position":"arms at sides or board across chest"}
        options.append(p)
    sequence={"base":["balanced","event-technique","event-endurance","maintenance"],
              "build":["event-technique","race-pace","recovery","event-endurance","maintenance"],
              "peak":["event-technique","race-pace","recovery","speed-skills","maintenance"],
              "taper":["event-technique","maintenance","recovery"],
              "recovery":["recovery","event-technique"]}[ph["phase"]]
    eligible={p["id"] for p in options if p["eligible"]}
    return options, {"sequence":[x for x in sequence if x in eligible], "recent_swims":len(recent),
                     "recent_planned_profiles":planned, "recent_demanding":demanding, "weekly_worsening":worsening,
                     "legs_loaded":legs_loaded,
                     "rule":"Sequence is a planning menu, not consecutive days. Recheck actual load and symptoms before each session; Sunday review adjusts the next week."}


# ── the templates ───────────────────────────────────────────────────────────
# swim segments: (kind, reps, metres, rest s, pace, stroke). pace: easy | css+N | css | css-N | fast | max.
# stroke: free | focus (the mix's leading stroke) | mix (IM order) | choice
SWIM = [
    {"id":"swim-kick-easy", "name":"Easy kick and body position", "tier":"easy", "focus":"free",
     "phases":["base","build","peak","taper","recovery"], "purpose":"Controlled kicking with reduced arm propulsion",
     "not_for":"Loaded legs or a shoulder position that causes discomfort",
     "segments":[("warmup",1,100,0,"easy","free"),("drill_swim",4,25,20,"easy","free"),
                 ("kick",8,50,25,"easy","free"),("aerobic",2,50,20,"easy","free"),("cooldown",1,100,0,"easy","free")]},
    # easy
    {"id": "swim-tech-easy", "name": "Technique and easy aerobic", "tier": "easy", "focus": "free", "phases": ["base", "recovery", "taper"],
     "purpose": "Stroke length and body position, drill then swim, with easy aerobic swimming", "not_for": "Fitness gains or speed",
     "segments": [("warmup", 1, 300, 0, "easy", "choice"), ("drill_swim", 8, 50, 15, "easy", "free"), ("aerobic", 4, 150, 20, "css+12", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-drill-ladder", "name": "Drill-swim ladder", "tier": "easy", "focus": "stroke", "phases": ["base", "build", "recovery"],
     "purpose": "Grooves the focus stroke: each drill followed straight away by full stroke", "not_for": "Endurance",
     "segments": [("warmup", 1, 300, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("drill_swim", 4, 75, 20, "easy", "focus"), ("drill_swim", 4, 100, 20, "css+12", "focus"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-recovery", "name": "Recovery swim", "tier": "easy", "focus": "mix", "phases": ["recovery", "taper", "base"],
     "purpose": "Blood flow and feel for the water after hard days", "not_for": "Anything but recovery",
     "segments": [("warmup", 1, 200, 0, "easy", "choice"), ("aerobic", 4, 100, 20, "easy", "mix"), ("kick", 4, 50, 20, "easy", "choice"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-easy-pull", "name": "Easy aerobic with pull", "tier": "easy", "focus": "free", "phases": ["base"],
     "purpose": "Easy volume and a feel for the catch (buoy, no paddles)", "not_for": "Kick or speed",
     "segments": [("warmup", 1, 300, 0, "easy", "free"), ("aerobic", 3, 200, 20, "css+12", "free"), ("pull", 4, 100, 20, "css+10", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-ow-skills", "name": "Open-water skills (in the pool)", "tier": "easy", "focus": "free", "phases": ["build", "peak"], "tri": True,
     "purpose": "Sighting every 6-9 strokes, bilateral breathing, turning without the wall", "not_for": "Fitness",
     "segments": [("warmup", 1, 300, 0, "easy", "free"), ("drill_swim", 6, 50, 15, "easy", "free"), ("aerobic", 6, 100, 15, "css+10", "free"), ("cooldown", 1, 200, 0, "easy", "free")]},
    {"id": "swim-stroke-maint", "name": "Stroke maintenance", "tier": "easy", "focus": "mix", "phases": ["base", "build", "peak"],
     "purpose": "Keeps the non-focus strokes in the body at low cost", "not_for": "Race fitness",
     "segments": [("warmup", 1, 300, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "mix"), ("aerobic", 8, 50, 15, "css+10", "mix"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    # moderate
    {"id": "swim-aerobic-300s", "name": "Aerobic endurance 300s", "tier": "moderate", "focus": "free", "phases": ["base", "build"],
     "purpose": "Aerobic engine: holding form over distance at a steady pace", "not_for": "Top speed",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "free"), ("aerobic", 4, 300, 20, "css+8", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-pyramid", "name": "Aerobic pyramid", "tier": "moderate", "focus": "free", "phases": ["base", "build"],
     "purpose": "Pacing and aerobic endurance across changing distances", "not_for": "Speed",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "free"), ("aerobic", 1, 100, 15, "css+8", "free"), ("aerobic", 1, 200, 20, "css+8", "free"), ("aerobic", 1, 300, 20, "css+8", "free"), ("aerobic", 1, 200, 20, "css+8", "free"), ("aerobic", 1, 100, 15, "css+6", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-focus-aerobic", "name": "Focus-stroke aerobic", "tier": "moderate", "focus": "stroke", "phases": ["base", "build"],
     "purpose": "Aerobic fitness in the event stroke, form first", "not_for": "Speed",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("aerobic", 8, 100, 20, "css+10", "focus"), ("aerobic", 4, 100, 15, "css+8", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-im-aerobic", "name": "IM aerobic", "tier": "moderate", "focus": "mix", "phases": ["base", "build"],
     "purpose": "All four strokes at an aerobic effort; transitions between strokes", "not_for": "Single-stroke speed",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "mix"), ("aerobic", 6, 100, 20, "css+10", "mix"), ("aerobic", 2, 200, 20, "css+10", "mix"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-tri-steady", "name": "Triathlon steady 400s", "tier": "moderate", "focus": "free", "phases": ["build", "peak"], "tri": True,
     "purpose": "Race-distance rhythm with sighting, just under race effort", "not_for": "Speed",
     "segments": [("warmup", 1, 400, 0, "easy", "free"), ("drill_swim", 4, 50, 15, "easy", "free"), ("aerobic", 3, 400, 30, "css+5", "free"), ("cooldown", 1, 200, 0, "easy", "free")]},
    {"id": "swim-kick-pull", "name": "Kick and pull strength", "tier": "moderate", "focus": "free", "phases": ["base"],
     "purpose": "Leg and pulling strength at an aerobic effort (no paddles while shoulders are loaded)", "not_for": "Whole-stroke rhythm",
     "segments": [("warmup", 1, 300, 0, "easy", "choice"), ("kick", 6, 50, 20, "css+15", "choice"), ("pull", 6, 100, 20, "css+8", "free"), ("aerobic", 2, 200, 20, "css+8", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-taper-sharp", "name": "Taper sharpener", "tier": "moderate", "focus": "stroke", "phases": ["taper"],
     "purpose": "Short, fast, fully rested reps: keeps speed while volume drops", "not_for": "Fitness gains",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("speed", 6, 50, 60, "fast", "focus"), ("aerobic", 4, 100, 20, "css+10", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    # hard
    {"id": "swim-css-100s", "name": "CSS 100s", "tier": "hard", "focus": "free", "phases": ["build", "base", "peak"],
     "purpose": "Threshold: the pace you can hold, the main engine for distance and triathlon", "not_for": "Top speed",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "free"), ("threshold", 10, 100, 15, "css", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-css-200s", "name": "CSS 200s", "tier": "hard", "focus": "free", "phases": ["build", "peak"],
     "purpose": "Threshold with longer reps: pace control under fatigue", "not_for": "Speed",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "free"), ("threshold", 5, 200, 20, "css+2", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-focus-threshold", "name": "Focus-stroke threshold 50s", "tier": "hard", "focus": "stroke", "phases": ["build", "peak"],
     "purpose": "Threshold fitness in the event stroke in short reps, so form holds", "not_for": "Endurance volume",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("threshold", 12, 50, 15, "css", "focus"), ("aerobic", 4, 100, 20, "css+10", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-broken-400", "name": "Broken race-pace 400s", "tier": "hard", "focus": "free", "phases": ["peak", "build"], "tri": True,
     "purpose": "Race pace with tiny rests: the feel of the race", "not_for": "Recovery",
     "segments": [("warmup", 1, 400, 0, "easy", "free"), ("drill_swim", 4, 50, 15, "easy", "free"), ("threshold", 12, 100, 10, "css-1", "free"), ("cooldown", 1, 200, 0, "easy", "free")]},
    {"id": "swim-im-threshold", "name": "IM threshold", "tier": "hard", "focus": "mix", "phases": ["build", "peak"],
     "purpose": "Threshold across all four strokes", "not_for": "Single-stroke speed",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "mix"), ("threshold", 8, 100, 20, "css", "mix"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-descend", "name": "Descending 50s", "tier": "hard", "focus": "stroke", "phases": ["build", "peak"],
     "purpose": "Pace awareness: each 50 of four faster than the last", "not_for": "Endurance",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("threshold", 16, 50, 20, "css-2", "focus"), ("aerobic", 2, 150, 20, "css+10", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    # very hard
    {"id": "swim-vo2", "name": "VO2 50s and max 25s", "tier": "very_hard", "focus": "free", "phases": ["peak", "build"],
     "purpose": "Top-end aerobic power and speed", "not_for": "Anyone carrying load; more than once a week",
     "segments": [("warmup", 1, 500, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "free"), ("speed", 12, 50, 30, "fast", "free"), ("speed", 8, 25, 45, "max", "free"), ("cooldown", 1, 300, 0, "easy", "choice")]},
    {"id": "swim-focus-speed", "name": "Focus-stroke speed 25s", "tier": "very_hard", "focus": "stroke", "phases": ["peak"],
     "purpose": "Race speed in the event stroke with full rest", "not_for": "Endurance",
     "segments": [("warmup", 1, 500, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("speed", 16, 25, 40, "max", "focus"), ("aerobic", 4, 100, 20, "css+10", "free"), ("cooldown", 1, 300, 0, "easy", "choice")]},
    {"id": "swim-race-sim", "name": "Event simulation, broken", "tier": "very_hard", "focus": "stroke", "phases": ["peak"],
     "purpose": "The race distance at race pace, broken into pieces with short rests", "not_for": "Base fitness",
     "segments": [("warmup", 1, 500, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("race", 4, 50, 10, "fast", "focus"), ("aerobic", 1, 200, 60, "easy", "free"), ("race", 4, 50, 10, "fast", "focus"), ("cooldown", 1, 300, 0, "easy", "choice")]},
    {"id": "swim-over-css", "name": "Over-CSS ladder", "tier": "very_hard", "focus": "free", "phases": ["peak", "build"],
     "purpose": "Above-threshold tolerance: 200-150-100-50, each faster", "not_for": "Recovery days",
     "segments": [("warmup", 1, 400, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "free"), ("threshold", 1, 200, 20, "css-1", "free"), ("threshold", 1, 150, 20, "css-2", "free"), ("threshold", 1, 100, 20, "css-3", "free"), ("speed", 1, 50, 60, "fast", "free"), ("aerobic", 2, 200, 30, "css+10", "free"), ("cooldown", 1, 200, 0, "easy", "choice")]},
    {"id": "swim-lactate", "name": "Race-pace 100s, long rest", "tier": "very_hard", "focus": "stroke", "phases": ["peak"],
     "purpose": "Holding race pace when it hurts", "not_for": "More than once a week",
     "segments": [("warmup", 1, 500, 0, "easy", "choice"), ("drill_swim", 4, 50, 15, "easy", "focus"), ("race", 6, 100, 60, "fast", "focus"), ("cooldown", 1, 400, 0, "easy", "choice")]},
    {"id": "swim-tri-sim", "name": "Triathlon swim simulation", "tier": "very_hard", "focus": "free", "phases": ["peak"], "tri": True,
     "purpose": "Race distance continuous with a hard start and surges, sighting throughout", "not_for": "Base",
     "segments": [("warmup", 1, 400, 0, "easy", "free"), ("speed", 4, 50, 20, "fast", "free"), ("threshold", 1, 1000, 0, "css+2", "free"), ("cooldown", 1, 200, 0, "easy", "free")]},
]
# run steps: (label, minutes, pace). pace: easy | steady | threshold | interval | rep | walk
RUN = [
    {"id": "run-walk", "name": "Easy run-walk", "tier": "easy", "phases": ["base", "recovery", "build", "peak", "taper"],
     "purpose": "Easy running with walk breaks: builds tolerance while impact stays low", "not_for": "Speed",
     "steps": [("walk warm-up", 5, "walk"), ("run-walk: 1 min easy run, 1 min walk (new) / 3 run, 1 walk (returning) / continuous (regular)", 20, "easy"), ("walk cool-down", 5, "walk")]},
    {"id": "run-easy-strides", "name": "Easy run and strides", "tier": "easy", "phases": ["base", "build", "peak", "taper"],
     "purpose": "Aerobic base plus running economy from strides, with little impact", "not_for": "Threshold",
     "steps": [("easy run", 25, "easy"), ("4-6 strides: 20 s quick and relaxed, walk back", 5, "rep"), ("walk", 5, "walk")]},
    {"id": "run-recovery", "name": "Recovery jog", "tier": "easy", "phases": ["recovery", "taper", "base"],
     "purpose": "Blood flow on a day after hard work", "not_for": "Fitness gains",
     "steps": [("very easy jog, flat", 20, "easy"), ("walk", 5, "walk")]},
    {"id": "run-steady", "name": "Steady aerobic", "tier": "moderate", "phases": ["base", "build"],
     "purpose": "The aerobic engine at a comfortable but purposeful pace", "not_for": "Speed",
     "steps": [("easy", 10, "easy"), ("steady", 25, "steady"), ("easy", 5, "easy")]},
    {"id": "run-progression", "name": "Progression run", "tier": "moderate", "phases": ["build", "base"],
     "purpose": "Finishing faster than you start, without a hard effort", "not_for": "Recovery",
     "steps": [("easy", 15, "easy"), ("steady", 10, "steady"), ("comfortably hard, just under threshold", 5, "threshold"), ("easy", 5, "easy")]},
    {"id": "run-long", "name": "Long run", "tier": "moderate", "phases": ["base", "build"],
     "purpose": "Endurance: the longest run of the week, easy the whole way (no more than about a quarter of the week's running)", "not_for": "Speed",
     "steps": [("easy, flat, walk breaks allowed", 50, "easy")]},
    {"id": "run-hill-strides", "name": "Short hill strides", "tier": "moderate", "phases": ["base", "build"],
     "purpose": "Strength and form uphill; walk down (downhill is extra impact)", "not_for": "Heavy running load",
     "steps": [("easy", 15, "easy"), ("6-8 x 10-15 s uphill, strong, walk down", 8, "rep"), ("easy", 10, "easy")]},
    {"id": "run-cruise", "name": "Cruise intervals", "tier": "hard", "phases": ["build", "peak"],
     "purpose": "Threshold: the pace you can hold for about an hour, in pieces", "not_for": "Anyone not cleared to run hard",
     "steps": [("easy", 15, "easy"), ("3 x 8 min threshold, 2 min jog between", 30, "threshold"), ("easy", 10, "easy")]},
    {"id": "run-tempo", "name": "Tempo run", "tier": "hard", "phases": ["build", "peak"],
     "purpose": "Sustained threshold running", "not_for": "Base or loaded weeks",
     "steps": [("easy", 15, "easy"), ("threshold", 20, "threshold"), ("easy", 10, "easy")]},
    {"id": "run-fartlek", "name": "Fartlek", "tier": "hard", "phases": ["base", "build"],
     "purpose": "Unstructured speed: 8 x 1 min hard, 1-2 min easy", "not_for": "Recovery",
     "steps": [("easy", 15, "easy"), ("8 x 1 min hard / 1-2 min easy", 20, "interval"), ("easy", 10, "easy")]},
    {"id": "run-vo2", "name": "VO2max intervals", "tier": "very_hard", "phases": ["peak", "build"],
     "purpose": "Top aerobic power: 5 x 3 min at interval pace, 3 min jog", "not_for": "Regular runners only; never on a loaded week",
     "steps": [("easy", 15, "easy"), ("5 x 3 min interval pace, 3 min jog", 30, "interval"), ("easy", 10, "easy")]},
    {"id": "run-race-pace", "name": "Race-pace reps", "tier": "very_hard", "phases": ["peak"],
     "purpose": "The goal race pace, rehearsed in pieces", "not_for": "Base",
     "steps": [("easy", 15, "easy"), ("6 x 1 km at race pace, 90 s jog", 30, "interval"), ("easy", 10, "easy")]},
]
MOBILITY = [("leg swings, front-back and side-side, 10 each leg", 3), ("walking lunges with a reach, 10 each side", 3),
            ("hip circles and deep squat hold", 3), ("ankle rocks and calf stretch against a wall", 3),
            ("cat-cow, thoracic rotations, world's greatest stretch", 4), ("easy walk", 5)]
# bike steps: (label, minutes, % of FTP low, high, rpm)
BIKE = [
    {"id": "bike-recovery", "name": "Recovery spin", "tier": "easy", "phases": ["recovery", "taper", "base", "build", "peak"],
     "purpose": "Blood flow, light legs", "not_for": "Fitness gains", "steps": [("recovery spin", 35, 45, 55, "85-95")]},
    {"id": "bike-endurance", "name": "Endurance ride", "tier": "easy", "phases": ["base", "build", "peak", "recovery"],
     "purpose": "The aerobic base (zone 2): most of your riding", "not_for": "Speed",
     "steps": [("warm-up", 10, 50, 60, "85-95"), ("endurance", 45, 60, 70, "85-95"), ("cool-down", 5, 45, 55, "85-95")]},
    {"id": "bike-cadence", "name": "Endurance with cadence drills", "tier": "easy", "phases": ["base"],
     "purpose": "Pedalling skill: 6 x 1 min spin-ups inside an endurance ride", "not_for": "Strength",
     "steps": [("warm-up", 10, 50, 60, "85-95"), ("endurance with 6 x 1 min at 100-110 rpm", 35, 60, 70, "100-110"), ("cool-down", 5, 45, 55, "90")]},
    {"id": "bike-tempo", "name": "Tempo", "tier": "moderate", "phases": ["base", "build"],
     "purpose": "Muscular endurance: 3 x 12 min steady-hard", "not_for": "Recovery",
     "steps": [("warm-up", 10, 50, 65, "90"), ("3 x 12 min tempo, 4 min easy", 48, 76, 87, "85-95"), ("cool-down", 7, 45, 55, "90")]},
    {"id": "bike-sweet-spot", "name": "Sweet spot", "tier": "moderate", "phases": ["base", "build"],
     "purpose": "The most fitness per minute below threshold: 3 x 12 min", "not_for": "Loaded legs",
     "steps": [("warm-up", 10, 50, 65, "90"), ("3 x 12 min sweet spot, 4 min easy", 48, 88, 93, "85-95"), ("cool-down", 7, 45, 55, "90")]},
    {"id": "bike-big-gear", "name": "Big-gear force", "tier": "moderate", "phases": ["base", "build"],
     "purpose": "Leg strength on the bike: 6 x 3 min at 55-65 rpm (counts as leg-muscle load)", "not_for": "Heavy leg load",
     "steps": [("warm-up", 10, 50, 65, "90"), ("6 x 3 min big gear, 3 min easy", 36, 75, 85, "55-65"), ("cool-down", 7, 45, 55, "90")]},
    {"id": "bike-long", "name": "Long endurance with a tempo finish", "tier": "moderate", "phases": ["base", "build"],
     "purpose": "Endurance, with 15 min of tempo to finish strong", "not_for": "Recovery",
     "steps": [("endurance", 60, 60, 70, "85-95"), ("tempo", 15, 76, 85, "85-95"), ("cool-down", 5, 45, 55, "90")]},
    {"id": "bike-threshold", "name": "Threshold 2 x 15", "tier": "hard", "phases": ["build", "peak"],
     "purpose": "Raising FTP: 2 x 15 min at threshold", "not_for": "Base or loaded weeks",
     "steps": [("warm-up", 12, 50, 70, "90"), ("2 x 15 min threshold, 5 min easy", 35, 95, 100, "85-95"), ("cool-down", 8, 45, 55, "90")]},
    {"id": "bike-over-under", "name": "Over-unders", "tier": "hard", "phases": ["build", "peak"],
     "purpose": "Clearing effort above threshold: 3 x (3 x 2 min over, 2 min under)", "not_for": "Base",
     "steps": [("warm-up", 12, 50, 70, "90"), ("3 x 12 min alternating 2 min at 105% / 2 min at 90%, 5 min easy", 46, 90, 105, "85-95"), ("cool-down", 8, 45, 55, "90")]},
    {"id": "bike-sprints", "name": "Sprints", "tier": "hard", "phases": ["build", "peak"],
     "purpose": "Neuromuscular power: 8 x 10 s all-out, 3 min easy", "not_for": "Endurance",
     "steps": [("warm-up", 15, 50, 70, "90"), ("8 x 10 s all-out, 3 min easy", 26, 50, 150, "100+"), ("cool-down", 10, 45, 55, "90")]},
    {"id": "bike-vo2", "name": "VO2max 5 x 4", "tier": "very_hard", "phases": ["peak", "build"],
     "purpose": "Top aerobic power: 5 x 4 min at 110-115%, 4 min easy", "not_for": "More than once a week; loaded weeks",
     "steps": [("warm-up", 15, 50, 70, "90"), ("5 x 4 min VO2, 4 min easy", 40, 110, 115, "90-100"), ("cool-down", 10, 45, 55, "90")]},
    {"id": "bike-30-30", "name": "30/30s", "tier": "very_hard", "phases": ["peak", "build"],
     "purpose": "Repeated hard efforts: 3 x (8 x 30 s at 120% / 30 s easy)", "not_for": "Base",
     "steps": [("warm-up", 15, 50, 70, "90"), ("3 x 8 min of 30 s at 120% / 30 s easy, 5 min between", 34, 50, 120, "95-105"), ("cool-down", 10, 45, 55, "90")]},
]


def _fmt(sec):
    return f"{int(sec // 60)}:{int(round(sec % 60)):02d}"


def _swim_pace(p, css, stroke="free"):
    css = css + STROKE_OFFSET.get(stroke, 0) if css else css
    if p == "max":
        return "all out"
    if p == "fast":
        return f"fast ({_fmt(css - 4)}/100 or quicker)" if css else "fast"
    if not css:
        return {"easy": "easy", "css": "threshold effort (hard but steady)"}.get(p, "steady" if "+" in p else "threshold, a touch faster")
    if p == "easy":
        return f"easy (~{_fmt(css + 18)}/100)"
    off = 0 if p == "css" else int(p[3:])
    return f"{_fmt(css + off)}/100"


def fill_swim(t, settings, css):
    """A swim template in the rider's numbers: stroke mix, drill share, volume for their level, CSS paces."""
    mix, level = settings["mix"], settings["level"]
    lead = max((s for s in STROKES if s != "free"), key=lambda s: mix[s])
    focus = lead if mix[lead] >= 30 else "free"
    target = settings.get("volume_scale", 1.0) * SWIM_VOLUME.get(level, 1900) * {"easy": 0.8, "moderate": 1.0, "hard": 1.0, "very_hard": 0.9}[t["tier"]]
    segs = [list(s) for s in t["segments"]]
    base = sum(r * m for _, r, m, *_ in segs)
    k = max(0.25, min(1.3, target / base))
    for s in segs:
        if s[0] not in ("warmup", "cooldown") and s[1] > 1:
            s[1] = max(1, round(s[1] * k))
    # the drill share: drill-swim reps sized to it
    total = sum(r * m for _, r, m, *_ in segs)
    dr = [s for s in segs if s[0] == "drill_swim"]
    if dr:
        want = settings["drill_share"] / 100 * total
        have = sum(s[1] * s[2] for s in dr)
        for s in dr:
            s[1] = max(2, round(s[1] * want / have)) if have else s[1]
    for sg in segs:                                            # a heavy stroke gets fewer reps
        if sg[5] == "focus" and sg[0] not in ("warmup", "cooldown") and sg[1] > 1:
            sg[1] = max(2, round(sg[1] * STROKE_REPS.get(focus, 1.0)))
        sg[5] = {"focus": focus}.get(sg[5], sg[5])            # slots -> strokes: focus, free, mix (IM), choice
    if settings.get("work_mix"):
        # Allocate main-set metres by purpose, retaining each template's effort/rest prescription.
        for sg in segs:
            if sg[0] in ("warmup","cooldown"):
                sg[2] = max(50, round(sg[2] * settings.get("volume_scale", 1) / 25) * 25)
        main_target = max(200, target - sum(g[1]*g[2] for g in segs if g[0] in ("warmup","cooldown")))
        units = round(main_target / 25)
        work = settings["work_mix"]
        allocations = {k:int(units*v/100) for k,v in work.items()}
        for k in sorted(work, key=lambda k: units*work[k]/100-allocations[k], reverse=True)[:units-sum(allocations.values())]:
            allocations[k] += 1
        main_segs=[]
        for category, n in allocations.items():
            if not n: continue
            candidates=[g for g in segs if g[0] == category or category == "swim" and g[0] in ("aerobic","threshold","speed","race")]
            if not candidates:
                candidates=[[category if category != "swim" else "aerobic",1,50,20,"easy","free"]]
            weights=[g[1]*g[2] for g in candidates]; total_weight=sum(weights)
            counts=[int(n*w/total_weight) for w in weights]
            for i in sorted(range(len(counts)),key=lambda i:n*weights[i]/total_weight-counts[i],reverse=True)[:n-sum(counts)]: counts[i]+=1
            for sg, count in zip(candidates, counts):
                if not count: continue
                g=list(sg); distance=count*25; rep_m=min(g[2],distance)
                reps, remainder=divmod(distance,rep_m)
                g[1],g[2]=reps,rep_m
                main_segs.append(g)
                if remainder: main_segs.append([g[0],1,remainder,g[3],g[4],g[5]])
        segs=[g for g in segs if g[0]=="warmup"]+main_segs+[g for g in segs if g[0]=="cooldown"]
    if settings.get("work_mix") and any(mix[k] != 25 for k in STROKES):
        # IM-order templates otherwise lock maintenance to 25% each despite a different profile.
        resolved=[]
        for sg in segs:
            if sg[5] != "mix" or sg[0] in ("warmup","cooldown","kick"):
                resolved.append(sg); continue
            units=sg[1]*sg[2]//25
            shares={k:int(units*mix[k]/100) for k in STROKES}
            for k in sorted(STROKES,key=lambda k:units*mix[k]/100-shares[k],reverse=True)[:units-sum(shares.values())]: shares[k]+=1
            for k,n in shares.items():
                if not n: continue
                size=min(sg[2],n*25); reps, remainder=divmod(n*25,size)
                resolved.append([sg[0],reps,size,sg[3],sg[4],k])
                if remainder: resolved.append([sg[0],1,remainder,sg[3],sg[4],k])
        segs=resolved
    # the ratio: the session's metres per stroke land near the mix - maintenance strokes take reps from the
    # freestyle (or surplus focus-stroke) aerobic and drill sets, so any mix works with the same template
    body = lambda: [sg for sg in segs if sg[0] not in ("warmup", "cooldown")]
    def metres():
        m = {x: 0.0 for x in STROKES}
        for sg in body():
            if settings.get("work_mix") and sg[0] == "kick":
                continue
            if sg[5] == "mix":
                for x in STROKES:
                    m[x] += sg[1] * sg[2] / 4
            elif sg[5] in m:
                m[sg[5]] += sg[1] * sg[2]
        return m
    main = sum(metres().values()) or 1
    for x in sorted(STROKES, key=lambda x: -mix[x]):
        short = mix[x] / 100 * main - metres()[x]
        if short < 50:
            continue
        have = metres()
        donors = [sg for sg in body() if sg[5] in STROKES and sg[5] != x and sg[0] in ("aerobic", "drill_swim", "pull", "threshold")
                  and have[sg[5]] - mix[sg[5]] / 100 * main >= min(sg[2], 100) * 0.5]
        for sg in sorted(donors, key=lambda g: (g[0] == "threshold", -g[1] * g[2])):   # threshold sets give last
            spare = metres()[sg[5]] - mix[sg[5]] / 100 * main
            if sg[1] == 1:                                    # a single swim changes stroke whole, if it fits
                if sg[2] <= short + 50 and sg[2] <= spare + 50:
                    sg[5] = x
                    short -= sg[2]
            else:
                k = min(sg[1] - 1, round(min(short, spare) / sg[2]))
                if k > 0:
                    sg[1] -= k
                    segs.insert(segs.index(sg) + 1, [sg[0], k, sg[2], sg[3], sg[4], x])
                    short -= k * sg[2]
            if short < 50:
                break
    lines, total, secs = [], 0, 0
    for kind, reps, m, rest, pace, stroke in segs:
        st = {"mix": "IM order", "choice": "choice"}.get(stroke) or STROKE_NAME[stroke]
        sk = {"mix": "mix", "choice": "free"}.get(stroke, stroke)
        label = {"warmup": "Warm-up", "cooldown": "Cool-down", "drill_swim": "Drill / swim", "aerobic": "Aerobic", "threshold": "Threshold",
                 "speed": "Speed", "race": "Race pace", "kick": "Kick", "pull": "Pull (buoy)"}[kind]
        how = ("each: first half a drill, second half full stroke" if kind == "drill_swim" else "arms at sides or board across chest; comfortable effort, no forced streamline" if kind == "kick" and settings.get("work_mix") else "")
        rep = f"{reps} x {m} m" if reps > 1 else f"{m} m"
        pace_text = "comfortable effort" if kind == "kick" and settings.get("work_mix") else _swim_pace(pace, css, sk)
        lines.append(f"{label}: {rep} {st}, {pace_text}" + (f", {rest} s rest" if rest and reps > 1 else "") + (f" ({how})" if how else ""))
        total += reps * m
        per100 = (css or 120) + STROKE_OFFSET.get(sk, 0) + (18 if pace == "easy" else 0)
        secs += reps * (m / 100 * per100 + rest)
    got = metres()
    main = sum(got.values()) or 1
    stroke_mix = {x: round(100 * v / main) for x, v in got.items()}
    profile_fields = {}
    if settings.get("profile_id"):
        work_metres = {k:sum(g[1]*g[2] for g in segs if g[0] == k or k == "swim" and g[0] in ("aerobic","threshold","speed","race")) for k in settings["work_mix"]}
        profile_fields = {"swim_profile":settings["profile_id"], "profile_name":settings["profile_name"],
                          "planned_work_mix":settings["work_mix"], "work_mix":{k:round(v/max(1,sum(work_metres.values()))*100,1) for k,v in work_metres.items()},
                          "equipment":settings["equipment"], "segments":[{"kind":g[0],"reps":g[1],"metres":g[2],"rest_s":g[3],"effort":g[4],"stroke":g[5]} for g in segs],
                          "load_note":"Planned structure only; actual watch data and check-ins feed the existing swim recovery model. Kicking also uses the legs."}
    return {**profile_fields, "id": t["id"], "name": t["name"], "tier": t["tier"], "purpose": t["purpose"], "not_for": t["not_for"],
            "lines": lines, "metres": total, "minutes": round(secs / 60), "focus_stroke": STROKE_NAME[focus], "stroke_mix": stroke_mix,
            "sources": [SOURCES["swim"], SOURCES["css"] if css else SOURCES["swim"], SOURCES["partwhole"]]}


def _run_paces(k5):
    if not k5:
        return None
    p = k5 / 5                                          # seconds per km at 5K pace
    return {"easy": (p + 75, p + 105), "steady": (p + 40, p + 55), "threshold": (p + 15, p + 22), "interval": (p - 3, p + 3), "rep": (p - 12, p - 6)}


def fill_run(t, paces, level):
    scale = {"new": 0.7, "returning": 0.85, "regular": 1.0}.get(level, 0.85)
    lines, mins = [], 0
    for label, m, pace in t["steps"]:
        mm = max(3, round(m * (scale if pace in ("easy", "steady") else 1)))
        pr = paces.get(pace) if paces else None
        lines.append(f"{label}: {mm} min" + (f" at {_fmt(pr[0])}-{_fmt(pr[1])}/km" if pr else f" ({pace})" if pace != "walk" else ""))
        mins += mm
    return {"id": t["id"], "name": t["name"], "tier": t["tier"], "purpose": t["purpose"], "not_for": t["not_for"], "lines": lines,
            "minutes": mins, "sources": [SOURCES["run"], SOURCES["polarized"]]}


def fill_bike(t, ftp, level):
    scale = {"new": 0.7, "returning": 0.85, "regular": 1.0}.get(level, 0.85)
    lines, mins, power = [], 0, []
    for label, m, lo, hi, rpm in t["steps"]:
        mm = max(3, round(m * scale))
        w = f"{round(lo * ftp / 100)}-{round(hi * ftp / 100)} W" if ftp else f"{lo}-{hi}% FTP"
        lines.append(f"{label}: {mm} min, {w}, {rpm} rpm")
        cadence=[float(x) for x in rpm.split("-")]
        power.append({"minutes":mm,"pct":(lo+hi)/2,"rpm":sum(cadence)/len(cadence)})
        mins += mm
    return {"id": t["id"], "name": t["name"], "tier": t["tier"], "purpose": t["purpose"], "not_for": t["not_for"], "lines": lines,
            "minutes": mins, "bike_plan":{"power_steps":power,
            "basis":"Template stage midpoint scenario; compressed interval descriptions need saved timed steps for exact planning"},
            "sources": [SOURCES["bike"], SOURCES["polarized"]]}


def snap(library, tier, ph, focus=None, tri=False, n=3):
    """The nearest templates: the tier first (one step away counts, less), then the phase, then the focus."""
    def score(t):
        s = -2 * abs(TIERS.index(t["tier"]) - TIERS.index(tier))
        s += 1.5 if ph in t["phases"] else 0
        if focus:
            s += 1 if t.get("focus") == focus else (0.5 if t.get("focus") == "mix" and focus == "stroke" else 0)
        if t.get("tri") and not tri:
            s -= 1
        return s
    return sorted(library, key=score, reverse=True)[:n]


def programming(d, profile, sport, today, readiness=None, headline=None, capacities=None, swim_profile=None, activities=None):
    """Everything the AI (or the app's add-a-session button) needs to program one session of `sport` today."""
    if sport not in ("swim", "run", "bike"):
        raise ValueError("sport is swim, run or bike (lifting has its own plan)")
    ph = phase(d, today)
    if sport == "swim":
        swim_events = [e for e in d.get("events", []) if e.get("kind") == "race"
                       and (e.get("sport") in ("swim", "tri") or (e.get("detail") or {}).get("type") in ("swim_meet", "triathlon"))
                       and dt.date.fromisoformat(e["date"]) >= today - dt.timedelta(days=7)]
        if swim_events:
            ph = phase({**d, "events":swim_events}, today)
    import phaseblend
    blend=phaseblend.resolve(d,today,readiness,headline)
    intent=blend['sports'].get('ride' if sport=='bike' else sport)
    if intent and ph['phase'] not in ('taper','recovery'):
        ph={**ph,'phase':intent['phase'],'why':ph['why']+'; '+blend['profile']['label']+': '+intent['role']}
    state, why = load_state(sport, readiness, headline)
    if intent and intent['role'] in ('hold','pause'):
        state='not_ready';why=why+intent['why']

    cap, tier = tier_for(state, ph["phase"])
    if intent and intent['role']=='maintain' and tier is not None:
        tier=TIERS[min(TIERS.index(tier),TIERS.index('moderate'))]
    level = ((profile or {}).get("experience") or {}).get(sport) or "returning"
    out = {"sport": sport, "phase": ph, "load_state": state, "load_why": why, "tier_cap": cap, "suggested_tier": tier, "level": level,
           "guidance": [
               "Most sessions easy or moderate; the hard ones are the key sessions of the week (about 80/20).",
               "Keep a small set of core sessions and repeat them for 4-6 weeks, progressing one thing a little each time; change at a phase change.",
               "Never above the tier cap: it comes from the load the rider is carrying.",
           ]}
    out['phase_blend']=blend
    if intent:out['guidance']+=intent['why']+[intent['maintenance']]
    ev = ph.get("event") or {}
    tri = (ev.get("detail") or {}).get("type") == "triathlon" or ev.get("sport") == "tri" or not ev
    if sport == "swim":
        settings = swim_settings(d, profile, ph)
        options, context = swim_profile_options(d, settings, ph, state, today, readiness, headline, activities)
        requested = swim_profile or ((d.get("programming") or {}).get("swim") or {}).get("profile_id") or "auto"
        if requested not in ("auto",) + SWIM_PROFILE_IDS: raise ValueError("Unknown swim profile")
        eligible = [p for p in options if p["eligible"] and (not intent or intent['role']!='maintain' or TIERS.index(p['tier'])<=TIERS.index('moderate'))]
        default = "recovery" if state == "heavy" or context["recent_demanding"] or context["weekly_worsening"] else {
            "base":"balanced", "build":"race-pace", "peak":"race-pace", "taper":"event-technique", "recovery":"recovery"}[ph["phase"]]
        if intent and intent['role']=='maintain':default='balanced'
        chosen = next((p for p in eligible if p["id"] == requested), None) if requested != "auto" else None
        chosen = chosen or next((p for p in eligible if p["id"] == default), None) or next(iter(eligible), None)
        out["swim"] = settings
        out["swim_baseline"] = copy.deepcopy(settings)
        out["swim_profiles"] = options
        out["swim_profile"] = {"requested":requested, "selected":chosen["id"] if chosen else None,
                               "fallback":requested != "auto" and (not chosen or chosen["id"] != requested),
                               "context":context, "sources":SWIM_PROFILE_SOURCES,
                               "basis":"Provisional coaching ratios and ordering rules, informed by research; calibrated with actual sessions and reports."}
    if tier is None:
        out["not_ready"] = True
        out["message"] = f"Not recommended today: {('; '.join(why)) or 'the load is too high'}."
        out["instead"] = {"name": "Dynamic mobility", "minutes": sum(m for _, m in MOBILITY),
                          "lines": [f"{l}: {m} min" for l, m in MOBILITY],
                          "or": "an easy bike or swim if those are go today" if sport == "run" else "mobility and an easy walk"}
        return out
    if sport == "swim":
        settings = {**settings, "profile_id":chosen["id"], "profile_name":chosen["name"], "mix":chosen["mix"],
                    "drill_share":chosen["drill_share"], "work_mix":chosen["work_mix"], "volume_scale":chosen["volume_scale"], "equipment":chosen["equipment"]}
        if chosen["id"] == "balanced":
            drill = out["swim_baseline"]["drill_share"]
            settings["work_mix"] = {**settings["work_mix"], "drill_swim":drill, "swim":90-drill}
            settings["drill_share"] = drill
        css = (capacities or {}).get("swim_css")
        lead = max((s for s in STROKES if s != "free"), key=lambda s: settings["mix"][s])
        focus = "stroke" if settings["mix"][lead] >= 30 else "free"
        out["swim"] = settings
        library = [t for t in SWIM if t["id"] in chosen["templates"] and TIERS.index(t["tier"]) <= TIERS.index(cap)]
        # Recovery and phase profiles must not inherit the full usual session volume.
        if ph["phase"] == "taper": settings["volume_scale"] = min(.5, settings["volume_scale"])
        out["templates"] = [fill_swim(t, settings, css) for t in snap(library, chosen["tier"], ph["phase"], focus, tri)]
        out["suggested_tier"] = chosen["tier"]
        for template in out["templates"]:
            template["swim_plan"]={"stroke_mix":template["stroke_mix"],"work_mix":template["work_mix"],"purpose":chosen["purpose"],
                "why":f"{chosen['name']}: {chosen['purpose']}. {ph['why']}; swim load {state}. "
                      +("Easier work follows recent demanding swimming or a worsening Sunday response." if out["swim_profile"]["context"]["recent_demanding"] or out["swim_profile"]["context"]["weekly_worsening"] else "; ".join(why))}

        out["guidance"] += ["Drills early while fresh, each followed by full-stroke swimming; keep the drill share near the setting.",
                            "Cap the main set near the distance where the stroke usually breaks down (get_insights, swim.session_length).",
                            "Paddles add shoulder load; keep hard sets to one or two a week."]
    elif sport == "run":
        out["templates"] = [fill_run(t, _run_paces((profile or {}).get("run_5k_s")), level) for t in snap([t for t in RUN if TIERS.index(t["tier"])<=TIERS.index(cap)], tier, ph["phase"])]
        out["guidance"] += ["The running blocks decide whether running happens at all; frequency before duration, flat before hills."]
    else:
        ftp = (capacities or {}).get("ftp") or (profile or {}).get("ftp")
        out["templates"] = [fill_bike(t, ftp, level) for t in snap([t for t in BIKE if TIERS.index(t["tier"])<=TIERS.index(cap)], tier, ph["phase"])]
        out["guidance"] += ["When the running blocks are high, riding keeps the aerobic work going without the impact."]
    if ph["phase"] == "taper":
        out["guidance"].append(f"Taper: cut volume 40-60%, keep some intensity ({SOURCES['taper']}).")
    return out
