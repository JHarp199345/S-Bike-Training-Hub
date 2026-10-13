"""lifting_framework.py - the joint framework the assistant plans lifting with (Jesse's design, 2026-10-11).

Private brief: docs/design/lifting-joint-framework.md. This module is the structure only: the joints, how they
group, which ways they move, the load levels and the shapes a session can take, plus a way to describe what a
drafted session covers. It is not the rulebook: training rules (load caps, pairings, spacing) come later and are
reviewed separately. Manual workouts never go through it; the assistant plans inside it.

Six joints in three groups:
  upper  shoulder, elbow, wrist
  trunk  spine, hip
  lower  knee, ankle

Exercises are tagged by how their strain spreads over the hub's body regions (the library's `shares`, the same
regions get_lifting uses). Each region maps onto the joints it moves; muscles that cross two joints are split
(hamstrings: hip and knee; calves: ankle and a little knee). So a squat honestly counts as trunk and lower: the
hips do about half the work, and the hip belongs to the trunk group.
"""
JOINTS = {
    "shoulder": {"group": "upper", "directions": [
        "flexion (raise the arm forward)", "extension (pull the arm down and back)",
        "abduction (raise the arm to the side)", "adduction (bring the arm to the side)",
        "horizontal push (press away from the chest)", "horizontal pull (row toward the chest)",
        "vertical push (press overhead)", "vertical pull (pull down from overhead)",
        "internal rotation", "external rotation",
        "shoulder-blade elevation and depression (shrug, pull down)", "shoulder-blade protraction and retraction"]},
    "elbow": {"group": "upper", "directions": ["flexion (curl)", "extension (press out, triceps)"]},
    "wrist": {"group": "upper", "directions": ["flexion", "extension", "grip and forearm rotation"]},
    "spine": {"group": "trunk", "directions": [
        "flexion (crunch)", "extension (back extension)", "rotation", "side bending",
        "anti-extension (resist arching: plank, rollout)", "anti-rotation (resist twisting: Pallof press)",
        "anti-side-bending (resist leaning: suitcase carry)"]},
    "hip": {"group": "trunk", "directions": [
        "extension (hinge, thrust, drive up from a squat)", "flexion (knee raise)",
        "abduction (leg out to the side)", "adduction (leg in)", "internal rotation", "external rotation"]},
    "knee": {"group": "lower", "directions": ["extension (squat up, leg extension)", "flexion (leg curl)"]},
    "ankle": {"group": "lower", "directions": ["plantarflexion (calf raise, push off)", "dorsiflexion (shin, toes up)"]},
}
GROUPS = {
    "upper": {"name": "Upper", "joints": ["shoulder", "elbow", "wrist"]},
    "trunk": {"name": "Trunk", "joints": ["spine", "hip"]},
    "lower": {"name": "Lower", "joints": ["knee", "ankle"]},
}
# Body region -> the joints it moves (fractions add to 1).
REGION_JOINTS = {
    "shoulders": {"shoulder": 1.0}, "scapula": {"shoulder": 1.0}, "pecs": {"shoulder": 1.0},
    "serratus": {"shoulder": 1.0}, "lats": {"shoulder": 0.85, "spine": 0.15},
    "traps": {"shoulder": 0.65, "spine": 0.35},
    "triceps": {"elbow": 0.85, "shoulder": 0.15}, "biceps": {"elbow": 0.85, "shoulder": 0.15},
    "forearms": {"wrist": 0.7, "elbow": 0.3},
    "abs": {"spine": 1.0}, "obliques": {"spine": 1.0}, "trunk": {"spine": 1.0}, "lower_back": {"spine": 1.0},
    "glutes": {"hip": 1.0}, "hip_flexors": {"hip": 1.0}, "adductors": {"hip": 1.0},
    "hamstrings": {"hip": 0.6, "knee": 0.4}, "quads": {"knee": 0.85, "hip": 0.15},
    "calves": {"ankle": 0.85, "knee": 0.15},
}
# Load levels as a share of the athlete's estimated one-rep maximum. Maximal (above heavy) is for tests only.
LOADS = {   # 2026-10-11: one intensity scale, % of the estimated max; heavy goes as far as is safe, never maxing
    "light": {"min_pct": 30, "max_pct": 60, "note": "Light can go well below 60% when 60% is hard for what is asked."},
    "medium": {"min_pct": 61, "max_pct": 80, "note": "Where most building happens: about 70-80% builds well."},
    "heavy": {"min_pct": 81, "max_pct": 105, "note": "As far as is safe, in small steps (for long-time lifters 1% is a lot). "
                                                     "The hub never prescribes maxing; it estimates the max instead."},
}
# The shapes a session can take: main exercises by how many groups are worked.
MAIN_RANGE = {1: (1, 3), 2: (1, 6), 3: (1, 6)}
MINOR_MAX = 3            # proposed: a few minor exercises (forearms, biceps, triceps, calves) on top of the mains
COUNTS_FROM = 25.0       # proposed: an exercise works a group when the group takes at least this % of it
STATUS = ("Structure only. Training rules (load caps for many main lifts or two big groups together, heavy spinal "
          "loading, spacing) are still being written; plan conservatively and explain your choices.")


def joints_of(shares):
    """{region: share} -> {joint: percent}, ignoring regions the framework doesn't know."""
    total = sum(v for k, v in (shares or {}).items() if k in REGION_JOINTS and v > 0)
    out = {j: 0.0 for j in JOINTS}
    if total <= 0:
        return out
    for region, v in shares.items():
        for joint, f in REGION_JOINTS.get(region, {}).items():
            if v > 0:
                out[joint] += v / total * f * 100
    return {j: round(p, 1) for j, p in out.items()}


def groups_of(shares):
    """{region: share} -> {group: percent}."""
    joints = joints_of(shares)
    return {g: round(sum(joints[j] for j in info["joints"]), 1) for g, info in GROUPS.items()}


def worked(groups):
    """The groups an exercise counts toward (its share reaches COUNTS_FROM), largest first."""
    return [g for g, p in sorted(groups.items(), key=lambda x: -x[1]) if p >= COUNTS_FROM]


def load_level(pct):
    if pct is None:
        return None
    if pct > LOADS["heavy"]["max_pct"]:
        return "maximal"
    for name in ("light", "medium", "heavy"):
        if pct <= LOADS[name]["max_pct"]:
            return name
    return None


def describe(exercises, library=None):
    """What a drafted session covers. exercises: [{name, role: main|minor, shares {region: share} (or a library
    name to look up), sets (default 1), load: light|medium|heavy, or load_pct}]. Returns each exercise's joints and
    groups, the session's blend (weighted by sets), the groups its main exercises work, and whether its shape fits
    the framework. Describes; never judges training quality or applies rules."""
    library = library or {}
    rows, blend, notes = [], {g: 0.0 for g in GROUPS}, []
    for ex in exercises or []:
        name = str(ex.get("name") or "").strip()
        shares = ex.get("shares") or ex.get("regions") or (library.get(name.lower()) or library.get(_key(name)) or {}).get("shares")
        if not shares:
            notes.append(f"{name or 'An exercise'} has no region shares and was left out of the blend.")
            rows.append({"name": name, "role": ex.get("role", "main"), "joints": None, "groups": None, "works": []})
            continue
        g = groups_of(shares)
        sets = max(1.0, float(ex.get("sets") or 1))
        for k, v in g.items():
            blend[k] += v * sets
        pct = ex.get("load_pct")
        level = ex.get("load") or load_level(pct)
        rows.append({"name": name, "role": ex.get("role", "main"), "sets": sets, "joints": joints_of(shares),
                     "groups": g, "works": worked(g), "load": level, "load_pct": pct})
    total = sum(blend.values()) or 1
    blend = {k: round(v / total * 100) for k, v in blend.items()}
    mains = [r for r in rows if r["role"] != "minor"]
    minors = [r for r in rows if r["role"] == "minor"]
    covered = sorted({g for r in mains for g in r["works"]}, key=list(GROUPS).index)
    lo, hi = MAIN_RANGE.get(len(covered), (0, 0))
    shape = {"groups": covered, "main_exercises": len(mains), "minor_exercises": len(minors),
             "main_range": [lo, hi] if covered else None}
    if mains and not covered:
        notes.append("No main exercise reaches the counting threshold for any group.")
    if covered and not lo <= len(mains) <= hi:
        notes.append(f"{len(mains)} main exercises is outside {lo}-{hi} for {len(covered)} group(s).")
    if len(minors) > MINOR_MAX:
        notes.append(f"{len(minors)} minor exercises is more than the suggested {MINOR_MAX}.")
    if any(r.get("load") == "maximal" for r in rows):
        notes.append("A load above heavy is maximal: tests only.")
    return {"exercises": rows, "blend": blend, "shape": shape, "fits_framework": not notes, "notes": notes,
            "status": STATUS}


def framework(library=None):
    """Everything the assistant needs to plan inside the framework, with the athlete's library tagged by group."""
    tagged = []
    for key, item in sorted((library or {}).items()):
        shares = item.get("shares")
        if shares:
            g = groups_of(shares)
            tagged.append({"name": item.get("name") or key, "groups": g, "works": worked(g), "kind": item.get("kind")})
    return {
        "about": ("Plan lifting by joints. Six joints in three groups; a session works one, two or three groups with a "
                  "number of main exercises, plus a few minor ones, at a load level. Compose original sessions from your "
                  "own exercise knowledge: give every exercise region shares (the regions below) so the hub can see "
                  "which joints and groups it works, and check drafts with describe_lift_structure. Use it for exercise "
                  "and workout ideas too, including during a session, and search the web for exercises when you can "
                  "(new ideas, variations, how to do them safely). Manual workouts "
                  "entered by the athlete or a coach are not bound by this."),
        "groups": GROUPS, "joints": JOINTS, "regions": REGION_JOINTS, "loads": LOADS,
        "session_shapes": {"main_exercises_by_groups": {str(k): list(v) for k, v in MAIN_RANGE.items()},
                           "minor_exercises_max": MINOR_MAX, "an_exercise_works_a_group_from_pct": COUNTS_FROM,
                           "examples": ["Upper only, 1-3 main exercises", "Trunk + lower, 1-6 (one compound can cover both)",
                                        "Upper + trunk + lower, 1-6 (a goblet squat to press covers all three)",
                                        "Easy day: all three groups, 1 exercise, light, a few sets"]},
        "library": tagged, "status": STATUS,
    }


# --- Session classifiers (2026-10-11; docs/design/lifting-classifiers.md) ----------------------------------
# Type = how many muscle groups the main exercises work (1-3). Duration = main exercises per group (1-3).
# Intensity = light / medium / heavy on the one % of max scale above. Style = how the weight is moved. Every session
# also carries two supporting minors (sport support and core), outside type and duration. Each lift is judged against
# its own record: the athlete's estimated max for it and what they actually moved the last time they did it.
STYLES = {
    "standard": {"sets": [3, 4], "reps": [6, 12], "about": "Regular sets, e.g. 3 x 10: the accepted volume; at medium (70-80%) a solid workout."},
    "endurance": {"sets": [2, 3], "reps": [15, 25], "about": "Few sets of many reps."},
    "power_explosive": {"sets": [5, 8], "reps": [1, 4], "about": "Many short sets, each moved fast, full rest between."},
    "power_heavy": {"sets": [1, 3], "reps": [1, 5], "about": "Few sets of few reps at a high load."},
}
STYLE_TARGET_PCT = {"light": 45, "medium": 70, "heavy": 85}
SPORT_SUPPORT = {
    "swim": ["Band external rotation", "Straight-arm pulldown"],
    "run": ["Single-leg calf raise", "Side-lying hip abduction"],
    "ride": ["Single-leg glute bridge", "Step-up"],
}
CORE = {"anti-rotation": ["Pallof press", "Side plank", "Dead bug"], "rotation": ["Cable chop", "Russian twist", "Half-kneeling cable lift"]}


def style_of(sets, reps):
    """How the weight was moved, from sets and reps (Jesse's styles; more can be added)."""
    sets, reps = float(sets or 0), float(reps or 0)
    if not sets or not reps:
        return None
    if reps >= 15:
        return "endurance"
    if reps <= 4 and sets >= 5:
        return "power_explosive"
    if reps <= 5:
        return "power_heavy"
    return "standard"


def _key(name):
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _total(x):
    """Total weight moved: weight x reps x sets, counted once for a per-side lift so sessions compare like for like;
    None when not recorded."""
    rows = x.get("set_details") or []
    if rows:
        t = sum(float(r.get("weight") or 0) * float(r.get("reps") or 0) for r in rows)
    else:
        if not x.get("weight") or not x.get("reps"):
            return None
        t = float(x["weight"]) * float(x["reps"]) * float(x.get("sets") or 1)
    return round(t, 1) or None


def last_time(name, logs, before):
    """The most recent logged performance of this lift before a date."""
    k = _key(name)
    for log in sorted(logs or [], key=lambda l: l.get("date", ""), reverse=True):
        if log.get("date", "") >= before:
            continue
        done = [x for x in log.get("lifts") or [] if _key(x.get("name")) == k and _total(x)]
        if done:   # every entry of the lift that session (warm-up and working sets), its heaviest set shown
            top = max(done, key=lambda x: float(x.get("weight") or 0))
            return {"date": log["date"], "weight": top.get("weight"), "reps": top.get("reps"), "sets": sum(int(x.get("sets") or 1) for x in done),
                    "entries": len(done), "total": round(sum(_total(x) for x in done), 1)}
    return None


def classify(exercises, logs=None, strength=None, date="9999-12-31", library=None, unit="lb"):
    """Type, duration, intensity and style of a session, and each lift against its own record.
    exercises: [{name, section or role (main|minor), sets, reps, weight, per_side, regions/shares}]."""
    import math
    library, strength = library or {}, strength or {}
    kg = {"kg": 1.0, "lb": 0.45359237}[unit]
    rows, counts = [], {}
    for x in exercises or []:
        role = "minor" if (x.get("section") or x.get("role")) == "minor" else "main"
        shares = x.get("regions") or x.get("shares") or (library.get(_key(x.get("name"))) or library.get(str(x.get("name", "")).lower()) or {}).get("shares")
        groups = groups_of(shares) if shares else {}
        works = worked(groups) if groups else []
        e1rm = (strength.get(_key(x.get("name"))) or {}).get("e1rm_kg")
        pct_max = round(float(x["weight"]) * kg / e1rm * 100) if e1rm and x.get("weight") else None
        prev = last_time(x.get("name"), logs, date)
        total = _total(x)
        pct_last = round(total / prev["total"] * 100) if total and prev else None
        level = load_level(pct_max) if pct_max is not None else (load_level(pct_last) if pct_last is not None else None)
        row = {"name": x.get("name"), "role": role, "works": works, "sets": x.get("sets"), "reps": x.get("reps"),
               "weight": x.get("weight"), "total_moved": total, "pct_of_estimated_max": pct_max,
               "last_time": prev, "pct_of_last_time": pct_last, "intensity": level,
               "style": "restorative" if x.get("style") == "restorative" else style_of(x.get("sets"), x.get("reps"))}
        rows.append(row)
        if role == "main" and works:
            counts[works[0]] = counts.get(works[0], 0) + 1
    mains = [r for r in rows if r["role"] == "main"]
    groups = [g for g in GROUPS if g in counts]
    typ = len(groups) or None
    duration = max(counts.values()) if counts else None
    weighted = [(r["pct_of_estimated_max"] if r["pct_of_estimated_max"] is not None else r["pct_of_last_time"], r["total_moved"] or 1)
                for r in mains if (r["pct_of_estimated_max"] is not None or r["pct_of_last_time"] is not None)]
    pct = round(sum(p * w for p, w in weighted) / sum(w for _, w in weighted)) if weighted else None
    styles = [r["style"] for r in mains if r["style"]]
    if styles.count("restorative") * 2 > len(styles):   # mostly holds, mobility and loaded stretching
        intensity_note = "restorative"
    else:
        intensity_note = None
    style = max(set(styles), key=styles.count) if styles else None
    intensity = "light" if intensity_note else load_level(pct)
    label = " · ".join(v for v in (f"Type {typ}" if typ else None, f"Duration {duration}" if duration else None,
                                   intensity.title() if intensity else None, (style or "").replace("_", " ").title() or None) if v)
    return {"label": label, "type": typ, "groups": groups, "duration": duration, "main_per_group": counts,
            "intensity": intensity, "pct": pct, "style": style, "exercises": rows,
            "minors": [r["name"] for r in rows if r["role"] == "minor"],
            "basis": "Intensity is % of each lift's estimated max (or of what was moved last time when no max is known), "
                     "weighted by total weight moved. Heavy goes as far as is safe; the hub never prescribes maxing."}


def design_context(lift_state, groups, duration, intensity, style, date, improving=(), unit="lb", week=None):
    """Everything to compose one session inside the classifiers, in one answer: the rules, per group the athlete's
    lifts with their last time and a target weight for the intensity, the style's sets and reps, and the two minors."""
    import datetime as dt
    groups = [g for g in groups if g in GROUPS]
    if not groups:
        raise ValueError("groups: one or more of upper, trunk, lower")
    if intensity not in LOADS or style not in STYLES:
        raise ValueError("intensity is light, medium or heavy; style is " + ", ".join(STYLES))
    duration = max(1, min(3, int(duration or 1)))
    kg = {"kg": 1.0, "lb": 0.45359237}[unit]
    logs, strength = lift_state.get("logs") or [], lift_state.get("strength") or {}
    seen = {}
    for log in logs:
        for x in log.get("lifts") or []:
            if x.get("name") and (x.get("regions") or x.get("shares")):
                seen[_key(x["name"])] = (x["name"], x.get("regions") or x.get("shares"))
    for k, v in (lift_state.get("library") or {}).items():
        if v.get("shares"):
            seen.setdefault(_key(v.get("name") or k), (v.get("name") or k, v["shares"]))
    rules = [r.get("text") for r in lift_state.get("rules") or []]
    never = [str(r.get("excludes") or "").lower() for r in lift_state.get("rules") or [] if r.get("kind") == "never" and r.get("excludes")]
    pct = STYLE_TARGET_PCT[intensity]
    by_group = {g: [] for g in groups}
    for k, (name, shares) in seen.items():
        if any(n and n in k for n in never):
            continue
        g = groups_of(shares)
        w = worked(g)
        if not w or w[0] not in by_group:
            continue
        e1rm = (strength.get(k) or {}).get("e1rm_kg")
        by_group[w[0]].append({"name": name, "works": w, "last_time": last_time(name, logs, date),
                               "estimated_max": round(e1rm / kg) if e1rm else None,
                               "target_weight": (round(e1rm * pct / 100 / kg / 5) * 5) if e1rm else None})
    for g in by_group:
        by_group[g].sort(key=lambda r: (r["last_time"] is None, r["name"]))
    iso = (week or dt.date.fromisoformat(date).isocalendar()[1])
    core_kind = "anti-rotation" if iso % 2 == 0 else "rotation"
    support = [x for s in improving for x in SPORT_SUPPORT.get(s, [])] or SPORT_SUPPORT["run"]
    return {"target": {"type": len(groups), "groups": groups, "duration": duration, "main_exercises": len(groups) * duration,
                       "intensity": {"name": intensity, **LOADS[intensity], "aim_pct": pct}, "style": {"name": style, **STYLES[style]}},
            "rules": rules, "candidates_by_group": by_group,
            "minors": {"sport_support": support, "core": {"this_week": core_kind, "options": CORE[core_kind]},
                       "dose": "2 x 10-15, light to medium; outside type and duration; chosen away from tissue a hard session loads that day"},
            "how": ("Pick the main exercises from the candidates (or search the web for others that fit the group and the "
                    "athlete's rules; name the source), set each one's weight from its target or last time, use the style's "
                    "sets and reps, add the two minors, then check with describe_lift_structure, which now returns the "
                    "classifiers. Judge each lift against its own last time. Never prescribe maxing.")}


# --- Choosing intensity and style from the athlete's own responses (v1, 2026-10-12) ---------------------------------
# Start from the phase (build ~70-80%, maintain light-medium, taper light at 40-60% of usual volume, recovery light),
# then let the last few sessions' responses move it: a "too hard" report or next-day soreness of 6+ steps down one
# level; clean reports allow a step up when building. Every step says why. Fitting a personal response curve from the
# reports is the long-term aim; this is the transparent first version.
LEVELS = ("light", "medium", "heavy")
PHASE_START = {"build": ("medium", "standard", 2), "improve": ("medium", "standard", 2), "maintain": ("medium", "standard", 1),
               "base": ("medium", "standard", 1), "taper": ("light", "standard", 1), "recovery": ("light", "standard", 1)}


def past_responses(lift_state, feedback=None, limit=5):
    """The last sessions with their classifiers, how they were reported and the next-day follow-up."""
    logs = sorted(lift_state.get("logs") or [], key=lambda l: l.get("date", ""))
    follow = lift_state.get("followups") or {}
    fb = {}
    for f in (feedback or {}).values():
        if f.get("sport") == "gym" and f.get("date"):
            fb.setdefault(f["date"], f)
    out = []
    for log in logs[-limit:]:
        c = classify(log.get("lifts"), logs, lift_state.get("strength"), log.get("date", "9999"), lift_state.get("library"), lift_state.get("unit", "lb"))
        fu = follow.get(log.get("date")) or {}
        sore = max((v for v in (fu.get("regions") or {}).values() if isinstance(v, (int, float))), default=None)
        rep = fb.get(log.get("date")) or {}
        out.append({"date": log.get("date"), "label": c["label"] or None, "intensity": c["intensity"], "style": c["style"],
                    "effort": rep.get("effort") or (log.get("rpe") and f"rpe {log['rpe']}"), "next_day_soreness_max": sore,
                    "next_day_compare": fu.get("compare")})
    return out


def recommend(lift_state, feedback=None, phase="build", checkin=None):
    """A starting intensity, style and duration for the next session, and why."""
    intensity, style, duration = PHASE_START.get(phase, PHASE_START["maintain"])
    why = [f"{phase} phase starts at {intensity}, {style}, duration {duration}"]
    volume = None
    if phase == "taper":
        volume = {"cut_range": [0.4, 0.6], "cut": 0.5,
                  "why": "Taper: about half the usual lifting volume until the reports show how long fitness holds for this athlete."}
    recent = past_responses(lift_state, feedback, 3)
    hard = [r for r in recent if r["effort"] == "too_hard" or (r["next_day_soreness_max"] or 0) >= 6 or r["next_day_compare"] == "worse"]
    clean = recent and all(r["effort"] in ("as_intended", "too_easy") and (r["next_day_soreness_max"] or 0) <= 3 for r in recent)
    i = LEVELS.index(intensity)
    if hard:
        i = max(0, i - 1)
        why.append(f"stepped down: {hard[-1]['date']} was reported hard or sore the next day")
    elif clean and phase in ("build", "improve") and i < 2:
        i += 1
        why.append("stepped up: the last sessions were reported as intended with little next-day soreness")
    sore_now = max((float((checkin or {}).get(k) or 0) for k in ("legs", "shoulders")), default=0)
    if sore_now >= 6:
        i = max(0, i - 1)
        why.append(f"today's check-in reports {sore_now:g}/10 soreness: one level easier")
    return {"intensity": LEVELS[i], "style": style, "duration": duration, "volume": volume, "why": why, "past_responses": recent}
