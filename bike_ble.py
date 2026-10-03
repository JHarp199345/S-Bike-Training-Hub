"""bike_ble.py - the radio side of bike setup: scan, inspect, capture, and connections.

Two transports with the same shape:
  Ble        the real radio, through bleak (imported only when used, so no-bike
             installs never need it).
  Sim        simulated bikes for tests, CI and demos. Set S_BIKE_SIM=1 (all of
             them) or a comma list: s29, kickr, acme, speaker, hrm.

Inspection and capture only LISTEN: they connect, read what's readable and
subscribe to notifications. Nothing is written to a bike here - writes happen
only in bike_check.py, through bikes.allowed_write.
"""
import asyncio
import os
import random
import time

import bikes

MAX_PACKETS = 80          # per characteristic, per capture


class NoRadio(RuntimeError):
    pass


def transport():
    sim = os.environ.get("S_BIKE_SIM", "").strip()
    if sim:
        return Sim(sim)
    return Ble()


def time_scale():
    """Tests speed the guided check up (S_BIKE_SIM_FAST=1): every wait x 0.02."""
    return 0.02 if os.environ.get("S_BIKE_SIM_FAST") else 1.0


# ── the real radio ───────────────────────────────────────────────────────────

class Ble:
    def _bleak(self):
        try:
            import bleak
            return bleak
        except ImportError:
            raise NoRadio("Bluetooth support isn't installed (the 'bleak' package). Run the setup again "
                          "without --no-bike to add it.")

    async def scan(self, timeout=6.0):
        bleak = self._bleak()
        try:
            found = await bleak.BleakScanner.discover(timeout=timeout, return_adv=True)
        except Exception as e:
            raise NoRadio(f"Couldn't scan: {e}. Is Bluetooth on, and does this app have permission to use it?")
        out = []
        for addr, (dev, adv) in found.items():
            out.append({"name": adv.local_name or dev.name, "address": addr, "rssi": adv.rssi,
                        "services": [str(s).lower() for s in adv.service_uuids or []]})
        return out

    async def connect(self, address):
        bleak = self._bleak()
        c = bleak.BleakClient(address)
        try:
            await c.connect(timeout=15)
        except Exception as e:
            raise NoRadio(f"Couldn't connect to the bike: {e}. Wake it by pedaling, and make sure no phone or "
                          "watch is connected to it.")
        return BleConn(c)


class BleConn:
    def __init__(self, c):
        self.c = c

    def services(self):
        return [{"uuid": str(s.uuid).lower(), "description": s.description,
                 "characteristics": [{"uuid": str(ch.uuid).lower(), "properties": list(ch.properties)}
                                     for ch in s.characteristics]} for s in self.c.services]

    @property
    def is_connected(self):
        return self.c.is_connected

    async def read(self, char):
        return bytes(await self.c.read_gatt_char(char))

    async def start_notify(self, char, cb):
        await self.c.start_notify(char, lambda _, d: cb(char, bytes(d)))

    async def write(self, char, value, response=True):
        await self.c.write_gatt_char(char, bytes(value), response=response)

    async def disconnect(self):
        try:
            await self.c.disconnect()
        except Exception:
            pass


# ── simulated bikes ──────────────────────────────────────────────────────────

ACME_SVC = "a0f1e000-5a1d-4c3b-9f00-6b1e5ac0b1e0"
ACME_DATA = "a0f1e001-5a1d-4c3b-9f00-6b1e5ac0b1e0"
ACME_CTRL = "a0f1e002-5a1d-4c3b-9f00-6b1e5ac0b1e0"
U = bikes.full_uuid

SIM_BIKES = {
    # Merach S29: FTMS, 16 levels; reboots (drops the connection) on reset or resistance 0
    "s29": {"name": "MRK-S29-A1B2", "address": "SIM:S29", "rssi": -48, "services": [U("1826"), U("180a")], "kind": "ftms",
            "range": (1, 16), "reboots_on": ("reset", "zero")},
    # A standard FTMS bike nobody has a profile for: works as-is
    "kickr": {"name": "KICKR BIKE 7F3A", "address": "SIM:KICKR", "rssi": -55, "services": [U("1826"), U("1818")],
              "kind": "ftms", "range": (1, 24), "reboots_on": ()},
    # A bike with its own protocol: readings on ACME_DATA, resistance 'f0b101{level}{sum8}' on ACME_CTRL,
    # levels 1-32. Anything else written to it makes it reboot - what the safety rules are for.
    "acme": {"name": "ACME IC7-0042", "address": "SIM:ACME", "rssi": -51, "services": [ACME_SVC], "kind": "custom",
             "range": (1, 32), "reboots_on": ("anything_else",)},
    "speaker": {"name": "JBL Flip 5", "address": "SIM:JBL", "rssi": -70, "services": [U("110b")], "kind": "none"},
    "hrm": {"name": "COROS HRM 51A", "address": "SIM:HRM", "rssi": -62, "services": [U("180d")], "kind": "none"},
}


class Sim:
    def __init__(self, which):
        keys = list(SIM_BIKES) if which in ("1", "all", "yes") else [k.strip() for k in which.split(",") if k.strip()]
        self.bikes = {SIM_BIKES[k]["address"]: SimBike(k, SIM_BIKES[k]) for k in keys if k in SIM_BIKES}

    async def scan(self, timeout=6.0):
        await asyncio.sleep(min(0.05, timeout))
        return [{k: b.spec[k] for k in ("name", "address", "rssi", "services")} for b in self.bikes.values()]

    async def connect(self, address):
        b = self.bikes.get(address)
        if not b or b.spec["kind"] == "none":
            raise NoRadio("Couldn't connect to that device (it isn't a bike).")
        b.connected = True
        return b


class SimBike:
    """A pedaling rider on a simulated bike: cadence ~80 rpm, power rises with the level."""

    def __init__(self, key, spec):
        self.key, self.spec = key, spec
        self.level = spec.get("range", (1, 1))[0] + 2
        self.connected = False
        self.reboots = 0
        self.writes = []
        self._subs = {}
        self._task = None
        self.cadence = float(os.environ.get("S_BIKE_SIM_CADENCE", "80"))
        self.rng = random.Random(7)

    # what the bike offers
    def services(self):
        k = self.spec["kind"]
        if k == "ftms":
            chars = [(U("2ad2"), ["notify"]), (U("2acc"), ["read"]), (U("2ad6"), ["read"]),
                     (U("2ad9"), ["write", "indicate"]), (U("2ada"), ["notify"])]
            return [{"uuid": U("1826"), "description": "Fitness Machine",
                     "characteristics": [{"uuid": u, "properties": p} for u, p in chars]},
                    {"uuid": U("180a"), "description": "Device Information",
                     "characteristics": [{"uuid": U("2a29"), "properties": ["read"]}]}]
        return [{"uuid": ACME_SVC, "description": "Unknown",
                 "characteristics": [{"uuid": ACME_DATA, "properties": ["notify"]},
                                     {"uuid": ACME_CTRL, "properties": ["write"]}]},
                {"uuid": U("180a"), "description": "Device Information",
                 "characteristics": [{"uuid": U("2a29"), "properties": ["read"]}]}]

    @property
    def is_connected(self):
        return self.connected

    def power(self):
        lo, hi = self.spec["range"]
        frac = (self.level - lo) / max(1, hi - lo)
        return max(0, (60 + 260 * frac) * (self.cadence / 80) ** 1.6 + self.rng.uniform(-4, 4))

    async def read(self, char):
        self._alive()
        lo, hi = self.spec.get("range", (1, 16))
        if char == U("2ad6"):
            return b"".join(int(v * 10).to_bytes(2, "little", signed=True) for v in (lo, hi, 1))
        if char == U("2acc"):
            return (0x4006).to_bytes(4, "little") + (1 << 2 | 1 << 13).to_bytes(4, "little")
        if char == U("2a29"):
            return {"s29": b"MERACH", "kickr": b"Wahoo Fitness", "acme": b"ACME Fitness"}.get(self.key, b"")
        raise NoRadio("not readable")

    async def start_notify(self, char, cb):
        self._alive()
        self._subs[char] = cb
        if not self._task:
            self._task = asyncio.ensure_future(self._run())

    def _athlete(self):
        """Tests and demos play the athlete: S_BIKE_SIM_CONTROL names a JSON file like {"cadence": 60}."""
        f = os.environ.get("S_BIKE_SIM_CONTROL")
        if f:
            try:
                import json
                with open(f) as fh:
                    ctl = json.load(fh)
                self.cadence = float(ctl.get("cadence", self.cadence))
                if ctl.get("knob") is not None and not self.writes:     # the athlete turns the bike's own knob
                    lo, hi = self.spec["range"]
                    self.level = int(min(hi, max(lo, ctl["knob"])))
            except (OSError, ValueError, AttributeError):
                pass

    async def _run(self):
        n = 0
        while self.connected:
            n += 1
            if n % 8 == 1:
                self._athlete()
            cad = max(0.0, self.cadence + self.rng.uniform(-2, 2)) if self.cadence else 0.0
            pw = self.power()
            if self.spec["kind"] == "ftms" and U("2ad2") in self._subs:
                self._subs[U("2ad2")](U("2ad2"), bikes.build_ibd(pw, cad, cad * 0.33, int(self.level * 10)))
            if self.spec["kind"] == "custom" and ACME_DATA in self._subs:
                if n % 4 == 0:     # a status packet now and then, which isn't a reading
                    self._subs[ACME_DATA](ACME_DATA, bytes.fromhex("f0a0") + bytes([n & 0xFF, 0, 0, 0, 0, 0]))
                else:
                    pkt = (bytes.fromhex("f0b2") + bytes([int(cad)]) + int(pw).to_bytes(2, "little")
                           + bytes([self.level]) + int(cad * 3.3).to_bytes(2, "little"))
                    self._subs[ACME_DATA](ACME_DATA, pkt)
            await asyncio.sleep(max(0.004, 0.25 * time_scale()))

    async def write(self, char, value, response=True):
        self._alive()
        value = bytes(value)
        self.writes.append((char, value.hex()))
        lo, hi = self.spec["range"]
        if self.spec["kind"] == "ftms" and char == U("2ad9"):
            op = value[0]
            if op == 0x01 and "reset" in self.spec["reboots_on"]:
                return self._reboot()
            if op == 0x04:
                lvl = int.from_bytes(value[1:3], "little", signed=True) / 10 if len(value) >= 3 else value[1]
                if lvl <= 0 and "zero" in self.spec["reboots_on"]:
                    return self._reboot()
                self.level = int(min(hi, max(lo, lvl)))
            if U("2ad9") in self._subs:
                self._subs[U("2ad9")](U("2ad9"), bytes([0x80, op, 0x01]))
            return
        if self.spec["kind"] == "custom" and char == ACME_CTRL and len(value) == 5 and value[:3] == bytes.fromhex("f0b101") \
                and value[4] == sum(value[:4]) & 0xFF and lo <= value[3] <= hi:
            self.level = value[3]
            return
        return self._reboot()          # an unexpected command

    def _reboot(self):
        self.reboots += 1
        self.connected = False
        self._subs.clear()
        self._task = None

    def _alive(self):
        if not self.connected:
            raise NoRadio("The bike disconnected.")

    async def disconnect(self):
        self.connected = False
        self._subs.clear()
        self._task = None


# ── inspection and capture (listen only) ─────────────────────────────────────

async def inspect(t, device, seconds=8.0):
    """Connect, list services, read the readable, and record notifications."""
    conn = await t.connect(device["address"])
    try:
        svcs = conn.services()
        readable = {}
        for s in svcs:
            for ch in s["characteristics"]:
                if "read" in ch["properties"] and len(readable) < 12:
                    try:
                        v = await conn.read(ch["uuid"])
                        readable[ch["uuid"]] = {"hex": v.hex(), "text": v.decode("ascii", "ignore") if v.isascii() else ""}
                    except Exception:
                        pass
        packets = await _listen(conn, svcs, seconds)
        return {"services": svcs, "readable": readable, "packets": packets,
                "listened_s": seconds, "note": "Recorded while the athlete pedaled (if they did)."}
    finally:
        await conn.disconnect()


async def capture(t, device, seconds, label):
    conn = await t.connect(device["address"])
    try:
        return {"label": label[:80], "seconds": seconds, "packets": await _listen(conn, conn.services(), seconds)}
    finally:
        await conn.disconnect()


async def _listen(conn, svcs, seconds):
    got, count = [], {}
    t0 = time.monotonic()

    def cb(char, data):
        if count.get(char, 0) < MAX_PACKETS:
            count[char] = count.get(char, 0) + 1
            got.append({"char": char, "t": round(time.monotonic() - t0, 2), "hex": data.hex()})
    subs = [ch["uuid"] for s in svcs for ch in s["characteristics"]
            if {"notify", "indicate"} & set(ch["properties"])][:6]
    for u in subs:
        try:
            await conn.start_notify(u, cb)
        except Exception:
            pass
    await asyncio.sleep(seconds * time_scale())
    return got

