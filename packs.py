"""packs.py - Ride World packs: signed game modes that run on the hub's own shared Godot engine (2026-10-12).

A pack is a folder in the data folder's modes/<id>/:
  manifest.json   id, name, version, format, engine (the Godot version it was built with), files {name: sha256},
                  plus what the mode needs, and a signature {key, sig} over everything else in the manifest
  game.pck        the mode's exported game data (no engine inside)
  other files     listed in the manifest (an icon, credits)

The hub carries the engine once (engine/<version>/ in the data folder or the app): every pack shares it, so ten packs
don't mean ten copies. A pack loads only when its signature comes from a trusted key and every file matches the
fingerprint the signature covers, so the official hub runs official packs and nothing modified. The hub's own page
starts the engine; a pack can't bring its own page or scripts.

Ed25519 is implemented here from RFC 8032 (section 6's reference) in plain Python: the hub keeps to the standard
library. Verifying one signature takes a few milliseconds.
"""
import hashlib
import json
import html
import secrets
import re
import os
from pathlib import Path

import paths

FORMAT = 1
# Public keys whose packs this hub runs (hex). The private key never leaves the publisher's computer.
TRUSTED_KEYS = {
    "jharp-2026": "d2933161537b1ca15936d0c2587fa8ab0e9b414d4a415d12ae43cdfada656be1",
}
SERVED = {".pck", ".png", ".jpg", ".webp", ".json", ".txt", ".ogg", ".mp3", ".wav"}   # what a pack may contain
ENGINE_FILES = ("godot.js", "godot.wasm", "godot.audio.worklet.js", "godot.audio.position.worklet.js")

# --- Ed25519 (RFC 8032, section 6) ---------------------------------------------------------------------------------
_p = 2 ** 255 - 19
_q = 2 ** 252 + 27742317777372353535851937790883648493
_inv = lambda x: pow(x, _p - 2, _p)
_d = -121665 * _inv(121666) % _p
_sqrt_m1 = pow(2, (_p - 1) // 4, _p)


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % _p, (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C, D = 2 * P[3] * Q[3] * _d % _p, 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F, G * H, F * G, E * H)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P, s = _add(P, P), s >> 1
    return Q


def _equal(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _recover_x(y, sign):
    if y >= _p:
        return None
    x2 = (y * y - 1) * _inv(_d * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p:
        x = x * _sqrt_m1 % _p
    if (x * x - x2) % _p:
        return None
    return _p - x if (x & 1) != sign else x


_gy = 4 * _inv(5) % _p
_gx = _recover_x(_gy, 0)
_G = (_gx, _gy, 1, _gx * _gy % _p)


def _compress(P):
    z = _inv(P[2])
    x, y = P[0] * z % _p, P[1] * z % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _p)


def _expand(secret):
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    return (a & ((1 << 254) - 8)) | (1 << 254), h[32:]


def _modq(b):
    return int.from_bytes(hashlib.sha512(b).digest(), "little") % _q


def public_key(secret):
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret, msg):
    a, prefix = _expand(secret)
    A = _compress(_mul(a, _G))
    r = _modq(prefix + msg)
    R = _compress(_mul(r, _G))
    return R + int.to_bytes((r + _modq(R + A + msg) * a) % _q, 32, "little")


def verify(public, msg, sig):
    if len(public) != 32 or len(sig) != 64:
        return False
    A, R = _decompress(public), _decompress(sig[:32])
    s = int.from_bytes(sig[32:], "little")
    if not A or not R or s >= _q:
        return False
    return _equal(_mul(s, _G), _add(R, _mul(_modq(sig[:32] + public + msg), A)))


# --- Packs ----------------------------------------------------------------------------------------------------------
def signed_bytes(manifest):
    """What a signature covers: the whole manifest except the signature itself, in one fixed form."""
    return json.dumps({k: v for k, v in manifest.items() if k != "signature"}, sort_keys=True, separators=(",", ":")).encode()


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(folder, keys=None):
    """(manifest, None) for an intact pack signed by a trusted key, or (manifest or None, why not)."""
    keys = TRUSTED_KEYS if keys is None else keys
    folder = Path(folder)
    try:
        m = json.loads((folder / "manifest.json").read_text())
    except (OSError, ValueError):
        return None, "This pack has no readable manifest."
    if m.get("format") != FORMAT:
        return m, "This pack was made for a different version of the hub."
    sig = m.get("signature") or {}
    key = keys.get(sig.get("key"))
    try:
        ok = bool(key) and verify(bytes.fromhex(key), signed_bytes(m), bytes.fromhex(sig.get("sig", "")))
    except ValueError:
        ok = False
    if not ok:
        return m, "This isn't an official S-Bike pack: its signature doesn't check out."
    files = m.get("files") or {}
    if not files.get(m.get("main", "game.pck")):
        return m, "This pack is missing its game."
    for name, digest in files.items():
        f = (folder / name).resolve()
        if not f.is_relative_to(folder.resolve()) or Path(name).suffix not in SERVED:
            return m, f"This pack lists a file it isn't allowed to carry: {name}"
        if not f.is_file() or fingerprint(f) != digest:
            return m, f"This pack has been changed since it was signed ({name})."
    return m, None


_checked = {}


def verified(folder):
    """check() remembered until any of the pack's files change, so a big game isn't re-fingerprinted on every request."""
    folder = Path(folder)
    try:
        stamp = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in sorted(folder.iterdir()) if f.is_file())
    except OSError:
        return None, "This pack isn't installed."
    if _checked.get(folder, (None,))[0] != stamp:
        _checked[folder] = (stamp, check(folder))
    return _checked[folder][1]


def isolated_engine_dir(version):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(version)):
        return None
    for base in (paths.CODE / "web/module-engine", paths.DATA / "module-engine"):
        d = base / str(version)
        if all((d / f).is_file() for f in ENGINE_FILES):
            return d
    return None


def engine_dir(version):
    """The shared engine for a Godot version: the data folder's copy first, then one shipped with the app."""
    for base in (paths.DATA / "engine", paths.CODE / "web" / "engine", paths.CODE / "web/module-engine", paths.DATA / "module-engine"):
        d = base / str(version)
        if all((d / f).is_file() for f in ENGINE_FILES):
            return d
    return None


def installed(folder=None):
    """Every pack in the data folder, with whether it can run here and why not."""
    root = Path(folder or paths.DATA / "modes")
    out = []
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if d.is_dir() and not d.name.startswith("."):
            m, why = check(d)
            if not why and not engine_dir((m or {}).get("engine")):
                why = f"This pack needs engine {m.get('engine')}, which this hub doesn't have yet."
            out.append({"id": d.name, "name": (m or {}).get("name", d.name), "version": (m or {}).get("version"),
                        "ok": not why, "why": why})
    return out


SENSOR_CONTROLS = '<style>.lean{position:fixed;left:12px;bottom:12px;z-index:2;max-width:330px;background:rgba(11,20,29,.88);color:#dbe7f0;\nborder:1px solid #2c4458;border-radius:12px;padding:12px 14px;font:14px/1.4 system-ui}.lean b{display:block;font-size:15px;margin-bottom:4px}\n.lean button{margin:8px 8px 0 0;padding:7px 12px;border-radius:8px;border:0;background:#2c4458;color:#fff;font:600 14px system-ui;cursor:pointer}\n.lean .go{background:#18a0a2}#lean-live,#lean-later{padding:7px 10px}#lean-live button{margin:0 0 0 8px;padding:4px 10px}</style>\n<div id="lean-card" class="lean" hidden><b>Lean with your camera</b>Your camera looks only at where your head and shoulders\nare, so leaning left or right steers. The video stays on this device: nothing is shown, recorded or sent anywhere.\n<br><button id="lean-yes" class="go">Turn on</button><button id="lean-no">Not now</button></div>\n<div id="lean-live" class="lean" hidden>&#9679; Camera: head and shoulders only<button id="lean-off">Off</button></div>\n<button id="lean-later" class="lean" hidden>Lean with camera<span id="lean-why"></span></button>\n<button id="tilt-ask" class="lean" hidden style="left:auto;right:12px">Turn on lean (tilt)</button>\n'


def page(m):
    """Trusted host shell; all pack code executes only in an opaque iframe."""
    pid = m["id"]
    title = html.escape(m.get("name", pid))
    config = json.dumps({"id": pid}).replace("<", "\\u003c")
    sensors = SENSOR_CONTROLS
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · S-Bike Training Hub</title><style>html,body{{margin:0;height:100%;background:#0b141d;color:#dbe7f0;font:15px system-ui}}#module-game{{width:100%;height:100%;border:0}}#status{{position:fixed;inset:0;display:grid;place-items:center;pointer-events:none}}[hidden]{{display:none!important}}</style></head><body>
<iframe id="module-game" title="{title}" sandbox="allow-scripts" allow="fullscreen" allowfullscreen src="/modes/{pid}/sandbox"></iframe>
<a href="/ride?setup=1" target="_top" aria-label="Return to Ride menu" style="position:fixed;top:10px;right:12px;z-index:10;padding:7px 12px;background:rgba(11,20,29,.85);border:1px solid #2c4458;border-radius:8px;color:#dbe7f0;text-decoration:none">← Return to Ride menu</a>
<div id="status">Connecting {title}…</div>{sensors}
<script id="module-config" type="application/json">{config}</script>
<script>const q=new URLSearchParams(location.search); if(q.has("dev")) document.getElementById("module-game").src+="?dev=1";</script>
<link rel="stylesheet" href="/web/hub-support.css"><script src="/web/support-policy.js"></script><script src="/web/hub-support.js"></script><script src="/vision/lean.js"></script><script src="/web/module-host.js"></script></body></html>""".encode()

def runtime_page(m, nonce):
    """The hub's own page for a pack: the shared engine runs the pack's game data. Packs bring no page or scripts."""
    v, pid = m["engine"], m["id"]
    config = {"args": [], "canvasResizePolicy": 2, "emscriptenPoolSize": 8, "ensureCrossOriginIsolationHeaders": False,
              "executable": f"/module-engine/{v}/godot", "mainPack": f"/modes/{pid}/{m.get('main', 'game.pck')}",
              "experimentalVK": False, "focusCanvas": True, "gdextensionLibs": [], "godotPoolSize": 4}
    title = html.escape(m.get("name", pid))
    js_title = json.dumps(m.get("name", pid)).replace("<", "\\u003c")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, user-scalable=no">
<title>{title} · S-Bike Training Hub</title>
<style>html,body,#canvas{{margin:0;padding:0;height:100%;width:100%;background:#0b141d;color:#dbe7f0;font-family:system-ui,sans-serif;overflow:hidden}}
#status{{position:fixed;inset:0;display:grid;place-items:center;text-align:center}}</style></head>
<body><canvas id="canvas">Your browser doesn't support this ride mode.</canvas><div id="status">Loading {title}…</div>
<script src="/web/module-runtime.js" crossorigin="anonymous"></script>
<script src="/module-engine/{v}/godot.js" crossorigin="anonymous"></script>
<script nonce="{nonce}">
const gameName = {js_title};
const status = document.getElementById('status');
const say = (t) => {{ if (status) status.textContent = t; }};
window.addEventListener('error', (e) => say('This ride mode hit a problem: ' + (e.message || e.error || 'unknown')));
const missing = Engine.getMissingFeatures({{threads: false}});
if (missing.length) {{
  say('This device or browser is missing what the game needs: ' + missing.join(', ') + '. Try another browser, or the computer running the hub.');
}} else {{
  const engine = new Engine({json.dumps(config)});
  engine.startGame({{onProgress: (done, total) => {{ if (total > 0) say('Loading ' + gameName + '… ' + Math.round(100 * done / total) + '%'); }}}})
    .then(() => status && status.remove(),
      (e) => say('This ride mode could not start: ' + (e && e.message || e)));
}}
</script></body></html>""".encode()


def error_page(why):
    safe = str(why).replace("<", "&lt;")
    return (f"<!doctype html><meta charset='utf-8'><title>Ride mode</title><body style='background:#0b141d;color:#dbe7f0;"
            f"font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0'><p>{safe}</p>").encode()


def new_key(path):
    """Make a signing key (publisher only). Written with owner-only permissions; back it up somewhere safe."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = os.urandom(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secret.hex())
    return public_key(secret).hex()


def sign_pack(folder, key_id, secret_hex):
    """Fingerprint every file in a pack folder, then sign the manifest (publisher only)."""
    folder = Path(folder)
    m = json.loads((folder / "manifest.json").read_text())
    m.pop("signature", None)
    m["format"] = FORMAT
    m["files"] = {f.name: fingerprint(f) for f in sorted(folder.iterdir()) if f.is_file() and f.name != "manifest.json"}
    m["signature"] = {"key": key_id, "sig": sign(bytes.fromhex(secret_hex), signed_bytes(m)).hex()}
    (folder / "manifest.json").write_text(json.dumps(m, indent=2))
    return m
