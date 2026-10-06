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
from map_paths import locate as map_folder
MAPS = map_folder()
WEB = HERE / "web"
TYPES = {".mjs": "text/javascript", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".glb": "model/gltf-binary",
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
    return {"id": r.id, "cid": cid, "name": r.name, "stats": r.stats(), "source": r.source,   # "course": made up, no real place
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
    if p == "/api/setup":
        # the welcome page's orientation (onboarding.py)
        import onboarding
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        if method == b"POST":
            try:
                out = onboarding.apply(base, json.loads(body or b"{}"))
            except (ValueError, TypeError) as e:
                return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
            return 200, "application/json", json.dumps(out).encode(), {}
        return 200, "application/json", json.dumps({"profile": onboarding.current(base), "first_run": onboarding.first_run(base),
                                                    "folder": str(HERE), "no_bike": bool(getattr(getattr(bridge, "args", None), "no_bike", False))}).encode(), {}
    if p == "/api/theme":
        import themes
        if method == b"POST":
            try:
                name = json.loads(body).get("theme")
                themes.set_theme(name)
            except (ValueError, TypeError, AttributeError):
                return 400, "application/json", b'{"error":"Choose a listed theme"}', {}
        elif method != b"GET":
            return 405, "application/json", b'{"error":"Method not allowed"}', {}
        return 200, "application/json", json.dumps({"theme": themes.current(), "options": themes.OPTIONS}).encode(), {}
    if p.startswith("/api/bike/"):
        import bike_api
        return await bike_api.handle(bridge, method, p, body)
    from urllib.parse import parse_qs, urlsplit
    if p == "/dashboard" and parse_qs(urlsplit(path).query).get("embedded", [""])[0] != "1":
        return 302, "text/plain", b"Open the Fitness Dashboard in Coach", {"Location": "/coach#fitness"}
    if p == "/course":
        return 302, "text/plain", b"Open unified ride screen", {"Location": "/ride?view=game"}
    if p in ("/ride/map", "/ride/game"):
        query = parse_qs(urlsplit(path).query)
        if query.get("embedded", [""])[0] != "1":
            view = "map" if p.endswith("map") else query.get("scene", ["game"])[0]
            if view not in ("map", "game", "pixel", "haunted"): view = "game"
            return 302, "text/plain", b"Open shared ride screen", {"Location": "/ride?view=" + view}
        name = "ride.html" if p.endswith("map") else "course.html"
        return 200, TYPES[".html"], (WEB / name).read_bytes(), {}
    if p == "/ride":
        return 200, TYPES[".html"], (WEB / "ride-hub.html").read_bytes(), {}
    if p == "/api/map/status":
        return 200, "application/json", json.dumps({"engine": (MAPS / "web/maplibre/maplibre-gl.mjs").exists(), "maps": bool(list((MAPS / "map").glob("*.pmtiles"))), "routing": (MAPS / "brouter/segments4").is_dir()}).encode(), {}
    if p == "/workouts":                 # the old block builder is gone: workouts are written on the coach page
        return 302, "text/plain", b"Write a workout on the coach page", {"Location": "/coach#write-ride"}
    if p in ("/ride", "/plan", "/fitness", "/milestones", "/coach", "/course", "/dashboard", "/welcome"):
        return 200, TYPES[".html"], (WEB / f"{p[1:]}.html").read_bytes(), {}
    if p == "/manifest.webmanifest":
        return 200, "application/manifest+json", (WEB / "manifest.webmanifest").read_bytes(), {"Cache-Control": "max-age=3600"}
    if p.startswith("/web/") and p.endswith((".js", ".css", ".svg", ".png", ".jpg", ".json", ".glb")):
        f = (WEB / p[5:]).resolve()
        if f.parent not in (WEB.resolve(), (WEB / "sprites").resolve(), (WEB / "vendor").resolve(), (WEB / "sports").resolve(), (WEB / "graveyard").resolve(), (WEB / "graveyard/Textures").resolve(), (WEB / "icons").resolve()) or not f.exists():
            return 404, "text/plain", b"not found", {}
        return 200, TYPES[f.suffix], f.read_bytes(), {}
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
    if p == "/api/ride/menu" and method == b"GET":
        import ride_library
        data = await asyncio.to_thread(ride_library.listing, bridge)
        return 200, "application/json", json.dumps(data).encode(), {"Cache-Control": "no-store"}
    if p == "/api/ride/menu/start" and method == b"POST":
        import ride_library
        try:
            req=json.loads(body or b"{}")
            if not isinstance(req,dict) or req.get('kind') not in ('workout','route'): raise ValueError()
        except ValueError:
            return 400,"application/json",b'{"error":"Choose a saved route or ERG workout."}',{}
        status=bridge.status()
        if status.get('workout') or status.get('route') or status.get('test'):
            return 409,"application/json",b'{"error":"Finish the active ride before starting another."}',{}
        if not status.get('bike') or status.get('no_bike'):
            return 409,"application/json",b'{"error":"Connect the bike first. You can still preview rides."}',{}
        data=await asyncio.to_thread(ride_library.listing,bridge)
        if data['guidance'].get('not_ready') or data['guidance'].get('review_required'):
            return 409,"application/json",b'{"error":"Review current cycling load and readiness in Fitness before starting."}',{}
        items=data['workouts'] if req['kind']=='workout' else data['routes']
        if not any(x['id']==req.get('id') for x in items):
            return 404,"application/json",b'{"error":"This saved ride is no longer available."}',{}
        # Recheck after the background calculation so a concurrent launch cannot be overwritten.
        status=bridge.status()
        if status.get('workout') or status.get('route') or status.get('test'):
            return 409,"application/json",b'{"error":"Another ride has already started."}',{}
        from urllib.parse import quote
        launch='/api/workouts/start/' if req['kind']=='workout' else '/api/route/start/'
        return await handle(bridge,method,launch+quote(req['id'],safe=''),b'{}',host)
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
                rides=Path(bridge.csv_path).parent if getattr(bridge,"csv_path",None) else HERE/"rides"
                await asyncio.get_running_loop().run_in_executor(None,capture_program_forecast,bridge,rides)
                if not bridge.workout_start_id(p.rsplit("/", 1)[1]):
                    return 404, "application/json", b'{"error":"no such workout"}', {}
                return 200, "application/json", b'{"ok":true}', {}
        except workouts.BadWorkout as e:
            return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
        except ValueError:
            return 400, "application/json", b'{"error":"that request didn\'t make sense"}', {}
    if p == "/posts" or p.startswith(("/api/posts", "/posts/", "/api/strava", "/strava/")):
        return await posts_api(bridge, method, path, p, body)
    if p == "/api/coach/progress-evidence":
        import progress_evidence
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        data = await asyncio.get_running_loop().run_in_executor(None, load_state, base)
        return 200, "application/json", json.dumps(progress_evidence.report(data)).encode(), {}
    if p.startswith("/api/coach") or p == "/api/calibration":      # calibration lives with the coach's data
        return await coach_api(bridge, method, path, p, body)
    if p == "/api/load":
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        data = await asyncio.get_running_loop().run_in_executor(None, load_state, base)
        import loads
        out = {k: v for k, v in data.items() if k != "days"} | {"days": data.get("days", [])[-42:]}
        if data.get("systems"):
            import coach
            cd = coach.load(coach.file_for(base / "rides")).get("checkins", {}).get(coach.today(), {})
            out["readiness"] = loads.readiness(data, cd)
        return 200, "application/json", json.dumps(out, ensure_ascii=False).encode(), {}
    if p == "/api/load/capacity" and method == b"POST":
        import loads
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        try:
            req = json.loads(body or b"{}")
            cal = loads.set_capacity(base, req.get("system"), req.get("usual_week"), req.get("note"))
        except (ValueError, TypeError) as e:
            return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
        _load_cache["key"] = None
        return 200, "application/json", json.dumps({"calibration": cal}).encode(), {}
    if p == "/api/load/swim-activity" and method == b"POST":
        import loads
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        try:
            req = json.loads(body or b"{}")
            info = loads.set_swim_activity(base, req.get("activity_id"), req.get("paddles"),
                                           req.get("pull_buoy"), req.get("swim_rpe"),
                **{k: req[k] for k in ("fins", "snorkel", "fins_fraction", "snorkel_fraction", "fin_type", "kick_rpe", "fin_kick_factor") if k in req})
        except (ValueError, TypeError) as e:
            return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
        _load_cache["key"] = None
        return 200, "application/json", json.dumps({"activity": info}).encode(), {}
    if p == "/api/load/phase" and method == b"POST":
        import loads
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        try:
            phase = loads.set_phase(base, json.loads(body or b"{}").get("phase"))
        except (ValueError, TypeError) as e:
            return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
        _load_cache["key"] = None
        return 200, "application/json", json.dumps({"phase": phase}).encode(), {}
    if p == "/api/morning":
        import morning
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        if method == b"POST":
            try:
                have = morning.record(base, json.loads(body or b"{}").get("days"))
            except (ValueError, TypeError, AttributeError) as e:
                return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
            _load_cache["key"] = None
            return 200, "application/json", json.dumps({"today": morning.assess(have), "days": len(have)}).encode(), {}
        have = morning.load(base)
        return 200, "application/json", json.dumps({"today": morning.assess(have), "days": have}).encode(), {}
    if p == "/api/steps":
        import loads
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        if method == b"POST":
            try:
                have = loads.set_steps(base, json.loads(body or b"{}").get("steps"))
            except (ValueError, TypeError, AttributeError) as e:
                return 400, "application/json", json.dumps({"error": str(e)}).encode(), {}
            _load_cache["key"] = None
            return 200, "application/json", json.dumps({"steps": have}).encode(), {}
        return 200, "application/json", json.dumps({"steps": loads.load_steps(base)}).encode(), {}
    if p == "/api/activities/upload" and method == b"POST":
        # a watch file chosen on the Coach page: the raw bytes, named in ?name=
        from urllib.parse import parse_qs, urlsplit
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        name = Path(parse_qs(urlsplit(path).query).get("name", [""])[0]).name
        ok = name.lower().endswith((".fit", ".tcx")) and not name.startswith(".") and 0 < len(body) <= 20_000_000
        if ok and name.lower().endswith(".fit"):
            ok = body[8:12] == b".FIT"
        elif ok:
            ok = b"TrainingCenterDatabase" in body[:4000]
        if not ok:
            return 400, "application/json", json.dumps({"error": f"{name or 'That file'} isn't a .fit or .tcx activity file"}).encode(), {}
        folder = base / "activities"
        folder.mkdir(exist_ok=True)
        dest = folder / name
        if dest.exists() and dest.read_bytes() == body:
            return 200, "application/json", json.dumps({"imported": [], "already": [name]}).encode(), {}
        dest.write_bytes(body)
        _load_cache["key"] = None
        return 200, "application/json", json.dumps({"imported": [name]}).encode(), {}
    if p == "/api/activities/import" and method == b"POST":
        base = Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE
        try:
            urls = json.loads(body or b"{}").get("urls") or []
        except ValueError:
            return 400, "application/json", b'{"error":"send {\"urls\": [...]}"}', {}
        res = await import_activities(base, urls)
        return 200, "application/json", json.dumps(res).encode(), {}
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
    if p == "/api/workout/resume" and method == b"POST":
        # pick up today's unfinished workout where it stopped (bridge.resume_offer is in /status as "resume")
        ok = bridge.workout_resume()
        return (200 if ok else 409), "application/json", json.dumps({"ok": ok}).encode(), {}
    if p == "/api/workout/resume/discard" and method == b"POST":
        bridge.resume_discard()
        return 200, "application/json", b'{"ok":true}', {}
    if p == "/api/workout/pause" and method == b"POST":
        # pause or resume the running workout by hand (it also pauses by itself when the rider stops)
        try:
            want = json.loads(body or b"{}").get("paused")
        except ValueError:
            want = None
        bridge.erg.paused = (not bridge.erg.paused) if want is None else bool(want)
        return 200, "application/json", json.dumps({"paused": bridge.erg.paused}).encode(), {}
    if p == "/api/course/forms":
        # which animals are the rider's forms, in order (the rider on the bike always comes first) - kept on the bridge
        f = HERE / "course_forms.json"
        known = set(json.loads((WEB / "sprites" / "animals.json").read_text())["animals"])
        if method == b"POST":
            try:
                forms = [x for x in json.loads(body or b"{}").get("forms", []) if x in known][:8]
            except (ValueError, AttributeError):
                forms = []
            if not forms:
                return 400, "application/json", b'{"error":"pick at least one animal"}', {}
            f.write_text(json.dumps({"forms": forms}))
        try:
            forms = [x for x in json.loads(f.read_text())["forms"] if x in known]
        except (OSError, ValueError, KeyError):
            forms = []
        return 200, "application/json", json.dumps({"forms": forms or ["unicorn", "wolf", "eagle", "dragon"]}).encode(), {}
    if p == "/api/course/start" and method == b"POST":
        # a ride planned without a map route: build today's course (course.py) and ride it like a route
        import coach, course
        try:
            req = json.loads(body or b"{}")
        except ValueError:
            req = {}
        rides = Path(bridge.csv_path).parent if getattr(bridge, "csv_path", None) else HERE / "rides"
        d = coach.load(coach.file_for(rides))
        day = with_focus(coach.day(d, coach.today()), bridge, d)
        minutes = float(req.get("minutes") or (day.get("plan") or {}).get("minutes") or 30)
        mass = getattr(getattr(bridge, "ride", None), "mass", 126.6)
        r, meta = course.build(minutes, day["focus"], mass, name=f"{day['focus']['name']} course · {round(minutes)} min")
        course.save(r, meta)
        bridge.route_start(r.id)
        return 200, "application/json", json.dumps({"id": r.id, "name": r.name}).encode(), {}
    if p.startswith("/api/course/") and method == b"GET":
        import course
        try:
            c = course.load(p.rsplit("/", 1)[1])
        except (OSError, ValueError, KeyError) as e:
            return 404, "application/json", json.dumps({"error": str(e)}).encode(), {}
        return 200, "application/json", json.dumps(c).encode(), {}
    if p.startswith("/api/route/") and p.endswith("/climbs") and method == b"GET":
        import session
        try:
            r = routes.load(p.split("/")[3])
        except (OSError, ValueError, IndexError):
            return 404, "application/json", b'{"error":"no such route"}', {}
        from bridge import virtual_speed
        ftp, mass = bridge.profile["ftp"], getattr(getattr(bridge, "ride", None), "mass", 126.6)
        rides_dir = Path(bridge.csv_path).parent if getattr(bridge, "csv_path", None) else HERE / "rides"
        try:
            hist = [c for c in json.loads((rides_dir / "climbs.json").read_text()) if c["route_id"] == r.id]
        except (OSError, ValueError):
            hist = []
        cl = session.climbs(r)
        import coach, skills
        d_ = coach.load(coach.file_for(rides_dir))
        factor = skills.LADDERS["climbing"]["levels"][skills.state(d_)["climbing"]["level"]]["goal_factor"]
        import cp as cp_mod
        cpw = cp_mod.estimate(cp_mod.best_curve(rides_dir), ftp)
        for c in cl:
            v = lambda w: virtual_speed(w, c["avg_grade"], mass)
            c["estimate_s"] = {k: round(c["length_m"] / v(f * ftp)) for k, f in (("easy", 0.6), ("steady", 0.75), ("hard", 0.9))}
            mine = [h["seconds"] for h in hist if h["n"] == c["n"]]
            c["best_s"], c["rides"] = (min(mine) if mine else None), len(mine)
            c["goal_s"] = round(c["best_s"] * factor) if c["best_s"] else c["estimate_s"]["steady"]   # the climb-pace step
            c["fastest_s"] = cp_mod.fastest_climb(c["length_m"], c["avg_grade"], mass, cpw["cp"], cpw["w_prime"])
            if c["fastest_s"] and c["goal_s"] < c["fastest_s"]:
                c["goal_s"] = c["fastest_s"]                   # never a goal your W' can't cover
        return 200, "application/json", json.dumps({"id": r.id, "name": r.name, "stats": r.stats(), "ftp": ftp,
                                                    "goal_factor": factor, "cp": cpw["cp"], "w_prime": cpw["w_prime"],
                                                    "climbs": cl}).encode(), {}
    if p == "/api/climbs" and method == b"GET":
        from urllib.parse import parse_qs, urlsplit
        q = parse_qs(urlsplit(path).query)
        rides_dir = Path(bridge.csv_path).parent if getattr(bridge, "csv_path", None) else HERE / "rides"
        try:
            have = json.loads((rides_dir / "climbs.json").read_text())
        except (OSError, ValueError):
            have = []
        if q.get("route_id"):
            have = [c for c in have if c["route_id"] == q["route_id"][0]]
        return 200, "application/json", json.dumps({"climbs": have[-int((q.get("limit") or ["200"])[0]):]}).encode(), {}
    if p.startswith("/api/route/") and method == b"GET":
        try:
            r = routes.load(p.rsplit("/", 1)[1])
        except (OSError, ValueError):
            return 404, "application/json", b'{"error":"no such route"}', {}
        return 200, "application/json", json.dumps(route_json(r)).encode(), {}
    if p == "/api/plan" and method == b"POST":
        return await plan(body)
    if p == "/api/plan/area" and method == b"POST":
        return await plan_area(bridge, body)
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


def today_focus(bridge):
    """Today's focus (focus.py) at the current FTP: the bridge's own if it's running, else from the coach plan."""
    import coach, focus
    if getattr(bridge, "focus", None):
        return bridge.focus
    rides = Path(bridge.csv_path).parent if getattr(bridge, "csv_path", None) else HERE / "rides"
    plan_ = coach.load(coach.file_for(rides))["plans"].get(coach.today()) or {}
    d = coach.load(coach.file_for(rides))
    return focus.resolve(plan_.get("focus"), bridge.profile["ftp"], (65, 80), plan_.get("verdict"), skill_levels(d)[0])


async def plan_area(bridge, body):
    """Area mode: loops inside a circle, judged for today's focus and a ride length in minutes.
    {center: [lat, lon], radius_km, minutes, focus?} - no center: the last area drawn on the planner."""
    import areaplan, focus, planner
    try:
        req = json.loads(body or b"{}")
        if req.get("center"):
            centre, radius = tuple(float(x) for x in req["center"]), float(req.get("radius_km", 5))
        else:
            last = areaplan.last_area()
            if not last:
                return 400, "application/json", b'{"error":"no area yet - circle one on the planner first"}', {}
            centre, radius = last[0], float(req.get("radius_km") or last[1])
        radius = max(1.0, min(40.0, radius))
        minutes = max(15.0, min(240.0, float(req.get("minutes", 45))))
        f = today_focus(bridge)
        if req.get("focus"):
            f = focus.resolve(focus.check(req["focus"]), bridge.profile["ftp"], tuple(f["rpm"]) if f else (65, 80))
        terrain = areaplan.Terrain.of(bridge) if hasattr(bridge, "args") else areaplan.Terrain()
        areaplan.save_area(None, centre, radius)
        found = await asyncio.get_running_loop().run_in_executor(
            None, lambda: areaplan.plan_area(centre, radius, minutes, f, terrain))
    except planner.PlannerError as e:
        return 422, "application/json", json.dumps({"error": str(e)}).encode(), {}
    except (KeyError, ValueError, TypeError, focus.BadFocus) as e:
        return 400, "application/json", json.dumps({"error": f"bad request: {e}"}).encode(), {}
    out = []
    for r, j in found:
        cid = next(_cid)
        _candidates[cid] = r
        out.append({**route_json(r, cid), "fit": j})
    while len(_candidates) > 40:
        _candidates.pop(next(iter(_candidates)))
    best = found[0][1]["score"] if found else 0
    longest = max((j["minutes"] for _, j in found), default=0)
    if found and longest < 0.75 * minutes:
        note = (f"The circle's too small for {minutes:.0f} min - the longest loop inside it is {longest} min. "
                f"Make the circle bigger, or ride one again when it finishes (about {max(2, round(minutes / max(longest, 1)))} times).")
    else:
        note = ("" if best >= 0.8 else
            f"This area is a stretch for {f['name'].lower()}: " + ("it's hilly for an easy day - a flatter area would suit it better."
                                                                   if f["key"] != "grit" else "a hillier area would give more steady climbing."))
    return 200, "application/json", json.dumps({"focus": f, "center": list(centre), "radius_km": radius,
                                                "minutes": minutes, "note": note, "routes": out}).encode(), {}


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


_load_cache = {"key": None, "data": None}


def load_state(base):
    """The body-systems picture, recomputed only when an activity, a ride, the profile or meta.json changes."""
    import loads
    base = Path(base)
    files = list((base / "activities").glob("*")) + list((base / "rides").glob("ride_*.csv")) + [base / "profile.json", base / "coach.json"]
    key = tuple(sorted((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files if f.exists())) + (str(__import__("datetime").date.today()),)
    if _load_cache["key"] != key:
        _load_cache["data"], _load_cache["key"] = loads.summary(base), key
    return _load_cache["data"]


def weekly_due(d, date, base):
    """The Sunday check-in, when it's open (Sunday through Tuesday) and not yet answered."""
    import weekly, datetime as _dt
    try:
        return weekly.due(d, _dt.date.fromisoformat(date), done_by_day(base, d))
    except Exception as e:
        return {"error": str(e)}


def lift_ctx(base, d, date):
    """What the steer needs from the load picture: the mechanical headline and today's readiness verdict."""
    import loads
    try:
        st = load_state(base)
        r = loads.readiness(st, (d["checkins"].get(date) or {})) if st.get("systems") else {}
        return {"headline": st.get("headline"), "verdict": r.get("verdict"),
                "engine_level": ((r.get("systems") or {}).get("engine") or {}).get("level"), "body_map":st.get("body_map")}
    except Exception:
        return {}


def lifting_today(d, date, base=None):
    """For Today: the day's planned lifts and whether they're checked off, the follow-up due, the unit."""
    import lifting
    s = lifting.state(d)
    sessions = [x for x in ((d["plans"].get(date) or {}).get("sessions") or []) if x.get("sport") == "gym" and x.get("lifts")]
    logged = {l["session"] for l in s["logs"] if l["date"] == date}
    return {"unit": s["unit"], "sessions": [{"index": i, "name": x["name"], "lifts": x["lifts"], "logged": x["name"] in logged,
                                            "log": next((l for l in s["logs"] if l["date"] == date and l["session"] == x["name"]), None)}
                                           for i, x in enumerate(sessions)],
            "pending_followup": lifting.pending_followup(d, __import__("datetime").date.fromisoformat(date)),
            "regions": lifting.regions(), "steer": lifting.steer(d, lift_ctx(base, d, date)) if base else None}


def with_systems(day_json, base):
    """Add the weakest-link body-systems readiness to a coach day, and let it win if it's worse."""
    import loads
    try:
        st = load_state(base)
        if not st.get("systems"):
            return day_json
        r = loads.readiness(st, (day_json.get("checkin") or {}))
        order = {"go": 0, "easy": 1, "rest": 2, None: -1}
        c = day_json.get("checkin") or {}
        final = max([r["verdict"], c.get("verdict")], key=lambda v: order[v])
        return {**day_json, "systems": r, "headline": st.get("headline"), "morning": st.get("morning"), "verdict": final,
                "zones": {x: st["systems"][x]["zone"] for x in loads.SYSTEMS}}
    except Exception as e:
        return {**day_json, "systems_error": str(e)}


def skill_levels(d, day_json=None):
    """Today's step on each skill ladder (one down on a day the watch or the check-in says easy), and the step."""
    import coach, skills
    mo = (day_json or {}).get("morning") or {}
    step = skills.step_today(d, (day_json or {}).get("date") or coach.today(), mo.get("level"))
    return skills.levels_for(d, step), step


def with_focus(day_json, bridge, d=None):
    """The day's focus resolved to ranges at the current FTP (on the rider's skill ladders), the presets, the ladders."""
    import coach, focus, skills
    plan = day_json.get("plan") or {}
    ftp = bridge.profile["ftp"]
    band = (getattr(bridge.args, "cadence_low", 65), getattr(bridge.args, "cadence_high", 80)) if hasattr(bridge, "args") else (65, 80)
    if d is None:
        rides = Path(bridge.csv_path).parent if getattr(bridge, "csv_path", None) else HERE / "rides"
        d = coach.load(coach.file_for(rides))
    levels, step = skill_levels(d, day_json)
    return {**day_json, "focus": focus.resolve(plan.get("focus"), ftp, band, plan.get("verdict"), levels),
            "focus_presets": {k: focus.resolve(k, ftp, band, None, levels) for k in focus.PRESETS},
            "skills": skills.summary(d, step)}


def done_by_day(base, d=None):
    """What was actually done each day (watch activities and bike rides): {date: [{sport, minutes}]}.
    With the coach data `d`, attempts that were cut short are left out (coach.counts)."""
    import coach
    try:
        st = load_state(base)
    except Exception:
        return {}
    out, small = {}, {}
    for a in st.get("activities", []):
        if d is not None and not coach.counts(d, a["date"], a["sport"], a["minutes"]):
            small[(a["date"], a["sport"])] = small.get((a["date"], a["sport"]), 0) + a["minutes"]
            continue
        out.setdefault(a["date"], []).append({"sport": a["sport"], "minutes": a["minutes"]})
    # pieces of one session (stopped, then resumed or restarted): together they are the day's session
    for (day, sport), mins in small.items():
        whole = [x for x in out.get(day, []) if x["sport"] == sport]
        if whole:
            whole[-1]["minutes"] += mins
        elif coach.counts(d, day, sport, mins):
            out.setdefault(day, []).append({"sport": sport, "minutes": mins})
    for day in out:
        for x in out[day]:
            x["minutes"] = round(x["minutes"])
            matching = [a for a in st.get("activities", []) if a["date"] == day and a["sport"] == x["sport"]]
            # Only aggregate a day's recordings when there is one session of this sport.
            # Multiple sessions keep their own activity's dose.
            peers = [v for v in out[day] if v["sport"] == x["sport"]]
            if len(peers) > 1:
                matching = [matching[peers.index(x)]] if peers.index(x) < len(matching) else []
            x["load"] = {k: round(sum(a.get(k) or 0 for a in matching), 1) for k in ("engine", "impact", "muscle")}
            x["km"] = round(sum(a.get("km") or 0 for a in matching), 2)
    return out


def calibration_view(d, rides, running_cleared_in=None):
    """The capacities (calibration.py) and which tests are coming due. Also checks benchmark runs for the block."""
    import calibration, coach
    try:
        st = load_state(rides.parent)
        est = st.get("calibration_estimates") or {}
        # benchmark runs on the plan: taken well (the two mornings after) -> the block may grow
        acts = {a["date"]: a for a in st.get("activities", []) if a["sport"] == "run"}
        rem = ((st.get("systems") or {}).get("impact", {}).get("tissue") or {}).get("remodeling") or {}
        for day, plan_ in d.get("plans", {}).items():
            if plan_.get("test") == "benchmark_run" and day in acts and rem.get("reference_points"):
                # Grade on a copy: a benchmark proposes capacity; it never grants it on a read.
                proposed = __import__('copy').deepcopy(d)
                result = calibration.block_test(proposed, day, acts[day], d.get("checkins", {}), rem["reference_points"])
                if result:
                    result = __import__('copy').deepcopy(result)
                    if result.get('result')=='grew': result['result']='review_candidate'
                    d.setdefault('benchmarks', {}).setdefault('runs', {})[day] = result
                    coach.save(d)
        # running calibrations on the plan: the athlete's own test sets the block once its eight-day watch is over
        for day, run_day in calibration.match_runs(d, acts).items():
            if run_day:
                end = (__import__("datetime").date.fromisoformat(run_day) + __import__("datetime").timedelta(days=calibration.CAL_WATCH_DAYS)).isoformat()
                others = sorted(k for k in acts if run_day < k <= end)
                if calibration.run_calibration(d, day, acts[run_day], d.get("checkins", {}), coach.today(), others, run_day):
                    coach.save(d)
                    _load_cache["key"] = None
        bench = calibration.benchmark_expectation(d, coach.today(), rem["reference_points"]) if rem.get("reference_points") else None
        return {"capacities": est, "due": calibration.due(est, running_cleared=(running_cleared_in == 0)), "benchmark": bench,
                "calibration_runs": calibration.calibration_runs(d, acts),
                "benchmarks": dict(sorted(((d.get("benchmarks") or {}).get("runs") or {}).items())[-5:]),
                "next_test_week": calibration.next_test_week(d)}
    except Exception as e:
        return {"error": str(e)}


def evaluate_skills(bridge, d, rides):
    """Move the skill ladders on what's happened (the rides, climb goals, and whether running is cleared)."""
    import coach, loads, skills
    try:
        st = load_state(rides.parent)
        run = loads.readiness(st, (d["checkins"].get(coach.today()) or {}))["running"]["verdict"] if st.get("systems") else None
        last_run = max((a["date"] for a in st.get("activities", []) if a["sport"] == "run"), default=None)
        changes = skills.evaluate(d, rides, run, last_run)
    except Exception as e:
        return [{"error": str(e)}]
    if changes:
        coach.save(d)
        for c in changes:
            if hasattr(bridge, "event"):
                bridge.event(f"Skill {'up' if c['to'] > c['from'] else 'down'}: {skills.LADDERS[c['skill']]['name']} "
                             f"step {c['to'] + 1} - {c['step']} ({c['why']})")
        if hasattr(bridge, "refresh_focus"):
            bridge.refresh_focus(force=True)
    return changes


async def import_activities(base, urls):
    """Download watch files (.fit/.tcx) into activities/ - for the coach syncing from COROS."""
    import urllib.request
    from urllib.parse import urlsplit
    folder = Path(base) / "activities"
    folder.mkdir(exist_ok=True)
    done, skipped = [], []
    for u in urls[:30]:
        parts = urlsplit(str(u))
        name = Path(parts.path).name
        if parts.scheme != "https" or not name.lower().endswith((".fit", ".tcx")) or "/" in name or name.startswith("."):
            skipped.append({"url": u, "why": "only https links to .fit or .tcx files"}); continue
        dest = folder / name
        if dest.exists() and dest.stat().st_size > 0:
            skipped.append({"url": u, "why": "already imported"}); continue
        def get():
            with urllib.request.urlopen(u, timeout=60) as r:
                return r.read(20_000_001)
        try:
            data = await asyncio.get_running_loop().run_in_executor(None, get)
        except OSError as e:
            skipped.append({"url": u, "why": f"download failed: {e}"}); continue
        if len(data) > 20_000_000 or (name.lower().endswith(".fit") and data[8:12] != b".FIT"):
            skipped.append({"url": u, "why": "not a FIT file (or too big)"}); continue
        dest.write_bytes(data)
        done.append(name)
    return {"imported": done, "skipped": skipped}


def capture_program_forecast(bridge, rides, d=None):
    """Persist pre-work forecasts; recorded sessions prevent a retrospective baseline."""
    import coach, training_block, recovery
    d=d if d is not None else coach.load(coach.file_for(rides))
    today=coach.today();done=done_by_day(rides.parent,d)
    f=training_block.forecast(d,today,done,load_state(rides.parent),d["checkins"].get(today),bridge.workouts)
    saved=recovery.save_forecasts(d,f,done)
    if saved:
        coach.save(d)
        path=Path(d["_path"]);stat=path.stat()
        if _load_cache["key"]:
            _load_cache["key"]=tuple((str(path),stat.st_mtime_ns,stat.st_size) if isinstance(x,tuple) and x[0]==str(path) else x for x in _load_cache["key"])
    return {"saved_dates":saved,"training_block":f}


async def coach_api(bridge, method, path, p, body):
    """The Coach page and the hub command: check-ins, the diagnostic, today's plan, time-split workouts."""
    import coach
    import workouts
    from urllib.parse import parse_qs, urlsplit
    js = lambda obj, code=200: (code, "application/json", json.dumps(obj, ensure_ascii=False).encode(), {})
    if p == "/api/coach/update-check" and method == b"GET":
        import updates
        try:return js(await asyncio.to_thread(updates.check,WEB))
        except Exception:return js({"error":"Could not reach the public update list. Your local Hub still works; try again later."},503)
    rides = Path(bridge.csv_path).parent if getattr(bridge, "csv_path", None) else HERE / "rides"
    d = coach.load(coach.file_for(rides))                  # beside the bridge's own rides: a test bridge writes its own
    q = parse_qs(urlsplit(path).query)
    date = (q.get("date") or [coach.today()])[0]
    try:
        req = json.loads(body or b"{}") if method == b"POST" else {}
        date = req.get("date") or date
        if not __import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return js({"error": "date is YYYY-MM-DD"}, 400)
        if p == "/api/coach/workout-goals":
            import workout_library
            if method==b"POST":
                item=workout_library.save_goal(d,req);coach.save(d)
                return js({'goal':item})
            return js({'goals':workout_library.goal_requests(d,(q.get('date') or [None])[0])})
        if p == "/api/coach/workout-goals/preview" and method==b"POST":
            import workout_library
            return js(workout_library.compare(req.get('sport'),req.get('goals'),req.get('session') or {}))
        if p == "/api/coach/run/preview" and method == b"POST":
            import run_workouts
            result = run_workouts.parse(req.get('fields'),req.get('repeats',1),req.get('mode','run_walk'))
            if result['valid']:
                result['exposure'] = run_workouts.exposure(result,bridge.profile)
            return js(result)
        if p == "/api/coach/workout-library":
            import workout_library
            if method==b"POST":
                if req.get('workout_import_id'):
                    import workout_imports
                    workout_imports.get(rides.parent,req['workout_import_id'])
                    if req.get('source_reviewed') is not True:raise ValueError('Review the source before keeping this workout')
                item=workout_library.save_template(d,req);coach.save(d)
                return js({'workout':item})
            if workout_library.add_starter_rides(d,bridge.profile["ftp"]):coach.save(d)     # the old builder's starters, once
            items=workout_library.listing(d,(q.get('sport') or [None])[0],q.get('favorites')==['1'],done_by_day(rides.parent,d))
            offset=max(0,min(1000,int((q.get('offset') or ['0'])[0])));limit=max(1,min(50,int((q.get('limit') or ['30'])[0])))
            summaries=[]
            for item in items[offset:offset+limit]:
                session=item['session'];summary={k:session[k] for k in ('sport','name','minutes','workout_goals') if k in session}
                summaries.append({**{k:item[k] for k in ('id','favorite','origin','created','updated','response_count')},'session':summary,'responses':item['responses'][-3:]})
            return js({'workouts':summaries,'total':len(items),'offset':offset,'next_offset':offset+limit if offset+limit<len(items) else None,'goals':workout_library.goal_requests(d),
                       'review':'Preferences and recorded responses guide selection; check current capacity, phase and whole-calendar load before reuse. Missing responses remain unknown.'})
        if p.startswith('/api/coach/workout-library/') and method==b'GET':
            import workout_library
            item=workout_library.get(d,p.rsplit('/',1)[1]);item['responses']=workout_library.responses(d,item,done_by_day(rides.parent,d))
            return js({'workout':item,'review':'Review exact details and current phase/load before scheduling; responses describe the original sessions.'})
        if p == "/api/coach/workout-library/favorite" and method==b"POST":
            import workout_library
            if req.get('id'):
                item=workout_library.get(d,req['id'])
                if not isinstance(req.get('favorite'),bool):raise ValueError('Favorite must be true or false')
                d['workout_library'][item['id']]['favorite']=req['favorite'];item['favorite']=req['favorite']
            else:item=workout_library.keep(d,date,req.get('index'),favorite=req.get('favorite',True))
            coach.save(d);return js({'workout':item})
        if p == "/api/coach/workout-import-capabilities" and method==b"GET":
            import workout_imports
            return js(workout_imports.capabilities())
        if p == "/api/coach/workout-import" and method==b"POST":
            import workout_imports
            return js(await asyncio.to_thread(workout_imports.upload,rides.parent,req))
        if p == "/api/coach/workout-imports" and method==b"GET":
            import workout_imports
            docs=[]
            for f in sorted(workout_imports.folder(rides.parent).glob('*/draft.json'),key=lambda f:f.stat().st_mtime,reverse=True)[:50]:
                try:
                    item=json.loads(f.read_text());docs.append({k:item[k] for k in ('id','name','status')})
                except (ValueError,OSError,KeyError):continue
            return js({'imports':docs})
        if p.startswith("/api/coach/workout-import/") and method==b"GET":
            import workout_imports,base64
            pieces=p.split('/');ident=pieces[4]
            if len(pieces)==7 and pieces[5]=='page':
                raw=workout_imports.get_page(rides.parent,ident,int(pieces[6]))
                return 200,'image/png',raw,{'Cache-Control':'no-store'}
            if len(pieces)==6 and pieces[5]=='source':
                raw,mime=workout_imports.source(rides.parent,ident)
                return 200,mime,raw,{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
            if len(pieces)!=5:raise ValueError('Unknown import view')
            doc=workout_imports.get(rides.parent,ident)
            if q.get('visual')==['1']:
                page=int((q.get('page') or ['1'])[0]);doc={**doc,'image':base64.b64encode(workout_imports.get_page(rides.parent,ident,page)).decode(),'image_page':page}
            return js(doc)
        if p == "/api/coach/swim/preview" and method==b"POST":
            import swim_workouts
            fields=swim_workouts.split_sections(req['text']) if 'text' in req else req.get('fields') or {}
            result=swim_workouts.parse(fields,req.get('repeats',1),req.get('unit','yd'),req.get('pool_length'))
            if req.get('minutes') is not None and float(req['minutes'])+.02<result['sendoff_minutes']:
                result['issues'].append(f"Timed sets already occupy {result['sendoff_minutes']:g} minutes; increase or clarify total session time")
                result['valid']=False
            return js({**result,'fields':fields})
        if p == "/api/coach/week":
            return js({"week": coach.week(d, date, done_by_day(rides.parent, d))})
        if p == "/api/coach/artwork":
            import artwork
            if method==b"POST":
                asset=artwork.upload(rides.parent,WEB,req)
                return js({'asset':asset,'assets':artwork.library(rides.parent,WEB)})
            return js({'assets':artwork.library(rides.parent,WEB)})
        if p == "/api/coach/forecast/save" and method == b"POST":
            return js(capture_program_forecast(bridge,rides,d))
        if p == "/api/coach/run-progression":
            import recovery
            rem=((load_state(rides.parent).get("systems") or {}).get("impact") or {}).get("tissue") or {}
            rem=rem.get("remodeling") or {}
            if method == b"POST":
                if req.get("action")=="begin_decline":
                    recovery.approve_decline(d,rem,coach.today(),req.get("note", ""))
                elif req.get("action")=="run_test":
                    recovery.record_run_test(d,req.get("step"),req,rem,coach.today())
                else:
                    recovery.record_check(d,req,coach.today())
                coach.save(d);_load_cache["key"]=None
                rem=((((load_state(rides.parent).get("systems") or {}).get("impact") or {}).get("tissue") or {}).get("remodeling") or {})
            return js(recovery.status(d,rem,coach.today()))
        if p == "/api/coach/today":
            evaluate_skills(bridge, d, rides)
            lr = coach.last_ride(rides, d=d)
            if lr:
                lr["rpe"] = (d["ratings"].get(lr["id"]) or {}).get("rpe")
            try:
                rem = (load_state(rides.parent)["systems"]["impact"]["tissue"] or {}).get("remodeling") or {}
                cleared = rem.get("cleared_to_run_in_days")
            except Exception:
                cleared = None
            cal = calibration_view(d, rides, cleared)
            capture_program_forecast(bridge,rides,d)
            return js({**with_focus(with_systems(coach.day(d, date), rides.parent), bridge, d), "last_ride": lr,
                       "events": coach.upcoming(d, date, cleared), "week": coach.week(d, date, done_by_day(rides.parent, d)),
                       "calibration": cal,
                       "rpe_words": coach.RPE_WORDS, "test_steps": coach.TEST_STEPS, "ftp": bridge.profile["ftp"],
                       "verdicts": coach.VERDICTS, "workouts": [{"id": w.get("id"), "name": w["name"]} for w in bridge.workouts],
                       "lifting": lifting_today(d, date, rides.parent),
                       "weekly": weekly_due(d, date, rides.parent),
                       "training_feedback":d.get("training_feedback",{}),
                       "workout_goals":__import__("workout_library").goal_requests(d,date),
                       "library_favorites":[i["id"] for i in d.get("workout_library",{}).values() if i.get("favorite")],
                       "training_block": __import__("training_block").forecast(
                           d, date, done_by_day(rides.parent, d), load_state(rides.parent), d["checkins"].get(date), bridge.workouts)})
        if p == '/api/coach/journal':
            import journal_album
            return js(journal_album.view(d))
        if p == "/api/coach/history":
            days = int((q.get("days") or ["30"])[0])
            since = (__import__("datetime").date.fromisoformat(date) - __import__("datetime").timedelta(days=days)).isoformat()
            return js({"checkins": {k: v for k, v in d["checkins"].items() if since <= k <= date},
                       "plans": {k: v for k, v in d["plans"].items() if since <= k <= date}})
        if p == '/api/coach/attention':
            import attention
            return js(attention.items(d,load_state(rides.parent),done_by_day(rides.parent,d),bridge.workouts,coach.today(),
                                      max(1,min(14,int((q.get('days') or ['7'])[0])))))
        if p == '/api/coach/coaching-review':
            import coaching_review, program_drafts
            state=load_state(rides.parent);done=done_by_day(rides.parent,d)
            if method==b'GET':
                return js({'outlook':coaching_review.outlook(d,state,done,bridge.workouts,coach.today(),int((q.get('days') or ['14'])[0])),
                           'capacity':coaching_review.capacity_candidates(d,state,coach.today()),
                           'recent_reviews':d.get('capacity_adjustments',[])[-12:]})
            revision=program_drafts.revision(d,rides.parent,bridge.profile,bridge.workouts,coach.today())
            try:
                if req.get('action')=='preview':return js(coaching_review.preview(d,state,done,bridge.workouts,coach.today(),rides.parent,revision,req))
                if req.get('action')=='apply':
                    result=coaching_review.apply(d,rides.parent,revision,coach.today(),req.get('draft_id'),req.get('approved'))
                    _load_cache['key']=None
                    return js(result)
                raise ValueError('Action is preview or apply')
            except program_drafts.Conflict as e:return js({'error':str(e),'code':'draft_conflict'},409)
        if p == "/api/coach/recent-weeks":
            import training_block as TB
            n = max(1, min(12, int((q.get("weeks") or ["4"])[0])))
            done = done_by_day(rides.parent, d)
            goal = d.get("program_goal") or {}
            avail = round(float(goal.get("hours") or 0) * 60) or None
            mon = TB.monday(__import__("datetime").date.fromisoformat(date))
            out = []
            for i in range(n, -2, -1):          # n weeks back, this week, and next week
                start = mon - __import__("datetime").timedelta(days=7 * i)
                w = TB._week(d, start, done)
                shapes = sorted({s.get("shape") for x in w["days"] for s in x["workouts"] if s.get("shape")})
                phase = next((ph for ph in d.get("phase_profiles", []) if ph["start"] <= start.isoformat() < ph["end"]), None)
                out.append({"week_of": w["start"], "when": "this week" if i == 0 else "next week" if i == -1 else f"{i} week{'s' if i > 1 else ''} ago",
                            "phase": phase and {"label": phase.get("label"), "stage": phase.get("stage")}, "shape": shapes,
                            "planned_minutes": w["total_minutes"], "done_minutes": w["done_minutes"], "available_minutes": avail,
                            "planned_share_of_available": round(w["total_minutes"] / avail, 2) if avail else None,
                            "completion": round(w["done_minutes"] / w["total_minutes"], 2) if w["total_minutes"] and i > 0 else None,
                            "hard_sessions": w["hard_sessions"],
                            "missed": [{"date": x["date"], "index": k, "session": s.get("name") or s.get("sport"), "minutes": s.get("minutes"),
                                        "reason": s.get("missed_reason")} for x in w["days"] for k, s in enumerate(x["workouts"]) if s.get("missed")]})
            return js({"coaching_review": {"outlook": __import__('coaching_review').outlook(d,load_state(rides.parent),done,bridge.workouts,coach.today()), "capacity": __import__('coaching_review').capacity_candidates(d,load_state(rides.parent),coach.today())}, "weeks": out, "goal": {k: goal.get(k) for k in ("goal", "sport", "target", "hours", "start")} if goal else None,
                       "note": "Planned vs done per week against the athlete's available time; missed sessions with their reasons."})
        if p == "/api/coach/missed" and method == b"GET":
            start = (q.get("start") or [(__import__("datetime").date.fromisoformat(coach.today()) - __import__("datetime").timedelta(days=84)).isoformat()])[0]
            end = (q.get("end") or [coach.today()])[0]
            return js({"missed": coach.missed_days(d, start, end, done_by_day(rides.parent, d)), "reasons": list(coach.MISS_REASONS)})
        if p == "/api/coach/missed" and method == b"POST":
            try:
                entry = coach.record_missed(d, date, req.get("index"), req.get("reason"), req.get("note", ""))
            except ValueError as e:
                return js({"error": str(e)}, 400)
            coach.save(d); _load_cache["key"] = None
            return js({"missed": entry, "week": coach.week(d, date, done_by_day(rides.parent, d))})
        if p == "/api/coach/flag" and method == b"POST":
            import journal
            c = d["checkins"].get(date)
            try:
                if not c:
                    raise ValueError("no check-in that day")
                f = journal.settle(c, req.get("id"), req.get("action"),
                                   __import__("datetime").datetime.now().isoformat(timespec="minutes"))
            except ValueError as e:
                return js({"error": str(e)}, 400)
            c["verdict"], c["why"] = coach.verdict(d, date)
            import recovery
            recovery.observe_checkin(d,date,c)
            coach.save(d); _load_cache["key"] = None
            return js({"flag": f, **with_systems(coach.day(d, date), rides.parent)})
        if p == "/api/coach/capacity-followup":
            if method!=b'POST':return js({'error':'Use POST to record a delayed recovery report'},405)
            import capacity_planning
            result=capacity_planning.record_followup(d,date,req.get('session_index'),req,done_by_day(rides.parent,d),coach.today())
            coach.save(d)
            return js({'followup':result,'notice':'Report saved. No capacity limit, hold or workout changed.'})
        if p == "/api/coach/capacity-review":
            import capacity_planning
            if method not in (b'GET', b'POST'):return js({'error':'Use GET or a read-only POST scenario'},405)
            if method==b'POST' and set(req)-{'demands'}:raise ValueError('Capacity review accepts only demands; it never saves')
            return js(capacity_planning.review(d,load_state(rides.parent),coach.today(),req.get('demands') if method==b'POST' else None,__import__('onboarding').current(rides.parent)))
        if p == "/api/coach/program-builder":
            import program_builder, training_block
            gate=training_block.running_gate(d,load_state(rides.parent),d['checkins'].get(coach.today()))
            if method == b"GET":
                goal=d.get('program_goal');phases=d.get('phase_profiles',[])
                weeks=program_builder.macro_weeks(phases,program_builder.P.date(goal['start']),max(program_builder.P.date(goal.get('end') or goal.get('target') or phases[-1]['end']),program_builder.P.date(phases[-1]['end'])),goal['focus'],goal['sport'],gate['status']!='open_for_review',goal['hours'],d.get('plans'),goal.get('schedule_options')) if goal and phases else []
                return js({'goal':goal,'phases':phases,'weeks':weeks,'events':d.get('events',[]),'running_hold':gate['status']!='open_for_review','last_application':(d.get('program_apply_receipts') or [None])[-1],'capacity_review':__import__('capacity_planning').review(d,load_state(rides.parent),coach.today(),athlete=__import__('onboarding').current(rides.parent)),'capabilities':{'reviewed_drafts':True,'calendar_evidence':True,'capacity_planning':True}})
            action=req.get('action','preview')
            if action not in ('preview','accept'):raise ValueError('action is preview or accept')
            import program_drafts
            state_revision=program_drafts.revision(d,rides.parent,bridge.profile,bridge.workouts,coach.today())
            if action=='accept':
                try:
                    result=program_drafts.apply(rides.parent,d,req.get('draft_id'),state_revision,coach.today())
                except program_drafts.Conflict as e:
                    return js({'error':str(e),'code':'draft_conflict','retry':'preview_program'},409)
                _load_cache['key']=None
                return js(result)
            proposal=program_builder.propose(d,req,coach.today(),gate)
            if req.get('starter_enabled'):
                import starter_programs, onboarding
                proposal['starter_level']=req.get('starter_level','easy')
                proposal['starter_equipment']=req.get('starter_equipment','basic')
                proposal['strength_anchors']=req.get('strength_anchors') or []
                proposal['neutral_forecast']=req.get('neutral_forecast',True)
                proposal['starter']=starter_programs.build(d,proposal,onboarding.current(rides.parent),load_state(rides.parent),done_by_day(rides.parent,d),bridge.workouts,today=coach.today())
            import capacity_planning
            proposal['capacity_review']=capacity_planning.review(d,load_state(rides.parent),coach.today(),proposal['capacity_demands'],__import__('onboarding').current(rides.parent))
            return js(program_drafts.store(rides.parent,proposal,state_revision))
        if p in ('/api/coach/calendar','/api/coach/reading-evidence'):
            import planning_evidence
            if method!=b'GET':return js({'error':'Evidence is read-only'},405)
            state=load_state(rides.parent);done=done_by_day(rides.parent,d)
            if p.endswith('/calendar'):
                return js(planning_evidence.calendar(d,state,done,bridge.workouts,coach.today(),date,int((q.get('days') or ['7'])[0])))
            return js(planning_evidence.explain(d,state,done,bridge.workouts,coach.today(),date,(q.get('metric') or ['cardio_fatigue'])[0]))
        if p == "/api/coach/phase-profiles":
            import phaseblend, loads, training_block
            if method == b"POST":
                action=req.get('action','save')
                if action not in ('save','preview'):raise ValueError('action is save or preview')
                phaseblend.save(d,req,coach.today())
                if action=='save':coach.save(d)
                date=req.get('start') or date
            st=load_state(rides.parent)
            rd=loads.readiness(st,d['checkins'].get(coach.today()) or {}) if st.get('systems') else {}
            gate=training_block.running_gate(d,st,d['checkins'].get(coach.today()))
            if gate['status']!='open_for_review':rd={**rd,'running':{'verdict':'rest','why':gate['reasons']}}
            return js(phaseblend.view(d,date,rd,st.get('headline')))
        if p == "/api/coach/progression":
            import progression, training_block
            if method == b"POST":
                action=req.get("action")
                if action=="enable":
                    progression.enable(d)
                elif action=="resolve_symptom":
                    key=req.get("report_key")
                    if key not in d.get("training_feedback",{}) or req.get("resolved") is not True:
                        raise ValueError("Explicitly confirm the recorded symptom has resolved")
                    d.setdefault("progression_symptom_reviews",{})[key]={"date":coach.today(),"note":str(req.get("note") or "")[:1000]}
                elif action=="compare":
                    result=progression.compare(d,coach.today(),req["session_date"],int(req.get("session_index",0)),load_state(rides.parent),done_by_day(rides.parent,d),bridge.workouts)
                    return js(result)
                else:raise ValueError("action is enable, resolve_symptom or compare")
                coach.save(d)
            return js({"policy":(d.get("training_block") or {}).get("progression"),
                       "decisions":d.get("progression_decisions",[])[-12:],
                       "active_symptoms":progression.active_symptoms(d,coach.today())})
        if p == "/api/coach/session-explanation" and method == b"POST":
            import session_explanations
            result=session_explanations.update(d,date,req.get("session_index"),req.get("text"),req.get("context_token"))
            if result["changed"]:coach.save(d)
            return js(result)
        if p == "/api/coach/session-report":
            import progression
            if method == b"POST":
                entry=progression.report(d,date,int(req.get("session_index",0)),req,done_by_day(rides.parent,d),coach.today())
                entry["assessment"]=progression.feedback(d,entry)
                coach.save(d)
                _load_cache["key"] = None
                progression.daily_adapt(d,coach.today(),done_by_day(rides.parent,d),load_state(rides.parent),bridge.workouts)
                coach.save(d)
                capture_program_forecast(bridge,rides,d)
                return js(entry)
            return js({"reports":d.get("training_feedback",{})})
        if p == "/api/coach/checkin" and method == b"POST":
            import copy,journal_album
            request_id=req.get('request_id')
            if request_id is not None and (not isinstance(request_id,str) or len(request_id)>100):raise ValueError('Invalid save identifier')
            existing=next((e for e in d.get('journal_entries',[]) if request_id and e.get('request_id')==request_id and e['date']==date),None)
            if existing:return js({**coach.day(d,date),'saved':True,'journal_entry':existing})
            previous=copy.deepcopy(d['checkins'].get(date))
            c = coach.record(d, date, req)
            entry=journal_album.append(d,date,c,journal_album.capture(d,date),previous,request_id)
            coach.save(d)  # Persist the report and album entry before any derived calculations.
            _load_cache["key"] = None
            if req.get('defer_refresh'):
                return js({**coach.day(d,date),'saved':True,'journal_entry':entry,'refresh_pending':True})
            # Other clients retain the complete synchronous update.
            return await coach_api(bridge,method,'/api/coach/checkin/refresh','/api/coach/checkin/refresh',json.dumps({'date':date,'request_id':entry.get('request_id')}).encode())
        if p == "/api/coach/checkin/refresh" and method == b"POST":
            import copy
            entries=[e for e in d.get('journal_entries',[]) if e['date']==date]
            entry=entries[-1] if entries else None
            if not entry:return js({'error':'No saved check-in to refresh'},400)
            if req.get('request_id') and entry.get('request_id')!=req['request_id']:
                return js({'saved':True,'superseded':True})
            c=d['checkins'].get(date,{})
            warning=None
            try:
                import progression
                st=load_state(rides.parent)
                readings={'headline':st.get('headline'),'day':next((x for x in st.get('days',[]) if x['date']==date),None)}
                if st.get('systems'):
                    import loads
                    readings['readiness']=loads.readiness(st,c)
                if entry['snapshot'].get('readings') is None:
                    entry['snapshot']['readings']=copy.deepcopy(readings)
                coach.save(d)
                progression.daily_adapt(d,date,done_by_day(rides.parent,d),st,bridge.workouts)
                coach.save(d)
                capture_program_forecast(bridge,rides,d)
            except Exception as e:
                warning='Your check-in was saved. Some training calculations could not refresh; try refreshing the readings.'
                print('Check-in saved; derived update failed:',e)
            result=with_systems(coach.day(d,date),rides.parent)
            needs=None
            if date==coach.today():
                try:                                  # what the assistant should go through with the athlete now
                    import attention
                    needs=attention.items(d,load_state(rides.parent),done_by_day(rides.parent,d),bridge.workouts,coach.today())
                except Exception as e:
                    print('Attention list failed:',e)
            return js({**result,'saved':True,'journal_entry':entry,'warning':warning,'attention':needs})
        if p == "/api/coach/test/start" and method == b"POST":
            capture_program_forecast(bridge,rides,d)
            bridge.coach_test_start()
            coach.record(d, date, {"test_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                                   "test_ride": Path(bridge.csv_path).stem})
            coach.save(d)
            return js({"ok": True, "steps": coach.TEST_STEPS})
        if p == "/api/coach/plan" and method == b"POST":
            import focus
            try:
                coach.set_plan(d, date, req.get("verdict"), req.get("note"), req.get("workout"), req.get("focus"),
                               req.get("sport"), req.get("minutes"))
                if req.get("sport")=="run" or any(x.get("sport")=="run" for x in req.get("sessions",[])):
                    import training_block
                    gate=training_block.running_gate(d,load_state(rides.parent),d["checkins"].get(coach.today()))
                    if gate["status"]!="open_for_review":raise ValueError("Running stays unscheduled: "+"; ".join(gate["reasons"] or ["mechanical metrics and preparatory checks need review"]))
                if "sessions" in req:
                    if any(x.get('library_id') or x.get('goal_request_id') for x in req['sessions']) and done_by_day(rides.parent,d).get(date):raise ValueError('Keep completed workouts when reusing library prescriptions')
                    coach.set_sessions(d, date, req["sessions"])
                    import workout_library
                    for i,source in enumerate(req['sessions']):
                        if source.get('workout_goals') or source.get('goal_request_id'):workout_library.attach_goals(d,date,i,source)
                        if source.get('library_id'):workout_library.keep(d,date,i)
            except (focus.BadFocus, ValueError, TypeError) as e:
                return js({"error": str(e)}, 400)
            coach.save(d)
            capture_program_forecast(bridge,rides,d)
            if hasattr(bridge, "refresh_focus"):
                bridge.refresh_focus(force=True)            # a new focus reaches the bike right away
            return js(with_focus(with_systems(coach.day(d, date), rides.parent), bridge))
        if p == "/api/coach/rate" and method == b"POST":
            ride = req.get("ride") or (coach.last_ride(rides, d=d) or {}).get("id")
            if not ride:
                return js({"error": "no ride to rate yet"}, 400)
            r = coach.rate(d, ride, req.get("rpe"))
            coach.save(d)
            bridge.event(f"Effort rating: {ride} felt {r['rpe']}/10 ({coach.RPE_WORDS[r['rpe']]})") if hasattr(bridge, "event") else None
            return js({"ride": ride, **r})
        if p == "/api/coach/test" and method == b"POST":
            import calibration
            try:
                if req.get('test')=='benchmark_run':
                    import training_block as TB
                    gate=TB.running_gate(d,load_state(rides.parent),d.get('checkins',{}).get(coach.today()))
                    if gate['status']!='open_for_review':raise ValueError('A benchmark cannot be scheduled through the current running hold')
                plan_ = calibration.schedule(d, date, req.get("test"))
                if req.get('test')=='benchmark_run':
                    if date<coach.today():raise ValueError('Schedule a future benchmark, not a past one')
                    projection=TB.projected_loads(d,coach.today(),[date],load_state(rides.parent),done_by_day(rides.parent,d),bridge.workouts).get(date) or {}
                    reading=next((m for m in projection.get('metrics',[]) if m['key']=='run_mechanical'),{})
                    if reading.get('after') is None or reading['after']>=1.5:raise ValueError('Benchmark forecast is unknown or exceeds the running planning limit; review its dose and spacing first')
            except ValueError as e:
                return js({"error": str(e)}, 400)
            coach.save(d)
            capture_program_forecast(bridge,rides,d)
            if hasattr(bridge, "refresh_focus"):
                bridge.refresh_focus(force=True)
            return js({"date": date, "plan": plan_})
        if p == "/api/coach/testweek" and method == b"POST":
            import calibration
            try:
                monday = req.get("monday") or calibration.next_test_week(d)
                cal = calibration_view(d, rides)
                due = [t["test"] for t in cal.get("due", [])] or None
                days = calibration.plan_test_week(d, monday, due)
            except ValueError as e:
                return js({"error": str(e)}, 400)
            coach.save(d)
            return js({"monday": monday, "days": days})
        if p == "/api/calibration" and method == b"POST":
            import calibration
            try:
                if req.get("calibration_run") and req.get("was_test") is not None:
                    e = calibration.calibration_confirm(d, req["calibration_run"], req["was_test"] is True, req.get("run_date"))
                elif req.get("calibration_run"):
                    e = calibration.calibration_stop(d, req["calibration_run"], req.get("reason"), req.get("note", ""))
                elif req.get("benchmark"):
                    e = calibration.benchmark_report(d, req["benchmark"], req.get("rpe"), req.get("pain", False), req.get("note", ""))
                elif req.get("t400") is not None:
                    import cp as cp_mod
                    note = f"400 m in {req['t400']} s, 200 m in {req['t200']} s"
                    e = calibration.record(d, "swim_css", calibration.css_from_times(req["t400"], req["t200"]), "test",
                                           req.get("date"), note)
                    e["d_prime"] = calibration.record(d, "swim_dprime", cp_mod.swim_d_prime(req["t400"], req["t200"]),
                                                      "test", req.get("date"), note)["value"]
                else:
                    e = calibration.record(d, req.get("capacity"), req.get("value"), req.get("kind", "manual"),
                                           req.get("date"), req.get("note", ""))
            except (ValueError, TypeError, KeyError) as e2:
                return js({"error": str(e2)}, 400)
            coach.save(d)
            _load_cache["key"] = None
            return js({"recorded": e})
        if p == "/api/coach/predictions":
            # race predictions the assistant made from the hub's models, refined and graded (predictions.py)
            import predictions
            if method == b"POST":
                try:
                    if req.get("result"):
                        out = predictions.result(d, req.get("event"), req.get("result"), req.get("legs"), req.get("note"))
                    else:
                        out = predictions.save(d, req.get("event"), req.get("likely"), req.get("low"), req.get("high"),
                                               req.get("legs"), req.get("basis"), req.get("levers"), coach.today())
                except (ValueError, TypeError) as e:
                    return js({"error": str(e)}, 400)
                coach.save(d)
                return js({"saved": out} | predictions.view(d, coach.today()))
            return js(predictions.view(d, coach.today()))
        if p == "/api/coach/event" and method == b"POST":
            if req.get("remove"):
                gone = coach.remove_event(d, req["remove"]); coach.save(d)
                return js({"removed": gone, "events": coach.upcoming(d)})
            try:
                ev = coach.add_event(d, req.get("date"), req.get("name") or "Event", req.get("kind", "race"),
                                     req.get("sport", "bike"), req.get("note"), req.get("detail"))
            except ValueError as e:
                return js({"error": str(e)}, 400)
            coach.save(d)
            return js({"added": ev, "events": coach.upcoming(d)})
        if p == "/api/coach/skill" and method == b"POST":
            import skills
            try:
                ev = skills.set_level(d, req.get("skill"), int(req.get("level", 1)) - 1,
                                      req.get("why") or "set by the coach")
            except (ValueError, TypeError) as e:
                return js({"error": str(e)}, 400)
            coach.save(d)
            capture_program_forecast(bridge,rides,d)
            if hasattr(bridge, "refresh_focus"):
                bridge.refresh_focus(force=True)
            return js({"changed": ev, "skills": skills.summary(d)})
        if p.startswith("/api/coach/programming"):
            # swim, bike and run templates and guidance for today's load (programming.py)
            import programming, rider, loads, datetime as _dt
            if p.endswith("/swim") and method == b"POST":
                s_ = programming.set_swim(d, req.get("mix"), req.get("drill_share"), req.get("follow_event"), req.get("profile_id"))
                coach.save(d)
                return js({"swim": s_})
            sport = (q.get("sport") or [req.get("sport") or "swim"])[0]
            st = load_state(rides.parent)
            rd = loads.readiness(st, d["checkins"].get(date) or {})
            est = st.get("calibration_estimates") or {}
            caps = {"swim_css": (est.get("swim_css") or {}).get("value"), "ftp": (est.get("ftp") or {}).get("value")}
            prof = rider.load(rides.parent / "profile.json")
            return js(programming.programming(d, prof, sport, _dt.date.fromisoformat(date), rd, st.get("headline"), caps,
                                               swim_profile=(q.get("swim_profile") or [req.get("swim_profile")])[0], activities=st.get("activities")))
        if p == "/api/coach/route/plan" and method == b"POST":
            import routes, copy, math, training_block, re
            rid = req.get("route_id")
            if not isinstance(rid,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,120}",rid): raise ValueError("Choose a saved route")
            try: route = routes.load(rid)
            except (OSError,ValueError,KeyError): raise ValueError("Saved route is unavailable")
            minutes = float(req.get("minutes", 45))
            if not math.isfinite(minutes) or not 1 <= minutes <= 600:
                raise ValueError("Choose a planned duration of 1–600 minutes")
            candidate = copy.deepcopy(d)
            items = copy.deepcopy(training_block.sessions(candidate["plans"].get(date) or {}))
            items = [s for s in items if s.get("sport") != "rest"]
            items.append({"sport":"ride", "name":route.name, "minutes":minutes, "route_id":route.id,
                          "note":f"Route ride · {route.length/1000:.1f} km. Duration is a planning target; terrain and pace change actual time."})
            coach.set_sessions(candidate, date, items, draft=True)
            coach.save(candidate)
            capture_program_forecast(bridge, rides, candidate)
            return js({"sessions":candidate["plans"][date]["sessions"]})
        if p == "/api/coach/workout-capabilities":
            return js({"section_aware_saving":True,"repeated_blocks":True,"session_actions":True,"cycling_power_parser":True,"swim_parser":True})
        if p == "/api/coach/session/action" and method == b"POST":
            index=req.get("index")
            originals=(d.get("plans",{}).get(date) or {}).get("sessions") or []
            if req.get("action")=="restore" and isinstance(index,int) and 0<=index<len(originals):
                saved=d.get("skipped_workouts",{}).get(originals[index].get("skipped_id"),{}).get("session",{})
                if saved.get("sport")=="run":
                    import training_block
                    gate=training_block.running_gate(d,load_state(rides.parent),d["checkins"].get(coach.today()))
                    if gate["status"]!="open_for_review":raise ValueError("Running remains gated; review load and readiness before restoring")
            # Refuse changes to a day containing imported actual exercise as well.
            if done_by_day(rides.parent,d).get(date):raise ValueError("Keep completed workouts; edit their reports instead")
            coach.session_action(d,date,index,req.get("action"))
            coach.save(d)
            capture_program_forecast(bridge,rides,d)
            return js({"ok":True})
        if p == "/api/coach/session/add" and method == b"POST":
            if req.get("run_recipe") is not None and req.get("sport") != "run":
                raise ValueError("Choose Running for a running recipe")
            if req.get("swim_recipe") is not None:
                if req.get("sport") != "swim":raise ValueError("Choose Swimming for a swim recipe")
                if req.get('workout_import_id'):
                    import workout_imports
                    workout_imports.get(rides.parent,req['workout_import_id'])
                    if req.get('source_reviewed') is not True:raise ValueError('Compare the extracted text with the source and confirm it before saving')
                if req.get('index') is not None and done_by_day(rides.parent,d).get(date):raise ValueError('Keep completed workouts; edit their reports instead')
                import swim_workouts
                candidate=swim_workouts.add(d,date,req)
                import workout_library
                at=req.get('index') if req.get('index') is not None else len(candidate['plans'][date]['sessions'])-1
                workout_library.attach_goals(candidate,date,at,req);workout_library.keep(candidate,date,at,favorite=req.get('favorite'))
                coach.save(candidate)
                capture_program_forecast(bridge,rides,candidate)
                return js({'sessions':candidate['plans'][date]['sessions']})
            if req.get("ride_blocks") is not None:
                if req.get("index") is not None and done_by_day(rides.parent,d).get(date):
                    raise ValueError("Keep completed workouts; edit their reports instead")
                import ride_workouts,workouts
                candidate,wid=ride_workouts.add(d,date,req)
                try:
                    import workout_library
                    at=req.get('index') if req.get('index') is not None else len(candidate['plans'][date]['sessions'])-1
                    workout_library.attach_goals(candidate,date,at,req);workout_library.keep(candidate,date,at,favorite=req.get('favorite'))
                    coach.save(candidate)
                except Exception:
                    workouts.delete(wid)
                    raise
                bridge.reload_workouts()
                capture_program_forecast(bridge,rides,candidate)
                return js({"sessions":candidate["plans"][date]["sessions"],"workout":wid})
            if req.get("sport")=="run":
                import training_block
                gate=training_block.running_gate(d,load_state(rides.parent),d["checkins"].get(coach.today()))
                if gate["status"]!="open_for_review":raise ValueError("Running stays unscheduled: "+"; ".join(gate["reasons"] or ["metrics and preparatory checks need review"]))
            if req.get('run_recipe') is not None:
                if req.get('index') is not None and done_by_day(rides.parent,d).get(date):
                    raise ValueError('Keep completed workouts; edit their reports instead')
                import run_workouts,workout_library
                candidate,at = run_workouts.add(d,date,req)
                workout_library.attach_goals(candidate,date,at,req)
                workout_library.keep(candidate,date,at,favorite=req.get('favorite'))
                coach.save(candidate);capture_program_forecast(bridge,rides,candidate)
                return js({'sessions':candidate['plans'][date]['sessions']})
            # add one session to a day from the Plan tab's + buttons (a plain list; the AI can refine it)
            p_ = d["plans"].get(date) or {}
            cur = list(p_.get("sessions") or ([{"sport": p_["sport"], "minutes": p_.get("minutes") or 0, "name": p_["sport"].title()}] if p_.get("sport") else []))
            manual_minutes=req.get('minutes')
            if not manual_minutes and req.get('sport')=='gym' and req.get('lifts'):
                import lifting
                manual_minutes=lifting.estimate_minutes(lifting.clean(d,req['lifts'],draft=bool(req.get('draft'))))
            cur.append({"sport": req.get("sport"), "minutes": int(manual_minutes or 30), "name": req.get("name") or str(req.get("sport")).title(),
                        "steps": req.get("steps") or [], "note": req.get("note") or "", "swim_profile": req.get("swim_profile"), "swim_plan":req.get("swim_plan"), "bike_plan":req.get("bike_plan"), "cadence":req.get("cadence"), "focus":req.get("focus"), "workout":req.get("workout"), "lifts":req.get("lifts"), "typed_workout":req.get("typed_workout")})
            coach.set_sessions(d, date, cur, draft=bool(req.get("draft")))
            if req.get('typed_workout'):
                import workout_library
                at=len(d['plans'][date]['sessions'])-1
                workout_library.attach_goals(d,date,at,req);workout_library.keep(d,date,at,favorite=req.get('favorite'))
            coach.save(d)
            capture_program_forecast(bridge,rides,d)
            return js({"sessions": d["plans"][date]["sessions"]})
        if p == "/api/coach/weekly":
            # the Sunday check-in (weekly.py): GET what's due, POST the answers
            import weekly
            if method == b"POST":
                import training_block
                sun = req.get("sunday") or (weekly.sunday_for(__import__("datetime").date.fromisoformat(date)) or __import__("datetime").date.fromisoformat(date)).isoformat()
                out = weekly.record(d, sun, req)
                coach.save(d)
                _load_cache["key"] = None
                gate = training_block.running_gate(d, load_state(rides.parent), d["checkins"].get(sun))
                done = done_by_day(rides.parent, d)
                decision = training_block.review(d, sun, done, gate)
                import progression
                progression_result = progression.apply_review(d, sun, done, load_state(rides.parent), bridge.workouts, today=date)
                coach.save(d)
                capture_program_forecast(bridge,rides,d)
                return js({"weekly": out, "sunday": sun, "decision": decision, "progression": progression_result})
            return js({"due": weekly_due(d, date, rides.parent), "answered": d.get("weekly", {})})
        if p == "/api/coach/block":
            import training_block
            if method == b"POST":
                try:
                    gate = training_block.running_gate(d, load_state(rides.parent), d["checkins"].get(date))
                    training_block.create(d, date, req.get("weeks", 4), req.get("start_date"), gate)
                except (ValueError, TypeError) as e:
                    return js({"error": str(e)}, 400)
                coach.save(d)
                capture_program_forecast(bridge,rides,d)
            return js(training_block.forecast(d, date, done_by_day(rides.parent, d), load_state(rides.parent), d["checkins"].get(date), bridge.workouts))
        if p.startswith("/api/coach/lifting"):
            # lifting and functional strength (lifting.py): plan, evaluate, check off, follow up, the rider's rules
            import lifting
            sub = p[len("/api/coach/lifting"):]
            ctx = lift_ctx(rides.parent, d, date)
            if sub == "" and method == b"GET":
                return js(lifting.summary(d, ctx=ctx))
            if method != b"POST":
                return js({"error": "not found"}, 404)
            if sub == "/plan":
                if (req.get('typed_workout') or req.get('workout_goals')) and done_by_day(rides.parent,d).get(date):raise ValueError('Keep completed workouts; edit their actual reports instead')
                pl = lifting.set_session(d, date, req.get("lifts"), req.get("name"), req.get("minutes"), req.get("index"),
                                         req.get("note"), draft=bool(req.get("draft")), override=req.get("override"),typed_workout=req.get("typed_workout"))
                if req.get('typed_workout') or req.get('workout_goals'):
                    import workout_library
                    at=req.get('index')
                    if at is None:at=next(i for i,x in enumerate(pl['sessions']) if x['sport']=='gym')
                    workout_library.attach_goals(d,date,at,req);workout_library.keep(d,date,at,favorite=req.get('favorite'))
                coach.save(d)
                capture_program_forecast(bridge,rides,d)
                gym = [s_ for s_ in pl["sessions"] if s_.get("lifts")]
                return js({"plan": pl, "evaluation": lifting.evaluate(d, gym[-1]["lifts"], ctx=ctx) if gym else None})
            if sub == "/evaluate":
                return js(lifting.evaluate(d, req.get("lifts"), ctx=ctx))
            if sub == "/log":
                entry = lifting.log(d, date, req.get("done"), req.get("rpe", 7), req.get("wellness", 7),
                                    req.get("session_index"), req.get("compare_last"), req.get("override"), ctx)
                coach.save(d)
                return js({"log": {k: v for k, v in entry.items() if k != "inputs"}})
            if sub == "/followup":
                f = lifting.followup(d, req.get("log_date"), req.get("ratings"), req.get("compare"), req.get("note"))
                coach.save(d)
                return js({"followup": f, "recovery": lifting.model(d)})
            if sub == "/rules":
                rs = lifting.remove_rule(d, req["remove"]) if req.get("remove") else lifting.add_rule(d, req.get("text"), req.get("note"))
                coach.save(d)
                return js({"rules": rs})
            if sub == "/exclude":                         # the first version's won't-do list: now rules
                rs = lifting.include(d, req.get("name")) if req.get("remove") else lifting.exclude(d, req.get("name"), req.get("why"))
                coach.save(d)
                return js({"rules": rs})
            if sub == "/unit":
                if req.get("unit") not in lifting.KG:
                    return js({"error": "unit is lb or kg"}, 400)
                lifting.state(d)["unit"] = req["unit"]
                coach.save(d)
                return js({"unit": req["unit"]})
            return js({"error": "not found"}, 404)
        if p == "/api/coach/session" and method == b"POST":
            import session
            rid = req.get("route_id")
            segs = req.get("segments")
            p_ = d["plans"].setdefault(date, {})
            if not segs:
                p_.pop("session", None)
            else:
                try:
                    r = routes.load(rid)
                    clean = session.check(r, segs)
                except (OSError, ValueError) as e:
                    return js({"error": str(e) if isinstance(e, session.BadSession) else f"no route {rid!r}"}, 400)
                p_["session"] = {"route_id": r.id, "route": r.name, "segments": clean}
                import cp as cp_mod
                cpw = cp_mod.estimate(cp_mod.best_curve(rides), bridge.profile["ftp"])
                mass = getattr(getattr(bridge, "ride", None), "mass", 126.6)
                warnings = []
                for sg in clean:
                    if sg["type"] == "climb_time":
                        g_ = (r.elevation_at(sg["end_m"]) - r.elevation_at(sg["start_m"])) / max(sg["end_m"] - sg["start_m"], 1) * 100
                        w_ = session.watts_for((sg["end_m"] - sg["start_m"]) / sg["seconds"], g_, mass)
                        f_ = cp_mod.feasible(w_, sg["seconds"], cpw["cp"], cpw["w_prime"])
                        if not f_["ok"]:
                            fast = cp_mod.fastest_climb(sg["end_m"] - sg["start_m"], g_, mass, cpw["cp"], cpw["w_prime"])
                            warnings.append(f"{sg['name']}: {f_['note']} - about {fast // 60}:{fast % 60:02d} is doable" if fast else f"{sg['name']}: {f_['note']}")
                    elif sg["type"] == "efforts":
                        f_ = cp_mod.feasible(sg["watts"], sg["on_s"], cpw["cp"], cpw["w_prime"])
                        if not f_["ok"]:
                            warnings.append(f"{sg['name']}: {f_['note']}")
                p_["session"]["warnings"] = warnings
            p_["updated"] = __import__("datetime").datetime.now().isoformat(timespec="minutes")
            coach.save(d)
            return js({"date": date, "session": p_.get("session")})
        if p == "/api/coach/split/rebalance" and method == b"POST":
            return js({"minutes": coach.rebalance([float(m) for m in req["minutes"]], int(req["index"]),
                                                  float(req["value"]), float(req["total"]))})
        if p == "/api/coach/split/save" and method == b"POST":
            blocks = coach.split_to_blocks(req["parts"])
            wid = workouts.save({"id": req.get("id"), "name": req.get("name") or "Timed workout",
                                 "note": req.get("note") or "", "blocks": blocks, "adaptive":req.get("adaptive")})
            bridge.reload_workouts()
            if req.get("plan"):
                coach.set_plan(d, date, workout=wid); coach.save(d)
            capture_program_forecast(bridge,rides,d)
            if req.get("ride"):
                bridge.workout_start_id(wid)
            return js({"id": wid})
    except (ValueError, KeyError, TypeError, workouts.BadWorkout) as e:
        return js({"error": str(e)}, 400)
    return js({"error": "not found"}, 404)
