"""bikes.py - which bike is this, how to talk to it, and the queued request for help.

No Bluetooth here: plain data in, plain data out, so it runs and is tested on
any computer. bike_ble.py does the radio work and bike_check.py the guided test.

A bike PROFILE is data, never code. It says how to recognize the bike, which
protocol it speaks, its resistance range, and what must never be sent to it:

  protocol "ftms"    the standard Fitness Machine Service (most smart bikes made
                     since ~2020). Readings and resistance work the standard way;
                     the profile only adds quirks (blocked commands, level format).
  protocol "custom"  a bike with its own protocol, described field by field:
                     where power/cadence/speed sit in its data packets, and the
                     bytes of its resistance command. bike_check.py proves it works.

Setup, in order (see setup_status):
  1. scan            identify() sorts nearby devices: known (a saved/built-in profile
                     matches), standard (speaks FTMS), or unrecognized.
  2. known/standard  choose() saves it as the active bike. Done - no AI needed.
  3. unrecognized    with the athlete's consent, open_request() queues a request
                     holding the scan, the bike's services and captured data.
                     The athlete tells their assistant "get my bike working";
                     the assistant reads the request over MCP, proposes a profile
                     (propose()), the hub runs the guided test, the athlete says
                     whether it got harder, and activate() makes it the bike.
"""
import datetime as dt
import json
import math
import re
import uuid as _uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILTIN = HERE / "bike_profiles"              # profiles shipped with the hub (and shared ones, once merged)
SIG = "-0000-1000-8000-00805f9b34fb"


def full_uuid(u):
    """'1826', '0x1826' or a full UUID -> the full lower-case 128-bit form."""
    s = str(u).strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if re.fullmatch(r"[0-9a-f]{4}", s):
        return f"0000{s}{SIG}"
    if re.fullmatch(r"[0-9a-f]{8}", s):
        return f"{s}{SIG}"
    return str(_uuid.UUID(s))                  # raises ValueError for anything else


FTMS_SERVICE = full_uuid("1826")
CP_SERVICE, CSC_SERVICE, HR_SERVICE = full_uuid("1818"), full_uuid("1816"), full_uuid("180d")
IBD, FTMS_CONTROL = full_uuid("2ad2"), full_uuid("2ad9")
SERVICE_NAMES = {FTMS_SERVICE: "Fitness Machine (FTMS)", CP_SERVICE: "Cycling Power", CSC_SERVICE: "Speed and Cadence",
                 HR_SERVICE: "Heart Rate", full_uuid("180a"): "Device Information", full_uuid("180f"): "Battery"}

# Commands a profile may name as never-to-send. "reset" and "resistance_zero" are
# the two that reboot the Merach S29 (2026-09-25) - the reason this list exists.
BLOCKABLE = {"reset": "FTMS reset (op 0x01)", "resistance_zero": "resistance level 0",
             "target_power": "FTMS target power / ERG (op 0x05)", "simulation": "FTMS hill simulation (op 0x11)",
             "start_stop": "FTMS start/stop (ops 0x07, 0x08)"}
LEVEL_FORMATS = ("ftms-level-x10", "ftms-level-u8")
FIELDS = ("power_w", "cadence_rpm", "speed_kmh", "resistance", "heart_rate")
CHECKSUMS = ("none", "sum8", "xor8")
MAX_LEVEL = 200


class BadProfile(ValueError):
    pass


# ── profiles ─────────────────────────────────────────────────────────────────

def _hex(s, what, allow_level=False):
    if not isinstance(s, str):
        raise BadProfile(f"{what}: hex bytes as a string, e.g. 'f0a1'")
    t = s.replace(" ", "").lower()
    if allow_level:
        t = t.replace("{level}", "")
    if len(t) % 2 or not re.fullmatch(r"[0-9a-f]*", t) or len(t) > 40:
        raise BadProfile(f"{what}: '{s}' isn't hex bytes (at most 20 bytes)")
    return s.replace(" ", "").lower()


def _keys(d, allowed, what):
    if not isinstance(d, dict):
        raise BadProfile(f"{what} must be an object")
    extra = set(d) - set(allowed)
    if extra:
        raise BadProfile(f"{what}: unknown field(s) {sorted(extra)}; allowed: {sorted(allowed)}")


def _num(v, what, lo, hi, integer=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (integer and int(v) != v) or not lo <= v <= hi:
        raise BadProfile(f"{what}: a {'whole ' if integer else ''}number from {lo} to {hi}")
    return int(v) if integer else float(v)


def _field(f, what):
    _keys(f, ("offset", "size", "signed", "endian", "scale"), what)
    _num(f.get("offset"), f"{what}.offset", 0, 63, True)
    if f.get("size") not in (1, 2, 3, 4):
        raise BadProfile(f"{what}.size: 1, 2, 3 or 4 bytes")
    if f.get("endian", "little") not in ("little", "big"):
        raise BadProfile(f"{what}.endian: little or big")
    if not isinstance(f.get("signed", False), bool):
        raise BadProfile(f"{what}.signed: true or false")
    if f.get("scale", 1) in (0, None) or not isinstance(f.get("scale", 1), (int, float)):
        raise BadProfile(f"{what}.scale: a non-zero number (the reading is raw x scale)")


def validate(p):
    """The profile, normalized, or BadProfile with a message an assistant can act on."""
    _keys(p, ("id", "name", "match", "protocol", "resistance", "blocked", "custom", "notes", "source", "tested"), "profile")
    if not isinstance(p.get("id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,47}", p["id"]):
        raise BadProfile("id: lower-case letters, digits and dashes, e.g. 'acme-ic7'")
    if not isinstance(p.get("name"), str) or not 2 <= len(p["name"].strip()) <= 60:
        raise BadProfile("name: the bike's name as people know it, e.g. 'Acme IC7'")
    m = p.get("match") or {}
    _keys(m, ("name_prefix", "address", "service"), "match")
    pre = m.get("name_prefix") or []
    if isinstance(pre, str):
        pre = [pre]
    if not isinstance(pre, list) or not all(isinstance(x, str) and 2 <= len(x) <= 30 for x in pre):
        raise BadProfile("match.name_prefix: the start of the bike's Bluetooth name (or a list of them)")
    if not pre and not m.get("address"):
        raise BadProfile("match needs name_prefix (or address) so the hub can find the bike again")
    m = {"name_prefix": pre} | ({"address": str(m["address"])} if m.get("address") else {}) \
        | ({"service": full_uuid(m["service"])} if m.get("service") else {})
    proto = p.get("protocol")
    if proto not in ("ftms", "custom"):
        raise BadProfile("protocol: 'ftms' (standard Fitness Machine Service) or 'custom'")
    r = p.get("resistance") or {}
    _keys(r, ("min", "max", "format", "none"), "resistance")
    if r.get("none"):
        r = {"none": True}
    else:
        lo, hi = _num(r.get("min", 1), "resistance.min", 0, MAX_LEVEL), _num(r.get("max"), "resistance.max", 1, MAX_LEVEL)
        if lo >= hi:
            raise BadProfile("resistance: min must be below max")
        r = {"min": lo, "max": hi}
        if proto == "ftms":
            fmt = (p.get("resistance") or {}).get("format", "ftms-level-x10")
            if fmt not in LEVEL_FORMATS:
                raise BadProfile(f"resistance.format: one of {LEVEL_FORMATS}")
            r["format"] = fmt
    blocked = p.get("blocked") or []
    if not isinstance(blocked, list) or not all(b in BLOCKABLE for b in blocked):
        raise BadProfile(f"blocked: a list drawn from {sorted(BLOCKABLE)}")
    out = {"id": p["id"], "name": p["name"].strip(), "match": m, "protocol": proto, "resistance": r,
           "blocked": sorted(set(blocked) | {"resistance_zero"})}
    if proto == "custom":
        c = p.get("custom")
        _keys(c, ("data", "control"), "custom")
        d = c.get("data")
        _keys(d, ("characteristic", "prefix", "fields"), "custom.data")
        try:
            d_char = full_uuid(d.get("characteristic"))
        except (ValueError, TypeError, AttributeError):
            raise BadProfile("custom.data.characteristic: the UUID of the characteristic that notifies the readings")
        fields = d.get("fields") or {}
        _keys(fields, FIELDS, "custom.data.fields")
        if "power_w" not in fields or "cadence_rpm" not in fields:
            raise BadProfile("custom.data.fields needs at least power_w and cadence_rpm")
        for k, f in fields.items():
            _field(f, f"custom.data.fields.{k}")
        data = {"characteristic": d_char, "prefix": _hex(d.get("prefix", ""), "custom.data.prefix"), "fields": fields}
        ctl = None
        if not r.get("none"):
            ct = c.get("control")
            _keys(ct, ("characteristic", "init", "resistance", "response"), "custom.control")
            try:
                c_char = full_uuid(ct.get("characteristic"))
            except (ValueError, TypeError, AttributeError):
                raise BadProfile("custom.control.characteristic: the UUID commands are written to")
            init = ct.get("init") or []
            if not isinstance(init, list) or len(init) > 4:
                raise BadProfile("custom.control.init: up to 4 hex commands sent once after connecting")
            rc = ct.get("resistance")
            _keys(rc, ("template", "size", "endian", "scale", "checksum"), "custom.control.resistance")
            tpl = _hex(rc.get("template"), "custom.control.resistance.template", allow_level=True)
            if tpl.count("{level}") != 1:
                raise BadProfile("custom.control.resistance.template: the command's hex bytes with {level} once, "
                                 "e.g. 'f0b101{level}'")
            if rc.get("size", 1) not in (1, 2):
                raise BadProfile("custom.control.resistance.size: 1 or 2 bytes")
            if rc.get("checksum", "none") not in CHECKSUMS:
                raise BadProfile(f"custom.control.resistance.checksum: one of {CHECKSUMS}")
            ctl = {"characteristic": c_char, "init": [_hex(x, "custom.control.init") for x in init],
                   "response": bool(ct.get("response", True)),
                   "resistance": {"template": tpl, "size": rc.get("size", 1), "endian": rc.get("endian", "little"),
                                  "scale": _num(rc.get("scale", 1), "custom.control.resistance.scale", 0.01, 100),
                                  "checksum": rc.get("checksum", "none")}}
        out["custom"] = {"data": data, "control": ctl}
    for k in ("notes", "source"):
        if isinstance(p.get(k), str):
            out[k] = p[k][:500]
    if isinstance(p.get("tested"), dict):
        out["tested"] = p["tested"]
    return out


def generic_ftms(name, address=None):
    """A profile for a standard FTMS bike seen as `name`: nothing to guess."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "ftms-bike").lower()).strip("-")[:40] or "ftms-bike"
    return validate({"id": f"ftms-{slug}"[:48].rstrip("-"), "name": name or "FTMS bike",
                     "match": {"name_prefix": [name]} if name else {"address": address},
                     "protocol": "ftms", "resistance": {"min": 1, "max": 32}, "source": "standard"})


def _dir(base):
    return Path(base) / "bike_profiles_local"


def all_profiles(base):
    """Built-in profiles, then the rider's own (which win on the same id)."""
    out = {}
    for folder in (BUILTIN, _dir(base)):
        for f in sorted(folder.glob("*.json")) if folder.exists() else ():
            try:
                p = validate(json.loads(f.read_text()))
                out[p["id"]] = p
            except (OSError, ValueError):
                continue
    return list(out.values())


def save_profile(base, p):
    p = validate(p)
    _dir(base).mkdir(parents=True, exist_ok=True)
    (_dir(base) / f"{p['id']}.json").write_text(json.dumps(p, indent=1))
    return p


def matches(p, name, address=None):
    m = p.get("match", {})
    if m.get("address") and address and m["address"].lower() == str(address).lower():
        return True
    return any((name or "").upper().startswith(x.upper()) for x in m.get("name_prefix", []))


# ── the active bike ──────────────────────────────────────────────────────────

def active(base):
    """The profile the bridge connects with, or None (the bridge then uses --name)."""
    try:
        a = json.loads((Path(base) / "bike.json").read_text())
        return validate(a["profile"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def set_active(base, p, how):
    p = validate(p)
    (Path(base) / "bike.json").write_text(json.dumps({"profile": p, "how": how, "since": _now()}, indent=1))
    return p


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


# ── identifying what the scan found ──────────────────────────────────────────

FITNESS_HINTS = re.compile(r"bike|cycl|spin|ftms|kickr|trainer|ic\d|s\d\d|mrk|echelon|keiser|schwinn|bowflex|"
                           r"yesoul|merach|sole|nordic|peloton|stages|wahoo|tacx|elite|zwift|joroto|renpho|ergo|"
                           r"row|tread|domyos|technogym|life ?fitness|sunny", re.I)


def identify(devices, base):
    """Sort a scan. Each device: {name, address, rssi, services: [uuid]}. Returns
    [{device, status: known|standard|unrecognized, profile?, why}], likeliest bike first."""
    profiles = all_profiles(base)
    act = active(base)
    if act and act["id"] not in {p["id"] for p in profiles}:
        profiles.append(act)
    out = []
    for d in devices:
        svcs = []
        for s in d.get("services") or []:
            try:
                svcs.append(full_uuid(s))
            except ValueError:
                pass
        d = dict(d, services=svcs)
        hit = next((p for p in profiles if matches(p, d.get("name"), d.get("address"))), None)
        if hit:
            out.append({"device": d, "status": "known", "profile": hit,
                        "why": f"Matches the saved profile for the {hit['name']}."})
        elif FTMS_SERVICE in svcs:
            out.append({"device": d, "status": "standard", "profile": generic_ftms(d.get("name"), d.get("address")),
                        "why": "Speaks the standard Fitness Machine Service: the hub can talk to it as-is."})
        else:
            sensor = [SERVICE_NAMES[s] for s in svcs if s in (CP_SERVICE, CSC_SERVICE)]
            out.append({"device": d, "status": "unrecognized",
                        "why": ("Sends " + " and ".join(sensor) + " but no resistance control the hub knows."
                                if sensor else "Doesn't advertise a fitness protocol the hub knows.")})
    rank = {"known": 0, "standard": 1, "unrecognized": 2}

    def likely(o):
        d = o["device"]
        return (rank[o["status"]], 0 if FITNESS_HINTS.search(d.get("name") or "") else 1, -(d.get("rssi") or -100))
    return sorted((o for o in out if o["device"].get("name") or o["status"] != "unrecognized"), key=likely)


def choose(base, found):
    """A known or standard bike the athlete picked: make it the active bike."""
    if found.get("status") not in ("known", "standard"):
        raise BadProfile("That bike isn't recognized yet - ask your assistant to set it up.")
    return set_active(base, found["profile"], found["status"])


# ── reading and commanding a custom-protocol bike ───────────────────────────

def parse(p, data):
    """Readings from one data packet, by the profile ({} when the packet isn't a reading)."""
    if p["protocol"] == "ftms":
        return parse_ftms(data)
    d = p["custom"]["data"]
    pre = bytes.fromhex(d["prefix"]) if d["prefix"] else b""
    if pre and not bytes(data).startswith(pre):
        return {}
    out = {}
    for k, f in d["fields"].items():
        o, n = f["offset"], f["size"]
        if o + n > len(data):
            return {}
        v = int.from_bytes(bytes(data[o:o + n]), f.get("endian", "little"), signed=f.get("signed", False))
        out[k] = round(v * f.get("scale", 1), 2)
    return out


def parse_ftms(data):
    """FTMS Indoor Bike Data, the fields the hub uses (same rules as bridge.parse_indoor_bike_data)."""
    data = bytes(data)
    if len(data) < 2:
        return {}
    flags, i, out = int.from_bytes(data[0:2], "little"), 2, {}
    try:
        def take(n, signed=False):
            nonlocal i
            if i + n > len(data):
                raise IndexError
            v = int.from_bytes(data[i:i + n], "little", signed=signed)
            i += n
            return v
        if not flags & 0x0001:
            out["speed_kmh"] = take(2) / 100
        if flags & 0x0002:
            take(2)
        if flags & 0x0004:
            out["cadence_rpm"] = take(2) / 2
        if flags & 0x0008:
            take(2)
        if flags & 0x0010:
            take(3)
        if flags & 0x0020:
            out["resistance"] = take(2, signed=True)
        if flags & 0x0040:
            out["power_w"] = take(2, signed=True)
        if flags & 0x0080:
            take(2)
        if flags & 0x0100:
            take(5)
        if flags & 0x0200:
            out["heart_rate"] = take(1)
    except IndexError:
        return out
    return out


def resistance_command(p, level):
    """The bytes that set `level`, after the safety rules. ValueError when not allowed."""
    r = p["resistance"]
    if r.get("none"):
        raise ValueError(f"The {p['name']} has no resistance control in its profile")
    if not r["min"] <= level <= r["max"]:
        raise ValueError(f"Level {level:g} is outside the {p['name']}'s range {r['min']:g}-{r['max']:g}")
    if level <= 0:
        raise ValueError("Resistance 0 is never sent (it reboots some bikes)")
    if p["protocol"] == "ftms":
        if r["format"] == "ftms-level-x10":
            return bytes([0x04]) + int(round(level * 10)).to_bytes(2, "little", signed=True)
        return bytes([0x04, int(round(level))])
    rc = p["custom"]["control"]["resistance"]
    raw = int(round(level * rc["scale"]))
    lvl = raw.to_bytes(rc["size"], rc["endian"]).hex()
    b = bytes.fromhex(rc["template"].replace("{level}", lvl))
    if rc["checksum"] == "sum8":
        b += bytes([sum(b) & 0xFF])
    elif rc["checksum"] == "xor8":
        x = 0
        for v in b:
            x ^= v
        b += bytes([x])
    return b


def allowed_write(p, char, value, levels=None):
    """Is this write safe to send to this bike? (ok, reason). Every write the hub makes
    during setup and the guided test passes through here; nothing else reaches the bike."""
    value = bytes(value)
    if p["protocol"] == "ftms":
        if full_uuid(char) != FTMS_CONTROL or not value:
            return False, "only the FTMS control point is written"
        op = value[0]
        if op == 0x00 and len(value) == 1:
            return True, "request control"
        if op == 0x01:
            return False, "reset is never sent"
        if op == 0x04:
            r = p["resistance"]
            if r.get("none"):
                return False, "no resistance control in this profile"
            lvl = (int.from_bytes(value[1:3], "little", signed=True) / 10 if len(value) >= 3
                   else value[1] if len(value) == 2 else None)
            if lvl is None or lvl <= 0:
                return False, "resistance 0 is never sent"
            if not r["min"] <= lvl <= r["max"]:
                return False, f"level {lvl:g} is outside {r['min']:g}-{r['max']:g}"
            return True, f"resistance {lvl:g}"
        names = {0x05: "target_power", 0x11: "simulation", 0x07: "start_stop", 0x08: "start_stop"}
        if op in names and names[op] not in p["blocked"]:
            return True, BLOCKABLE[names[op]]
        return False, f"op 0x{op:02x} isn't sent to this bike"
    ctl = p["custom"]["control"]
    if not ctl or full_uuid(char) != ctl["characteristic"]:
        return False, "only the profile's control characteristic is written"
    if value.hex() in ctl["init"]:
        return True, "init command"
    r = p["resistance"]
    if r.get("none"):
        return False, "no resistance control in this profile"
    scale = ctl["resistance"]["scale"]
    lo, hi = math.ceil(r["min"] * scale - 1e-9), math.floor(r["max"] * scale + 1e-9)
    for lvl in (levels if levels is not None else (raw / scale for raw in range(max(1, lo), hi + 1))):
        try:
            if resistance_command(p, lvl) == value:
                return True, f"resistance {lvl:g}"
        except ValueError:
            continue
    return False, "not one of the profile's commands"


def build_ibd(power_w, cadence_rpm, speed_kmh, resistance=None):
    """An FTMS Indoor Bike Data packet from readings, for apps that only speak FTMS
    (Kinomap, Zwift) when the bike itself speaks something else."""
    flags = 0x0004 | 0x0040 | (0x0020 if resistance is not None else 0)
    b = flags.to_bytes(2, "little") + int(max(0, speed_kmh) * 100).to_bytes(2, "little") \
        + int(max(0, cadence_rpm) * 2).to_bytes(2, "little")
    if resistance is not None:
        b += int(resistance).to_bytes(2, "little", signed=True)
    return b + int(max(-32768, min(32767, power_w))).to_bytes(2, "little", signed=True)


# ── the queued request for the assistant ────────────────────────────────────

RULES = [
    "First confirm the bike: say its Bluetooth name from the request (e.g. 'ACME IC7-0042') and ask the athlete "
    "whether that is the bike they mean. If not, stop - they rescan and pick theirs on the welcome page.",
    "Write a bike PROFILE (data). The hub never runs code you write.",
    "Never include the commands listed under 'blocked'; the hub refuses resistance 0, resets, and anything outside "
    "the profile's range regardless.",
    "Start from what the bike advertises and the captured packets: find the bytes that change with pedaling "
    "(cadence, power). Use capture_bike_data to record more while the athlete pedals at a speed you ask for.",
    "Power vs speed: both rise with cadence, so cadence captures alone can't tell them apart. Hold the SAME cadence "
    "and ask the athlete to turn the bike's resistance knob between two captures (most bikes have one): power rises, "
    "speed and cadence don't. Don't call a field power until you've seen this.",
    "If the bike lists the Fitness Machine service, use protocol 'ftms' - it's standard.",
    "For a custom resistance command you can't confirm from the bike's data, say so; a wrong guess is caught by the "
    "guided test, which only nudges resistance in small steps while the athlete pedals.",
    "The athlete decides: tell them what you found and ask before running the guided test.",
]


def _req_file(base):
    return Path(base) / "bike_setup.json"


def load_request(base):
    try:
        return json.loads(_req_file(base).read_text())
    except (OSError, ValueError):
        return None


def save_request(base, req):
    req["updated"] = _now()
    f = _req_file(base)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(req, indent=1))
    tmp.replace(f)
    return req


def open_request(base, device, inspection, consent):
    """The athlete said yes: queue the request for their assistant."""
    if consent is not True:
        raise BadProfile("The athlete's consent is needed before anything goes to an assistant.")
    req = {"id": _uuid.uuid4().hex[:10], "status": "waiting_for_assistant", "created": _now(),
           "consent": {"given": _now(), "shared": "the bike's Bluetooth name, services and data packets - "
                                                   "no training history"},
           "device": {k: device.get(k) for k in ("name", "address", "rssi", "services")},
           "inspection": inspection, "captures": [], "proposals": [], "checks": [], "feel": None,
           "say": "get my bike working"}
    return save_request(base, req)


def brief(req):
    """What get_bike_setup_request hands the assistant."""
    if not req:
        return {"pending": False, "message": "No bike setup request is waiting. If the athlete's bike isn't connecting, "
                "ask them to open the hub's welcome page (Your bike), scan, and say yes to asking you for help."}
    return {"pending": req["status"] not in ("done", "cancelled"), "request": req,
            "what_to_do": [
                "1. Read device, inspection (services, characteristics, readable values) and the captured packets.",
                "2. Name the bike from device.name and ask the athlete to confirm it's theirs; then say in plain "
                "words what you think it speaks.",
                "3. Capture while they pedal as you ask: 60 rpm, then 90 rpm (finds cadence); then the same cadence "
                "with the resistance knob turned up (finds power - speed won't move).",
                "4. Call propose_bike_profile with your profile; it is checked and decoded against the captures.",
                "5. Ask 'pedaling steadily and ready?' and wait for their yes; then call run_bike_check with "
                "athlete_ready true. It nudges resistance in small steps.",
                "6. Ask the athlete whether it got harder in the middle, and record it with record_bike_feel.",
                "7. If the check passed and they felt it, call activate_bike_profile. Offer to share it.",
            ],
            "rules": RULES, "blockable": BLOCKABLE,
            "profile_format": PROFILE_FORMAT}


PROFILE_FORMAT = {
    "id": "lower-case-with-dashes", "name": "Brand Model", "match": {"name_prefix": ["START-OF-BLE-NAME"]},
    "protocol": "ftms | custom", "resistance": {"min": 1, "max": 32, "format": "ftms-level-x10 | ftms-level-u8 (ftms only)"},
    "or_resistance": {"none": True},
    "blocked": sorted(BLOCKABLE),
    "custom (protocol custom only)": {
        "data": {"characteristic": "uuid that notifies readings", "prefix": "hex bytes every reading packet starts with (optional)",
                 "fields": {k: {"offset": 0, "size": 2, "signed": False, "endian": "little", "scale": 1} for k in ("power_w", "cadence_rpm")}
                 | {"optional": list(FIELDS[2:])}},
        "control": {"characteristic": "uuid commands are written to", "init": ["hex sent once after connecting"],
                    "resistance": {"template": "hex with {level} once, e.g. f0b101{level}", "size": 1, "endian": "little",
                                   "scale": 1, "checksum": "none | sum8 | xor8 (one byte appended over all bytes)"},
                    "response": True}},
}


def propose(base, profile, note=""):
    """The assistant's profile: validated, decoded against every captured packet, kept on the request."""
    req = load_request(base)
    if not req or req["status"] in ("done", "cancelled"):
        raise BadProfile("No bike setup request is open.")
    p = validate(dict(profile, source="assistant"))
    decoded = []
    for cap in [{"label": "inspection", "packets": (req.get("inspection") or {}).get("packets", [])}] + req["captures"]:
        rows = [parse(p, bytes.fromhex(pk["hex"])) for pk in cap["packets"]
                if pk.get("char") == (p["custom"]["data"]["characteristic"] if p["protocol"] == "custom" else IBD)]
        rows = [r for r in rows if r]
        if rows:
            decoded.append({"capture": cap["label"], "packets": len(rows),
                            "avg": {k: round(sum(r.get(k, 0) for r in rows) / len(rows), 1) for k in rows[0]},
                            "range": {k: [min(r.get(k, 0) for r in rows), max(r.get(k, 0) for r in rows)] for k in rows[0]}})
    warn = []
    if not decoded:
        warn.append("None of the captured packets decode with this profile - check the data characteristic and prefix.")
    for d in decoded:
        cad = d["range"].get("cadence_rpm", [0, 0])
        if cad[1] > 200 or cad[0] < 0:
            warn.append(f"{d['capture']}: cadence {cad} rpm isn't believable - check its offset/scale.")
        pw = d["range"].get("power_w", [0, 0])
        if pw[1] > 2500 or pw[0] < -50:
            warn.append(f"{d['capture']}: power {pw} W isn't believable - check its offset/scale/signed.")
    req["proposals"].append({"at": _now(), "profile": p, "note": note[:500], "decoded": decoded, "warnings": warn})
    req["status"] = "profile_proposed"
    save_request(base, req)
    return {"profile": p, "decoded": decoded, "warnings": warn,
            "next": "Ask the athlete to pedal steadily, then run_bike_check." if not warn else
                    "Fix the warnings (or capture more data) before running the check."}


def latest_profile(req):
    return req["proposals"][-1]["profile"] if req and req.get("proposals") else None


def record_feel(base, felt, note=""):
    req = load_request(base)
    if not req:
        raise BadProfile("No bike setup request is open.")
    if felt not in ("harder", "no_change", "unsure"):
        raise BadProfile("felt: harder, no_change or unsure")
    req["feel"] = {"felt": felt, "note": note[:300], "at": _now()}
    return save_request(base, req)


def activate(base, share=False):
    """Make the checked profile the bike. Requires a passed check, and the athlete's
    'harder' when resistance was tested."""
    req = load_request(base)
    p = latest_profile(req)
    if not p:
        raise BadProfile("No profile has been proposed yet.")
    check = req["checks"][-1] if req.get("checks") else None
    if not check or check.get("profile_id") != p["id"] or not check.get("passed"):
        raise BadProfile("Run the guided check with this profile first - it must pass before the bike is switched over.")
    if check.get("resistance_tested") and (req.get("feel") or {}).get("felt") != "harder":
        raise BadProfile("The athlete hasn't confirmed the resistance got harder. Ask them, and record it with "
                         "record_bike_feel - or set resistance to {'none': true} to use the bike without resistance control.")
    p = dict(p, tested={"at": check["at"], "readings": check.get("readings"), "felt": (req.get("feel") or {}).get("felt")})
    p = save_profile(base, p)
    set_active(base, p, "assistant")
    req["status"] = "done"
    req["activated"] = {"profile_id": p["id"], "at": _now(), "share": bool(share)}
    save_request(base, req)
    out = {"activated": p, "message": f"The {p['name']} is now the hub's bike. The bridge connects with it on its next "
                                      f"search (within a few seconds)."}
    if share:
        out["share"] = share_link(p)
    return out


def share_link(p):
    """A pre-filled 'Does it work with my bike?' issue, so the next owner needs no assistant."""
    from urllib.parse import quote
    body = ("A bike profile made with the hub's guided setup, checked on the bike.\n\n```json\n"
            + json.dumps({k: v for k, v in p.items() if k != "tested"} | {"tested": p.get("tested")}, indent=1) + "\n```\n")
    return ("https://github.com/JHarp199345/S-Bike-Training-Hub/issues/new?labels=bike-profile&title="
            + quote(f"Bike profile: {p['name']}") + "&body=" + quote(body))


def cancel(base):
    req = load_request(base)
    if req:
        req["status"] = "cancelled"
        save_request(base, req)
    return req


def setup_status(base):
    """For the welcome page: the active bike and any open request, in a sentence."""
    a, req = active(base), load_request(base)
    if req and req["status"] not in ("done", "cancelled"):
        msg = {"waiting_for_assistant": "Waiting for your assistant. Open it and type: get my bike working",
               "profile_proposed": "Your assistant has proposed how to talk to the bike.",
               "checking": "Guided check running - keep pedaling steadily.",
               "checked": "Guided check finished."}.get(req["status"], req["status"])
        last = (req.get("checks") or [{}])[-1]
        if req["status"] == "checked":
            msg = ("Guided check passed. Your assistant will ask how it felt." if last.get("passed") and last.get("resistance_tested")
                   else "Guided check passed." if last.get("passed")
                   else "Guided check didn't pass - your assistant will explain and suggest what to try next.")
        return {"active": a, "request": {k: req.get(k) for k in ("id", "status", "device", "checks", "feel", "say")},
                "message": msg}
    return {"active": a, "request": None,
            "message": f"Your bike: {a['name']}." if a else "No bike set up yet (or riding without one)."}
