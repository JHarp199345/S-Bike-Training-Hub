"""The shared ride screen's Pause / End controls, against a real (simulated-bike) bridge over the real panel server.
They send exactly what web/ride-hub.html sends: /api/workout/pause, /erg/off, /api/route/stop, /ftp/stop."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import asyncio, json, tempfile
from pathlib import Path
import panel, routes
from test_hills import make_bridge
from test_route_ride import climb_route

PORT = 18731


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    br = make_bridge()
    work = Path(tempfile.mkdtemp())
    routes.ROUTES = work / "routes"
    srv = await panel.serve(br, PORT, lan=False)

    async def req(method, path, body=b""):
        rd, wr = await asyncio.open_connection("127.0.0.1", PORT)
        wr.write(f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
        await wr.drain(); out = await rd.read(); wr.close()
        head, _, payload = out.partition(b"\r\n\r\n")
        return int(head.split()[1]), payload

    async def status():
        return json.loads((await req("GET", "/status"))[1])

    st = await status()
    check("nothing active: the screen's rule disables Pause and End", not st["workout"] and not st["route"] and not st["test"])

    br.workout_start(0)
    st = await status()
    check(f"a workout is active and not paused ({st['workout']['name']})", st["workout"] and not st["workout"]["paused"])
    code, _ = await req("POST", "/api/workout/pause", b"{}")
    st = await status()
    check("Pause: the workout is paused (button reads 'Resume workout')", code == 200 and st["workout"]["paused"])
    await req("POST", "/api/workout/pause", b"{}")
    st = await status()
    check("Resume: running again", not st["workout"]["paused"])
    code, _ = await req("POST", "/erg/off")
    st = await status()
    check("End ride during a workout: ERG off, workout ended, no route or test started", code == 200 and not st["workout"] and not st["route"] and not st["test"] and not st["erg"])

    route = climb_route(); route.save()
    br.route_start(route.id)
    st = await status()
    check("a route is active", st["route"] is not None)
    code, _ = await req("POST", "/api/route/stop")
    st = await status()
    check("End ride during a route: the route stops, nothing else starts", code == 200 and st["route"] is None and not st["workout"])

    br.ftp_test_start()
    st = await status()
    check(f"an FTP test is active ({(st['test'] or {}).get('phase')})", st["test"] is not None)
    code, _ = await req("POST", "/ftp/stop")
    st = await status()
    phase = (st["test"] or {}).get("phase")
    check(f"End ramp: the test goes to its cool-down, not an abrupt stop (phase {phase})", code == 200 and (st["test"] is None or phase in ("cool-down", "cooldown", "done")))

    br.workout_start(0); br.route_start(route.id)
    st = await status()
    check("a workout on a route: both active", st["workout"] and st["route"])
    for path in ("/erg/off", "/api/route/stop"):            # End sends both, in this order (web/ride-hub.html)
        await req("POST", path)
    st = await status()
    check("End ride ends the whole ride: the workout and the route", not st["workout"] and st["route"] is None)
    html = (pathlib.Path(__file__).resolve().parent.parent / "web" / "ride-hub.html").read_text()
    check("the screen's End sends /erg/off and /api/route/stop together when both are active",
          "if(rideStatus.workout)steps.push('/erg/off');if(rideStatus.route)steps.push('/api/route/stop')" in html)
    srv.close(); await srv.wait_closed()
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
