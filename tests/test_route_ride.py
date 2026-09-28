"""Riding a route twice: resistance follows the climb, Kinomap is ignored, and the
second ride races the first as a ghost. The route is built in: 2 km of valley,
5 km climbing at about 6%, then 2 km down."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, datetime as dt, json, os, tempfile, time, types
import bridge as b
import routes
from test_hills import ARGS



def climb_route():
    pts, ele, d, lat = [], 700.0, 0.0, 45.05
    step = 20 / 111_195                                           # ~20 m north per point
    while d <= 9000:
        g = 0.0 if d < 2000 else 6.0 if d < 7000 else -5.0
        pts.append((lat, 6.03, ele))
        lat += step; d += 20; ele += g / 100 * 20
    return routes.Route(pts, "Valley and climb")


def fresh_bridge(folder):
    cwd = os.getcwd(); os.chdir(folder)
    br = b.Bridge(types.SimpleNamespace(**ARGS)); os.chdir(cwd)
    br.csv_path = pathlib.Path(folder) / br.csv_path       # make paths absolute for the test
    br.push = lambda *a, **k: None
    br.static[b.RES_RANGE] = (10).to_bytes(2, "little") + (160).to_bytes(2, "little") + (10).to_bytes(2, "little")
    br.static[b.FEATURE] = bytes.fromhex("0b50000004000000")
    br.describe_features()
    return br


def ride(br, watts, seconds, clock):
    """Pedal at `watts` for `seconds`, one tick per simulated second, logging like the real bridge."""
    levels = []
    for _ in range(seconds):
        clock[0] += 1
        r = br.ride
        r.power, r.cadence = watts, 78
        r.last_tick -= 1; r.tick()
        br.feed_route(); br.feed_ghost()
        br.csv.writerow([dt.datetime.fromtimestamp(clock[0]).isoformat(timespec="seconds"), watts, 78, 20, 0,
                         br.target_level, round(r.road_kmh(), 2), round(r.road_m(), 1), r.grade, br.gear, 0, ""])
        levels.append(br.target_level)
        if not br.route_ride:
            break
    return levels


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    work = pathlib.Path(tempfile.mkdtemp()); (work / "rides").mkdir()
    routes.ROUTES = work / "routes"
    b.STATE = work / "state.json"
    route = climb_route()
    route.save()

    # Simulated wall clock so both rides' timestamps are comparable.
    clock = [time.time()]
    real_time = time.time
    b.time.time = lambda: clock[0]
    try:
        br = fresh_bridge(work)
        br.route_start(route.id)
        check("route started, ghost has nothing to race yet (first time)", br.route_ride and br.ghost.match is None)
        class CP: uuid = b.CONTROL
        before = br.target_level
        br.on_write(CP(), b"\x11\x00\x00" + (800).to_bytes(2, "little", signed=True) + b"\x28\x33")   # Kinomap: +8%
        check("a Kinomap hill is ignored while riding our own route", br.target_level == before)
        lv = ride(br, 140, 6000, clock)
        grades_seen = sorted({round(x) for x in [br.route_fed or 0]})
        top = max(lv); flat = lv[len(lv) // 10]
        check(f"resistance follows the real mountain: valley ~L{flat}, climb up to L{top}", top >= flat + 2)
        check(f"route finished by itself after {len(lv) / 60:.0f} simulated minutes", br.route_ride is None)
        ev = [e for e in br.events]
        check("finish is logged", any("Route finished" in e for e in ev))
        first_ride = br.csv_path

        clock[0] += 3600
        br2 = fresh_bridge(work)
        br2.route_start(route.id)
        check(f"second ride: ghost = the first ride ({br2.ghost.match.name if br2.ghost.match else None})",
              br2.ghost.match is not None and br2.ghost.match.name == first_ride.stem)
        ride(br2, 165, 900, clock)                      # 15 minutes, harder
        g = br2.ghost.gap()
        check(f"pushing 165 W instead of 140: {abs(g[0])} s {'ahead' if g[0] < 0 else 'behind'}, {abs(g[1])} m", g and g[0] < 0 and g[1] > 0)
        st = br2.status()
        check(f"status for the map: {st['route']['done_m']} m of {st['route']['total_m']} m, at {st['route']['lat']}, {st['route']['lon']}",
              st["route"] and 0 < st["route"]["done_m"] < st["route"]["total_m"])
    finally:
        b.time.time = real_time
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
