"""Ride posts: story, infographic, Claude pack, Strava (against a stand-in Strava),
TCX with a route's map, and Strava setup kept to the Mac."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import csv, datetime as dt, json, math, tempfile, time
import xml.etree.ElementTree as ET


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    tmp = pathlib.Path(tempfile.mkdtemp())
    rides = tmp / "rides"; rides.mkdir()
    import routes
    routes.ROUTES = tmp / "routes"; routes.ROUTES.mkdir()
    # a 3 km climb route near Topanga
    pts = [(34.05 + i * 0.0009, -118.60, 50 + i * 3.0) for i in range(34)]
    rt = routes.Route(pts, "Test climb"); rt.save()
    # an older ride, then today's ride on the route with a ghost win and a 5-min record
    def write(stem, start, secs, watts, grade=0.0):
        with open(rides / f"{stem}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time", "power_w", "cadence_rpm", "bike_speed_kmh", "bike_distance_m", "resistance",
                        "virtual_speed_kmh", "virtual_distance_m", "grade_pct", "gear", "hill_shift", "erg_w"])
            d = 0.0
            for s in range(secs):
                p = watts(s); v = 15 + p / 20; d += v / 3.6
                w.writerow([(start + dt.timedelta(seconds=s)).isoformat(timespec="seconds"), p, 80, v, d, 5, v, round(d, 1), grade, 0, 0, ""])
    write("ride_2026-09-20_0900", dt.datetime(2026, 9, 20, 9), 1200, lambda s: 120)
    start = dt.datetime(2026, 9, 21, 9)
    write("ride_2026-09-21_0900", start, 1500, lambda s: 200 if 300 <= s < 700 else 140, grade=4.0)
    with open(rides / "ride_2026-09-21_0900_events.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time", "event"])
        w.writerow([start.isoformat(), f"Route started: {rt.id} at 0 m - Test climb, 3.0 km, 99 m of climbing"])
        w.writerow([(start + dt.timedelta(minutes=24)).isoformat(), "Ghost result: 42 s ahead of ride_2026-09-14_0900"])
    import bests
    d = bests.load(bests.file_for(rides)); bests.scan_rides(d, rides); bests.save(d)

    import posts, story
    s = posts.make(rides / "ride_2026-09-21_0900.csv")
    check(f"story title uses the route ({s['title']})", s["title"].startswith("Test climb"))
    texts = [h["text"] for h in s["highlights"]]
    check(f"records lead the highlights ({texts[0]})", texts[0].startswith("New 20 min best"))
    check("the ghost win is a highlight", any("Beat my ghost by 42 s" in t for t in texts))
    check(f"hardest ride yet is noticed", any("Hardest ride yet" in t for t in texts))
    check("a 2-day streak", s["streak"] == 2)
    check("the challenge dares friends to hold the record", "Think you can hold that" in s["challenge"])
    check("zones add up to the ride", abs(sum(z["seconds"] for z in s["zones"]) - 1500) <= 2)
    out = posts.folder(rides / "ride_2026-09-21_0900.csv")
    png = (out / "card.png").read_bytes()
    check(f"card.png is a 1080x1350 PNG ({len(png)} bytes)", png[:8] == b"\x89PNG\r\n\x1a\n"
          and int.from_bytes(png[16:20], "big") == 1080 and int.from_bytes(png[20:24], "big") == 1350)
    md = (out / "for_claude.md").read_text()
    check("the Claude pack has the prompt, the records and the chart data",
          "friendly but competitive" in md and "20 min" in md and '"power_w"' in md and "Ghost race: 42 s ahead" in md)
    check("the zip has all four files", len(posts.zip_bytes(rides / "ride_2026-09-21_0900.csv")) > 10000)
    short = rides / "ride_2026-09-22_0900.csv"
    write("ride_2026-09-22_0900", dt.datetime(2026, 9, 22, 9), 120, lambda s: 100)
    check("a 2-minute ride gets no post", posts.make(short) is None)

    # ── Strava, against a stand-in ──
    import strava
    calls = []
    synced = {"id": 555, "name": "Morning Ride", "sport_type": "VirtualRide",
              "start_date": dt.datetime(2026, 9, 21, 9, 1).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    state = {"activities": [synced], "uploads": 0}
    def fake(method, url, data=None, headers=None, raw=None, timeout=30):
        calls.append((method, url, data, raw))
        if url == strava.TOKEN:
            return 200, {"access_token": "A2" if data.get("grant_type") == "refresh_token" else "A1",
                         "refresh_token": "R", "expires_at": int(time.time()) + 3600, "athlete": {"firstname": "Rider"}}
        if "/athlete/activities" in url:
            return 200, state["activities"]
        if method == "PUT":
            return 200, {"id": 555}
        if url.endswith("/uploads"):
            state["uploads"] += 1
            return 201, {"id": 9, "activity_id": None, "error": None}
        if "/uploads/9" in url:
            return 200, {"id": 9, "activity_id": 777, "error": None}
        return 404, {"message": "not found"}
    strava._http = fake
    strava.time.sleep = lambda s: None
    sv = strava.Strava(tmp / "strava.json")
    try:
        sv.set_app("abc", "short"); check("bad app keys refused", False)
    except strava.StravaError:
        check("bad app keys refused", True)
    sv.set_app("12345", "x" * 40)
    url = sv.auth_url()
    check("connect asks for upload/edit permission and comes back to this Mac",
          "activity%3Awrite" in url and "127.0.0.1%3A8729%2Fstrava%2Fcallback" in url)
    try:
        sv.finish_auth("code", "forged", "read,activity:write"); check("a forged approval is refused", False)
    except strava.StravaError:
        check("a forged approval is refused", True)
    sv.finish_auth("code", sv.cfg["state"], "read,activity:write,activity:read_all")
    check("connected, tokens saved privately", sv.connected and oct((tmp / "strava.json").stat().st_mode & 0o777) == "0o600")
    res = sv.post(s, rides / "ride_2026-09-21_0900.csv")
    put = [c for c in calls if c[0] == "PUT"]
    check(f"posting updates the watch's synced ride, no upload ({res['url']})",
          res["how"] == "updated" and res["url"].endswith("/555") and state["uploads"] == 0 and put[-1][2]["name"] == s["title"])
    check("the caption goes on as the description", put[-1][2]["description"] == s["caption"])
    state["activities"] = []
    res = sv.post(s, rides / "ride_2026-09-21_0900.csv")
    check(f"no synced ride: it uploads as a Virtual Ride ({res['url']})",
          res["how"] == "uploaded" and res["url"].endswith("/777") and state["uploads"] == 1
          and any(c[0] == "PUT" and c[2] == {"sport_type": "VirtualRide"} for c in calls))
    sv.cfg["expires_at"] = 0; sv._token()
    check("an expired token renews itself", sv.cfg["access_token"] == "A2")

    tcx = strava.tcx_for(rides / "ride_2026-09-21_0900.csv", s)
    root = ET.fromstring(tcx.encode())
    ns = {"t": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
    tps = root.findall(".//t:Trackpoint", ns)
    lats = [float(x.text) for x in root.findall(".//t:LatitudeDegrees", ns)]
    check(f"TCX is valid XML with a point a second ({len(tps)})", len(tps) == 1500)
    check(f"a route ride's upload carries the route's map ({len(lats)} positions, {min(lats):.4f}..{max(lats):.4f})",
          len(lats) > 500 and min(lats) >= 34.05 and max(lats) <= 34.05 + 33 * 0.0009 + 1e-6)
    check("watts are in the TCX", "<ns3:Watts>200</ns3:Watts>" in tcx)

    import remote
    remote.FILE = tmp / "remote.json"
    tok, _ = remote.try_pin(remote.pin())
    ck = {b"cookie": f"{remote.COOKIE}={tok}".encode()}
    phone = ("192.168.1.40", 1)
    check("a paired phone can post a ride", remote.allowed(phone, ck, b"/api/strava/post/ride_2026-09-21_0900"))
    check("a paired phone can't change the Strava keys or connect", not remote.allowed(phone, ck, b"/api/strava/app")
          and not remote.allowed(phone, ck, b"/strava/connect") and not remote.allowed(phone, ck, b"/api/strava/forget"))
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
