"""mapserver.py - the map side of the control panel.

Everything the 3D ride view and the route planner need, served from this Mac:

    /ride, /plan                 the two map pages (web/ride.html, web/plan.html)
    /lib/<file>                  the MapLibre engine (downloaded to maps/web by setup.sh)
    /tiles/{z}/{x}/{y}           map tiles from the downloaded .pmtiles files
    /terrain/{z}/{x}/{y}.png     elevation tiles for 3D terrain
    /style.json                  how the map is drawn
    /api/places?q=               find a town or mountain  GET
    /api/near?lat=&lon=          the town nearest a point GET
    /api/ideas                   famous rides to plan    GET
    /api/routes                  saved routes            GET
    /api/route/<id>              one route's geometry    GET
    /api/plan                    plan routes             POST {start, end} or {start, km, want, loop}
    /api/route/save              keep a planned route    POST {cid, name}
    /api/route/import            GPX file -> route       POST (the GPX text)
    /api/route/start/<id>        ride it                 POST
    /api/route/stop              stop riding it          POST

Planning takes a few seconds, so it runs in a worker thread; the bike link
never waits for it.
"""
import asyncio
import itertools
import json
from pathlib import Path

import routes
import places
import ideas

HERE = Path(__file__).resolve().parent
MAPS = Path(__import__("os").environ.get("S_BIKE_MAPS") or HERE / "maps")     # made by setup.sh
WEB = HERE / "web"
TYPES = {".mjs": "text/javascript", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
         ".html": "text/html; charset=utf-8", ".json": "application/json", ".map": "application/json"}

_maps = None
_maps_at = 0.0
_candidates = {}                     # planned-but-unsaved routes, by temporary id
_cid = itertools.count(1)


_maps_seen = None


def maps():
    """The downloaded maps. Once a minute the folder is checked; a piece that
    has finished downloading (renamed from .part) or a half-written one that
    has completed shows up without restarting the bridge."""
    global _maps, _maps_at, _maps_seen
    import time
    if _maps is None or time.monotonic() - _maps_at > 60:
        _maps_at = time.monotonic()
        seen = sorted((p.name, p.stat().st_size) for p in (MAPS / "map").glob("*.pmtiles"))
        if _maps is None or seen != _maps_seen or _maps.pending:
            from pmtiles_reader import MapSet
            _maps, _maps_seen = MapSet(MAPS / "map"), seen
    return _maps


def route_json(r, cid=None):
    return {"id": r.id, "cid": cid, "name": r.name, "stats": r.stats(),
            "points": [[round(p[1], 6), round(p[0], 6)] for p in r.points],       # [lon, lat] for the map
            "profile": r.profile(100.0)}


REG, MED, ITA = ["Noto Sans Regular"], ["Noto Sans Medium"], ["Noto Sans Italic"]
HALO = {"text-halo-color": "rgba(255,255,255,0.9)", "text-halo-width": 1.6, "text-halo-blur": 0.3}
SHOWN = [">=", ["zoom"], ["coalesce", ["get", "min_zoom"], 0]]          # each place from the zoom the map says


def labels():
    """Names on the map: countries, regions, cities by size, streets, peaks, water."""
    name = ["coalesce", ["get", "name:en"], ["get", "name"]]
    local = ["get", "name"]
    return [
        {"id": "water-names", "type": "symbol", "source": "map", "source-layer": "water",
         "filter": ["all", ["==", ["geometry-type"], "Point"], ["has", "name"]],
         "layout": {"text-field": local, "text-font": ITA, "text-size": 13, "text-max-width": 8},
         "paint": {"text-color": "#3f6f94", **HALO}},
        {"id": "street-names", "type": "symbol", "source": "map", "source-layer": "roads", "minzoom": 12,
         "filter": ["all", ["has", "name"], ["!=", ["get", "kind_detail"], "service"],   # no alley/driveway names
                    # main roads from zoom 12, side streets from 14
                    ["any", ["in", ["get", "kind"], ["literal", ["major_road", "highway"]]],
                            ["all", ["==", ["get", "kind"], "minor_road"], [">=", ["zoom"], 14]]]],
         "layout": {"symbol-placement": "line", "text-field": local, "text-font": REG, "text-max-angle": 30,
                    "text-size": ["interpolate", ["linear"], ["zoom"], 12, 10.5, 17, 14]},
         "paint": {"text-color": "#3b3a36", **HALO}},
        {"id": "road-numbers", "type": "symbol", "source": "map", "source-layer": "roads", "minzoom": 8, "maxzoom": 13,
         "filter": ["all", ["has", "ref"], ["in", ["get", "kind"], ["literal", ["highway", "major_road"]]]],
         "layout": {"symbol-placement": "line", "symbol-spacing": 400, "text-field": ["get", "ref"], "text-font": MED,
                    "text-size": 10.5, "text-rotation-alignment": "viewport"},
         "paint": {"text-color": "#7a4a06", **HALO}},
        {"id": "peaks", "type": "symbol", "source": "map", "source-layer": "pois",
         "filter": ["all", ["in", ["get", "kind"], ["literal", ["peak", "volcano"]]], ["has", "name"], SHOWN],
         "layout": {"text-field": ["case", ["has", "elevation"],
                                   ["concat", "▲ ", local, "\n", ["to-string", ["round", ["get", "elevation"]]], " m"],
                                   ["concat", "▲ ", local]],
                    "text-font": MED, "text-size": 12, "text-max-width": 9, "text-anchor": "top"},
         "paint": {"text-color": "#5b4630", **HALO}},
        {"id": "neighbourhoods", "type": "symbol", "source": "map", "source-layer": "places",
         "filter": ["all", ["in", ["get", "kind"], ["literal", ["neighbourhood", "macrohood"]]], SHOWN],
         "layout": {"text-field": local, "text-font": MED, "text-size": 11, "text-transform": "uppercase",
                    "text-letter-spacing": 0.1, "text-max-width": 7},
         "paint": {"text-color": "#7b756b", **HALO}},
        {"id": "towns", "type": "symbol", "source": "map", "source-layer": "places",
         "filter": ["all", ["==", ["get", "kind"], "locality"], SHOWN],
         "layout": {"text-field": local, "text-font": MED, "text-max-width": 8,
                    "symbol-sort-key": ["-", 20, ["coalesce", ["get", "population_rank"], 0]],
                    "text-size": ["interpolate", ["linear"], ["coalesce", ["get", "population_rank"], 0],
                                  2, 11, 6, 13, 9, 16, 12, 20]},
         "paint": {"text-color": "#1f2328", **HALO}},
        {"id": "regions", "type": "symbol", "source": "map", "source-layer": "places", "maxzoom": 9,
         "filter": ["all", ["==", ["get", "kind"], "region"], SHOWN],
         "layout": {"text-field": name, "text-font": REG, "text-size": 13, "text-transform": "uppercase",
                    "text-letter-spacing": 0.15, "text-max-width": 8},
         "paint": {"text-color": "#8a8174", **HALO}},
        {"id": "countries", "type": "symbol", "source": "map", "source-layer": "places", "maxzoom": 7,
         "filter": ["==", ["get", "kind"], "country"],
         "layout": {"text-field": name, "text-font": MED, "text-size": 16, "text-transform": "uppercase",
                    "text-letter-spacing": 0.2},
         "paint": {"text-color": "#5d574e", **HALO}},
    ]


def style(host):
    """The map's look: natural colours, shaded 3D terrain, roads by importance.
    No text labels yet - those need a font download."""
    t = f"http://{host}"
    def road(name, kinds, color, w, casing):
        """A road drawn twice: a darker outline, then the fill - so it stands out from the land."""
        width = lambda k: ["interpolate", ["exponential", 1.6], ["zoom"], 5, w * 0.25 * k, 10, w * 0.9 * k, 14, w * 3 * k, 18, w * 14 * k]
        filt = ["in", ["get", "kind"], ["literal", kinds]]
        lay = {"line-cap": "round", "line-join": "round"}
        return [{"id": name + "-casing", "type": "line", "source": "map", "source-layer": "roads", "filter": filt,
                 "paint": {"line-color": casing, "line-width": width(1.0), "line-gap-width": 0}, "layout": lay},
                {"id": name, "type": "line", "source": "map", "source-layer": "roads", "filter": filt,
                 "paint": {"line-color": color, "line-width": width(0.62)}, "layout": lay}]
    roads = [road("paths", ["path", "other"], "#fbfaf7", 0.55, "#b9b2a4"),
             road("minor-roads", ["minor_road"], "#ffffff", 1.0, "#a39d91"),
             road("major-roads", ["major_road"], "#ffe07a", 1.7, "#c49a2c"),
             road("highways", ["highway"], "#f59e42", 2.3, "#b45f12")]
    for lay in roads[0]:
        lay["minzoom"] = 12                        # footpaths only once you're zoomed into a town
    layers = [
        {"id": "background", "type": "background", "paint": {"background-color": "#e6e1d6"}},
        {"id": "earth", "type": "fill", "source": "map", "source-layer": "earth", "paint": {"fill-color": "#ece8df"}},
        {"id": "farm", "type": "fill", "source": "map", "source-layer": "landcover",
         "filter": ["in", ["get", "kind"], ["literal", ["farmland", "grassland"]]], "paint": {"fill-color": "#dfe6c8"}},
        {"id": "forest", "type": "fill", "source": "map", "source-layer": "landcover",
         "filter": ["in", ["get", "kind"], ["literal", ["forest", "scrub"]]], "paint": {"fill-color": "#b9d3a0"}},
        {"id": "park", "type": "fill", "source": "map", "source-layer": "landuse",
         "filter": ["in", ["get", "kind"], ["literal", ["park", "nature_reserve", "forest", "wood", "golf_course"]]],
         "paint": {"fill-color": "#c6dcae"}},
        {"id": "urban", "type": "fill", "source": "map", "source-layer": "landuse",
         "filter": ["in", ["get", "kind"], ["literal", ["residential", "commercial", "industrial", "retail"]]],
         "paint": {"fill-color": "#e2ddd4"}},
        {"id": "hillshade", "type": "hillshade", "source": "dem-shade",
         "paint": {"hillshade-exaggeration": 0.45, "hillshade-shadow-color": "#5b5a52"}},
        # Only real water areas: the layer also holds river and stream LINES, and a fill layer
        # would close each winding river into a shape and paint bands across whole valleys.
        {"id": "water", "type": "fill", "source": "map", "source-layer": "water",
         "filter": ["==", ["geometry-type"], "Polygon"], "paint": {"fill-color": "#9cc3de"}},
        {"id": "rivers", "type": "line", "source": "map", "source-layer": "water",
         "filter": ["==", ["geometry-type"], "LineString"], "paint": {"line-color": "#9cc3de", "line-width": 1.5}},
        *[r[0] for r in roads],                    # every outline first, then every fill,
        *[r[1] for r in roads],                    # so crossings look like crossings
        {"id": "buildings", "type": "fill-extrusion", "source": "map", "source-layer": "buildings", "minzoom": 14,
         "paint": {"fill-extrusion-color": "#d6cfc4", "fill-extrusion-height": ["coalesce", ["get", "height"], 7],
                   "fill-extrusion-opacity": 0.85}},
        *labels(),
    ]
    return {"version": 8, "name": "S-Bike Hub", "glyphs": f"{t}/fonts/{{fontstack}}/{{range}}.pbf",
            "sources": {
                "map": {"type": "vector", "tiles": [f"{t}/tiles/{{z}}/{{x}}/{{y}}"], "minzoom": 0, "maxzoom": 14,
                        "attribution": "© OpenStreetMap contributors · Protomaps"},
                "dem": {"type": "raster-dem", "tiles": [f"{t}/terrain/{{z}}/{{x}}/{{y}}.png"], "encoding": "terrarium",
                        "tileSize": 256, "maxzoom": 12, "attribution": "Mapzen terrain"},
                "dem-shade": {"type": "raster-dem", "tiles": [f"{t}/terrain/{{z}}/{{x}}/{{y}}.png"],
                              "encoding": "terrarium", "tileSize": 256, "maxzoom": 12}},
            "terrain": {"source": "dem", "exaggeration": 1.3},
            "sky": {"sky-color": "#9ec7ef", "horizon-color": "#e4eef7", "fog-color": "#e9eef2", "horizon-fog-blend": 0.6},
            "layers": layers}


async def handle(bridge, method, path, body, host):
    """(status, content type, body bytes, extra headers) for map paths, or None."""
    p = path.split("?")[0]
    if p in ("/ride", "/plan", "/fitness", "/workouts", "/milestones", "/coach"):
        return 200, TYPES[".html"], (WEB / f"{p[1:]}.html").read_bytes(), {}
    if p.startswith("/web/") and p.endswith(".js"):
        f = (WEB / p[5:]).resolve()
        if f.parent != WEB.resolve() or not f.exists():
            return 404, "text/plain", b"not found", {}
        return 200, TYPES[".js"], f.read_bytes(), {}
    if p.startswith("/lib/"):
        f = (MAPS / "web" / "maplibre" / p[5:]).resolve()
        if f.parent != (MAPS / "web" / "maplibre").resolve() or not f.exists():
            return 404, "text/plain", b"not found", {}
        return 200, TYPES.get(f.suffix, "application/octet-stream"), f.read_bytes(), {"Cache-Control": "max-age=86400"}
    if p.startswith("/tiles/"):
        try:
            z, x, y = (int(v) for v in p.split("/")[2:5])
        except ValueError:
            return 400, "text/plain", b"bad tile", {}
        tile = maps().get(z, x, y)
        if not tile:
            return 204, "text/plain", b"", {}
        return 200, "application/x-protobuf", tile, {"Content-Encoding": "gzip", "Cache-Control": "max-age=86400"}
    if p.startswith("/terrain/"):
        parts = p.split("/")[2:5]
        try:
            z, x, y = int(parts[0]), int(parts[1]), int(parts[2].split(".")[0])
        except (ValueError, IndexError):
            return 400, "text/plain", b"bad tile", {}
        f = MAPS / "terrain" / str(z) / str(x) / f"{y}.png"
        if not f.exists():
            return 204, "text/plain", b"", {}
        return 200, "image/png", f.read_bytes(), {"Cache-Control": "max-age=86400"}
    if p.startswith("/fonts/"):
        from urllib.parse import unquote
        parts = unquote(p).split("/")
        stack, rng = parts[2].split(",")[0].strip(), parts[-1]
        f = MAPS / "web" / "fonts" / stack / rng
        if f.resolve().parent.parent != (MAPS / "web" / "fonts").resolve() or not f.exists():
            return 200, "application/x-protobuf", b"", {}   # a script we haven't got: no glyphs, no error
        return 200, "application/x-protobuf", f.read_bytes(), {"Cache-Control": "max-age=86400"}
    if p == "/style.json":
        return 200, "application/json", json.dumps(style(host)).encode(), {}
    if p == "/api/places":
        from urllib.parse import parse_qs, urlsplit
        q = parse_qs(urlsplit(path).query).get("q", [""])[0]
        pending = places.ensure(maps())
        found = await asyncio.get_running_loop().run_in_executor(None, places.search, q)
        return 200, "application/json", json.dumps({"results": found, "indexing": pending}).encode(), {}
    if p == "/api/near":
        from urllib.parse import parse_qs, urlsplit
        qs = parse_qs(urlsplit(path).query)
        try:
            lat, lon = float(qs["lat"][0]), float(qs["lon"][0])
        except (KeyError, ValueError):
            return 400, "application/json", b'{"error":"lat and lon please"}', {}
        places.ensure(maps())
        near = await asyncio.get_running_loop().run_in_executor(None, places.nearest, lat, lon)
        return 200, "application/json", json.dumps(near).encode(), {}
    if p == "/api/fitness":
        import fitness
        data = await asyncio.get_running_loop().run_in_executor(None, fitness.summary, HERE / "rides")
        return 200, "application/json", json.dumps(data).encode(), {}
    if p.startswith("/api/workouts"):
        import workouts
        ftp = bridge.profile["ftp"]
        try:
            if p == "/api/workouts" and method == b"GET":
                return 200, "application/json", json.dumps({"ftp": ftp, "workouts": workouts.list_all(ftp)}).encode(), {}
            if p == "/api/workouts/preview" and method == b"POST":
                steps = workouts.flatten(json.loads(body or b"{}").get("blocks") or [])
                return 200, "application/json", json.dumps({"steps": steps, "stats": workouts.stats(steps, ftp)}).encode(), {}
            if p == "/api/workouts/save" and method == b"POST":
                wid = workouts.save(json.loads(body or b"{}"))
                bridge.reload_workouts()
                return 200, "application/json", json.dumps({"id": wid}).encode(), {}
            if p.startswith("/api/workouts/delete/") and method == b"POST":
                workouts.delete(p.rsplit("/", 1)[1])
                bridge.reload_workouts()
                return 200, "application/json", b'{"ok":true}', {}
            if p.startswith("/api/workouts/start/") and method == b"POST":
                if not bridge.workout_start_id(p.rsplit("/", 1)[1]):
                    return 404, "application/json", b'{"error":"no such workout"}', {}
                return 200, "application/json", b'{"ok":true}', {}
        except workouts.BadWorkout as e:
            return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
        except ValueError:
            return 400, "application/json", b'{"error":"that request didn\'t make sense"}', {}
    if p == "/posts" or p.startswith(("/api/posts", "/posts/", "/api/strava", "/strava/")):
        return await posts_api(bridge, method, path, p, body)
    if p.startswith("/api/coach"):
        return await coach_api(bridge, method, path, p, body)
    if p == "/api/milestones":
        import milestones
        goal = bridge.profile.get("weekly_rides", 3)
        data = await asyncio.get_running_loop().run_in_executor(None, milestones.compute, HERE / "rides", goal)
        return 200, "application/json", json.dumps(data, ensure_ascii=False).encode(), {}
    if p == "/api/milestones/goal" and method == b"POST":
        import rider
        try:
            n = int(json.loads(body or b"{}").get("rides"))
            if not 1 <= n <= 7:
                raise ValueError
        except (ValueError, TypeError):
            return 400, "application/json", b'{"error":"a weekly goal of 1 to 7 rides"}', {}
        bridge.profile["weekly_rides"] = n
        rider.save(bridge.profile)
        return 200, "application/json", json.dumps({"weekly_rides": n}).encode(), {}
    if p == "/api/regions":
        try:
            regs = json.loads((HERE / "regions.json").read_text())["regions"]
        except (OSError, ValueError, KeyError):
            regs = []
        return 200, "application/json", json.dumps(regs).encode(), {}
    if p == "/api/home":
        import rider
        prof = rider.load(Path(bridge.csv_path).parent.parent / "profile.json" if getattr(bridge, "csv_path", None) else HERE / "profile.json")
        if method == b"POST":
            try:
                h = json.loads(body or b"{}")
                home = [float(h["lon"]), float(h["lat"]), float(h.get("zoom", 11))]
                if not (-180 <= home[0] <= 180 and -85 <= home[1] <= 85):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                return 400, "application/json", b'{"error":"lon, lat, zoom please"}', {}
            prof["home"] = home
            rider.save(prof)
            return 200, "application/json", json.dumps({"center": home[:2], "zoom": home[2]}).encode(), {}
        if prof.get("home"):
            h = prof["home"]
            return 200, "application/json", json.dumps({"center": h[:2], "zoom": h[2], "set": True}).encode(), {}
        try:                                  # no home view set yet: the first region in regions.json
            r = json.loads((HERE / "regions.json").read_text())["regions"][0]
            return 200, "application/json", json.dumps({"center": r["center"], "zoom": r["zoom"], "set": False}).encode(), {}
        except (OSError, ValueError, KeyError, IndexError):
            return 200, "application/json", b'{"center":[0,20],"zoom":2,"set":false}', {}
    if p == "/api/ideas":
        return 200, "application/json", json.dumps(ideas.IDEAS).encode(), {}
    if p == "/api/routes":
        return 200, "application/json", json.dumps(routes.list_routes()).encode(), {}
    if p.startswith("/api/route/") and method == b"GET":
        try:
            r = routes.load(p.rsplit("/", 1)[1])
        except (OSError, ValueError):
            return 404, "application/json", b'{"error":"no such route"}', {}
        return 200, "application/json", json.dumps(route_json(r)).encode(), {}
    if p == "/api/plan" and method == b"POST":
        return await plan(body)
    if p == "/api/route/save" and method == b"POST":
        req = json.loads(body or b"{}")
        r = _candidates.get(int(req.get("cid", 0)))
        if not r:
            return 404, "application/json", b'{"error":"that plan has expired - plan again"}', {}
        r.name = (req.get("name") or r.name).strip()[:60]
        r.id = routes.Route([r.points[0]], r.name).id        # a fresh id from the chosen name
        r.save()
        return 200, "application/json", json.dumps({"id": r.id}).encode(), {}
    if p == "/api/route/import" and method == b"POST":
        try:
            r = routes.from_gpx(body.decode("utf-8", errors="replace"))
            if len(r.points) < 2:
                raise ValueError("no track points in that file")
        except Exception as e:
            return 400, "application/json", json.dumps({"error": f"couldn't read that GPX: {e}"}).encode(), {}
        r.save()
        return 200, "application/json", json.dumps({"id": r.id, "name": r.name}).encode(), {}
    if p.startswith("/api/route/start/") and method == b"POST":
        try:
            bridge.route_start(p.rsplit("/", 1)[1])
        except (OSError, ValueError) as e:
            return 404, "application/json", json.dumps({"error": str(e)}).encode(), {}
        return 200, "application/json", b'{"ok":true}', {}
    if p == "/api/route/stop" and method == b"POST":
        bridge.route_stop()
        return 200, "application/json", b'{"ok":true}', {}
    return None


async def plan(body):
    import planner
    try:
        req = json.loads(body or b"{}")
        start = tuple(req["start"])
        loop = asyncio.get_running_loop()
        if req.get("end"):
            found = await loop.run_in_executor(None, planner.plan, start, tuple(req["end"]))
        else:
            km = max(3.0, min(150.0, float(req.get("km", 20))))
            want = req.get("want") or None
            if req.get("loop"):
                found = await loop.run_in_executor(None, lambda: planner.loops(start, km, 4, want))
            else:                                  # virtual ride: it can end anywhere
                found = await loop.run_in_executor(None, lambda: planner.outs(start, km, 4, want))
    except planner.PlannerError as e:
        return 422, "application/json", json.dumps({"error": f"no route found: {e}"}).encode(), {}
    except (KeyError, ValueError, TypeError) as e:
        return 400, "application/json", json.dumps({"error": f"bad request: {e}"}).encode(), {}
    out = []
    for r in found:
        cid = next(_cid)
        _candidates[cid] = r
        out.append(route_json(r, cid))
    while len(_candidates) > 40:                              # keep memory bounded
        _candidates.pop(next(iter(_candidates)))
    return 200, "application/json", json.dumps(out).encode(), {}


RIDE_RE = __import__("re").compile(r"ride_[0-9_\-]{10,30}")


def _strava():
    import strava
    return strava.Strava(HERE / "strava.json")


async def posts_api(bridge, method, path, p, body):
    """Ride posts: the list, one post, its image and pack; Strava connect and post."""
    import posts
    import strava
    from urllib.parse import parse_qs, urlsplit
    loop = asyncio.get_running_loop()
    rides = HERE / "rides"
    js = lambda obj, code=200: (code, "application/json", json.dumps(obj, ensure_ascii=False).encode(), {})

    def ride_path(stem):
        if not RIDE_RE.fullmatch(stem or "") or not (rides / f"{stem}.csv").exists():
            return None
        return rides / f"{stem}.csv"

    if p == "/posts":
        return 200, TYPES[".html"], (WEB / "posts.html").read_bytes(), {}
    if p == "/api/posts":
        import fitness, rider
        prof = rider.load(HERE / "profile.json")
        allr = await loop.run_in_executor(None, fitness.all_rides, rides, prof, HERE / "fitness_cache.json")
        out = []
        for r in reversed(allr):
            if r["minutes"] < posts.MIN_MINUTES:
                continue
            st = posts.load(rides / f"{r['ride']}.csv")
            out.append({"ride": r["ride"], "date": r["date"], "start": r["start"], "minutes": r["minutes"],
                        "load": r["tss"], "made": bool(st), "title": st["title"] if st else None,
                        "top": st["highlights"][0] if st and st["highlights"] else None})
        return js(out[:60])
    if p.startswith("/api/posts/"):
        parts = p.split("/")
        make = len(parts) == 5 and parts[3] == "make"
        rp = ride_path(parts[4] if make else parts[3])
        if not rp:
            return js({"error": "no such ride"}, 404)
        st = None if make else posts.load(rp)
        if st is None:
            st = await loop.run_in_executor(None, posts.make, rp)
        if st is None:
            return js({"error": "that ride is too short for a post"}, 422)
        return js(st)
    if p.startswith("/posts/"):
        parts = p.split("/")
        rp = ride_path(parts[2] if len(parts) > 3 else "")
        if not rp:
            return 404, "text/plain", b"no such ride", {}
        f = parts[3]
        if f == "pack.zip":
            data = await loop.run_in_executor(None, posts.zip_bytes, rp)
            return 200, "application/zip", data, {"Content-Disposition": f'attachment; filename="{rp.stem}_post.zip"'}
        types = {"card.png": "image/png", "for_claude.md": "text/markdown; charset=utf-8",
                 "caption.txt": "text/plain; charset=utf-8", "story.json": "application/json"}
        fp = posts.folder(rp) / f
        if f not in types or not fp.exists():
            return 404, "text/plain", b"not made yet", {}
        extra = {"Content-Disposition": f'attachment; filename="{rp.stem}_{f}"'} if "download" in path else {}
        return 200, types[f], fp.read_bytes(), extra

    sv = _strava()
    try:
        if p == "/api/strava":
            return js(sv.status())
        if p == "/api/strava/app" and method == b"POST":
            req = json.loads(body or b"{}")
            sv.set_app(req.get("client_id"), req.get("client_secret"))
            return js(sv.status())
        if p == "/api/strava/forget" and method == b"POST":
            sv.forget()
            return js(sv.status())
        if p == "/strava/connect":
            return 302, "text/plain", b"", {"Location": sv.auth_url()}
        if p == "/strava/callback":
            q = parse_qs(urlsplit(path).query)
            if q.get("error"):
                return 302, "text/plain", b"", {"Location": "/posts?strava=declined"}
            await loop.run_in_executor(None, sv.finish_auth, q.get("code", [""])[0], q.get("state", [""])[0],
                                       q.get("scope", [""])[0])
            return 302, "text/plain", b"", {"Location": "/posts?strava=connected"}
        if p.startswith("/api/strava/post/") and method == b"POST":
            rp = ride_path(p.rsplit("/", 1)[1])
            if not rp:
                return js({"error": "no such ride"}, 404)
            st = posts.load(rp) or await loop.run_in_executor(None, posts.make, rp)
            if not st:
                return js({"error": "that ride is too short for a post"}, 422)
            req = json.loads(body or b"{}")
            st = {**st, "title": (req.get("title") or st["title"])[:250], "caption": req.get("caption") or st["caption"]}
            res = await loop.run_in_executor(None, lambda: sv.post(st, rp, allow_upload=bool(req.get("allow_upload", True))))
            bridge.event(f"Posted to Strava ({res['how']}): {st['title']}")
            return js(res)
    except strava.StravaError as e:
        if p == "/strava/callback":
            from urllib.parse import quote
            return 302, "text/plain", b"", {"Location": "/posts?strava_error=" + quote(str(e))}
        return js({"error": str(e)}, 400)
    return js({"error": "not found"}, 404)


async def coach_api(bridge, method, path, p, body):
    """The Coach page and the hub command: check-ins, the diagnostic, today's plan, time-split workouts."""
    import coach
    import workouts
    from urllib.parse import parse_qs, urlsplit
    js = lambda obj, code=200: (code, "application/json", json.dumps(obj, ensure_ascii=False).encode(), {})
    rides = Path(bridge.csv_path).parent if getattr(bridge, "csv_path", None) else HERE / "rides"
    d = coach.load(coach.file_for(rides))                  # beside the bridge's own rides: a test bridge writes its own
    q = parse_qs(urlsplit(path).query)
    date = (q.get("date") or [coach.today()])[0]
    try:
        req = json.loads(body or b"{}") if method == b"POST" else {}
        date = req.get("date") or date
        if not __import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return js({"error": "date is YYYY-MM-DD"}, 400)
        if p == "/api/coach/today":
            return js({**coach.day(d, date), "test_steps": coach.TEST_STEPS, "ftp": bridge.profile["ftp"],
                       "verdicts": coach.VERDICTS, "workouts": [{"id": w.get("id"), "name": w["name"]} for w in bridge.workouts]})
        if p == "/api/coach/history":
            days = int((q.get("days") or ["30"])[0])
            since = (__import__("datetime").date.fromisoformat(date) - __import__("datetime").timedelta(days=days)).isoformat()
            return js({"checkins": {k: v for k, v in d["checkins"].items() if since <= k <= date},
                       "plans": {k: v for k, v in d["plans"].items() if since <= k <= date}})
        if p == "/api/coach/checkin" and method == b"POST":
            c = coach.record(d, date, req)
            coach.save(d)
            if c.get("verdict"):
                bridge.event(f"Check-in: {coach.VERDICTS[c['verdict']]} ({'; '.join(c['why'])})")
            return js(coach.day(d, date))
        if p == "/api/coach/test/start" and method == b"POST":
            bridge.coach_test_start()
            coach.record(d, date, {"test_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                                   "test_ride": Path(bridge.csv_path).stem})
            coach.save(d)
            return js({"ok": True, "steps": coach.TEST_STEPS})
        if p == "/api/coach/plan" and method == b"POST":
            coach.set_plan(d, date, req.get("verdict"), req.get("note"), req.get("workout"))
            coach.save(d)
            return js(coach.day(d, date))
        if p == "/api/coach/split/rebalance" and method == b"POST":
            return js({"minutes": coach.rebalance([float(m) for m in req["minutes"]], int(req["index"]),
                                                  float(req["value"]), float(req["total"]))})
        if p == "/api/coach/split/save" and method == b"POST":
            blocks = coach.split_to_blocks(req["parts"])
            wid = workouts.save({"id": req.get("id"), "name": req.get("name") or "Timed workout",
                                 "note": req.get("note") or "", "blocks": blocks})
            bridge.reload_workouts()
            if req.get("ride"):
                bridge.workout_start_id(wid)
            if req.get("plan"):
                coach.set_plan(d, date, workout=wid); coach.save(d)
            return js({"id": wid})
    except (ValueError, KeyError, TypeError, workouts.BadWorkout) as e:
        return js({"error": str(e)}, 400)
    return js({"error": "not found"}, 404)
