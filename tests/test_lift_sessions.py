"""How a lifting session is built (the rider's design, 2026-10-03): 2 main compound lifts + 3 minor (single-limb,
prehab, core) at 45 minutes, 2 + 1 at 30, a third main and its supporting minor at 60, power on request; minor
lifts from the athlete's sport-support pools, kept off tomorrow's tissue; the core slot alternating anti-rotation
and rotation; the athlete's rules swapping lifts, never dropping them; phases setting sets, reps and effort."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import lift_sessions as L
import lifting

ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


def build(focus="full", minutes=45, stage="build", shape="build", equipment="barbell", d=None, **kw):
    return L.build_session(d or {}, focus, minutes, stage, shape, "moderate", equipment, **kw)


roles = lambda lifts: [x["role"] for x in lifts]
names = lambda lifts: [x["name"] for x in lifts]
t, lifts, steps = build(minutes=30)
check(f"30 min: 2 main + 1 minor ({roles(lifts)})", roles(lifts) == ["main", "main", "prehab"])
t, lifts, steps = build(minutes=45)
check(f"45 min: 2 main + 3 minor ({roles(lifts)})", roles(lifts) == ["main", "main", "prehab", "single-limb", "core"])
t, lifts, steps = build(minutes=60)
check(f"60 min: a third main lift and its supporting minor ({roles(lifts)})",
      roles(lifts).count("main") == 3 and len(lifts) == 7)
t, lifts, steps = build(minutes=45, power=True)
check("power is the athlete's option, first after the warm-up", roles(lifts)[0] == "power")
check("main lifts come first and heaviest", roles(build(minutes=45)[1])[:2] == ["main", "main"])

# the athlete's rules swap lifts; they never leave a hole
d = {}
for r in ["No BB squats", "I can't do pull ups", "No barbell deadlifts"]:
    lifting.add_rule(d, r)
full = names(build(d=d)[1])
check(f"'No BB squats' -> a goblet squat ({full[0]})", full[0] == "Goblet squat")
pull = names(build("upper_pull", d=d)[1])
check(f"'I can't do pull ups' -> a lat pulldown ({pull[0]})", pull[0] == "Lat pulldown")
hip = names(build("hip", d=d)[1])
check(f"'No barbell deadlifts' -> a dumbbell Romanian deadlift ({hip[0]})", hip[0] == "DB Romanian deadlift")
check("…and the session keeps its shape", len(build(d=d)[1]) == 5)
basic = build(equipment="basic")[1]
check("basic equipment: bodyweight and bands only", all(x["kind"] in ("bodyweight", "band") for x in basic))

# phases
main = lambda stage, shape=None: next(x for x in build(stage=stage, shape=shape or stage)[1] if x["role"] == "main")
check("base: 3 x 10-12, 3-4 in reserve", (main("base")["sets"], main("base")["rep_range"], main("base")["rir"]) == (3, "10-12", "3-4"))
check("build: 4 x 4-6, heavy, 2-3 in reserve", (main("build")["sets"], main("build")["rep_range"], main("build")["rir"]) == (4, "4-6", "2-3"))
check("event-specific: 3 x 3-5", (main("specific")["sets"], main("specific")["rep_range"]) == (3, "3-5"))
taper = build(stage="taper", shape="taper")
check("taper: main lifts kept light, minor lifts one set", main("taper")["sets"] == 2 and all(x["sets"] == 1 for x in taper[1] if x["role"] != "main")
      and "light" in taper[0])
chk = build(stage="build", shape="check")
check("check week: one comfortable set of each", all(x["sets"] == 1 for x in chk[1]) and chk[0] == "Strength check")
check("never to failure", any("Never to failure" in s for s in build()[2]))

# sport support, freshness, core
swim = build(sports=["swim", "run"], priorities={"swim": "improve", "run": "maintain"}, turn=0)[1]
check(f"an improving swimmer gets swim dryland in the support slot ({names(swim)})",
      next(x for x in swim if x["role"] == "prehab")["name"] in L.SUPPORT["swim"])
fresh = build(sports=["swim"], priorities={"swim": "improve"}, tomorrow=("shoulders",))[1]
minor = [x for x in fresh if x["role"] != "main"]
check(f"a hard swim tomorrow keeps the minor lifts off the shoulders ({names(minor)})",
      all(max([x["regions"].get(r, 0) for r in ("shoulders", "lats", "scapula")]) < 30 for x in minor))
cores = [next(x for x in build(turn=n)[1] if x["role"] == "core")["name"] for n in (0, 1)]
check(f"the core slot alternates anti-rotation and rotation ({cores})",
      cores[0] in L.CORE["anti"] and cores[1] in L.CORE["rotate"])
check("every exercise has a load profile", all(sum(v[1].values()) == 100 for v in L.EX.values()))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
