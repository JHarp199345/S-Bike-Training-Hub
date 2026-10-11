import sys, pathlib, tempfile, json, asyncio; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from types import SimpleNamespace
import setup_guide as G

today = "2026-10-12"
s = G.status({}, {}, [], today)
assert s["next"] == "basics" and not s["complete"] and [x["step"] for x in s["steps"]][:3] == ["basics", "health", "sports"]
p = {"weight_kg": 72.6, "age": 41, "gender": "another"}
assert G.status(p, {}, [], today)["next"] == "health"
d = {"health_history": {"screenings": [{"result": "no_clearance_needed"}]}}
assert G.status(p, d, [], today)["next"] == "sports"
p = {**p, "sports": ["lift", "run"], "experience": {"lift": "new", "run": "new"}}
r = G.status(p, d, [], today)
assert r["next"] == "routine" and r["routine_needed_for"] == ["lift", "run"]
assert G.status(p, {**d, "sport_baselines": {"lift": {}}}, [{"sport": "run"}], today)["next"] == "goal"   # a recorded run counts
d = {**d, "sport_baselines": {"lift": {}, "run": {}}, "program_goal": {"goal": "x"}, "phase_profiles": [{}]}
assert G.status(p, d, [], today)["next"] == "first_week"
d["plans"] = {"2026-10-14": {"sessions": [{"sport": "run"}]}}
assert G.status(p, d, [], today)["complete"]

# the endpoint keeps earlier answers when a later one is saved, and checks gender
import mapserver, coach
base = pathlib.Path(tempfile.mkdtemp()); (base / "rides").mkdir()
bridge = SimpleNamespace(csv_path=str(base / "rides" / "x.csv"), args=SimpleNamespace(no_bike=True))
async def post(path, body):
    code, _, raw, _ = await mapserver.handle(bridge, b"POST", path, json.dumps(body).encode(), "localhost")
    return code, json.loads(raw)
async def main():
    code, r = await post("/api/setup/basics", {"unit": "lb", "weight": 160, "age": 41, "gender": "another"})
    assert code == 200 and r["profile"]["gender"] == "another" and r["profile"]["weight_kg"] == 72.6, r
    code, r = await post("/api/setup/basics", {"sports": ["lift"], "experience": {"lift": "new"}})
    assert code == 200 and r["profile"]["sports"] == ["lift"] and r["profile"]["age"] == 41 and r["profile"]["weight_kg"] == 72.6, r
    code, r = await post("/api/setup/basics", {"gender": "robot"})
    assert code == 400 and "gender" in r["error"]
    code, _, raw, _ = await mapserver.handle(bridge, b"GET", "/api/setup/status", b"", "localhost")
    assert json.loads(raw)["next"] == "health"
    code, _, raw, _ = await mapserver.handle(bridge, b"POST", "/api/assistant/seen", b"{}", "localhost")
    assert json.loads(raw)["connected"]
asyncio.run(main())
print("PASS setup guide: step order, merge-safe basics, gender check, assistant light")
