import asyncio
import json
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import module_sandbox as sandbox
import panel


class Bridge:
    def __init__(self):
        self.mode = self.session = self.route_ride = self.test = None
        self.actions = []

    def status(self):
        return {"power": 120, "cadence": 80, "ftp": 200, "mass": 85, "workouts": ["PRIVATE"],
                "profile": {"name": "PRIVATE"}, "reports": ["PRIVATE"], "events": ["PRIVATE"], "grade": float("nan")}

    def mode_start(self, pid, name):
        self.mode = {"id": pid}; self.actions.append(("start", pid, name))

    def mode_grade(self, value):
        self.actions.append(("grade", value)); return True, value

    def mode_mark(self, text):
        self.actions.append(("mark", text))

    def mode_end(self, text):
        self.actions.append(("end", text)); self.mode = None


class SandboxTest(unittest.TestCase):
    def setUp(self):
        sandbox._sessions.clear()
        self.bridge = Bridge()
        self.manifest = {"name": "Test game", "engine": "4.7.1", "permissions": {"telemetry": list(sandbox.TELEMETRY), "controls": ["hills", "markers", "lean"]}}
        self.verify = patch("packs.verified", return_value=(self.manifest, None)); self.verify.start()
        self.engine = patch("packs.isolated_engine_dir", return_value=pathlib.Path(".")); self.engine.start()
        self.addCleanup(self.verify.stop); self.addCleanup(self.engine.stop)

    def call(self, action, **args):
        return sandbox.handle(self.bridge, b"POST", json.dumps({"action": action, **args}).encode())

    def test_telemetry_is_selected_and_finite(self):
        out = self.call("open", id="test")
        self.assertEqual(out["data"], {"power": 120, "cadence": 80, "ftp": 200, "mass": 85, "bike": False, "no_bike": False})
        token = out["token"]
        self.assertNotIn("token", self.call("snapshot", token=token))

    def test_saves_live_with_the_hub(self):
        import tempfile, paths
        with patch.object(paths, "DATA", pathlib.Path(tempfile.mkdtemp())):
            out = self.call("open", id="test")
            self.assertEqual(out["saves"], {})
            self.assertEqual(self.call("save", token=out["token"], file="bike.cfg", text="[bikes]\nrider=1"), {"ok": True})
            self.assertEqual(self.call("open", id="test")["saves"], {"bike.cfg": "[bikes]\nrider=1"}, "there on the next launch")
            token = self.call("open", id="test")["token"]
            with self.assertRaises(ValueError): self.call("save", token=token, file="../escape", text="x")
            with self.assertRaises(ValueError): self.call("save", token=token, file="big", text="x" * sandbox.SAVE_LIMIT)
            self.assertTrue(json.loads(sandbox.saves_file("test").read_text()), "a readable JSON file")
        headers = sandbox.runtime_headers("test.game.localhost:8729", "test", "4.7.1")
        self.assertIn('"storage"', headers["Clear-Site-Data"], "the browser's own storage is wiped every launch")

    def test_markers_are_capped_per_session(self):
        token = self.call("open", id="test")["token"]
        self.call("start", token=token)
        session = sandbox._sessions[token]
        session["marks"] = sandbox.MARKS_LIMIT
        with self.assertRaises(ValueError): self.call("mark", token=token, text="one too many")

    def test_declared_fields_and_missing_permissions(self):
        self.manifest["permissions"] = {"telemetry": ["ftp"], "controls": []}
        out = self.call("open", id="test")
        self.assertEqual(out["data"], {"ftp": 200, "bike": False, "no_bike": False})
        self.call("start", token=out["token"])
        with self.assertRaises(ValueError): self.call("mark", token=out["token"], text="test")
        self.manifest.pop("permissions")
        with self.assertRaises(ValueError): self.call("open", id="test")

    def test_identity_capabilities_limits_and_revoke(self):
        token = self.call("open", id="test")["token"]
        with self.assertRaises(ValueError): self.call("start", token=token, id="other")
        self.call("start", token=token)
        self.assertEqual(self.bridge.actions[0], ("start", "test", "Test game"))
        self.assertEqual(self.call("grade", token=token, value=100)["grade"], 15)
        with self.assertRaises(ValueError): self.call("grade", token=token, value=float("nan"))
        with self.assertRaises(ValueError): self.call("fetch", token=token, url="/status")
        self.call("close", token=token)
        self.assertIsNone(self.bridge.mode)
        with self.assertRaises(ValueError): self.call("snapshot", token=token)

    def test_no_hills_and_active_route_are_respected(self):
        self.manifest["permissions"]["controls"] = []
        token = self.call("open", id="test")["token"]
        self.bridge.route_ride = object()
        with self.assertRaises(ValueError): self.call("start", token=token)
        self.bridge.route_ride = None
        self.call("start", token=token)
        with self.assertRaises(ValueError): self.call("grade", token=token, value=1)

    def test_workout_taking_control_blocks_game_grade(self):
        token = self.call("open", id="test")["token"]
        self.call("start", token=token)
        original = self.bridge.status
        self.bridge.status = lambda: {**original(), "workout": {"name": "active"}}
        with self.assertRaises(ValueError): self.call("grade", token=token, value=3)
        self.assertFalse(any(a[0] == "grade" for a in self.bridge.actions))

    def test_expired_and_replaced_sessions_stop_their_own_mode(self):
        token = self.call("open", id="test")["token"]
        self.call("start", token=token)
        sandbox._sessions[token]["seen"] -= sandbox.TTL + 1
        with self.assertRaises(ValueError): self.call("snapshot", token=token)
        self.assertIsNone(self.bridge.mode)
        a = self.call("open", id="test")["token"]
        b = self.call("open", id="next")["token"]
        with self.assertRaises(ValueError): self.call("start", token=a)
        self.call("start", token=b)
        self.assertEqual(self.bridge.mode["id"], "next")

    def test_browser_origin_gate(self):
        private = ["/status", "/api/setup/status", "/api/modes/session", "/stop", "/api/modes/import", "/history", "/mode/start/test"]
        for headers in [{b"origin": b"null"}, {b"sec-fetch-site": b"cross-site"},
                        {b"origin": b"https://evil.example", b"host": b"127.0.0.1:8729"}]:
            for path in private:
                for method in [b"GET", b"POST"]:
                    self.assertFalse(sandbox.request_allowed(method, path.encode(), headers), (method, path))
        self.assertTrue(sandbox.request_allowed(b"GET", b"/engine/4.7.1/godot.wasm", {b"origin": b"null"}))
        self.assertFalse(sandbox.request_allowed(b"POST", b"/modes/test/game.pck", {b"origin": b"null"}))
        self.assertFalse(sandbox.request_allowed(b"GET", b"/engine/../status", {b"origin": b"null"}))
        self.assertTrue(sandbox.request_allowed(b"POST", b"/api/modes/session", {b"origin": b"http://127.0.0.1:8729", b"host": b"127.0.0.1:8729", b"sec-fetch-site": b"same-origin"}))

    def test_hub_page_navigation_is_allowed_but_game_navigation_is_not(self):
        navigation = {b"sec-fetch-site": b"cross-site", b"sec-fetch-mode": b"navigate", b"sec-fetch-dest": b"document"}
        for path in [b"/coach", b"/ride?setup=1", b"/modes/monster-chase/"]:
            self.assertTrue(sandbox.request_allowed(b"GET", path, navigation))
            self.assertFalse(sandbox.request_allowed(b"GET", path, {**navigation, b"sec-fetch-dest": b"iframe"}))
            self.assertFalse(sandbox.request_allowed(b"GET", path, {**navigation, b"origin": b"null"}))
        for path in [b"/status", b"/api/modes/session", b"/stop"]:
            self.assertFalse(sandbox.request_allowed(b"GET", path, navigation))
        self.assertFalse(sandbox.request_allowed(b"POST", b"/coach", navigation))

    def test_http_gate_precedes_handlers_and_body_read(self):
        async def run():
            server = await panel.serve(self.bridge, port=0, lan=False)
            port = server.sockets[0].getsockname()[1]
            try:
                for route in ["/status", "/stop", "/api/modes/session", "/api/music/folder/upload"]:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.write(f"POST {route} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: null\r\nContent-Length: 999999\r\n\r\n".encode())
                    await writer.drain()
                    response = await asyncio.wait_for(reader.read(), 2)
                    self.assertTrue(response.startswith(b"HTTP/1.1 403"), response[:100])
                    writer.close(); await writer.wait_closed()
            finally:
                server.close(); await server.wait_closed()
        asyncio.run(run())
        self.assertEqual(self.bridge.actions, [])



class GameNameTest(unittest.TestCase):
    def test_game_names(self):
        h = lambda v: {b"host": v}
        self.assertEqual(sandbox.game_pack(h(b"monster-chase.game.localhost:8729")), "monster-chase")
        self.assertIsNone(sandbox.game_pack(h(b"127.0.0.1:8729")))
        self.assertIsNone(sandbox.game_pack(h(b"localhost:8729")))
        self.assertEqual(sandbox.game_pack(h(b"a.b.game.localhost:8729")), "")
        self.assertEqual(sandbox.game_pack(h(b".game.localhost")), "")

    def test_game_name_serves_only_game_files(self):
        ok = lambda pid, path, m=b"GET": sandbox.game_path_allowed(pid, m, path)
        self.assertTrue(ok("mc", b"/modes/mc/sandbox?dev=1"))
        self.assertTrue(ok("mc", b"/modes/mc/game.pck"))
        self.assertTrue(ok("mc", b"/module-engine/4.7.1/godot.wasm"))
        self.assertTrue(ok("mc", b"/web/module-runtime.js"))
        for bad in (b"/", b"/ride", b"/api/status", b"/api/modes/session", b"/modes/other/game.pck", b"/modes/mc/",
                    b"/modes/mc/../x", b"/remote/pin", b"/web/ride-hub.html", b"/vision/lean.js"):
            self.assertFalse(ok("mc", bad), bad)
        self.assertFalse(ok("mc", b"/modes/mc/sandbox", b"POST"))
        self.assertFalse(ok("", b"/modes/mc/sandbox"))

if __name__ == "__main__": unittest.main()
