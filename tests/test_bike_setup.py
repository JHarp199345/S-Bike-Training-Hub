"""Bike setup end to end, with simulated bikes (bike_ble.Sim) and the real MCP server:

  matched bikes   the Merach S29 (a built-in profile) and a standard FTMS bike connect
                  with one click - no request, no assistant
  unrecognized    a bike with its own protocol: consent, the queued request, the
                  assistant's tools over MCP (read, capture, propose, check, feel,
                  activate), wrong profiles caught, and the bridge using the result
  safety          resistance 0, resets, out-of-range levels and stray bytes never
                  reach a bike
"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json, os, subprocess, tempfile, threading, types

os.environ["S_BIKE_SIM"] = "1"
os.environ["S_BIKE_SIM_FAST"] = "1"
HERE = pathlib.Path(__file__).resolve().parent.parent
import bikes, bike_ble, bike_check

ok = True


def check(name, cond):
    global ok
    cond = bool(cond)
    ok &= cond
    print(("PASS " if cond else "FAIL ") + name)


ACME_GOOD = {
    "id": "acme-ic7", "name": "ACME IC7", "match": {"name_prefix": ["ACME IC7"]}, "protocol": "custom",
    "resistance": {"min": 1, "max": 32},
    "custom": {"data": {"characteristic": bike_ble.ACME_DATA, "prefix": "f0b2",
                        "fields": {"cadence_rpm": {"offset": 2, "size": 1},
                                   "power_w": {"offset": 3, "size": 2},
                                   "resistance": {"offset": 5, "size": 1}}},
               "control": {"characteristic": bike_ble.ACME_CTRL,
                           "resistance": {"template": "f0b101{level}", "size": 1, "checksum": "sum8"}}}}


def with_(p, **kw):
    q = json.loads(json.dumps(p))
    for path, v in kw.items():
        d = q
        keys = path.split("__")
        for k in keys[:-1]:
            d = d[k]
        d[keys[-1]] = v
    return q


def unit():
    tmp = pathlib.Path(tempfile.mkdtemp())
    scan = asyncio.run(bike_ble.Sim("1").scan())
    found = bikes.identify(scan, tmp)
    by = {o["device"]["name"]: o for o in found}
    check("the S29 is recognized from its built-in profile", by["MRK-S29-A1B2"]["status"] == "known"
          and by["MRK-S29-A1B2"]["profile"]["id"] == "merach-s29")
    check("a standard FTMS bike is recognized as standard", by["KICKR BIKE 7F3A"]["status"] == "standard")
    check("a bike with its own protocol is unrecognized", by["ACME IC7-0042"]["status"] == "unrecognized")
    check("a speaker and a heart-rate strap are unrecognized too", by["JBL Flip 5"]["status"] == "unrecognized"
          and by["COROS HRM 51A"]["status"] == "unrecognized")
    check("recognized bikes are listed first, the fitness-looking unknown before the speaker",
          [o["status"] for o in found[:2]] == ["known", "standard"]
          and [o["device"]["name"] for o in found].index("ACME IC7-0042") < [o["device"]["name"] for o in found].index("JBL Flip 5"))

    p = bikes.validate(ACME_GOOD)
    check("a good custom profile validates (resistance_zero always blocked)", "resistance_zero" in p["blocked"])
    bad = [({"id": "Bad Id"}, "id"), (with_(ACME_GOOD, protocol="bluetooth"), "protocol"),
           (with_(ACME_GOOD, custom__control__resistance__template="f0b101"), "{level}"),
           (with_(ACME_GOOD, custom__data__prefix="zz"), "hex"),
           (with_(ACME_GOOD, custom__data__fields={"power_w": {"offset": 3, "size": 2}}), "cadence_rpm"),
           (with_(ACME_GOOD, resistance={"min": 10, "max": 5}), "min"),
           (with_(ACME_GOOD, run="os.system('x')"), "unknown field"),
           (with_(ACME_GOOD, blocked=["format_disk"]), "blocked")]
    msgs = []
    for prof, want in bad:
        try:
            bikes.validate(prof)
            msgs.append(None)
        except bikes.BadProfile as e:
            msgs.append(str(e) if want in str(e) else None)
    check("bad profiles are refused with a message saying what to fix", all(msgs))

    cmd = bikes.resistance_command(p, 9)
    check("a custom resistance command is built with its checksum", cmd.hex() == "f0b10109" + f"{(0xf0 + 0xb1 + 1 + 9) & 0xff:02x}")
    pkt = bytes.fromhex("f0b2") + bytes([82]) + (215).to_bytes(2, "little") + bytes([9, 0, 0])
    check("a custom data packet decodes", bikes.parse(p, pkt) == {"cadence_rpm": 82, "power_w": 215, "resistance": 9})
    check("a status packet (other prefix) isn't a reading", bikes.parse(p, bytes.fromhex("f0a00100000000")) == {})
    ibd = bikes.build_ibd(215, 82, 27.1, 90)
    check("readings round-trip through an FTMS packet for Kinomap",
          bikes.parse_ftms(ibd) == {"speed_kmh": 27.1, "cadence_rpm": 82.0, "resistance": 90, "power_w": 215})

    s29 = next(x for x in bikes.all_profiles(tmp) if x["id"] == "merach-s29")
    ctl = bikes.FTMS_CONTROL
    refused = [bikes.allowed_write(s29, ctl, b"\x01")[0], bikes.allowed_write(s29, ctl, b"\x04\x00\x00")[0],
               bikes.allowed_write(s29, ctl, bytes([0x04]) + (170).to_bytes(2, "little"))[0],
               bikes.allowed_write(s29, ctl, bytes.fromhex("1100000a0028"))[0],
               bikes.allowed_write(s29, bikes.IBD, b"\x00")[0],
               bikes.allowed_write(p, bike_ble.ACME_CTRL, bytes.fromhex("f0b10100a2"))[0],
               bikes.allowed_write(p, bike_ble.ACME_CTRL, bytes.fromhex("deadbeef"))[0]]
    check("never sent: reset, resistance 0, level 17 on a 16-level bike, blocked simulation, other characteristics, "
          "custom level 0, stray bytes", not any(refused))
    check("sent: request control and an in-range level", bikes.allowed_write(s29, ctl, b"\x00")[0]
          and bikes.allowed_write(s29, ctl, bytes([0x04]) + (80).to_bytes(2, "little"))[0]
          and bikes.allowed_write(p, bike_ble.ACME_CTRL, cmd)[0])
    try:
        bikes.resistance_command(s29, 0)
        zero = False
    except ValueError:
        zero = True
    check("resistance 0 can't even be built", zero)


def guided_check():
    sim = bike_ble.Sim("acme,s29")
    acme = sim.bikes["SIM:ACME"]
    dev = {"address": "SIM:ACME"}
    good = asyncio.run(bike_check.run(dev, ACME_GOOD, sim))
    check(f"the guided check passes with the right profile ({good['effect']['seen']})",
          good["passed"] and good["resistance_tested"] and good["stayed_connected"] and acme.reboots == 0)
    check("it only nudged: easy level, one step at a time, back to easy",
          good["effect"]["hard_level"] - good["effect"]["easy_level"] <= 12
          and all(w["why"].startswith("resistance") for w in good["sent"])
          and good["sent"][-1]["why"] == f"resistance {good['effect']['easy_level']:g}")
    wrong = with_(ACME_GOOD, custom__control__resistance__template="f0b201{level}")
    bad = asyncio.run(bike_check.run(dev, wrong, sim))
    check("a wrong resistance command fails the check (the bike dropped; nothing more was sent)",
          not bad["passed"] and acme.reboots == 1 and len(bad["sent"]) == 1
          and any("disconnected" in x for x in bad["problems"]))
    offs = with_(ACME_GOOD, custom__data__fields__cadence_rpm={"offset": 6, "size": 2})
    bad2 = asyncio.run(bike_check.run(dev, offs, sim))
    check("a wrong cadence field fails before any command is sent", not bad2["passed"] and not bad2["sent"]
          and any("Cadence" in x for x in bad2["problems"]))
    os.environ["S_BIKE_SIM_CADENCE"] = "0"
    still = asyncio.run(bike_check.run(dev, ACME_GOOD, bike_ble.Sim("acme")))
    del os.environ["S_BIKE_SIM_CADENCE"]
    check("no pedaling: the check says so and sends nothing", not still["passed"] and not still["sent"])
    s29 = asyncio.run(bike_check.run({"address": "SIM:S29"}, bikes.all_profiles("/nonexistent")[0], sim))
    check("the S29 passes the same check without being reset or sent level 0",
          s29["passed"] and sim.bikes["SIM:S29"].reboots == 0
          and not any(w[1].startswith(("01", "040000")) for w in sim.bikes["SIM:S29"].writes))


def rpc(url, *msgs):
    env = {**os.environ, "S29_HUB_URL": url}
    out = subprocess.run([sys.executable, str(HERE / "mcp_server.py")], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                         capture_output=True, text=True, env=env, timeout=120)
    return [json.loads(l) for l in out.stdout.splitlines() if l.strip()]


def tool(url, name, args=None):
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}
    r = rpc(url, init, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args or {}}})
    res = r[1]["result"]
    text = res["content"][0]["text"]
    return (None, text) if res.get("isError") else (json.loads(text), None)


def http(url, path, body=None):
    import urllib.request, urllib.error
    req = urllib.request.Request(url + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def end_to_end():
    import panel
    tmp = pathlib.Path(tempfile.mkdtemp())
    (tmp / "rides").mkdir()
    events = []

    class FakeBridge:
        profile = {"ftp": 180, "ftp_source": "test"}
        csv_path = tmp / "rides" / "ride_no_bike.csv"
        args = types.SimpleNamespace(no_bike=False)
        def event(self, m): events.append(m)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(panel.serve(FakeBridge(), 18761, lan=False))
    threading.Thread(target=loop.run_forever, daemon=True).start()
    url = "http://127.0.0.1:18761"

    # MCP surface
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}}
    r = rpc(url, init, {"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "prompts/get", "params": {"name": "get-my-bike-working"}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    check("the server tells the assistant what 'get my bike working' means",
          "get my bike working" in r[0]["result"]["instructions"] and "get_bike_setup_request" in r[0]["result"]["instructions"])
    check("…and offers it as a prompt", r[1]["result"]["prompts"][0]["name"] == "get-my-bike-working"
          and "get_bike_setup_request" in r[2]["result"]["messages"][0]["content"]["text"])
    names = {t["name"] for t in r[3]["result"]["tools"]}
    check("all six bike tools are listed", {"get_bike_setup_request", "capture_bike_data", "propose_bike_profile",
                                           "run_bike_check", "record_bike_feel", "activate_bike_profile"} <= names)
    desc = next(t for t in r[3]["result"]["tools"] if t["name"] == "get_bike_setup_request")["description"]
    check("the first tool's description names the phrase", "get my bike working" in desc)

    # 1. a matching bike: one click, no assistant
    code, sc = http(url, "/api/bike/scan", {})
    check(f"scan finds the S29 first ({sc['message']})", code == 200 and sc["likely"]["device"]["name"] == "MRK-S29-A1B2")
    code, ch = http(url, "/api/bike/choose", {"address": "SIM:S29"})
    st = http(url, "/api/bike/status")[1]
    check("choosing it makes it the bike, with no request queued", code == 200 and st["active"]["id"] == "merach-s29"
          and st["request"] is None and json.loads((tmp / "bike.json").read_text())["how"] == "known")
    br, _ = tool(url, "get_bike_setup_request")
    check("asked anyway, the assistant hears there's nothing to do and which bike is set up",
          br["pending"] is False and br["active_bike"]["name"] == "Merach S29")
    code, _ = http(url, "/api/bike/choose", {"address": "SIM:KICKR"})
    check("a standard FTMS bike connects with one click too", code == 200
          and http(url, "/api/bike/status")[1]["active"]["protocol"] == "ftms")
    code, j = http(url, "/api/bike/choose", {"address": "SIM:ACME"})
    check("an unrecognized bike can't be 'chosen' - it needs setting up", code == 422 and "assistant" in j["error"])

    # 2. an unrecognized bike: consent, queue, the assistant over MCP
    code, j = http(url, "/api/bike/request", {"address": "SIM:ACME"})
    check("nothing is queued without the athlete's yes", code == 400 and not (tmp / "bike_setup.json").exists())
    code, j = http(url, "/api/bike/request", {"address": "SIM:ACME", "consent": True})
    check("with it, the request is queued and the page says what to type",
          code == 200 and j["say"] == "get my bike working" and j["request"]["status"] == "waiting_for_assistant"
          and j["request"]["inspection"]["packets"])
    check("the page shows the waiting message", "get my bike working" in http(url, "/api/bike/status")[1]["message"])
    br, _ = tool(url, "get_bike_setup_request")
    req = br["request"]
    check("the assistant reads it: the device, its unknown service and characteristics, and data packets",
          br["pending"] and req["device"]["name"] == "ACME IC7-0042"
          and any(s["uuid"] == bike_ble.ACME_SVC for s in req["inspection"]["services"])
          and req["inspection"]["packets"]["shown"] and br["what_to_do"] and br["profile_format"])
    check("the assistant is told to confirm the bike by name with the athlete first",
          "confirm" in br["rules"][0] and "ACME IC7-0042" in br["rules"][0] or "confirm the bike" in br["rules"][0])
    check("…without the athlete's training history", "rides" not in json.dumps(req) and "checkins" not in json.dumps(req))
    cap, _ = tool(url, "capture_bike_data", {"seconds": 5, "label": "steady 90 rpm"})
    check("capture records more packets on request (listen-only: nothing written)",
          cap["capture"]["label"] == "steady 90 rpm" and cap["capture"]["packets"]["shown"])
    pr, _ = tool(url, "propose_bike_profile", {"profile": with_(ACME_GOOD, custom__data__fields__power_w={"offset": 2, "size": 4}),
                                               "note": "first guess"})
    check(f"a profile with a wrong power field gets warnings ({pr['warnings'][:1]})", pr["warnings"])
    _, err = tool(url, "propose_bike_profile", {"profile": {"id": "x"}})
    check("an invalid profile comes back as a message the assistant can act on", err and "id:" in err)
    pr, _ = tool(url, "propose_bike_profile", {"profile": ACME_GOOD, "note": "f0b2 packets: cadence byte 2, power 3-4"})
    dec = pr["decoded"][0]["avg"]
    check(f"the right profile decodes believable numbers ({dec})", not pr["warnings"] and 60 < dec["cadence_rpm"] < 100
          and 20 < dec["power_w"] < 1500)
    _, err = tool(url, "activate_bike_profile")
    check("activation before the check is refused", err and "check" in err)
    _, err = tool(url, "run_bike_check", {})
    check("the check won't run until the assistant says the athlete is ready", err and "athlete_ready" in err)
    ck, _ = tool(url, "run_bike_check", {"athlete_ready": True})
    check("the guided check passes over MCP", ck["check"]["passed"] and "harder" in ck["next"])
    _, err = tool(url, "activate_bike_profile")
    check("activation before the athlete confirms the feel is refused", err and "record_bike_feel" in err)
    tool(url, "record_bike_feel", {"felt": "harder", "note": "noticeably heavier, then easy again"})
    act, _ = tool(url, "activate_bike_profile", {"share": True})
    st = http(url, "/api/bike/status")[1]
    check("activated: it's the bike now, the request is closed", act["activated"]["id"] == "acme-ic7"
          and st["active"]["id"] == "acme-ic7" and st["request"] is None
          and (tmp / "bike_profiles_local" / "acme-ic7.json").exists())
    check("sharing gives a pre-filled GitHub issue link", act["share"].startswith("https://github.com/JHarp199345/")
          and "acme-ic7" in act["share"])
    found = {o["device"]["name"]: o["status"] for o in http(url, "/api/bike/scan", {})[1]["found"]}
    check("the next scan recognizes it - no assistant needed again", found["ACME IC7-0042"] == "known")
    check("the hub's event log recorded the setup", any("set up by the assistant" in e for e in events))

    # 3. the bridge connects with the new profile
    import bridge
    os.chdir(tmp)
    b = types.SimpleNamespace(args=types.SimpleNamespace(name=bridge.DEFAULT_NAME), event=events.append,
                              bike_profile=None, level_format=3)
    prof = bridge.Bridge.wanted_profile(b)
    check("the bridge picks up the set-up bike (bike.json)", prof and prof["id"] == "acme-ic7")
    b.bike_profile = prof
    check("its levels become the bike's own command", bridge.Bridge.level_command(b, 9) == bikes.resistance_command(prof, 9))
    sent = []
    b.bike = types.SimpleNamespace(write_gatt_char=lambda c, v, response=True: _record(sent, c, v))
    b.have_control = True
    asyncio.run(bridge.Bridge.forward(b, bytes.fromhex("0401")))
    asyncio.run(bridge.Bridge.forward(b, bikes.resistance_command(prof, 9)))
    check("an FTMS command from Kinomap isn't forwarded raw to a custom bike; its own level is",
          len(sent) == 1 and sent[0][1] == bikes.resistance_command(prof, 9).hex())
    b.args.name = "MYBIKE"
    check("--name given by hand still wins", bridge.Bridge.wanted_profile(b) is None)
    s29 = next(x for x in bikes.all_profiles(tmp) if x["id"] == "merach-s29")
    b2 = types.SimpleNamespace(bike_profile=s29, static={}, res_range=(1.0, 32.0), event=events.append, level_format=3,
                               bike_sims=True)
    bridge.Bridge.apply_profile(b2, s29)
    check("the S29 profile sets its 16 levels and keeps hills as levels (simulation blocked)",
          b2.res_range == (1.0, 16.0) and b2.bike_sims is False)
    loop.call_soon_threadsafe(loop.stop)


async def _record(sent, c, v):
    sent.append((c, bytes(v).hex()))


def welcome_page():
    html = (HERE / "web" / "welcome.html").read_text()
    check("the welcome page has the bike step: scan, consent, and the line to type",
          all(x in html for x in ('id="bikescan"', 'id="bikeyes"', "get my bike working", "/api/bike/")))


unit()
guided_check()
end_to_end()
welcome_page()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
