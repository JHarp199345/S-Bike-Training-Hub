"""remote.py - let the Pixel on the handlebars use the panel over Wi-Fi.

The panel always answers this Mac. Anything else on the network has to pair
first: scan the QR code on the Mac's panel (a one-time code, good for ten
minutes, used up on the spot), or open http://<this Mac>:8729 and type the
6-digit PIN shown there. The phone then gets a long random token in a cookie
that keeps it paired from then on. Wrong PINs are rate-limited, and "Forget paired
phones" on the Mac's panel cancels every token and picks a new PIN.

Stopping the bridge stays a Mac-only button: nothing on the handlebars can end
the bridge by a stray tap.
"""
import hmac
import json
import os
import secrets
import socket
import time
from pathlib import Path

FILE = Path(__file__).resolve().parent / "remote.json"      # PIN and paired tokens (kept out of git)
COOKIE = "sbikeremote"
MAC_ONLY = (b"/stop",)
# Connecting Strava (the OAuth callback comes back to 127.0.0.1) and its keys: this Mac only.
MAC_ONLY_PREFIXES = (b"/strava/", b"/api/strava/app", b"/api/strava/forget",
                     b"/api/music/settings", b"/api/music/connect", b"/api/music/forget",
                     b"/api/music/apple", b"/api/music/plex")
MAX_FAILS, LOCKOUT = 5, 60.0                                  # 5 wrong PINs -> a minute's wait

_fails = []                                                   # times of recent wrong PINs
_codes = {}                                                   # one-time QR pairing codes -> expiry (monotonic)
CODE_TTL = 600.0                                              # a QR works for 10 minutes, once


def _load():
    try:
        d = json.loads(FILE.read_text())
        if isinstance(d.get("pin"), str) and isinstance(d.get("tokens"), list):
            return d
    except (OSError, ValueError):
        pass
    d = {"pin": f"{secrets.randbelow(1_000_000):06d}", "tokens": []}
    _save(d)
    return d


def _save(d):
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.chmod(tmp, 0o600)
    tmp.replace(FILE)


def pin():
    return _load()["pin"]


def forget_all():
    """Unpair every phone and choose a new PIN."""
    _save({"pin": f"{secrets.randbelow(1_000_000):06d}", "tokens": []})


def is_local(peer):
    host = peer[0] if peer else ""
    return host in ("127.0.0.1", "::1") or host.startswith("::ffff:127.")


def _cookie(headers):
    for part in headers.get(b"cookie", b"").decode(errors="replace").split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE:
            return v
    return ""


def paired(headers):
    tok = _cookie(headers)
    return bool(tok) and any(hmac.compare_digest(tok, t) for t in _load()["tokens"])


def allowed(peer, headers, path):
    """May this request go through? This Mac: always. Others: paired, and not Mac-only."""
    if is_local(peer):
        return True
    p = path.split(b"?")[0]
    return paired(headers) and p not in MAC_ONLY and not p.startswith(MAC_ONLY_PREFIXES)


def try_pin(given, now=None):
    """A new token for the right PIN, or (None, reason)."""
    now = time.monotonic() if now is None else now
    _fails[:] = [t for t in _fails if now - t < LOCKOUT]
    if len(_fails) >= MAX_FAILS:
        return None, f"Too many wrong PINs - wait {int(LOCKOUT - (now - _fails[0])) + 1} s"
    d = _load()
    if not hmac.compare_digest(str(given).strip(), d["pin"]):
        _fails.append(now)
        return None, "That's not the PIN on the Mac's panel"
    tok = secrets.token_urlsafe(32)
    d["tokens"] = (d["tokens"] + [tok])[-10:]                  # at most 10 paired devices
    _save(d)
    return tok, None


def qr_code(now=None):
    """The current one-time pairing code for the QR: reused while it has over a
    minute left, otherwise a fresh one. Codes live only in memory."""
    now = time.monotonic() if now is None else now
    for c, exp in list(_codes.items()):
        if exp <= now:
            del _codes[c]
    live = [c for c, exp in _codes.items() if exp - now > 60]
    if live:
        return live[-1], _codes[live[-1]] - now
    c = secrets.token_urlsafe(16)
    _codes[c] = now + CODE_TTL
    while len(_codes) > 3:
        del _codes[next(iter(_codes))]
    return c, CODE_TTL


def try_code(given, now=None):
    """A new token for a valid QR code (used up on the spot), or (None, reason)."""
    now = time.monotonic() if now is None else now
    _fails[:] = [t for t in _fails if now - t < LOCKOUT]
    if len(_fails) >= MAX_FAILS:
        return None, f"Too many tries - wait {int(LOCKOUT - (now - _fails[0])) + 1} s"
    exp = next((e for c, e in _codes.items() if hmac.compare_digest(c, str(given))), None)
    if exp is None or exp <= now:
        _fails.append(now)
        return None, "That QR code has expired or was already used - scan the one on the Mac's panel now"
    _codes.pop(str(given), None)
    d = _load()
    tok = secrets.token_urlsafe(32)
    d["tokens"] = (d["tokens"] + [tok])[-10:]
    _save(d)
    return tok, None


def lan_addresses():
    """How a phone on the same Wi-Fi reaches this Mac: its IP and its .local name."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))              # picks the outgoing interface; sends nothing
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        import subprocess
        name = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True,
                              timeout=2).stdout.strip()
        if name:
            out.append(f"{name}.local")
    except (OSError, subprocess.SubprocessError):
        pass
    return out


PAIR_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>S-Bike Hub · Pair</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{color-scheme:dark}
 body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0b0f14;
      color:#eef1f5;font:17px/1.4 -apple-system,Roboto,"Helvetica Neue",sans-serif}
 div{background:#151b23;border-radius:18px;padding:26px;width:min(340px,90vw);box-sizing:border-box;text-align:center}
 h1{margin:0 0 6px;font-size:26px} p{color:#8b98a8;margin:0 0 18px}
 input{width:100%;box-sizing:border-box;font-size:38px;letter-spacing:10px;text-align:center;padding:12px;
       border-radius:12px;border:1px solid #2a3441;background:#0b0f14;color:#fff}
 button{width:100%;margin-top:14px;padding:16px;border:0;border-radius:12px;font-size:19px;font-weight:700;
        background:#2563eb;color:#fff}
 #err{color:#fca5a5;min-height:24px;margin-top:10px}
</style></head><body><div>
<h1>S-Bike Hub</h1><p id="lead">Type the PIN shown on the Mac's panel to use this phone as the handlebar remote.</p>
<form id="f"><input id="pin" inputmode="numeric" pattern="[0-9]*" maxlength="6" autocomplete="one-time-code" autofocus>
<button>Pair this phone</button></form><div id="err"></div></div>
<script>
const $=id=>document.getElementById(id);
async function pair(body){ const r=await fetch('/pair',{method:'POST',body}); const j=await r.json();
  if(r.ok){ history.replaceState(null,'','/pair'); location.href='/ride'; } else $('err').textContent=j.error; return r.ok; }
$('f').onsubmit=e=>{ e.preventDefault(); pair($('pin').value); };
// Opened from the QR on the Mac's panel: pair straight away (a script, so link previews can't use the code up).
const code=new URLSearchParams(location.search).get('code');
if(code){ $('lead').textContent='Pairing this phone…'; pair(JSON.stringify({code})).then(ok=>{ if(!ok) $('lead').textContent="Scan the QR on the Mac's panel again, or type the PIN:"; }); }
</script></body></html>"""


def handle(peer, method, path, headers, body):
    """(status, content type, body, extra headers) for pairing requests and for
    anything an unpaired device asks for; None lets the request through."""
    p = path.split(b"?")[0]
    if p == b"/pair" and method == b"POST":
        text = body.decode(errors="replace").strip()
        try:
            code = json.loads(text).get("code") if text.startswith("{") else None
        except (ValueError, AttributeError):
            code = None
        tok, err = try_code(code) if code else try_pin(text)
        if not tok:
            return 403, "application/json", json.dumps({"error": err}).encode(), {}
        return 200, "application/json", b'{"ok":true}', {
            "Set-Cookie": f"{COOKIE}={tok}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Strict"}
    if p == b"/pair":
        return 200, "text/html; charset=utf-8", PAIR_PAGE.encode(), {}
    if p == b"/remote/forget" and method == b"POST":
        if not is_local(peer):
            return 403, "application/json", b'{"error":"only from the Mac"}', {}
        forget_all()
        return 200, "application/json", b'{"ok":true}', {}
    if p == b"/remote/qr":
        if not is_local(peer):
            return 403, "application/json", b'{"error":"only from the Mac"}', {}
        import qr
        ip = next((a for a in lan_addresses() if a[0].isdigit()), None)
        if not ip:
            return 200, "application/json", b'{"error":"no Wi-Fi address"}', {}
        port = (headers.get(b"host", b"").decode().rpartition(":")[2] or "8729")
        code, left = qr_code()
        url = f"http://{ip}:{port}/pair?code={code}"
        return 200, "application/json", json.dumps({"url": url, "svg": qr.svg(url, 220), "expires_in": int(left)}).encode(), {}
    if p == b"/remote/info":
        if not is_local(peer):
            return 403, "application/json", b'{"error":"only from the Mac"}', {}
        return 200, "application/json", json.dumps({"pin": pin(), "addresses": lan_addresses()}).encode(), {}
    if allowed(peer, headers, p):
        return None
    if is_local(peer) or paired(headers):                    # paired, but a Mac-only action
        return 403, "application/json", b'{"error":"only from the Mac"}', {}
    if method == b"GET" and not p.startswith((b"/api/", b"/status", b"/tiles/", b"/terrain/", b"/lib/")):
        return 302, "text/plain", b"", {"Location": "/pair"}
    return 401, "application/json", b'{"error":"pair this device first"}', {}
