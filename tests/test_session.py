"""Sessions on a route: its climbs found, a climb time goal turned into watts and paced, big-gear efforts shifted
into, a focus for part of the route, every climb recorded - and the bridge running it from today's plan."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json, tempfile
import coach, planner, routes, session
from test_hills import make_bridge


def road(parts, start=(45.9, 6.1)):
    """A road east from `start`: parts are (metres, grade %), a point every 25 m."""
    pts, e, d = [], 200.0, 0.0
    for length, g in parts:
        for _ in range(int(length / 25)):
            lat, lon = planner._offset(start, d, 90)
            pts.append((lat, lon, e))
            d += 25; e += g / 100 * 25
    lat, lon = planner._offset(start, d, 90)
    pts.append((lat, lon, e))
    return routes.Route(pts, "test road")


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    r = road([(1000, 0), (1500, 6), (1000, 0), (600, 9), (1000, 0)])
    cl = session.climbs(r)
    check(f"finds the two climbs ({[(c['n'], c['start_m'], c['end_m'], c['avg_grade']) for c in cl]})",
          len(cl) == 2 and abs(cl[0]["start_m"] - 1000) <= 100 and abs(cl[0]["end_m"] - 2500) <= 100
          and abs(cl[1]["avg_grade"] - 9) < 1.5)
    check("a flat road has none", session.climbs(road([(5000, 0.5)])) == [])
    w = session.watts_for(1500 / 600, 6, 126.6)
    check(f"1.5 km at 6% in 10 min needs about {w:.0f} W at 126.6 kg", 190 < w < 225)
    from bridge import virtual_speed
    check("...and that's the inverse of the bridge's own speed physics", abs(virtual_speed(w, 6, 126.6) - 2.5) < 0.01)

    segs = session.check(r, [{"type": "climb_time", "climb": 1, "seconds": 600},
                             {"type": "efforts", "climb": 2, "count": 2, "on_s": 15, "off_s": 60, "watts": 200}])
    check("climb numbers become distances along the route", segs[0]["start_m"] == cl[0]["start_m"] and segs[1]["at_m"] == cl[1]["start_m"])
    for bad in ([{"type": "climb_time", "climb": 5, "seconds": 600}], [{"type": "efforts", "at_m": 100, "watts": 5000}],
                [{"type": "sprint"}], []):
        try:
            session.check(r, bad); check(f"refuses {bad}", False)
        except session.BadSession:
            check(f"refuses {bad}", True)

    # ride the climb goal: slow at first (behind), then at the pace it asks for
    run = session.Runner(r, segs[:1], 180, 126.6)
    c0, c1 = segs[0]["start_m"], segs[0]["end_m"]
    t, d, outs = 0.0, c0 - 5, []
    while d < c1 + 5 and t < 2000:
        o = run.update(t, d, 150, 70, 6)
        outs.append(o)
        v = 1.5 if t < 120 else ((o["pace"] or {}).get("target_w", 150) and
                                 virtual_speed(o["watts"][0] / 0.95, 6, 126.6) if o["watts"] else 2.5)
        d += v; t += 1
    first = next(o for o in outs if o["pace"])
    behind = next((o for o in outs if o["pace"] and o["pace"]["elapsed_s"] == 110), None)
    check(f"on reaching the climb it shifts straight into the gear for the pace ({first['shift_to_watts'][0]:.0f} W)",
          first["shift_to_watts"] and abs(first["shift_to_watts"][0] - w) < 15)
    check(f"slow start: it says you're behind ({behind['cue']})", behind and behind["pace"]["ahead_s"] < -10 and "behind" in behind["cue"])
    check(f"...and asks for more watts to catch up ({behind['pace']['target_w']} W vs {first['pace']['target_w']})",
          behind["pace"]["target_w"] > first["pace"]["target_w"])
    res = run.results[0]
    check(f"at the top: time vs goal ({res['took_s']} s vs {res['goal_s']}) and the gear handed back",
          res["type"] == "climb_time" and abs(res["took_s"] - 600) < 40 and any(o["restore_gear"] for o in outs))

    run = session.Runner(r, segs[1:], 180, 126.6)
    t, d, shifts, restores, cues = 0.0, segs[1]["at_m"] - 3, 0, 0, []
    for _ in range(200):
        o = run.update(t, d, 205 if o.get("watts") else 120, 60, 9)
        shifts += bool(o["shift_to_watts"]); restores += o["restore_gear"]; cues.append(o["cue"])
        t += 1; d += 3
    rr = run.results[0]
    check(f"efforts: a big-gear shift at the start of each ({shifts}) and back after ({restores})", shifts == 2 and restores >= 2)
    check(f"countdown cues ({[c for c in cues if c][:1]})", any("Effort 1 of 2" in c for c in cues) and any("Easy" in c for c in cues))
    check(f"results: {rr['made']} of 2 at 90%+ of 200 W ({[e['avg_w'] for e in rr['efforts']]})", rr["made"] == 2)

    fs = session.check(r, [{"type": "focus", "climb": 1, "focus": "grit"}])
    import focus
    run = session.Runner(r, fs, 180, 126.6, lambda f: focus.resolve(f, 180))
    inside, outside = run.update(0, cl[0]["start_m"] + 50, 150, 60, 6), run.update(1, cl[0]["end_m"] + 200, 150, 60, 0)
    check(f"a grit focus on the climb only ({inside['rpm']} rpm on it, {outside['rpm']} after)", inside["rpm"] == [50, 65] and outside["rpm"] is None)

    resumed = session.Runner(r, segs, 180, 126.6, start_at=segs[0]["start_m"] + 300)
    check("resuming mid-route: a goal already started is passed, not re-run", resumed.segs[0]["state"] == "passed" and resumed.segs[1]["state"] == "waiting")
    rec, out = session.ClimbRecorder(r), None
    t, d = 0.0, 0.0
    while d < r.length - 10:
        out = rec.update(t, d, 140, 65, 3.0, 0) or out
        d += 3.0; t += 1
    check(f"every climb is recorded, goal or not ({[(c['n'], c['seconds'], c['avg_w'], c['vam']) for c in rec.done]})",
          len(rec.done) == 2 and rec.done[0]["avg_w"] == 140 and rec.done[0]["vam"] > 0)

    # the bridge: today's plan has a session on this route; starting the route runs it
    tmp = pathlib.Path(tempfile.mkdtemp())
    old = routes.ROUTES
    routes.ROUTES = tmp
    try:
        r.save()
        br = make_bridge()
        d_ = coach.load(coach.file_for(pathlib.Path(br.csv_path).parent))
        d_["plans"][coach.today()] = {"session": {"route_id": r.id, "segments": segs}}
        coach.save(d_)
        br.refresh_focus(force=True)
        br.route_start(r.id)
        check(f"starting the route loads today's session ({[e for e in br.events if 'Session on' in e][:1]})",
              br.session is not None and br.climb_rec is not None)
        br.ride.vdistance = br.route_ride.offset + segs[0]["start_m"] + 10
        br.ride.power, br.ride.cadence = 150.0, 70.0
        br.feed_route()                                        # the road's grade first, as every second of a ride
        g0 = br.gear
        br.session_tick()
        want = session.watts_for(1500 / 600, 6, br.ride.mass)          # the pace's watts at this bridge's rider weight
        mid = sum(br.auto.watt_band) / 2 if br.auto.watt_band else 0
        check(f"at the climb: auto-shift steers to the pace's watts ({br.auto.watt_band}, pace needs ~{want:.0f}) and the gear "
              f"went up ({g0} -> {br.gear})", br.auto.watt_band and abs(mid - want) / want < 0.25 and br.gear > g0)
        check("the ride view gets the cue and pace", br.status()["session"]["pace"]["name"] == "Climb 1")
        br.route_stop()
        check("stopping the route hands the gear back and puts the day's focus back",
              br.gear == g0 and br.auto.watt_band == tuple(float(x) for x in br.focus["watts"]))
    finally:
        routes.ROUTES = old
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
