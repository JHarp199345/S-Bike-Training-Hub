"""lifting_framework.py - the joint framework the assistant plans lifting with (2026-10-11).

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
LOADS = {
    "light": {"min_pct": 30, "max_pct": 60, "note": "Light can go well below 60% when 60% is hard for what is asked."},
    "medium": {"min_pct": 60, "max_pct": 80},
    "heavy": {"min_pct": 80, "max_pct": 90},
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
        shares = ex.get("shares") or (library.get(name.lower()) or {}).get("shares")
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
