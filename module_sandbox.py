"""Browser module boundary: isolated game frames, selected telemetry and leased controls.

This is not an OS sandbox. Trust in the browser and the bundled engine remains.
No module receives the session token or a generic Hub URL/request capability.
"""
import json
import math
import re
import secrets
import time
from urllib.parse import urlsplit

import packs
import paths

_sessions = {}
TTL = 20.0
TELEMETRY = ("power", "cadence", "speed", "distance", "grade", "gear", "erg", "ftp", "mass", "heart_rate", "workout")
ASSET_HEADERS = {"Access-Control-Allow-Origin": "*", "Cross-Origin-Resource-Policy": "cross-origin"}
# The Hub's own scripts a game frame runs, besides the engine. The frame's rules name each one: no inline scripts.
FRAME_SCRIPTS = ("/web/module-runtime.js", "/web/module-start.js")
# Browser features a game never gets. Camera lean runs in the Hub's page, which passes on only the lean value.
PERMISSIONS_DENIED = ("camera", "microphone", "geolocation", "usb", "serial", "bluetooth", "hid", "midi",
                      "accelerometer", "gyroscope", "magnetometer", "display-capture", "clipboard-read",
                      "clipboard-write", "payment", "publickey-credentials-get", "xr-spatial-tracking",
                      "idle-detection", "local-fonts")


def request_allowed(method, path, headers):
    """Run before any route/body handling. Opaque frames cannot call private routes.

    Fetch Metadata also covers no-cors requests without an Origin header. Native
    clients retain their existing pairing/authentication behavior.
    """
    origin = headers.get(b"origin", b"")
    site = headers.get(b"sec-fetch-site", b"")
    foreign = origin == b"null" or site == b"cross-site"
    if origin and origin != b"null":
        parsed = urlsplit(origin.decode("ascii", "replace"))
        foreign |= parsed.netloc.encode() != headers.get(b"host", b"") or parsed.scheme not in ("http", "https")
    if not foreign:
        return True
    p = path.decode("ascii", "replace").split("?", 1)[0]
    # Human top-level page navigation is not a game API request. Only known
    # UI documents, never endpoints or subframe navigations, receive this exception.
    pages = {"/", "/ride", "/coach", "/panel", "/plan", "/welcome"}
    if (method == b"GET" and not origin and headers.get(b"sec-fetch-mode") == b"navigate"
            and headers.get(b"sec-fetch-dest") == b"document"
            and (p in pages or re.fullmatch(r"/modes/[a-z0-9-]+/", p))):
        return True
    # Only inert signed files and the Hub-owned engine/runtime are reachable.
    return bool(method == b"GET" and (
        re.fullmatch(r"/(?:engine|module-engine)/[0-9.]+/godot(?:\.wasm|\.js|\.audio(?:\.position)?\.worklet\.js)", p)
        or p in FRAME_SCRIPTS
        or re.fullmatch(r"/modes/[a-z0-9-]+/(?:sandbox|[^/.][^/]*)", p)
    ))


GAME_SUFFIX = ".game.localhost"


def game_pack(headers):
    """The pack a request is for when it arrives on a game's own name, else None.

    Chrome 142+ (Local Network Access) refuses every load an opaque sandbox frame makes to this computer, so on this
    computer each game runs on its own name instead: <pack>.game.localhost:<hub port>. Browsers route *.localhost here
    and treat each name as its own site, so a game is walled off from the Hub (and from other games) by the ordinary
    same-origin rules, on the Hub's own port: nothing extra opens or needs closing. "" is a malformed game name.
    """
    host = headers.get(b"host", b"").decode("ascii", "replace").lower()
    name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if not name.endswith(GAME_SUFFIX):
        return None
    pid = name[:-len(GAME_SUFFIX)]
    return pid if re.fullmatch(r"[a-z0-9-]{1,60}", pid) else ""


def game_path_allowed(pid, method, path):
    """On a game's name the Hub serves that game's signed files, the engine and the bridge script. Nothing else."""
    p = path.decode("ascii", "replace").split("?", 1)[0]
    return bool(pid and method in (b"GET", b"HEAD") and (
        re.fullmatch(r"/module-engine/[0-9.]+/godot(?:\.wasm|\.js|\.audio(?:\.position)?\.worklet\.js)", p)
        or p in FRAME_SCRIPTS
        or re.fullmatch(rf"/modes/{re.escape(pid)}/(?:sandbox|[^/.][^/]*)", p)
    ))


def runtime_headers(host, pid, version):
    if not re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]+)?", host):
        raise ValueError("Invalid Hub host")
    engine = f"{host}/module-engine/{version}/"
    files = f"{host}/modes/{pid}/"
    runtime = " ".join(f"{host}{p}" for p in FRAME_SCRIPTS)
    own = host.lower().split(":")[0].endswith(GAME_SUFFIX)
    port = host.rsplit(":", 1)[1] if own and ":" in host else ""
    hub = " ".join(f"http://{h}{':' + port if port else ''}" for h in ("127.0.0.1", "localhost"))   # CSP frame-ancestors can't name [::1]
    return {
        "Content-Security-Policy": (
            # on its own name the game keeps a real (separate) origin; elsewhere it stays an opaque frame
            ("sandbox allow-scripts allow-same-origin; " if own else "sandbox allow-scripts; ") + "default-src 'none'; "
            f"script-src 'unsafe-eval' 'wasm-unsafe-eval' {engine} {runtime}; "
            f"connect-src {engine} {files}; img-src data: blob: {files}; "
            f"media-src blob: {files}; style-src 'unsafe-inline'; worker-src blob: {engine}; "
            "frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; "
            # no peer connections (WebRTC can reach any server, outside connect-src); browsers without it ignore it
            "webrtc 'block'; "
            + (f"frame-ancestors {hub}" if own else "frame-ancestors 'self'")
        ),
        "Permissions-Policy": ", ".join(f"{f}=()" for f in PERMISSIONS_DENIED),
        "X-DNS-Prefetch-Control": "off",
        # nothing a game keeps in the browser survives to its next launch; its saves go through the Hub (saves_file)
        "Clear-Site-Data": '"storage", "cookies"',
        # The Hub page requires its rules of whatever loads in the game frame (module-host.js, iframe csp); this page
        # accepts them. An outside page that doesn't is refused, and one that does can run no script of its own.
        "Allow-CSP-From": "*",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        **ASSET_HEADERS,
    }


def permissions(manifest):
    declared = manifest.get("permissions")
    if not isinstance(declared, dict) or set(declared) != {"telemetry", "controls"}:
        raise ValueError("This game needs an update declaring its data and controls")
    fields, controls = declared["telemetry"], declared["controls"]
    if not isinstance(fields, list) or not isinstance(controls, list):
        raise ValueError("Invalid game permissions")
    if any(not isinstance(f, str) or f not in TELEMETRY for f in fields) or any(not isinstance(c, str) or c not in ("hills", "markers", "lean") for c in controls):
        raise ValueError("Unsupported game permissions")
    return {"fields": list(dict.fromkeys(fields)), **{c: c in controls for c in ("hills", "markers", "lean")}}


def telemetry(bridge, fields=TELEMETRY):
    raw = bridge.status()
    out = {}
    for key in fields:
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            out[key] = value
    # A game may follow the active clock, never inspect workout names, steps,
    # schedules, athlete history or arbitrary nested status objects.
    workout = raw.get("workout")
    if "workout" in fields and isinstance(workout, dict):
        clock = {}
        for key in ("elapsed", "total"):
            value = workout.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                clock[key] = value
        for key in ("paused", "auto_paused"):
            if isinstance(workout.get(key), bool):
                clock[key] = workout[key]
        if "total" in clock and "elapsed" in clock:
            out["workout"] = clock
    out["bike"] = bool(raw.get("bike"))
    out["no_bike"] = bool(raw.get("no_bike"))
    return out


SAVE_LIMIT = 256 * 1024     # a game's saved settings, all files together
MARKS_LIMIT = 300           # ride markers one game session may add


def saves_file(pid):
    """A game's saved settings live with the Hub, not in the browser: one readable JSON file per game, {name: text}.
    The browser's own storage for the game is wiped every launch (Clear-Site-Data), so nothing a game keeps survives
    except what passes through here, and it's deleted once the game is no longer installed (packs.installed)."""
    return paths.DATA / "game-saves" / f"{pid}.json"


def load_saves(pid):
    try:
        saves = json.loads(saves_file(pid).read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in saves.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(saves, dict) else {}


def _save(pid, name, text):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,59}", name):
        raise ValueError("Invalid save name")
    if not isinstance(text, str):
        raise ValueError("Invalid save text")
    saves = load_saves(pid)
    saves[name] = text
    out = json.dumps(saves, indent=1, ensure_ascii=False)
    if len(out.encode()) > SAVE_LIMIT:
        raise ValueError("This game's saved settings are too large")
    f = saves_file(pid)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(out)
    tmp.replace(f)


def _revoke(bridge, token):
    session = _sessions.pop(token, None)
    if session and session["bridge"] is bridge and session["started"]:
        mode = getattr(bridge, "mode", None)
        if mode and mode.get("id") == session["id"]:
            bridge.mode_end("game connection closed")


def handle(bridge, method, body):
    if method != b"POST":
        raise ValueError("Use POST for module sessions")
    if len(body) > SAVE_LIMIT + 4096:
        raise ValueError("Module request is too large")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("Invalid module request")
    now = time.monotonic()
    for token, session in list(_sessions.items()):
        if now - session["seen"] > TTL:
            _revoke(session["bridge"], token)
    action = data.get("action")
    if action == "open":
        pid = data.get("id")
        if set(data) != {"action", "id"} or not isinstance(pid, str) or not re.fullmatch(r"[a-z0-9-]{1,60}", pid):
            raise ValueError("Invalid game identifier")
        manifest, why = packs.verified(paths.DATA / "modes" / pid)
        if why or not packs.isolated_engine_dir((manifest or {}).get("engine")):
            raise ValueError(why or "The game engine is unavailable")
        for token, session in list(_sessions.items()):
            if session["bridge"] is bridge:
                _revoke(bridge, token)
        token = secrets.token_urlsafe(32)
        declared = permissions(manifest)
        hills = declared["hills"]
        _sessions[token] = {"bridge": bridge, "id": pid, "name": manifest.get("name", pid),
                            "seen": now, "started": False, "hills": hills, "permissions": declared, "last_grade": 0.0, "last_mark": 0.0,
                            "marks": 0}
        return {"token": token, "capabilities": declared, "data": telemetry(bridge, declared["fields"]), "saves": load_saves(pid)}
    token = data.get("token")
    session = _sessions.get(token) if isinstance(token, str) else None
    if not session or session["bridge"] is not bridge:
        raise ValueError("Game session is unavailable")
    allowed = {"snapshot": set(), "start": set(), "grade": {"value"}, "mark": {"text"}, "end": {"text"}, "close": set(),
               "save": {"file", "text"}}
    if action not in allowed or set(data) != {"action", "token"} | allowed[action]:
        raise ValueError("This game request is not allowed")
    if action == "snapshot":
        session["seen"] = now
        return {"data": telemetry(bridge, session["permissions"]["fields"])}
    if action == "close":
        _revoke(bridge, token)
        return {"ok": True}
    if action == "save":
        session["seen"] = now
        _save(session["id"], data["file"], data["text"])
        return {"ok": True}
    if action == "start":
        if not session["started"]:
            current = bridge.status()
            if any(current.get(key) for key in ("workout", "route", "test")) or any(getattr(bridge, attr, None) for attr in ("session", "route_ride", "test")):
                raise ValueError("Finish the active workout, route or test before game control")
            bridge.mode_start(session["id"], session["name"])
            session["started"] = True
        return {"ok": True}
    if not session["started"] or not getattr(bridge, "mode", None) or bridge.mode.get("id") != session["id"]:
        raise ValueError("Start this game before sending controls")
    if action == "grade":
        current = bridge.status()
        if any(current.get(key) for key in ("workout", "route", "test")):
            raise ValueError("The active workout, route or test controls resistance")
        value = data["value"]
        if not session["hills"] or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("This hill request is not allowed")
        if now - session["last_grade"] < 0.09:
            raise ValueError("Hill requests are arriving too quickly")
        session["last_grade"] = now
        ok, grade = bridge.mode_grade(max(-10.0, min(15.0, value)))
        return {"ok": ok, "grade": grade}
    text = data["text"]
    if not isinstance(text, str) or len(text) > 120 or any(ord(c) < 32 for c in text):
        raise ValueError("Invalid game text")
    if action == "mark":
        if not session["permissions"]["markers"]:
            raise ValueError("Game markers are not declared")
        if now - session["last_mark"] < 1.0:
            raise ValueError("Game markers are arriving too quickly")
        if session["marks"] >= MARKS_LIMIT:
            raise ValueError("This game has added as many ride markers as a session allows")
        session["last_mark"] = now
        session["marks"] += 1
        bridge.mode_mark(text)
    else:
        bridge.mode_end(text)
        session["started"] = False
    return {"ok": True}
