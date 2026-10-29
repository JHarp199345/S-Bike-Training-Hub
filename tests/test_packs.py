import pathlib
"""Ride World packs: Ed25519 matches RFC 8032; the hub runs only signed, unmodified packs on its shared engine."""
import sys, pathlib, json, asyncio, tempfile; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import packs, paths, mapserver

# RFC 8032 section 7.1, tests 1 and 2
sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
assert packs.public_key(sk).hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
sig = packs.sign(sk, b"")
assert sig.hex() == ("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
assert packs.verify(packs.public_key(sk), b"", sig) and not packs.verify(packs.public_key(sk), b"x", sig)
sk2 = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
assert packs.sign(sk2, b"\x72").hex() == ("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")
assert not packs.verify(packs.public_key(sk2), b"\x72", sig[:63] + bytes([sig[63] ^ 1]))

tmp = pathlib.Path(tempfile.mkdtemp())
paths.DATA = mapserver.DATA = tmp
pub = packs.new_key(tmp / "key")
secret = (tmp / "key").read_text()
if sys.platform != "win32":  # Windows does not expose POSIX owner/group permission bits.
    assert (tmp / "key").stat().st_mode & 0o777 == 0o600
packs.TRUSTED_KEYS = {"test": pub}

eng = tmp / "module-engine" / "4.7.1"; eng.mkdir(parents=True)
legacy = tmp / "engine" / "4.7.1"; legacy.mkdir(parents=True)
for f in packs.ENGINE_FILES:
    (eng / f).write_bytes(b"engine"); (legacy / f).write_bytes(b"engine")


def make(pid, **extra):
    d = tmp / "modes" / pid; d.mkdir(parents=True)
    (d / "game.pck").write_bytes(b"GDPC game data")
    (d / "credits.txt").write_text("credits")
    (d / "manifest.json").write_text(json.dumps({"id": pid, "name": "Test <mode>", "version": "1", "engine": "4.7.1", **extra}))
    packs.sign_pack(d, "test", secret)
    return d


good = make("good")
assert packs.check(good)[1] is None
bad = make("changed"); (bad / "game.pck").write_bytes(b"GDPC other game")
assert "changed since it was signed" in packs.check(bad)[1]
price = make("price"); m = json.loads((price / "manifest.json").read_text()); m["price"] = "free"
(price / "manifest.json").write_text(json.dumps(m))
assert "signature" in packs.check(price)[1]
other = make("other"); packs.TRUSTED_KEYS = {"test": packs.public_key(sk).hex()}
assert "signature" in packs.check(other)[1], "a key the hub doesn't trust"
packs.TRUSTED_KEYS = {"test": pub}
# a signed manifest still can't reach outside its folder or carry a page or script
sneaky = make("sneaky"); m = json.loads((sneaky / "manifest.json").read_text()); m.pop("signature")
m["files"]["../good/game.pck"] = m["files"]["game.pck"]; m["files"]["index.html"] = "0" * 64
(sneaky / "manifest.json").write_text(json.dumps({**m, "signature": {"key": "test", "sig": packs.sign(bytes.fromhex(secret), packs.signed_bytes(m)).hex()}}))
assert "isn't allowed" in packs.check(sneaky)[1]
old = make("old", engine="4.6.0")
assert [p["ok"] for p in packs.installed()] == [False, True, False, True, False, False]
assert "engine 4.6.0" in next(p["why"] for p in packs.installed() if p["id"] == "old")


def get(path):
    return asyncio.run(mapserver.handle(None, "GET", path, b"", "localhost"))


s, ctype, body, hdr = get("/modes/good/")
# the wrapper starts opaque; module-host.js points the frame at the game's own name (or the opaque sandbox)
assert s == 200 and b'sandbox="allow-scripts"' in body and b"/web/module-host.js" in body and b' src="/modes/' not in body
assert b"allow-same-origin" not in body and b"Test &lt;mode&gt;" in body
host_js = (pathlib.Path(__file__).resolve().parent.parent / "web/module-host.js").read_text()
assert "/modes/${config.id}/sandbox" in host_js and ".game.localhost" in host_js
assert hdr["Cross-Origin-Embedder-Policy"] == "require-corp"
_, _, runtime, runtime_headers = get("/modes/good/sandbox")
assert b"/module-engine/4.7.1/godot.js" in runtime and b'"mainPack": "/modes/good/game.pck"' in runtime
assert runtime_headers["Content-Security-Policy"].startswith("sandbox allow-scripts;")
assert "allow-same-origin" not in runtime_headers["Content-Security-Policy"]
assert "camera=()" in runtime_headers["Permissions-Policy"]
# side doors closed (2026-10-29): no peer connections, no DNS prefetch, no clipboard/screen capture/payments, and the
# host takes a game off the screen if its frame ever loads a second page
assert "webrtc 'block'" in runtime_headers["Content-Security-Policy"]
assert runtime_headers["X-DNS-Prefetch-Control"] == "off"
assert all(f"{f}=()" in runtime_headers["Permissions-Policy"] for f in ("display-capture", "clipboard-read", "payment"))
assert "function guard" in host_js and "guard(frame)" in host_js and "guard(own)" in host_js
assert "sbike-leaving" in host_js
# inside the game frame (sandbox probe, 2026-10-29): no WebRTC, no inner frames (which would hand back a fresh
# WebRTC), and leaving is reported as it happens
runtime_js = (pathlib.Path(__file__).resolve().parent.parent / "web/module-runtime.js").read_text()
assert "'RTCPeerConnection'" in runtime_js and "Frames are not available to games" in runtime_js
assert "addEventListener('pagehide'" in runtime_js and "MutationObserver" in runtime_js and "const hub=parent" in runtime_js
# the frame's rules name every script (no inline code), the game page accepts rules required by the Hub page, and the
# Hub page requires them, so an outside page a game navigates to can't run scripts of its own
assert b"nonce" not in runtime and b'src="/web/module-start.js"' in runtime and b'type="application/json"' in runtime
assert runtime_headers["Allow-CSP-From"] == "*" and "'nonce-" not in runtime_headers["Content-Security-Policy"]
assert "own.setAttribute('csp'," in host_js
# saves live with the Hub, the frame's heartbeat feeds a watchdog, and game sound goes through a Hub-owned limiter
assert "saved:(name)" in runtime_js and "send('save'" in runtime_js and "result={ok:true,capabilities,saves}" in host_js
assert "sbike-alive" in runtime_js and "stopped responding" in host_js
# the frame's signals are handled before the game-request checks, which return on anything else (a bug on 2026-10-29
# that left the watchdog deaf and closed healthy games)
assert host_js.index("type==='sbike-alive'") < host_js.index("m.type!=='sbike-module'")
assert host_js.index("type==='sbike-leaving'") < host_js.index("m.type!=='sbike-module'")
assert "createDynamicsCompressor" in runtime_js and "AudioNode.prototype,'connect'" in runtime_js
# on a game's own name: a real but separate origin, embeddable only by this computer's Hub
_, _, _, own = asyncio.run(mapserver.handle(None, "GET", "/modes/good/sandbox", b"", "good.game.localhost:8729"))
csp = own["Content-Security-Policy"]
assert csp.startswith("sandbox allow-scripts allow-same-origin;") and "frame-ancestors http://127.0.0.1:8729 " in csp
assert "good.game.localhost:8729/module-engine/4.7.1/" in csp and "'self'" not in csp
assert get("/modes/good/game.pck")[:3:2] == (200, b"GDPC game data")
assert get("/modes/good/manifest.json")[0] == 404, "only files the manifest lists"
assert get("/modes/changed/")[0] == 403 and get("/modes/changed/game.pck")[0] == 403
assert get("/modes/old/")[0] == 403
assert get("/modes/../engine/4.7.1/godot.js")[0] == 404
assert get("/engine/4.7.1/godot.js")[:3:2] == (200, b"engine") and get("/engine/4.7.1/godot.html")[0] == 404
assert get("/engine/4.6.0/godot.js")[0] == 404
# a pack that needs a newer hub (encrypted game data, 2026-10-29) is refused with a clear reason; a current one runs
assert packs.hub_version() is not None
packs.hub_version = lambda: (1, 12, 4)
assert packs.needs_newer_hub({"needs": {"hub": "1.12.4"}}) is None and packs.needs_newer_hub({"needs": {"hills": "x"}}) is None
make("future", needs={"hub": "1.13.0"})
future = next(p for p in packs.installed() if p["id"] == "future")
assert not future["ok"] and "needs Hub 1.13.0 or later" in future["why"]
assert "invalid hub version" in packs.needs_newer_hub({"needs": {"hub": "soon"}})
print("PASS packs: RFC 8032 vectors, signed packs run on the shared engine, changed/unsigned/untrusted packs refused")
