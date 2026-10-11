import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import lifting_framework as F

# every region maps to joints that add up, and every joint belongs to a group
for region, joints in F.REGION_JOINTS.items():
    assert abs(sum(joints.values()) - 1) < 1e-9, region
    assert all(j in F.JOINTS for j in joints), region
assert {j for g in F.GROUPS.values() for j in g["joints"]} == set(F.JOINTS)

# group shares: a bench press is upper, a squat is trunk and lower (hips do half), a shrug is upper and trunk
bench = F.groups_of({"pecs": 50, "triceps": 30, "shoulders": 20})
assert bench["upper"] == 100 and F.worked(bench) == ["upper"]
squat = F.groups_of({"quads": 40, "glutes": 30, "adductors": 15, "trunk": 15})
assert F.worked(squat) == ["trunk", "lower"]
assert set(F.worked(F.groups_of({"traps": 80, "forearms": 20}))) == {"upper", "trunk"}
assert F.groups_of({}) == {"upper": 0, "trunk": 0, "lower": 0}

# load levels
assert F.load_level(30) == "light" and F.load_level(60) == "light" and F.load_level(75) == "medium"
assert F.load_level(88) == "heavy" and F.load_level(95) == "maximal" and F.load_level(None) is None

# a sled push and hip thrusts: two groups, two mains, a minor curl on top; fits
d = F.describe([
    {"name": "Sled push", "shares": {"quads": 40, "glutes": 25, "calves": 20, "hamstrings": 10, "trunk": 5}, "sets": 3},
    {"name": "Hip thrust", "shares": {"glutes": 60, "hamstrings": 25, "quads": 15}, "sets": 3, "load_pct": 75},
    {"name": "Curl", "role": "minor", "shares": {"biceps": 80, "forearms": 20}, "sets": 2}])
assert d["shape"]["groups"] == ["trunk", "lower"] and d["shape"]["main_exercises"] == 2 and d["fits_framework"], d
assert sum(d["blend"].values()) in (99, 100, 101)
assert d["exercises"][1]["load"] == "medium"

# too many mains for one group, too many minors, a maximal load, and an untagged exercise are all noted
press = {"pecs": 60, "triceps": 40}
d = F.describe([{"name": f"Press {i}", "shares": press} for i in range(4)]
               + [{"name": f"Curl {i}", "role": "minor", "shares": {"biceps": 1}} for i in range(4)]
               + [{"name": "Max", "shares": press, "load_pct": 97}, {"name": "Mystery"}])
assert not d["fits_framework"] and len(d["notes"]) == 4, d["notes"]

# library lookup by name, and the framework lists the library tagged by group
lib = {"goblet squat": {"name": "Goblet squat", "shares": {"quads": 40, "glutes": 30, "adductors": 15, "trunk": 15}}}
assert F.describe([{"name": "Goblet squat"}], lib)["exercises"][0]["works"] == ["trunk", "lower"]
fw = F.framework(lib)
assert fw["library"][0]["works"] == ["trunk", "lower"] and fw["session_shapes"]["main_exercises_by_groups"]["3"] == [1, 6]
print("PASS lifting framework: joints, groups, loads, session description")
