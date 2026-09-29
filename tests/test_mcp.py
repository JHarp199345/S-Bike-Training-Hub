"""The MCP server: the protocol handshake, every tool listed with a schema, tools
working against a (scratch) bridge, and a clear message when the bridge is off."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json, os, subprocess, tempfile, threading

HERE = pathlib.Path(__file__).resolve().parent.parent


def rpc(url, *msgs):
    env = {**os.environ, "S29_HUB_URL": url}
    out = subprocess.run([sys.executable, str(HERE / "mcp_server.py")], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                         capture_output=True, text=True, env=env, timeout=60)
    return [json.loads(l) for l in out.stdout.splitlines() if l.strip()]


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                                        "clientInfo": {"name": "test", "version": "1"}}}
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    r = rpc("http://127.0.0.1:1", init, note, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_today", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "no/such"})
    check("handshake answers with the client's protocol version", r[0]["result"]["protocolVersion"] == "2025-06-18"
          and r[0]["result"]["capabilities"].get("tools") is not None)
    check("the initialized notification gets no reply", [m["id"] for m in r] == [1, 2, 3, 4])
    tools = r[1]["result"]["tools"]
    check(f"{len(tools)} tools, each with a description and a JSON schema",
          len(tools) == 36 and all(t["description"] and t["inputSchema"]["type"] == "object" for t in tools))
    check("with the bridge off, a tool says so plainly (not a crash)",
          r[2]["result"]["isError"] and "isn't running" in r[2]["result"]["content"][0]["text"])
    check("an unknown method gets a JSON-RPC error", r[3]["error"]["code"] == -32601)

    # against a scratch bridge
    import panel, workouts
    tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / "rides").mkdir()
    workouts.FOLDER = tmp / "workouts"; workouts.FOLDER.mkdir()
    class FakeBridge:
        profile = {"ftp": 180, "ftp_source": "test"}
        csv_path = tmp / "rides" / "ride_2026-10-01_0700.csv"
        workouts = []
        def reload_workouts(self): self.workouts = [{"id": w["id"], "name": w["name"]} for w in workouts.list_all(180, workouts.FOLDER)]
        def workout_start_id(self, wid): return True
        def coach_test_start(self): pass
        def event(self, m): pass
    loop = asyncio.new_event_loop()
    srv = loop.run_until_complete(panel.serve(FakeBridge(), 18733, lan=False))
    threading.Thread(target=loop.run_forever, daemon=True).start()
    url = "http://127.0.0.1:18733"
    call = lambda i, name, args: {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
    r = rpc(url, init, call(2, "record_checkin", {"date": "2026-10-01", "legs": 6, "gut": "easy"}),
            call(3, "create_timed_workout", {"total_minutes": 30, "intervals": 3, "interval_pct": 70, "name": "Easy 3x",
                                             "make_today_plan": True, "date": "2026-10-01"}),
            call(4, "set_plan", {"date": "2026-10-01", "verdict": "easy",
                                 "note": "Legs 6/10: 30 min easy, 85+ rpm, stop if they complain."}),
            call(5, "get_today", {"date": "2026-10-01"}), call(6, "list_workouts", {}))
    ck = json.loads(r[1]["result"]["content"][0]["text"])
    check(f"record_checkin returns the verdict ({ck['checkin']['verdict']})", ck["checkin"]["verdict"] == "easy")
    wid = json.loads(r[2]["result"]["content"][0]["text"])["id"]
    check(f"create_timed_workout saves it ({wid})", (workouts.FOLDER / f"{wid}.json").exists())
    today = json.loads(r[4]["result"]["content"][0]["text"])
    check("get_today shows the plan, the note and the workout the coach set",
          today["plan"]["verdict"] == "easy" and "85+ rpm" in today["plan"]["note"] and today["plan"]["workout"] == wid)
    check("list_workouts includes it", any(w["id"] == wid for w in json.loads(r[5]["result"]["content"][0]["text"])))
    loop.call_soon_threadsafe(srv.close)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
