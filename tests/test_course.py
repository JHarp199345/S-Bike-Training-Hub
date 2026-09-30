"""The course: a ride planned without a map route, built as a made-up route whose hills are the workout."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import tempfile
import course, focus, routes


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    f = focus.resolve("cadence", 180)
    r, meta = course.build(30, f, 126.6)
    parts = meta["parts"]
    check(f"warm-up, three climbs with spins between, cool-down ({[p['kind'] for p in parts]})",
          [p["kind"] for p in parts] == ["warmup", "climb", "spin", "climb", "spin", "climb", "spin", "cooldown"])
    check(f"the parts share the minutes ({sum(p['minutes'] for p in parts):.1f} of 30)", abs(sum(p["minutes"] for p in parts) - 30) < 0.2)
    mins = sum(pp["minutes"] * 60 for pp in parts)
    ride_s = sum((pp["end_m"] - pp["start_m"]) / course.speed_at(sum(f["watts"]) / 2, sum(pp["grade"]) / 2, 126.6) for pp in parts)
    check(f"at the focus's middle watts it takes about the planned time ({ride_s / 60:.1f} min for {r.length / 1000:.1f} km)",
          abs(ride_s - mins) < 60)
    s = r.stats()
    check(f"gentle: the steepest grade is {s['max_grade']}% (the focus sets the watts; the terrain only leans on them)", s["max_grade"] <= 3)
    check("climbs go up, spins come down", all((p["grade"][0] > 0) == (p["kind"] == "climb") for p in parts if p["kind"] in ("climb", "spin")))
    gates = meta["gates"]
    check(f"a push gate on each climb and a spin gate on each descent ({len(gates)})",
          sorted(g["kind"] for g in gates) == ["push"] * 3 + ["spin"] * 3)
    check("gates never ask for more than the day's focus allows",
          all((g["target"].get("watts", 0) <= f["watts"][1]) and (g["target"].get("rpm", 0) <= f["rpm"][1]) for g in gates))
    check("five forms, one every few minutes on the lit road", meta["forms"] == ["bike", "unicorn", "gorilla", "panda", "dragon"]
          and meta["form_minutes"] == 5)
    tmp = tempfile.mkdtemp()
    course.save(r, meta, tmp)
    back = course.load(r.id, tmp)
    check("saved like a route (the bridge rides it) with its parts and gates beside the points",
          abs(routes.load(r.id, tmp).length - r.length) < 1 and back["gates"] == gates and len(back["profile"]) > 100)
    check("courses stay out of the saved map routes", routes.list_routes(tmp) == [])
    plain = routes.Route([(45.9, 6.1 + i * 0.0005, 200 + i * 0.4) for i in range(60)], "a real road")
    plain.save(tmp)
    pc = course.load(plain.id, tmp)
    check(f"a saved map route opens in the game view: its real hills, no gates ({len(pc['profile'])} points)",
          pc.get("map_route") and pc["gates"] == [] and len(pc["profile"]) > 20)
    import erg, time as _time
    e = erg.Erg.__new__(erg.Erg)
    e.workout = {"name": "Timed", "steps": [(300, 100), (240, 150), (120, 105)], "started": _time.monotonic() - 330}
    ws = e.workout_status(_time.monotonic())
    check(f"a running workout reports every block, so the game draws what's ahead ({ws['blocks']}, block {ws['step']})",
          ws["blocks"] == [[300, 100], [240, 150], [120, 105]] and ws["step"] == 2 and ws["total"] == 660 and 329 <= ws["elapsed"] <= 332)
    no_w = course.build(20, focus.resolve("off", 180), 126.6)[1]
    check("a cadence-only day: spin gates only, no watt gates", all(g["kind"] == "spin" for g in no_w["gates"]))
    # the animals: a strip for every one in the manifest, and the forms setting kept on the bridge
    import asyncio, json
    import mapserver
    web = pathlib.Path(__file__).resolve().parent.parent / "web" / "sprites"
    sheet = json.loads((web / "animals.json").read_text())
    missing = [f"{k}:{g}" for k, a in sheet["animals"].items() for g, gd in a["gaits"].items() if not (web / gd["file"]).exists()]
    check(f"{len(sheet['animals'])} animals, each with its sprite strip ({'missing: ' + ', '.join(missing) if missing else 'all there'})",
          len(sheet["animals"]) >= 15 and not missing)
    check("each knows where its feet touch the ground, and whether it runs, walks or flies",
          all(0 <= gd["base"] < gd["top"] <= 1 and a["kind"] in ("run", "walk", "fly") and "run" in a["gaits"]
              for a in sheet["animals"].values() for gd in a["gaits"].values()))
    walkers = [k for k, a in sheet["animals"].items() if "walk" in a["gaits"]]
    check(f"the farm animals walk as well as gallop, so pace can show as a change of gait ({', '.join(walkers)})", len(walkers) >= 8)
    real = mapserver.HERE
    try:
        mapserver.HERE = pathlib.Path(tempfile.mkdtemp())
        call = lambda m, b=b"": asyncio.run(mapserver.handle(None, m, "/api/course/forms", b, "localhost"))
        check("no forms chosen yet: a default line-up", json.loads(call(b"GET")[2])["forms"] == ["unicorn", "wolf", "eagle", "dragon"])
        r = call(b"POST", json.dumps({"forms": ["horse", "gorilla", "fox", "dragon"]}).encode())
        check(f"the rider's order is kept; animals we don't have are dropped ({json.loads(r[2])['forms']})",
              json.loads(call(b"GET")[2])["forms"] == ["horse", "fox", "dragon"])
        check("an empty line-up is refused", call(b"POST", b'{"forms":[]}')[0] == 400)
        served = asyncio.run(mapserver.handle(None, b"GET", "/web/sprites/horse.png", b"", "localhost"))
        check("the strips are served as images", served[0] == 200 and served[1] == "image/png")
        sneaky = asyncio.run(mapserver.handle(None, b"GET", "/web/../profile.json", b"", "localhost"))
        check("nothing outside the web folders is served", sneaky[0] == 404)
    finally:
        mapserver.HERE = real
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
