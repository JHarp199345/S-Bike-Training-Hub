"""lifting.py - lifting and functional-strength load: planned sessions, the check-off, load per body region.

The rider's design (2026-09-30):
  - A gym session is a list of exercises: anything - barbell lifts, medicine-ball throws, cable swings, kneeling
    kettlebell lifts, holds and hangs. The rider can build it as a plain list (name, sets x reps or time, weight,
    tempo); the AI scores it: the kind of exercise, whether it's restorative or build work, and how the whole
    movement's strain is shared across the body (deadlift: lower back 30%, glutes 25%, hamstrings 20% ...).
    An exercise the AI has scored before is recognised by name from the library.
  - After the workout the check-off runs down the list: done? same weight, or more, or less? Session effort
    (1-10) and how you feel after (1-10). No logging as you go.
  - More weight than planned: more load. Less weight: it asks why.
        too heavy  -> the load stays as planned (the lighter weight was your limit, the same hard work) and the
                      strength estimate for that lift comes down, so the next plan starts where you really are
        chose to   -> the load is what you actually lifted
  - Three days later it asks how those regions feel (1-10) - open for two more days. Those answers fit each region's block, the
    same way the swim block is fitted to next-morning shoulders.
  - Rules the rider types ("No squats", "Favorite lift: incline dumbbell press") that every AI reads. "No ..." and
    "never ..." rules are enforced: a plan with one of those exercises is refused.
  - The steer: restorative or build. Carrying a lot of load (any system near its limit), about 80% of a session's
    work should be restorative - controlled, mild stress: holds, slow tempo, hangs, loaded stretching. Fresh, it
    drops to 5-10% maintenance and the build work leads. Those numbers are a starting guess; the after-session
    and follow-up reports move the curve. The rider's own call always wins - an override is recorded, not refused.

LOAD (estimates from sets, reps, weight and tempo - not a measurement of tissue):
  weighted lifts (barbell, dumbbell, kettlebell, machine, cable) - intensity against an estimated one-rep max
      (Epley: 1RM = weight x (1 + reps/30), with the reps left in reserve from the effort rating):
          set points = reps x (weight / 1RM / 0.75)^2 x tempo       a set of 10 at 75% of max = 10 points
  throws, swings and chops (power), bands, bodyweight, holds - effort, not a max:
          set points = reps x (effort / 7)^2 x kind factor x (1 + kg / 20)^0.5 x tempo   (seconds count as reps / 3)
  tempo: seconds per rep (e.g. 3-0-3 = 6) against a normal ~2 s rep: x (seconds / 2)^0.5, at most x 2.
  holds (the rider's report, 2026-10-03: a 9 s pause at the top of a fly, a heavy curl held, scored next to nothing):
      a hold is time under the full load, so it counts as reps, not as a tempo bonus: every 3 s held is one more rep
      at the same intensity (the same 3 s the effort formula uses; a held second has no lowering phase, where most
      soreness comes from, so it counts a bit less than a moving one). A pause in each rep (hold, seconds):
      reps x (1 + hold / 3). A weighted static hold (seconds and a weight, with a known or given max) is judged
      against the max like a lift: seconds / 3 reps, and
      the weight may be above the lifting max (up to 1.3x: you can hold more than you can lift).
  to failure: a set taken to failure has no reps in reserve - the strength estimate uses 0, not the session effort.
  The movement's points are shared across its regions by the AI's percentages. Leg regions count toward the
  leg-muscle system the running and riding share; every region gets its own recovery block.
"""
import datetime as dt
import math
import re
import statistics

import bodymap

KG = {"kg": 1.0, "lb": 0.45359237}
KINDS = ("barbell", "dumbbell", "kettlebell", "machine", "cable", "band", "medicine_ball", "power", "bodyweight", "other")
STYLES = ("restorative", "build")
MAX_BASED = ("barbell", "dumbbell", "kettlebell", "machine", "cable")     # a one-rep max makes sense
HOLD_S_PER_REP = 3.0     # seconds held that count as one rep
HOLD_REL_MAX = 1.3        # a held weight can be above the lifting max (isometric and lowering strength run higher)
# "power": swings, chops and throws with any implement (cable, band, bat) - fast, rotational, not judged against a max
KIND_FACTOR = {"medicine_ball": 0.8, "power": 0.8, "band": 0.6, "bodyweight": 0.7, "other": 0.7, "cable": 0.6,
               "kettlebell": 0.8, "dumbbell": 0.8, "barbell": 0.9, "machine": 0.7}
LEG_REGIONS = ("quads", "hamstrings", "glutes", "calves", "adductors", "hip_flexors")
PLAN_RPE = 8              # an unlogged plan is judged as if done with ~2 reps left in reserve
EFFORT_RPE = 7            # effort-based moves before they're done
WHY = ("too_heavy", "chose")
NORMAL_REP_S = 2.0

# the region block: like the swim block (swimload.py), fitted to follow-up ratings
HALF_LIFE_DAYS = 1.75     # muscle soreness and recovery run ~2-3 days
THRESHOLD = 1.5
DEFAULT_REF = 15.0        # points in one block before any session: about a hard 3 x 10 shared over a few regions
PRIOR_SD = 0.5
REPORT_SD = 1.5
WEEKLY_SD = 1.0          # the Sunday check-in is the week's considered answer: trusted a little more
GRID = [math.exp(math.log(0.33) + i * (math.log(3.0) - math.log(0.33)) / 60) for i in range(61)]
FOLLOW_DAYS = (3, 5)      # the follow-up is due 3 days after a session, and stays open two more (the rider's schedule)

# the steer: the restorative share of a session's work, from the load carried (1.0 = a system at its limit)
STEER_LO, STEER_HI = 0.075, 0.80     # fresh ... beat up (the rider's starting numbers - a guess, tuned by reports)
STEER_FROM, STEER_AT = 0.5, 1.0      # load ratio where it starts rising, and where it's all the way up
GUIDANCE = [
    "The rider's rules come first: never plan an exercise a rule excludes, and use their favourites often.",
    "Read the steer before planning. Restorative work is controlled, mild stress that keeps healing tissue loaded "
    "without grinding it down: isometric holds, slow tempo (e.g. 3 s down, 3 s up), dead hangs, loaded stretching, "
    "light carries. Build work is progressive strength: heavier sets, more reps over the weeks.",
    "When the steer says restorative, make about that share of the session's work restorative; when it says build, "
    "keep restorative work to 5-10% as maintenance.",
    "The steer depends on the session's muscles: leg limits count only when the legs are worked (steer_without_legs "
    "shows the day for an upper-body or core session). Evaluate a session to get its own steer.",
    "Space the legs: running, riding and leg lifting share one leg budget, and bone and tendon recover far more slowly "
    "than muscle. Prefer steady small doses over one big leg day that costs two weeks.",
    "The steer is a suggestion from the models. Explain it; if the rider wants something else, their call wins - "
    "record it as their override and plan what they asked for.",
    "Load numbers are estimates from sets, reps, weight and tempo, tuned by the rider's reports - not measurements.",
]


def key(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


JOINED = re.compile(r"\b(pull|chin|push|sit|step|pike)(ups?|downs?)\b")    # "pullups" reads like "pull ups"


def _stems(text):
    words = JOINED.sub(r"\1 \2", key(text)).split()
    return [w[:-1] if len(w) >= 3 and w.endswith("s") and not w.endswith("ss") else w for w in words]


def state(d):
    s = d.setdefault("lifting", {})
    s.setdefault("unit", "lb")
    for k in ("strength", "library", "followups"):
        s.setdefault(k, {})
    for k in ("rules", "logs"):
        s.setdefault(k, [])
    for x in s.pop("exclusions", []) or []:               # the first version's won't-do list becomes rules
        s["rules"].append({"text": f"No {x['name']}", "note": x.get("why") or "", "date": x.get("date")})
    return s


def regions():
    return {k: v[0] for k, v in bodymap.REGIONS.items() if k != "feet"}


# ── the rider's rules ───────────────────────────────────────────────────────
NEVER = re.compile(r"^\s*(?:no|never|don'?t do|do not do|i don'?t do|can'?t do|i can'?t do|avoid)\s+(.+?)\s*\.?\s*$", re.I)
FAVOURITE = re.compile(r"favou?rite|i (?:really )?(?:like|love)", re.I)


def rule_kind(text):
    m = NEVER.match(text)
    if m:
        return "never", m.group(1)
    if FAVOURITE.search(text):
        return "favourite", None
    return "note", None


def rules(d):
    out = []
    for i, r in enumerate(state(d)["rules"]):
        kind, what = rule_kind(r["text"])
        out.append({"id": i, "text": r["text"], "note": r.get("note") or "", "date": r.get("date"), "kind": kind,
                    **({"excludes": what} if what else {})})
    return out


def add_rule(d, text, note=""):
    text = str(text or "").strip()[:200]
    if not text:
        raise ValueError("type the rule")
    s = state(d)
    s["rules"] = [r for r in s["rules"] if r["text"].lower() != text.lower()]
    s["rules"].append({"text": text, "note": str(note or "")[:200], "date": dt.date.today().isoformat()})
    return rules(d)


def remove_rule(d, text):
    s = state(d)
    k = key(text)
    before = len(s["rules"])
    s["rules"] = [r for r in s["rules"] if key(r["text"]) != k and key(rule_kind(r["text"])[1] or "") != k]
    if len(s["rules"]) == before:
        raise ValueError(f"no rule '{text}'")
    return rules(d)


KIND_WORDS = {"barbell": "barbell", "dumbbell": "dumbbell", "kettlebell": "kettlebell", "machine": "machine",
              "cable": "cable", "band": "band", "banded": "band", "medicine": "medicine_ball", "bodyweight": "bodyweight"}


def excluded(d, name, kind=None):
    """The rule that excludes this exercise, if any. "No squats" excludes "Back squat" and "Goblet squat"; "No barbell
    squats" excludes a squat done with a barbell (by its kind, or the word in its name) but not a goblet squat."""
    ex = _stems(name)
    for r in rules(d):
        if r["kind"] != "never":
            continue
        want = _stems(r["excludes"])
        kinds = {KIND_WORDS[w] for w in want if w in KIND_WORDS}
        rest = [w for w in want if w not in KIND_WORDS and w != "ball"]
        if not rest:
            continue
        if not any(ex[i:i + len(rest)] == rest for i in range(len(ex) - len(rest) + 1)):
            continue
        if kinds and not (kind in kinds or any(w in KIND_WORDS and KIND_WORDS[w] in kinds for w in ex)):
            continue
        return r
    return None


# compatibility with the first version's tools
def exclude(d, name, why=""):
    return add_rule(d, f"No {name}", why)


def include(d, name):
    return remove_rule(d, name)


# ── planning ────────────────────────────────────────────────────────────────
def _shares(x, names):
    """{region: fraction} from the AI's percentages ({region: %}) or a plain list (main region counts most)."""
    reg = x.get("regions") or {}
    if isinstance(reg, list):
        reg = {r: (1.0 if i == 0 else 0.6) for i, r in enumerate(reg)}
    reg = {r: float(v) for r, v in reg.items() if r in names and float(v) > 0}
    tot = sum(reg.values())
    return {r: round(v / tot, 3) for r, v in sorted(reg.items(), key=lambda kv: -kv[1])} if tot else {}


def tempo_seconds(t):
    if not t:
        return None
    parts = [int(p) for p in re.findall(r"\d+", str(t))[:4]]
    return sum(parts) or None if parts else None


def clean(d, lifts, unit=None, draft=False):
    """Validate a list of exercises. Refuses anything a rule excludes. With draft=True (the rider's plain list),
    an exercise may come without a kind or regions: the library fills them in if the AI scored it before, and
    otherwise it waits for the AI to score it."""
    s = state(d)
    unit = unit or s["unit"]
    if not isinstance(lifts, list) or not 1 <= len(lifts) <= 30:
        raise ValueError("lifts is a list of 1-30 exercises")
    names = regions()
    out = []
    for x in lifts:
        if not isinstance(x, dict) or not str(x.get("name") or "").strip():
            raise ValueError("every exercise needs a name")
        name = str(x["name"]).strip()[:80]
        known0 = s["library"].get(key(name)) or {}
        bad = excluded(d, name, x.get("kind") or known0.get("kind"))
        if bad:
            raise ValueError(f"'{name}' is ruled out by the rider's rule \"{bad['text']}\" - pick something else")
        known = s["library"].get(key(name)) or {}
        kind = x.get("kind") or (known.get("kind") if known.get("scored") else None)
        shares = _shares(x, names) or (known.get("shares") if known.get("scored") and not x.get("regions") else {})
        style = x.get("style") or (known.get("style") if known.get("scored") else None)
        if kind and kind not in KINDS:
            raise ValueError(f"kind is one of {', '.join(KINDS)}")
        if style and style not in STYLES:
            raise ValueError("style is restorative or build")
        if not draft and (not kind or not shares):
            raise ValueError(f"'{name}': give its kind and regions (the share of the movement each region takes, "
                             f"from: {', '.join(names)})")
        sets = int(x.get("sets") or 1)
        reps = int(x["reps"]) if x.get("reps") else None
        secs = int(x["seconds"]) if x.get("seconds") else None
        if not 1 <= sets <= 20 or (reps is None) == (secs is None) or (reps and not 1 <= reps <= 100) or (secs and not 1 <= secs <= 600):
            raise ValueError(f"'{name}': sets 1-20, and reps 1-100 or seconds 1-600 (one of them)")
        w = x.get("weight")
        w = None if w in (None, "") else float(w)
        if w is not None and not 0 <= w <= 1000:
            raise ValueError(f"'{name}': weight 0-1000")
        u = x.get("unit") or unit
        if u not in KG:
            raise ValueError("unit is lb or kg")
        hold = int(x["hold"]) if x.get("hold") else None
        if hold and (not reps or not 1 <= hold <= 120):
            raise ValueError(f"'{name}': hold is 1-120 seconds held in each rep (for a static hold, give seconds instead)")
        tempo = str(x.get("tempo") or "").strip()[:12] or None
        ts = tempo_seconds(tempo)
        if tempo and not ts:
            raise ValueError(f"'{name}': tempo like 3-0-3 (seconds down, pause, up)")
        if not style and kind:
            style = "restorative" if (secs and not reps) or (ts and ts >= 6) else "build"
        out.append({"name": name, "how": str(x.get("how") or known.get("how") or "")[:300],
                    "equipment": str(x.get("equipment") or known.get("equipment") or "")[:80],
                    "kind": kind, "style": style, "sets": sets, "reps": reps, "seconds": secs, "weight": w, "unit": u,
                    "tempo": tempo, "hold": hold, "per_side": bool(x.get("per_side", known.get("per_side", False))),
                    "regions": shares, "scored": bool(kind and shares)})
    return out


def set_session(d, date, lifts, name=None, minutes=None, index=None, note=None, draft=False, override=None):
    """Put a gym session on the day's plan (replacing the day's gym session at `index`, or the first gym session,
    or adding one). If that session was already checked off, its load is recalculated with the new scoring."""
    import coach
    ls = clean(d, lifts, draft=draft)
    p = d["plans"].setdefault(date, {})
    sessions = list(p.get("sessions") or ([{"sport": p["sport"], "minutes": p.get("minutes") or 0, "name": p["sport"].title()}]
                                           if p.get("sport") else []))
    new = {"sport": "gym", "minutes": int(minutes or estimate_minutes(ls)), "name": (name or "Strength")[:80], "steps": [],
           "note": (note or "")[:300], "workout": None, "lifts": ls}
    gyms = [i for i, s in enumerate(sessions) if s.get("sport") == "gym"]
    at = index if index is not None and 0 <= index < len(sessions) else (gyms[0] if gyms else None)
    old = sessions[at]["name"] if at is not None else None
    if at is None:
        sessions.append(new)
    else:
        sessions[at] = new
    coach.set_sessions(d, date, sessions, _trusted=True)
    if override:
        p["sessions"][at if at is not None else -1]["override"] = str(override)[:300]
    remember(d, ls, date)
    for l in list(state(d)["logs"]):                     # scored after the check-off: recalculate its load
        if l["date"] == date and l["session"] in (old, new["name"]) and l.get("inputs"):
            i = l["inputs"]
            state(d)["logs"].remove(l)
            log(d, date, i["done"], i["rpe"], i["wellness"], i.get("session_index"), i.get("compare_last"),
                i.get("override"), _session_name=new["name"])
    return p


def estimate_minutes(lifts):
    def rep_s(x):
        return tempo_seconds(x.get("tempo")) or 4
    work = sum(x["sets"] * ((x["reps"] or 0) * (rep_s(x) + (x.get("hold") or 0)) + (x["seconds"] or 0)) * (2 if x["per_side"] else 1) for x in lifts) / 60
    rest = sum(x["sets"] for x in lifts) * 1.5
    return max(10, round(work + rest))


def remember(d, lifts, date, done=False):
    lib = state(d)["library"]
    for x in lifts:
        e = lib.setdefault(key(x["name"]), {"times_done": 0})
        e.update({k: x[k] for k in ("name", "how", "equipment", "per_side")})
        if x.get("scored"):
            e.update({"kind": x["kind"], "style": x["style"], "shares": x["regions"], "scored": True})
        e["last_planned"] = date
        if done:
            e["times_done"] += 1
            e["last_done"] = date
            e["last"] = {k: x.get(k) for k in ("sets", "reps", "seconds", "hold", "weight", "unit", "tempo")}


# ── load ────────────────────────────────────────────────────────────────────
def one_rm(weight_kg, reps, rir=0):
    return weight_kg * (1 + (reps + rir) / 30)


def _kg(x, w=None):
    w = x.get("weight") if w is None else w
    return None if w is None else w * KG[x.get("unit") or "lb"]


def tempo_factor(x):
    ts = tempo_seconds(x.get("tempo"))
    return min(2.0, (ts / NORMAL_REP_S) ** 0.5) if ts and x.get("reps") else 1.0


def points(d, x, weight=None, reps=None, sets=None, rpe=None, e1rm=None, hold=None, seconds=None):
    """(points, detail) for one exercise as planned, or as done when weight/reps/sets/rpe/hold/seconds are given."""
    if not x.get("scored"):
        return 0.0, {"method": "not scored yet"}
    reps = x["reps"] if reps is None else reps
    sets = x["sets"] if sets is None else sets
    hold = x.get("hold") if hold is None else hold
    secs = x.get("seconds") if seconds is None else seconds
    side = 2 if x["per_side"] else 1
    tf = tempo_factor(x)
    wkg = _kg(x, weight)
    held = {"hold_s": hold, "hold_reps": round(reps * hold / HOLD_S_PER_REP, 1)} if hold and reps else {}
    reps_eq = reps * (1 + hold / HOLD_S_PER_REP) if hold and reps else reps
    if x["kind"] in MAX_BASED and wkg and not reps and secs:
        known = (state(d)["strength"].get(key(x["name"])) or {}).get("e1rm_kg")
        if e1rm or known:
            e1rm, src = (e1rm, "given") if e1rm else (known, "your history")
            rel = min(HOLD_REL_MAX, wkg / e1rm)
            per_set = secs / HOLD_S_PER_REP * (rel / 0.75) ** 2 * side
            return per_set * sets, {"method": "hold against max", "e1rm_kg": round(e1rm, 1), "e1rm_from": src,
                                    "intensity_pct": round(100 * rel), "hold_reps": round(secs / HOLD_S_PER_REP, 1)}
    if x["kind"] in MAX_BASED and wkg and reps and reps <= 20:
        known = (state(d)["strength"].get(key(x["name"])) or {}).get("e1rm_kg")
        if e1rm is None:
            e1rm, src = (known, "your history") if known else (one_rm(wkg, reps, max(0, 10 - (rpe or PLAN_RPE))),
                                                               f"assumed from this set at effort {rpe or PLAN_RPE}")
        else:
            src = "given"
        rel = min(1.0, wkg / e1rm)
        per_set = reps_eq * (rel / 0.75) ** 2 * side * tf
        return per_set * sets, {"method": "intensity", "e1rm_kg": round(e1rm, 1), "e1rm_from": src,
                                "intensity_pct": round(100 * rel), **held, **({"tempo_factor": round(tf, 2)} if tf != 1 else {})}
    count = reps_eq if reps else (secs or 0) / 3
    eff = (rpe or EFFORT_RPE) / 7
    heft = (1 + (wkg or 0) / 20) ** 0.5
    per_set = count * eff ** 2 * KIND_FACTOR[x["kind"]] * heft * side * tf
    return per_set * sets, {"method": "effort", "effort": rpe or EFFORT_RPE, "kind_factor": KIND_FACTOR[x["kind"]], **held,
                            **({"tempo_factor": round(tf, 2)} if tf != 1 else {})}


def spread(x, pts):
    return {r: pts * share for r, share in (x.get("regions") or {}).items()}


# ── the steer: restorative or build ─────────────────────────────────────────
def _curve(ratio, offset=0.0):
    t = max(0.0, min(1.0, (ratio - STEER_FROM) / (STEER_AT - STEER_FROM)))
    return max(0.05, min(0.90, STEER_LO + (STEER_HI - STEER_LO) * t + offset))


def learned_offset(d):
    """How the rider's reports have moved the curve. After a session: poor how-you-feel-after (4 or less) or a sore
    follow-up (7+) when it had no more restorative work than suggested -> more restorative next time at that load;
    good ones (7+ after, follow-ups 4 or less) with less restorative work than suggested -> less. Recent sessions,
    small steps, never more than 0.3 either way."""
    s = state(d)
    off = 0.0
    for l in s["logs"][-12:]:
        sug, did = l.get("steer_share"), l.get("restorative_share")
        if sug is None or did is None:
            continue
        fu = s["followups"].get(l["date"]) or {}
        sore = max(fu.get("regions", {}).values(), default=None)
        bad = l["wellness"] <= 4 or (sore is not None and sore >= 7)
        good = l["wellness"] >= 7 and (sore is None or sore <= 4)
        if bad and did <= sug + 0.1:
            off += 0.05
        elif good and did <= sug - 0.1:
            off -= 0.03
    return max(-0.3, min(0.3, off))


WORKS_SHARE = 0.2        # a session "works the legs" when they take at least a fifth of its load (kneeling core work doesn't)
SWIM_REGIONS = ("shoulders", "scapula", "lats", "serratus", "pecs", "traps", "triceps")


def steer(d, ctx=None, session_regions=None, today=None):
    """The suggested restorative share of today's session, and why. ctx: {"headline": loads headline, "verdict":
    readiness verdict, "engine_level": heart and lungs} from the load summary.
    A session's own muscles decide which limits count (the rider's rule, 2026-09-30): running blocks, impact and the
    leg muscles only when it works the legs; swim blocks only when it works the swimming muscles; and without the
    legs, the day's heart-and-lungs verdict stands in for the leg-led overall one. With no session yet, all count."""
    ctx = ctx or {}
    mech = (ctx.get("headline") or {}).get("mechanical") or {}
    if isinstance(session_regions, dict):              # {region: points}: a group counts when it takes a real share of the work
        tot = sum(session_regions.values()) or 1
        share = lambda group: sum(v for r, v in session_regions.items() if r in group) / tot
        legs, swim = share(LEG_REGIONS) >= WORKS_SHARE, share(SWIM_REGIONS) >= WORKS_SHARE
    else:
        regs = set(session_regions or [])
        legs = not session_regions or bool(regs & set(LEG_REGIONS))
        swim = not session_regions or bool(regs & set(SWIM_REGIONS))
    parts = {}
    if legs:
        parts.update({"running blocks": mech.get("remodeling_ratio"), "impact": mech.get("impact_ratio"),
                      "leg muscles": mech.get("muscle_ratio")})
    if swim:
        parts["swim blocks"] = mech.get("swim_ratio")
    rec = model(d, today)["regions"]
    look = session_regions or list(rec)
    for r in look:
        if r in rec:
            parts[f"{rec[r]['name'].lower()} (lifting)"] = rec[r]["blocks"] / THRESHOLD
    parts = {k: round(v, 2) for k, v in parts.items() if v is not None}
    ratio = max(parts.values(), default=0.0)
    verdict = ctx.get("verdict") if legs else (ctx.get("engine_level") or None)
    said = "today's verdict" if legs else "today's heart-and-lungs verdict"
    why = [f"{k} at {round(100 * v)}% of the limit" for k, v in sorted(parts.items(), key=lambda kv: -kv[1])[:3] if v >= STEER_FROM]
    if verdict == "rest":
        ratio = max(ratio, 1.0); why.insert(0, f"{said} is rest")
    elif verdict == "easy":
        ratio = max(ratio, 0.85); why.insert(0, f"{said} is easy")
    if session_regions and not legs:
        why.append("the legs aren't worked, so the running and leg limits don't count")
    import bodymap
    overlap=bodymap.overlap_advice(ctx.get("body_map") or {},"lift",set(session_regions) if session_regions else None)
    if overlap:
        ratio=max(ratio,.85);why.extend(overlap)
    off = learned_offset(d)
    share = _curve(ratio, off)
    mode = "restorative" if share >= 0.5 else "build" if share <= 0.15 else "mixed"
    import phaseblend
    intent=phaseblend.resolve(d,today or dt.date.today(),headline=ctx.get('headline'))['sports'].get('gym')
    return {"phase_intent":intent,"mode": mode, "restorative_share": round(share, 2), "load_ratio": round(ratio, 2), "why": why or ["everything well under its limit"],
            "loads": parts, "learned_offset": round(off, 2),
            "note": "The 80% / 5-10% ends are the rider's starting guess; after-session and follow-up reports move the curve. "
                    "A suggestion - the rider's call wins."}


def restorative_share(rows_or_lifts, pts):
    tot = sum(pts)
    return round(sum(p for x, p in zip(rows_or_lifts, pts) if x.get("style") == "restorative") / tot, 2) if tot else None


def evaluate(d, lifts, today=None, ctx=None, draft=True):
    """What a session would do, before it's done: points per exercise and region, the restorative share against the
    steer, against the rider's usual, and what each region is still carrying. For the AI to score a session."""
    ls = clean(d, lifts, draft=draft)
    rows, reg, pts = [], {}, []
    for x in ls:
        p, det = points(d, x)
        pts.append(p)
        for r, v in spread(x, p).items():
            reg[r] = reg.get(r, 0) + v
        rows.append({"name": x["name"], "points": round(p, 1), **det, "style": x["style"], "regions": x["regions"],
                     "scored": x["scored"]})
    past = [l["points_total"] for l in state(d)["logs"][-8:] if l["points_total"]]
    rec = model(d, today)
    carrying = {r: rec["regions"].get(r, {}).get("blocks") for r in reg}
    after = {r: round((rec["regions"].get(r, {}).get("blocks") or 0) + v / (rec["regions"].get(r, {}).get("reference") or DEFAULT_REF), 2)
             for r, v in reg.items()}
    total = sum(pts)
    st = steer(d, ctx, reg or list({r for x in ls for r in (x.get("regions") or {})}), today)
    share = restorative_share(ls, pts)
    fit = None
    if share is not None:
        gap = share - st["restorative_share"]
        fit = ("matches the steer" if abs(gap) <= 0.15 else
               f"more grinding than the steer suggests ({round(100 * share)}% restorative vs {round(100 * st['restorative_share'])}%)" if gap < 0 else
               f"more restorative than the steer suggests ({round(100 * share)}% vs {round(100 * st['restorative_share'])}%)")
    return {"exercises": rows, "unscored": [x["name"] for x in ls if not x["scored"]],
            "points_total": round(total, 1), "regions": {r: round(v, 1) for r, v in reg.items()},
            "leg_points": round(sum(v for r, v in reg.items() if r in LEG_REGIONS), 1),
            "usual_session": round(statistics.median(past), 1) if past else None,
            "vs_usual": round(total / statistics.median(past), 2) if past and total else None,
            "restorative_share": share, "steer": st, "fits_steer": fit,
            "regions_carrying_blocks": carrying, "regions_after_blocks": after, "threshold_blocks": THRESHOLD,
            "minutes": estimate_minutes(ls), "note": "estimates from sets, reps, weight and tempo - not a measurement of tissue"}


# ── the check-off ───────────────────────────────────────────────────────────
def log(d, date, done, rpe, wellness, session_index=None, compare_last=None, override=None, ctx=None, _session_name=None):
    """The check-off: `done` is one entry per planned lift, in order:
    {"done": true|false, "weight": ..., "reps": ..., "sets": ..., "hold": s, "seconds": s, "failure": true,
     "why": "too_heavy"|"chose"} (anything left out = as planned; failure = taken to failure, no reps in reserve).
    Returns the log. Raises ValueError naming the lifts that need a why."""
    s = state(d)
    p = d["plans"].get(date) or {}
    gyms = [x for x in (p.get("sessions") or []) if x.get("sport") == "gym" and x.get("lifts")]
    if not gyms:
        raise ValueError(f"no planned lifts on {date}")
    sess = next((g for g in gyms if g["name"] == _session_name), None) if _session_name else None
    sess = sess or (gyms[session_index or 0] if (session_index or 0) < len(gyms) else gyms[0])
    plan = sess["lifts"]
    done = done or [{} for _ in plan]
    if len(done) != len(plan):
        raise ValueError(f"one entry per planned lift ({len(plan)})")
    rpe = max(1, min(10, int(rpe)))
    wellness = max(1, min(10, int(wellness)))
    rir = max(0, min(4, 10 - rpe))
    need = [x["name"] for x, a in zip(plan, done) if a.get("done", True) and a.get("weight") is not None
            and x.get("weight") is not None and float(a["weight"]) < x["weight"] and a.get("why") not in WHY]
    if need:
        raise ValueError("lighter than planned - why? (too_heavy or chose): " + ", ".join(need))
    plan_reg = {}
    for x in plan:
        for r, v in spread(x, points(d, x)[0]).items():
            plan_reg[r] = plan_reg.get(r, 0) + v
    st = steer(d, ctx, plan_reg or None, dt.date.fromisoformat(date))
    rows, reg, total, pts = [], {}, 0.0, []
    for x, a in zip(plan, done):
        if not a.get("done", True):
            rows.append({"name": x["name"], "done": False, "points": 0, "style": x.get("style")})
            pts.append(0.0)
            continue
        w = x["weight"] if a.get("weight") is None else float(a["weight"])
        reps = x["reps"] if a.get("reps") is None else int(a["reps"])
        sets = x["sets"] if a.get("sets") is None else int(a["sets"])
        hold = x.get("hold") if a.get("hold") is None else int(a["hold"])
        secs = x.get("seconds") if a.get("seconds") is None else int(a["seconds"])
        if hold is not None and (not 0 <= hold <= 120 or hold and not reps):
            raise ValueError("Hold is 0–120 seconds per rep; static holds use seconds")
        if secs is not None and not 1 <= secs <= 600:
            raise ValueError("Static hold is 1–600 seconds")
        if a.get("failure") is not None and not isinstance(a["failure"], bool):
            raise ValueError("Failure must be true or false")
        fail = bool(a.get("failure"))
        lrir, lrpe = (0, 10) if fail else (rir, rpe)
        k = key(x["name"])
        known = (s["strength"].get(k) or {}).get("e1rm_kg")
        why = a.get("why") if (x.get("weight") is not None and w is not None and w < x["weight"]) else None
        wkg = _kg(x, w)
        new_rm = None
        if x.get("scored") and x["kind"] in MAX_BASED and wkg and reps and reps <= 20:
            # the yardstick: the known max, or the one the plan implied (its weight at ~2 reps in reserve) - so a heavier
            # set than planned counts as harder, a lighter one as easier
            anchor = known or (one_rm(_kg(x), x["reps"], 10 - PLAN_RPE) if x.get("weight") and x.get("reps") else None)
            if why == "too_heavy":
                new_rm = one_rm(wkg, reps, 0)                        # that was the limit
                p_, det = points(d, x, e1rm=anchor or one_rm(wkg, reps, 0))   # the load as planned
                det["note"] = "too heavy: the load stays as planned; strength estimate lowered"
            else:
                from_set = one_rm(wkg, reps, lrir)
                if fail:
                    new_rm = from_set                                # to failure: that set was the limit
                elif x["reps"] and reps < x["reps"] and (w or 0) <= (x["weight"] or 0):
                    new_rm = one_rm(wkg, reps, 0)                    # missed reps: at the limit
                elif from_set > (known or anchor or 0) or not (known or anchor):
                    new_rm = from_set
                # no history: at the planned weight, the plan's guess or what the reported effort says, whichever is stronger
                # (an easy set means the weight was further from the max than the plan assumed); heavier than planned is
                # judged against the plan, so it counts as harder
                yard = known or (max(anchor or 0, from_set) if (w or 0) <= (x.get('weight') or 0) else (anchor or from_set))
                p_, det = points(d, x, weight=w, reps=reps, sets=sets, rpe=lrpe, e1rm=yard, hold=hold)
                if why == "chose":
                    det["note"] = "chose lighter: the load is what was lifted"
        else:
            if why == "too_heavy":
                p_, det = points(d, x, rpe=lrpe)
                det["note"] = "too heavy: the load stays as planned"
            else:
                p_, det = points(d, x, weight=w, reps=reps, sets=sets, rpe=lrpe, hold=hold, seconds=secs)
        if new_rm:
            s["strength"][k] = {"name": x["name"], "e1rm_kg": round(new_rm, 1), "date": date,
                                "from": f"{w:g} {x['unit']} x {reps}" + (" (too heavy)" if why == "too_heavy" else "")}
        for r, v in spread(x, p_).items():
            reg[r] = reg.get(r, 0) + v
        total += p_
        pts.append(p_)
        rows.append({"name": x["name"], "done": True, "weight": w, "unit": x["unit"], "reps": reps, "sets": sets,
                     "seconds": secs, "hold": hold, "failure": fail or None, "tempo": x.get("tempo"), "points": round(p_, 1), "why": why, **det,
                     "style": x.get("style"), "regions": x.get("regions") or {}})
    entry = {"date": date, "session": sess["name"], "rpe": rpe, "wellness": wellness, "lifts": rows,
             "points_total": round(total, 1), "regions": {r: round(v, 1) for r, v in reg.items()},
             "leg_points": round(sum(v for r, v in reg.items() if r in LEG_REGIONS), 1),
             "unscored": [x["name"] for x in plan if not x.get("scored")],
             "minutes": sess.get("minutes") or estimate_minutes(plan), "compare_last": compare_last,
             "steer_share": st["restorative_share"], "steer_mode": st["mode"],
             "restorative_share": restorative_share([{"style": r.get("style")} for r in rows], pts),
             "override": override or sess.get("override"),
             "inputs": {"done": done, "rpe": rpe, "wellness": wellness, "session_index": session_index,
                        "compare_last": compare_last, "override": override},
             "logged": dt.datetime.now().isoformat(timespec="minutes")}
    s["logs"] = [l for l in s["logs"] if not (l["date"] == date and l["session"] == sess["name"])] + [entry]
    s["logs"].sort(key=lambda l: l["date"])
    remember(d, [x for x, a in zip(plan, done) if a.get("done", True)], date, done=True)
    return entry


def followup(d, log_date, ratings, compare=None, note=None, today=None):
    """How the regions from the session on `log_date` feel now (1-10, 10 = very sore), and how it compared."""
    s = state(d)
    if not any(l["date"] == log_date for l in s["logs"]):
        raise ValueError(f"no logged lift session on {log_date}")
    clean_r = {r: max(1, min(10, int(v))) for r, v in (ratings or {}).items() if r in regions()}
    if not clean_r:
        raise ValueError("rate at least one region 1-10")
    if compare not in (None, "easier", "same", "harder"):
        raise ValueError("compare is easier, same or harder")
    s["followups"][log_date] = {"date": (today or dt.date.today()).isoformat(), "regions": clean_r,
                                "compare": compare, "note": str(note or "")[:300]}
    return s["followups"][log_date]


def pending_followup(d, today=None):
    today = today or dt.date.today()
    s = state(d)
    for l in reversed(s["logs"]):
        age = (today - dt.date.fromisoformat(l["date"])).days
        if age > FOLLOW_DAYS[1]:
            break
        if FOLLOW_DAYS[0] <= age and l["date"] not in s["followups"] and l["regions"]:
            top = sorted(l["regions"], key=l["regions"].get, reverse=True)[:4]
            return {"log_date": l["date"], "session": l["session"], "days_ago": age,
                    "regions": [{"key": r, "name": regions()[r]} for r in top]}
    return None


# ── the region blocks, fitted ───────────────────────────────────────────────
def _simulate(events, first, today, ref):
    """events: {date: points} for one region -> {date: blocks}."""
    decay = 2 ** (-1 / HALF_LIFE_DAYS)
    out, score, day = {}, 0.0, first
    while day <= today:
        score *= decay
        score += events.get(day.isoformat(), 0.0) / ref
        out[day.isoformat()] = score
        day += dt.timedelta(days=1)
    return out


def _predict(blocks):
    return max(1.0, min(10.0, 1 + 5 * blocks / THRESHOLD))


def model(d, today=None):
    """Each region's lifting block: what it's carrying now, one block's size (fitted to follow-ups), when it's clear."""
    today = today or dt.date.today()
    s = state(d)
    logs = [l for l in s["logs"] if l["date"] <= today.isoformat()]
    out = {}
    if not logs:
        return {"regions": out, "threshold_blocks": THRESHOLD, "sessions": 0}
    first = dt.date.fromisoformat(logs[0]["date"])
    for r in {r for l in logs for r in l["regions"]}:
        events = {}
        for l in logs:
            if l["regions"].get(r):
                events[l["date"]] = events.get(l["date"], 0) + l["regions"][r]
        doses = [v for _, v in sorted(events.items())][:3]
        initial = max(5.0, 3 * statistics.median(doses)) if doses else DEFAULT_REF
        obs = [(f["date"], v, REPORT_SD) for ld, f in s["followups"].items() for rr, v in f["regions"].items() if rr == r and f["date"] <= today.isoformat()]
        obs += [(sun, w["lift"][r], WEEKLY_SD) for sun, w in (d.get("weekly") or {}).items()     # the Sunday check-in: the anchor
                if r in (w.get("lift") or {}) and sun <= today.isoformat() and sun >= logs[0]["date"]]
        reviewed = next((x for x in reversed(d.get('capacity_adjustments', [])) if x['target']=='lift_'+r and x['date']<=today.isoformat()), None)
        if reviewed:
            initial = reviewed['reference']
            obs = [x for x in obs if x[0]>reviewed['date']]
        ref, interval = initial, None
        if obs:
            logw = []
            for g in GRID:
                hist = _simulate(events, first, today, initial * g)
                ll = sum(-0.5 * ((y - _predict(hist.get(dd, 0.0))) / sd) ** 2 for dd, y, sd in obs)
                logw.append(ll - 0.5 * (math.log(g) / PRIOR_SD) ** 2)
            top = max(logw); w = [math.exp(x - top) for x in logw]; tot = sum(w); w = [x / tot for x in w]
            ref = initial * math.exp(sum(wi * math.log(g) for wi, g in zip(w, GRID)))
            cum, lo, hi = 0.0, None, None
            for wi, g in zip(w, GRID):
                cum += wi
                lo = initial * g if lo is None and cum >= 0.1 else lo
                hi = initial * g if hi is None and cum >= 0.9 else hi
            interval = [round(lo, 1), round(hi, 1)]
        hist = _simulate(events, first, today, ref)
        blocks = hist[today.isoformat()]
        clear = 0 if blocks < 1.0 else math.ceil(math.log(1.0 / blocks) / math.log(2 ** (-1 / HALF_LIFE_DAYS)))
        out[r] = {"name": regions()[r], "blocks": round(blocks, 2), "reference": round(ref, 1), "reference_interval": interval,
                  "reference_from": "reviewed capacity + follow-ups" if reviewed else f"fitted to {len(obs)} follow-up{'s' if len(obs) != 1 else ''}" if obs else "first sessions · provisional",
                  "follow_ups_used": len(obs), "under_one_block_in_days": clear,
                  "leg": r in LEG_REGIONS}
    return {"regions": out, "threshold_blocks": THRESHOLD, "sessions": len(logs),
            "method": f"{HALF_LIFE_DAYS}-day half-life; each region's block fitted to follow-up ratings · estimates"}


def unscored_sessions(d, today=None):
    today = (today or dt.date.today()).isoformat()
    out = []
    for date, p in sorted(d["plans"].items()):
        if date < today:
            continue
        for i, s_ in enumerate(p.get("sessions") or []):
            if s_.get("sport") == "gym" and any(not x.get("scored") for x in s_.get("lifts") or []):
                out.append({"date": date, "index": i, "name": s_["name"], "lifts": s_["lifts"]})
    return out


def summary(d, today=None, ctx=None):
    s = state(d)
    return {"unit": s["unit"], "regions": regions(), "kinds": list(KINDS), "styles": list(STYLES),
            "rules": rules(d), "guidance": GUIDANCE, "steer": steer(d, ctx, None, today),
            "steer_without_legs": steer(d, ctx, ["abs", "obliques", "lower_back", "biceps", "forearms"], today),
            "unscored_sessions": unscored_sessions(d, today),
            "library": sorted(s["library"].values(), key=lambda e: (-e.get("times_done", 0), e["name"]))[:60],
            "strength": {v["name"]: {"e1rm": round(v["e1rm_kg"] / KG[s["unit"]]), "unit": s["unit"], "date": v["date"], "from": v["from"]}
                         for v in s["strength"].values()},
            "recent": [{k: v for k, v in l.items() if k != "inputs"} for l in s["logs"][-10:][::-1]],
            "followups": s["followups"], "pending_followup": pending_followup(d, today),
            "recovery": model(d, today)}
