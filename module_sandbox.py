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
TELEMETRY = ("power", "cadence", "speed", "distance", "grade", "gear", "erg", "ftp", "mass")
ASSET_HEADERS = {"Access-Control-Allow-Origin": "*", "Cross-Origin-Resource-Policy": "cross-origin"}


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
        or p == "/web/module-runtime.js"
        or re.fullmatch(r"/modes/[a-z0-9-]+/(?:sandbox|[^/.][^/]*)", p)
    ))


def runtime_headers(host, pid, version, nonce):
    if not re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]+)?", host):
        raise ValueError("Invalid Hub host")
    engine = f"{host}/module-engine/{version}/"
    files = f"{host}/modes/{pid}/"
    runtime = f"{host}/web/module-runtime.js"
    return {
        "Content-Security-Policy": (
            "sandbox allow-scripts; default-src 'none'; "
            f"script-src 'nonce-{nonce}' 'unsafe-eval' 'wasm-unsafe-eval' {engine} {runtime}; "
            f"connect-src {engine} {files}; img-src data: blob: {files}; "
            f"media-src blob: {files}; style-src 'unsafe-inline'; worker-src blob: {engine}; "
            "frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        ),
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), usb=(), serial=(), bluetooth=(), accelerometer=(), gyroscope=(), magnetometer=()",
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
    out["bike"] = bool(raw.get("bike"))
    out["no_bike"] = bool(raw.get("no_bike"))
    return out


def _revoke(bridge, token):
    session = _sessions.pop(token, None)
    if session and session["bridge"] is bridge and session["started"]:
        mode = getattr(bridge, "mode", None)
        if mode and mode.get("id") == session["id"]:
            bridge.mode_end("game connection closed")


def handle(bridge, method, body):
    if method != b"POST":
        raise ValueError("Use POST for module sessions")
    if len(body) > 2048:
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
        import game_licenses
        game_licenses.require(manifest)
        for token, session in list(_sessions.items()):
            if session["bridge"] is bridge:
                _revoke(bridge, token)
        token = secrets.token_urlsafe(32)
        declared = permissions(manifest)
        hills = declared["hills"]
        _sessions[token] = {"bridge": bridge, "id": pid, "name": manifest.get("name", pid),
                            "seen": now, "started": False, "hills": hills, "permissions": declared, "last_grade": 0.0, "last_mark": 0.0}
        return {"token": token, "capabilities": declared, "data": telemetry(bridge, declared["fields"])}
    token = data.get("token")
    session = _sessions.get(token) if isinstance(token, str) else None
    if not session or session["bridge"] is not bridge:
        raise ValueError("Game session is unavailable")
    allowed = {"snapshot": set(), "start": set(), "grade": {"value"}, "mark": {"text"}, "end": {"text"}, "close": set()}
    if action not in allowed or set(data) != {"action", "token"} | allowed[action]:
        raise ValueError("This game request is not allowed")
    if action == "snapshot":
        session["seen"] = now
        return {"data": telemetry(bridge, session["permissions"]["fields"])}
    if action == "close":
        _revoke(bridge, token)
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
        session["last_mark"] = now
        bridge.mode_mark(text)
    else:
        bridge.mode_end(text)
        session["started"] = False
    return {"ok": True}
