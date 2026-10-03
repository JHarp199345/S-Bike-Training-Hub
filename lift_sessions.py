"""lift_sessions.py - how a lifting session is built (the rider's design, 2026-10-03).

  2 main compound lifts + 3 minor (a single-limb lift, a prehab isolation, core) at 45 minutes;
  2 main + 1 minor (prehab) at 30; at 60 a third main lift and its supporting minor are added. A power block
  (jumps or med-ball throws, 5 min after the warm-up) is the athlete's option.

The main lifts follow the session's focus (the athlete's split). The minor lifts are drawn from support pools for
the athlete's sports - swim dryland, run support, bike support - weighted toward the sports being improved, and
kept off tissue that tomorrow's hard session needs. The core slot alternates anti-rotation and rotation (the
trunk has to resist the roll and drive it). Every slot has ranked alternatives, so an exercise the athlete's
rules exclude ("I can't do pull ups", "No barbell deadlifts") is swapped for the next, never dropped.

Phases set reps and effort, never to failure (reps in reserve, RIR): base 2-3 x 10-12 (RIR 3-4); build 3-4 x 4-6
(RIR 2-3, heavy); event-specific 2-3 x 3-5 with explosive intent (RIR 3); taper / maintenance 1-2 sets (RIR 3+);
check weeks a single comfortable 6-10 rep set (RIR 2-3). Minor lifts stay 2-3 x 8-15 (RIR 2-3), one set in a taper.
Progression is double progression: when every set reaches the top of its range with the reps in reserve to
spare, add 2.5-5% next time; check weeks reset the numbers.
"""
import math

# name: (kind, region shares, how). Barbell and basic versions sit side by side in the slot lists below.
EX = {
    "BB squat": ("barbell", {"quads": 35, "glutes": 30, "hamstrings": 15, "adductors": 10, "lower_back": 10}, "Squat to a comfortable depth; safeties set."),
    "Goblet squat": ("dumbbell", {"quads": 40, "glutes": 30, "adductors": 15, "trunk": 15}, "Hold the weight at the chest; sit between the hips."),
    "Chair squat": ("bodyweight", {"quads": 35, "glutes": 30, "hamstrings": 15, "adductors": 10, "lower_back": 10}, "Sit back to a chair and stand without using the hands."),
    "BB front squat": ("barbell", {"quads": 45, "glutes": 25, "trunk": 20, "adductors": 10}, "Elbows high; upright torso."),
    "BB Romanian deadlift": ("barbell", {"hamstrings": 40, "glutes": 30, "lower_back": 25, "lats": 5}, "Hinge with a long spine; stop where the hamstrings tighten."),
    "DB Romanian deadlift": ("dumbbell", {"hamstrings": 40, "glutes": 35, "lower_back": 20, "forearms": 5}, "Dumbbells slide down the thighs; long spine."),
    "Single-leg hip hinge": ("bodyweight", {"hamstrings": 40, "glutes": 40, "lower_back": 10, "calves": 10}, "Reach the free leg back; hips square."),
    "BB hip thrust": ("barbell", {"glutes": 65, "hamstrings": 20, "quads": 15}, "Shoulders on a bench; ribs down at the top."),
    "Glute bridge": ("bodyweight", {"glutes": 60, "hamstrings": 30, "lower_back": 10}, "Lift the hips smoothly; squeeze at the top."),
    "BB good morning": ("barbell", {"hamstrings": 40, "lower_back": 35, "glutes": 25}, "Light; hinge with soft knees."),
    "BB bench press": ("barbell", {"pecs": 50, "triceps": 30, "shoulders": 20}, "Safeties or a spotter."),
    "DB bench press": ("dumbbell", {"pecs": 50, "triceps": 25, "shoulders": 20, "trunk": 5}, "Wrists stacked over elbows."),
    "Incline push-up": ("bodyweight", {"pecs": 45, "triceps": 25, "shoulders": 15, "abs": 15}, "Hands on a bench; body in one line."),
    "BB overhead press": ("barbell", {"shoulders": 50, "triceps": 30, "scapula": 10, "abs": 10}, "Press overhead without arching the lower back."),
    "DB overhead press": ("dumbbell", {"shoulders": 50, "triceps": 30, "scapula": 10, "trunk": 10}, "Seated or standing; ribs down."),
    "Pike push-up": ("bodyweight", {"shoulders": 50, "triceps": 30, "pecs": 10, "abs": 10}, "Hips high; head between the hands."),
    "BB row": ("barbell", {"lats": 40, "scapula": 20, "biceps": 20, "lower_back": 20}, "Torso still; pull to the lower ribs."),
    "Single-arm DB row": ("dumbbell", {"lats": 45, "scapula": 25, "biceps": 20, "trunk": 10}, "Hand and knee on a bench; no twisting."),
    "Resistance-band row": ("band", {"lats": 40, "scapula": 30, "biceps": 30}, "Squeeze the shoulder blades back."),
    "Pull-up": ("bodyweight", {"lats": 50, "biceps": 20, "scapula": 15, "forearms": 10, "abs": 5}, "Full hang to chin over the bar; sets of your max minus two."),
    "Lat pulldown": ("machine", {"lats": 50, "biceps": 20, "scapula": 20, "forearms": 10}, "Pull to the upper chest; no leaning back."),
    "Band lat pulldown": ("band", {"lats": 50, "biceps": 20, "scapula": 20, "forearms": 10}, "Band anchored high; pull to the chest."),
    # single-limb
    "Split squat": ("bodyweight", {"quads": 40, "glutes": 30, "adductors": 15, "hamstrings": 10, "calves": 5}, "Rear foot on the floor; controlled depth."),
    "DB step-up": ("dumbbell", {"quads": 40, "glutes": 35, "calves": 15, "adductors": 10}, "Drive through the whole foot on the box."),
    "Step-down": ("bodyweight", {"quads": 50, "glutes": 30, "calves": 10, "adductors": 10}, "Slowly lower the free heel to the floor."),
    "Single-arm DB press": ("dumbbell", {"pecs": 40, "triceps": 25, "shoulders": 20, "obliques": 15}, "One arm on a bench; resist the twist."),
    "Single-arm band row": ("band", {"lats": 45, "scapula": 30, "biceps": 15, "obliques": 10}, "Stand tall; no rotation."),
    # prehab / support
    "Calf raise": ("bodyweight", {"calves": 90, "trunk": 10}, "Slow down, pause at the bottom; single leg when easy."),
    "Bent-knee calf raise": ("bodyweight", {"calves": 95, "quads": 5}, "Knees bent to load the soleus (Achilles health)."),
    "Band hip abduction": ("band", {"glutes": 80, "hip_flexors": 10, "trunk": 10}, "Band at the knees; small, controlled steps or lifts."),
    "Band external rotation": ("band", {"shoulders": 60, "scapula": 40}, "Elbow at the side; rotate out slowly."),
    "Band pull-apart": ("band", {"scapula": 50, "shoulders": 30, "lats": 20}, "Arms straight; squeeze the shoulder blades."),
    "Y-T-W raise": ("bodyweight", {"scapula": 55, "shoulders": 35, "traps": 10}, "Face down on a bench; thumbs up; light."),
    "Straight-arm pulldown": ("cable", {"lats": 60, "triceps": 15, "scapula": 15, "abs": 10}, "Arms long, sweep to the hips: the swim catch."),
    "Hip extension": ("bodyweight", {"glutes": 55, "hamstrings": 35, "lower_back": 10}, "Glute-led; no arching."),
    "Single-leg glute bridge": ("bodyweight", {"glutes": 60, "hamstrings": 30, "trunk": 10}, "Hips level; drive through the heel."),
    "Tibialis raise": ("bodyweight", {"calves": 100}, "Back to a wall; lift the toes (shin health)."),
    # core: anti-rotation and rotation
    "Pallof press": ("band", {"obliques": 50, "abs": 30, "trunk": 20}, "Press out and hold; don't let the band turn you."),
    "Dead bug": ("bodyweight", {"abs": 70, "obliques": 20, "hip_flexors": 10}, "Alternate arm and leg reaches without arching the lower back."),
    "Side plank": ("bodyweight", {"obliques": 60, "abs": 20, "glutes": 20}, "Straight line from head to feet."),
    "Band woodchop": ("band", {"obliques": 55, "abs": 25, "shoulders": 10, "glutes": 10}, "Rotate from the hips and trunk, high to low."),
    "Half-kneeling rotation": ("band", {"obliques": 60, "abs": 25, "scapula": 15}, "Hips still; turn the ribcage."),
    "Med-ball rotational throw": ("medicine_ball", {"obliques": 50, "abs": 20, "glutes": 20, "shoulders": 10}, "Throw against a wall from the hips; catch and reset."),
    # power (optional)
    "Box jump": ("bodyweight", {"quads": 35, "glutes": 30, "calves": 30, "hamstrings": 5}, "Land soft; step down. Low box."),
    "Pogo hops": ("bodyweight", {"calves": 80, "quads": 10, "glutes": 10}, "Quick, stiff ankles; small hops."),
    "Med-ball chest throw": ("medicine_ball", {"pecs": 40, "triceps": 30, "shoulders": 20, "abs": 10}, "Explosive push against a wall."),
}

# per focus: main lifts (each a ranked list: barbell first where it exists), then the third main and its supporting minor
MAINS = {
    "full": [["BB squat", "Goblet squat", "Chair squat"], ["BB row", "Single-arm DB row", "Resistance-band row"],
             (["BB overhead press", "DB overhead press", "DB bench press", "Incline push-up"], ["Band external rotation", "Band pull-apart"])],
    "lower": [["BB squat", "Goblet squat", "Chair squat"], ["BB Romanian deadlift", "DB Romanian deadlift", "Single-leg hip hinge"],
              (["BB hip thrust", "Glute bridge"], ["Band hip abduction", "Single-leg glute bridge"])],
    "legs": [["BB squat", "Goblet squat", "Chair squat"], ["BB Romanian deadlift", "DB Romanian deadlift", "Single-leg hip hinge"],
             (["BB hip thrust", "Glute bridge"], ["Band hip abduction", "Single-leg glute bridge"])],
    "upper": [["BB bench press", "DB bench press", "Incline push-up"], ["BB row", "Single-arm DB row", "Resistance-band row"],
              (["BB overhead press", "DB overhead press", "Pike push-up"], ["Band pull-apart", "Y-T-W raise"])],
    "push": [["BB squat", "Goblet squat", "Chair squat"], ["BB bench press", "DB bench press", "Incline push-up"],
             (["BB overhead press", "DB overhead press", "Pike push-up"], ["Single-arm DB press", "Band external rotation"])],
    "pull": [["BB Romanian deadlift", "DB Romanian deadlift", "Single-leg hip hinge"], ["BB row", "Single-arm DB row", "Resistance-band row"],
             (["Pull-up", "Lat pulldown", "Band lat pulldown"], ["Single-arm DB row", "Single-arm band row"])],
    "knee": [["BB squat", "Goblet squat", "Chair squat"], ["BB front squat", "Split squat", "Step-down"],
             (["DB step-up", "Step-down"], ["Calf raise", "Bent-knee calf raise"])],
    "hip": [["BB Romanian deadlift", "DB Romanian deadlift", "Single-leg hip hinge"], ["BB hip thrust", "Glute bridge"],
            (["BB good morning", "Single-leg hip hinge", "Hip extension"], ["Band hip abduction", "Single-leg glute bridge"])],
    "upper_push": [["BB bench press", "DB bench press", "Incline push-up"], ["BB overhead press", "DB overhead press", "Pike push-up"],
                   (["DB bench press", "Incline push-up"], ["Single-arm DB press", "Band external rotation"])],
    "upper_pull": [["Pull-up", "Lat pulldown", "Band lat pulldown"], ["BB row", "Single-arm DB row", "Resistance-band row"],
                   (["Single-arm DB row", "Single-arm band row"], ["Band pull-apart", "Y-T-W raise"])],
}
SINGLE = {"legs": ["Split squat", "DB step-up", "Step-down"], "upper": ["Single-arm DB row", "Single-arm DB press", "Single-arm band row"]}
SUPPORT = {   # sport-support pools for the prehab slot
    "swim": ["Straight-arm pulldown", "Band external rotation", "Y-T-W raise", "Band pull-apart", "Lat pulldown"],
    "run": ["Bent-knee calf raise", "Calf raise", "Band hip abduction", "Tibialis raise"],
    "ride": ["Single-leg glute bridge", "Hip extension", "Band hip abduction"],
    "gym": ["Band pull-apart", "Band hip abduction", "Calf raise"],
}
CORE = {"anti": ["Pallof press", "Dead bug", "Side plank"], "rotate": ["Band woodchop", "Half-kneeling rotation", "Med-ball rotational throw"]}
POWER = {"legs": ["Box jump", "Pogo hops"], "upper": ["Med-ball chest throw", "Med-ball rotational throw"]}
LEG_FOCUS = {"full", "lower", "legs", "push", "pull", "knee", "hip"}
# what each equipment setting gives: basic is bodyweight and bands; a gym has everything
EQUIPMENT = {"basic": {"bodyweight", "band"}, "barbell": {"barbell", "dumbbell", "kettlebell", "machine", "cable", "band",
                                                           "medicine_ball", "bodyweight"}}

# phase -> (main sets, main reps, main RIR, main rest s, % of estimated max), minor (sets, reps, RIR)
PHASE = {
    "base": ((3, "10-12", "3-4", 90, .62), (2, "12-15", "2-3")),
    "build": ((4, "4-6", "2-3", 150, .80), (3, "8-12", "2-3")),
    "peak": ((4, "4-6", "2-3", 150, .80), (3, "8-12", "2-3")),
    "specific": ((3, "3-5", "3", 150, .72), (2, "8-12", "2-3")),
    "taper": ((2, "3-5", "3+", 150, .72), (1, "8-12", "3")),
    "race_week": ((1, "3-5", "3+", 150, .65), (1, "8-12", "3")),
    "recovery": ((2, "8-10", "4", 90, .55), (1, "10-15", "3-4")),
    "assessment": ((1, "6-10", "2-3", 120, .45), (1, "10-15", "3")),
    "check": ((1, "6-10", "2-3", 120, .55), (1, "10-15", "3")),
}


def _pick(d, options, used, equipment, avoid=()):
    """The first option the athlete's rules allow (barbell only with barbell equipment), not used yet this session,
    and not loading tissue to protect."""
    import lifting
    for name in options:
        kind, shares, _ = EX[name]
        if kind not in EQUIPMENT.get(equipment, EQUIPMENT["barbell"]) or name in used:
            continue
        if avoid and set(shares) & set(avoid) and max((shares[r] for r in avoid if r in shares), default=0) >= 30:
            continue
        if lifting.excluded(d, name, kind):
            continue
        return name
    return None


def _weight(anchor, pct, level):
    import lifting
    if not anchor:
        return None
    unit = anchor["unit"]
    step = 2.5 if unit == "lb" else 1
    pct = pct - {"easy": .05, "moderate": 0, "higher": -.03}.get(level, 0)
    w = anchor["e1rm_kg"] * pct / lifting.KG[unit]
    return min(anchor["weight"], max(step, math.floor(w / step) * step))      # never over the comfortable reported set


def build_session(d, focus, minutes, stage, shape, level, equipment, anchors=None, sports=None, priorities=None,
                  tomorrow=(), power=False, turn=0):
    """(name, lifts, steps) for one lifting session. `tomorrow`: tissue tomorrow's hard sessions need
    ('legs', 'shoulders'); `turn`: how many lifting sessions came before (rotates pools and the core slot)."""
    focus = focus if focus in MAINS else "full"
    phase = "check" if shape == "check" else stage if stage in PHASE else "base"
    (ms, mreps, mrir, mrest, pct), (ns, nreps, nrir) = PHASE[phase]
    size = 1 if minutes < 35 else 3 if minutes < 55 else 4
    avoid = (("quads", "hamstrings", "glutes", "calves") if "legs" in tomorrow else ()) + \
            (("shoulders", "lats", "scapula") if "shoulders" in tomorrow else ())
    used, lifts = set(), []

    def add(name, sets, reps, rir, rest, role, main=False):
        if not name:
            return
        used.add(name)
        kind, shares, how = EX[name]
        anchor = (anchors or {}).get(name) if main else None
        lifts.append({"name": name, "kind": kind, "sets": sets, "reps": int(reps.split("-")[0].split()[0]), "rep_range": reps,
                      "rir": rir, "rest_seconds": rest,
                      "regions": shares, "style": "build", "how": how, "role": role, "equipment": equipment,
                      "weight": _weight(anchor, pct, level), "unit": anchor["unit"] if anchor else "lb",
                      "calibration_basis": None})

    m1, m2, (m3, m3_minor) = MAINS[focus]
    leg_focus = focus in LEG_FOCUS and focus not in ("upper", "upper_push", "upper_pull")
    if power:
        pw = POWER["legs" if leg_focus and "legs" not in tomorrow else "upper"]
        add(_pick(d, pw, used, equipment), 3, "3-5", "fresh", 60, "power")
    add(_pick(d, m1, used, equipment), ms, mreps, mrir, mrest, "main", True)
    add(_pick(d, m2, used, equipment), ms, mreps, mrir, mrest, "main", True)
    if size >= 4:
        add(_pick(d, m3, used, equipment), ms, mreps, mrir, mrest, "main", True)
        add(_pick(d, m3_minor, used, equipment, avoid), ns, nreps, nrir, 60, "minor")
    # prehab / sport support: the sports being improved weigh double; rotate through them session to session
    pools = [sp for sp in (sports or ["gym"]) if sp in SUPPORT]
    weighted = [sp for sp in pools for _ in range(2 if (priorities or {}).get(sp) == "improve" else 1)] or ["gym"]
    sport = weighted[turn % len(weighted)]
    support = SUPPORT[sport][turn // len(weighted) % len(SUPPORT[sport]):] + SUPPORT[sport]
    add(_pick(d, support, used, equipment, avoid) or _pick(d, SUPPORT["gym"], used, equipment, avoid), ns, nreps, nrir, 60, "prehab")
    if size >= 3:
        single = SINGLE["legs" if leg_focus else "upper"]
        add(_pick(d, single, used, equipment, avoid) or _pick(d, SINGLE["upper" if leg_focus else "legs"], used, equipment, avoid),
            ns, nreps, nrir, 75, "single-limb")
        core = CORE["anti" if turn % 2 == 0 else "rotate"]
        add(_pick(d, core, used, equipment) or _pick(d, CORE["anti"], used, equipment), ns, "8-12 / 20-30 s", nrir, 45, "core")
    names = {"full": "full body", "lower": "lower body", "legs": "legs", "upper": "upper body", "push": "push (squat + press)",
             "pull": "pull (hinge + row)", "knee": "knee-dominant", "hip": "hip-dominant", "upper_push": "upper push", "upper_pull": "upper pull"}
    title = ("Strength check" if phase == "check" else "Strength maintenance (light)" if phase in ("taper", "race_week")
             else f"Strength: {names[focus]}") + (f" · {sport} support" if sport != "gym" and phase not in ("check",) else "")
    steps = ["5-8 min easy movement, then 2-3 ramp-up sets of the first lift (about 40%, 60%, 80% of the working weight)"]
    for x in lifts:
        load = f" at {x['weight']} {x['unit']}" if x["weight"] is not None else ""
        steps.append(f"{x['role'].capitalize()}: {x['name']} {x['sets']} × {x['rep_range']}{load}, {x['rir']} reps in reserve, "
                     f"rest {x['rest_seconds']} s. {x['how']}")
    if phase == "check":
        steps.insert(1, "Check week: one comfortable 6-10 rep set per lift with 2-3 reps left, and record it. No maximum attempts.")
    else:
        steps.append("Never to failure. When every set reaches the top of its range with the reps in reserve to spare, add 2.5-5% next time.")
    return title, lifts, steps
