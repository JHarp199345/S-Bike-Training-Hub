"""Recording a test through the API and the MCP record_test tool (the route was unreachable before 2026-10-03)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json, os, subprocess, tempfile, threading, types
import panel, coach

tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / "rides").mkdir()


class FakeBridge:
    profile = {"ftp": 180, "ftp_source": "test"}
    csv_path = tmp / "rides" / "ride_x.csv"
    workouts = []
    args = types.SimpleNamespace(no_bike=True)
    def event(self, m): pass


loop = asyncio.new_event_loop()
loop.run_until_complete(panel.serve(FakeBridge(), 18781, lan=False))
threading.Thread(target=loop.run_forever, daemon=True).start()
env = {**os.environ, "S29_HUB_URL": "http://127.0.0.1:18781"}
msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "record_test", "arguments":
         {"capacity": "ftp", "value": 196, "kind": "test", "date": "2026-10-01", "note": "ramp test"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "record_test", "arguments":
         {"t400": 480, "t200": 225, "date": "2026-10-02"}}}]
out = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "mcp_server.py")],
                     input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, env=env, timeout=60)
res = [json.loads(l) for l in out.stdout.splitlines() if l.strip()]
ok = all(not r["result"].get("isError") for r in res[1:])
d = coach.load(coach.file_for(tmp / "rides"))
cal = d.get("calibration") or {}
ok &= any(e["value"] == 196 for e in cal.get("ftp", [])) and bool(cal.get("swim_css"))
print(("PASS" if ok else "FAIL") + " record_test saves an FTP result and a swim CSS test through the MCP tool")
if not ok:
    print(res, cal)
loop.call_soon_threadsafe(loop.stop)
sys.exit(0 if ok else 1)
