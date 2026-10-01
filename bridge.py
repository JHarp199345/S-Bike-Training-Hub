#!/usr/bin/env python3
"""bridge.py - share one Merach S29 with Kinomap and a COROS watch at once.

The S29 accepts one Bluetooth connection. This program is that connection, and
it re-advertises the bike as a new device, "SBike Hub", that several apps can
join at the same time:

    Merach S29 --(FTMS)--> Mac --+--> FTMS              Kinomap (phone)
                                 +--> Cycling Power     COROS watch
                                 +--> Speed & Cadence   COROS watch

Kinomap's resistance commands are passed through to the bike, so its hills
still work. Heart rate is not involved: the watch measures its own and can
broadcast it to Kinomap directly.

Every ride is also saved on the Mac as a CSV in ./rides. Nothing here uses the
internet.

Run it from the macOS Terminal app (Bluetooth permission belongs to Terminal):

    .venv/bin/python bridge.py
    .venv/bin/python bridge.py --wheel 2096    # wheel size the watch assumes, mm
"""
import argparse
import asyncio
import collections
import csv
import json
import webbrowser
import datetime as dt
import logging
import math
import os
import signal
import threading
import time
from pathlib import Path

from bleak import BleakClient, BleakScanner
import shortuuid  # noqa: F401  (must load before bless servers are built)
from autoshift import AutoShift
from erg import Erg, load_workouts
from ftptest import RampTest
from ghost import Ghost
import bests
import cp as cp_mod
import focus
import live
import session
import routes
import rider
from bless import BlessServer, GATTAttributePermissions as Perm, GATTCharacteristicProperties as Prop

log = logging.getLogger("bridge")


def u(short):
    return f"0000{short:04x}-0000-1000-8000-00805f9b34fb"


FTMS, IBD, FEATURE, CONTROL, STATUS = u(0x1826), u(0x2AD2), u(0x2ACC), u(0x2AD9), u(0x2ADA)
RES_RANGE, PWR_RANGE, TRAINING = u(0x2AD6), u(0x2AD8), u(0x2AD3)
CPS, CP_MEAS, CP_FEAT, SENSOR_LOC = u(0x1818), u(0x2A63), u(0x2A65), u(0x2A5D)
CSC, CSC_MEAS, CSC_FEAT = u(0x1816), u(0x2A5B), u(0x2A5C)

# Readings beyond these are the bike's stop-pedalling glitches (seen in the scan:
# 186 rpm at 0 W, then 41 km/h at 0 rpm). A human on this bike never gets there.
MAX_CADENCE, MAX_SPEED, MAX_POWER, MAX_SPEED_JUMP = 150, 60.0, 1500, 20.0


class Ride:
    """Current bike state, cleaned, plus the running totals the watch needs."""

    def __init__(self, wheel_mm):
        self.power = self.cadence = self.speed = 0.0
        self.distance = self.resistance = 0
        self.crank_revs = 0.0
        self.wheel_revs = 0.0
        self.last_tick = time.monotonic()
        self.crank_event = self.wheel_event = 0  # seconds * 1024, rolls over
        self.wheel_m = wheel_mm / 1000
        self.vspeed = 0.0       # virtual road speed, m/s
        self.vdistance = 0.0    # virtual distance, m
        self.grade = 0.0        # current hill, % (from Kinomap)
        self.mass = 126.6       # rider + bike, kg (set from arguments)
        self.use_virtual = True

    def update(self, fields):
        cad = fields.get("cadence_rpm")
        spd = fields.get("speed_kmh")
        pwr = fields.get("power_w")
        if cad is not None and cad > MAX_CADENCE:
            return False
        if spd is not None and spd > MAX_SPEED:
            return False
        if pwr is not None and not 0 <= pwr <= MAX_POWER:
            return False
        if pwr and cad == 0:
            return False  # no watts without the pedals turning
        if spd is not None and abs(spd - self.speed) > MAX_SPEED_JUMP:
            return False  # a flywheel can't gain 20 km/h in half a second
        if cad is not None:
            self.cadence = cad
        if spd is not None:
            self.speed = spd
        if pwr is not None:
            self.power = pwr
        self.distance = fields.get("distance_m", self.distance)
        self.resistance = fields.get("resistance", self.resistance)
        return True

    def tick(self):
        """Advance crank and wheel counters. A watch derives cadence and speed
        from how fast these counters climb, not from a number we send."""
        now = time.monotonic()
        dt_s, self.last_tick = now - self.last_tick, now
        # Virtual speed eases toward what the current watts hold on this hill,
        # over about 3 s, so a surge or a crest doesn't teleport the rider.
        target = virtual_speed(self.power if self.cadence > 0 else 0, self.grade, self.mass)
        self.vspeed += (target - self.vspeed) * min(1.0, dt_s / 3.0)
        if self.vspeed < 0.05 and target == 0:
            self.vspeed = 0.0
        self.vdistance += self.vspeed * dt_s
        before_c, before_w = int(self.crank_revs), int(self.wheel_revs)
        self.crank_revs += self.cadence / 60 * dt_s
        self.wheel_revs += (self.road_kmh() / 3.6) / self.wheel_m * dt_s
        stamp = int(now * 1024) & 0xFFFF
        if int(self.crank_revs) != before_c:
            self.crank_event = stamp
        if int(self.wheel_revs) != before_w:
            self.wheel_event = stamp

    def road_kmh(self):
        """Speed the watch and Kinomap are told: virtual unless turned off."""
        return self.vspeed * 3.6 if self.use_virtual else self.speed

    def road_m(self):
        return self.vdistance if self.use_virtual else self.distance

    def cycling_power(self):
        # flags: crank revolution data present
        return (0x0020).to_bytes(2, "little") + int(self.power).to_bytes(2, "little", signed=True) \
            + (int(self.crank_revs) & 0xFFFF).to_bytes(2, "little") + self.crank_event.to_bytes(2, "little")

    def speed_cadence(self):
        # flags: wheel and crank revolution data present
        return bytes([0x03]) + (int(self.wheel_revs) & 0xFFFFFFFF).to_bytes(4, "little") \
            + self.wheel_event.to_bytes(2, "little") \
            + (int(self.crank_revs) & 0xFFFF).to_bytes(2, "little") + self.crank_event.to_bytes(2, "little")


def virtual_speed(power_w, grade_pct, mass_kg, crr=0.005, cda=0.40, rho=1.2):
    """Road speed in m/s that power_w holds on grade_pct for a rider+bike of
    mass_kg: gravity and rolling resistance plus air drag, solved for speed.
    CdA 0.40 is an upright rider on a road bike. On a descent the answer never
    drops below coasting speed, where gravity alone balances drag."""
    theta = math.atan(grade_pct / 100)
    a = mass_kg * 9.81 * (math.sin(theta) + crr * math.cos(theta))  # N, gravity + rolling
    k = 0.5 * rho * cda                                            # drag = k * v^2
    lo = math.sqrt(-a / k) if a < 0 else 0.0                       # coasting speed
    hi = 25.0                                                      # 90 km/h cap
    if power_w <= 0 or hi * (a + k * hi * hi) <= power_w:
        return lo if power_w <= 0 else hi
    for _ in range(60):
        mid = (lo + hi) / 2
        if mid * (a + k * mid * mid) < power_w:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def rewrite_ibd(data: bytes, speed_kmh: float, distance_m: float) -> bytes:
    """Put the bridge's virtual speed and distance into an Indoor Bike Data
    packet, leaving every other field as the bike sent it."""
    b = bytearray(data)
    if len(b) < 2:
        return bytes(data)
    flags, i = int.from_bytes(b[0:2], "little"), 2
    try:
        if not flags & 0x0001 and i + 2 <= len(b):
            b[i:i + 2] = int(max(0, min(65535, speed_kmh * 100))).to_bytes(2, "little")
            i += 2
        i += 2 if flags & 0x0002 else 0
        i += 2 if flags & 0x0004 else 0
        i += 2 if flags & 0x0008 else 0
        if flags & 0x0010 and i + 3 <= len(b):
            b[i:i + 3] = int(max(0, distance_m)).to_bytes(3, "little")
    except (IndexError, OverflowError):
        return bytes(data)
    return bytes(b)


def parse_indoor_bike_data(data: bytes) -> dict:
    """FTMS Indoor Bike Data (0x2AD2). The S29 alternates two packets: one with
    cadence/distance/resistance/power, one with speed/heart rate."""
    flags = int.from_bytes(data[0:2], "little")
    i, out = 2, {}

    def take(n, signed=False):
        nonlocal i
        v = int.from_bytes(data[i:i + n], "little", signed=signed)
        i += n
        return v

    try:
        if not flags & 0x0001:
            out["speed_kmh"] = take(2) / 100
        if flags & 0x0002:
            take(2)
        if flags & 0x0004:
            out["cadence_rpm"] = take(2) / 2
        if flags & 0x0008:
            take(2)
        if flags & 0x0010:
            out["distance_m"] = take(3)
        if flags & 0x0020:
            out["resistance"] = take(2, signed=True)
        if flags & 0x0040:
            out["power_w"] = take(2, signed=True)
    except IndexError:
        return {}
    return out


OPCODES = {0x00: "control request", 0x01: "reset", 0x04: "target resistance", 0x05: "target power",
           0x07: "start", 0x08: "stop/pause", 0x11: "hill simulation"}


def describe_command(v: bytes) -> str:
    op = v[0] if v else -1
    try:
        if op == 0x04:
            return f"set resistance {v[1] / 10:g}"
        if op == 0x05:
            return f"set power {int.from_bytes(v[1:3], 'little', signed=True)} W"
        if op == 0x11:
            grade = int.from_bytes(v[3:5], "little", signed=True) / 100
            return f"hill {grade:+.1f}%"
    except IndexError:
        pass
    return f"{OPCODES.get(op, 'command')} ({v.hex()})"


STATE = Path(__file__).resolve().parent / "state.json"
RESUME_WITHIN = 15 * 60     # seconds: a crash older than this starts a fresh ride
RESUME = STATE.with_name("resume.json")   # the workout in progress: survives End, a reload, a restart (until it finishes)
RESUME_AFTER = 30           # seconds of pedalling before a workout is worth resuming (or replaces the saved one)


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def read_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def write_state(data):
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, STATE)            # atomic: a crash mid-write never leaves half a file


def window_closed(bridge):
    """The Terminal window went away: keep riding, write to the log instead."""
    try:
        out = os.open(os.devnull, os.O_WRONLY)
        os.dup2(out, 1)
        os.dup2(out, 2)
        os.close(out)
    except OSError:
        pass
    for h in logging.getLogger().handlers[:]:
        if type(h) is logging.StreamHandler:            # the window's handler (not the log files)
            logging.getLogger().removeHandler(h)
    bridge.event("Terminal window closed - bridge keeps running (stop it from the panel or the menu icon)")


def resumable_state():
    """The last run's state if it ended in a crash recently enough to resume:
    it says it was running, its process is gone, and its ride file exists."""
    st = read_state()
    if (st.get("running") and not pid_alive(st.get("pid")) and st.get("ride")
            and Path(st["ride"]).exists() and time.time() - st.get("saved_at", 0) < RESUME_WITHIN):
        return st
    return None


class Bridge:
    def __init__(self, args):
        self.args = args
        self.ride = Ride(args.wheel)
        self.bike: BleakClient | None = None
        self.server: BlessServer | None = None
        self.loop = asyncio.get_running_loop()
        self.static = {}  # values read once from the bike and served to Kinomap
        self.events = collections.deque(maxlen=12)  # recent happenings, for the control panel
        self.live = live.Live()                     # last 10 min second by second, and calories
        self.started = time.monotonic()
        self.seen = {"power": 0, "cadence": 0, "kinomap": 0}
        self.stop = asyncio.Event()
        self.have_control = False
        self.send_failures = 0
        self.send_retries = 0
        self.watch_ibd_at = 0.0
        self.descent_gears = 0       # harder gears gained while descending
        self.descent_left_at = None  # when the road stopped going down
        self.gear = 0                # levels added to (or taken from) every hill, by auto-shift or hand
        self.hill_shift = 0.0        # gears changed for the current grade itself, at the bottom of the hill
        self.hill_level = None       # level the current hill calls for, before gears
        self.outbox_lock = threading.Lock()
        self.latest = {}             # (char, kind) -> (svc, value): sensor data, newest wins
        self.ordered = collections.deque()  # control replies: every one delivered, in order
        if args.weight is None:                          # the rider's own weight, set once in profile.json
            args.weight = float(rider.load(Path("rides").resolve().parent / "profile.json").get("weight_kg", 80.0))
        self.ride.mass = args.weight + args.bike_mass
        self.ride.use_virtual = not args.bike_speed
        self.profile = rider.load(Path("rides").resolve().parent / "profile.json")
        self.auto = AutoShift(self.shift, low=args.cadence_low, high=args.cadence_high, up_hold=args.up_hold,
                              power_cap=args.upshift_cap_w or 0.9 * self.profile["ftp"])
        self.test = None             # an FTP ramp test in progress
        self.moving_since = None     # wall-clock start of this ride's movement, for the ghost
        self.ghost_name = None
        self.route_ride = None       # a planned route being ridden (replaces Kinomap's grades)
        self.route_fed = None        # last grade fed from the route (0.5% steps)
        self.route_started = None    # wall-clock time the route began, for its ghost
        self.grace_grade = None      # grade at the last auto-shift grace period
        self.auto.enabled = not args.no_auto
        self.focus = None            # today's focus: a cadence range and a watt range (focus.py), from the coach plan
        self.focus_track = focus.Tracker()
        self.focus_checked = 0.0
        self.wbal = None             # W' balance, live (cp.py)
        self.wbal_ftp = None
        self.session = None          # today's session on this route: climb goals, efforts, part-route focus (session.py)
        self.climb_rec = None        # every climb on the route, recorded
        self.session_out = None      # what the session asked for this second (cue, pace)
        self.session_gear = None     # the gear from before an effort shifted, to hand back
        self._applied = None         # the (rpm, watts) ranges last given to auto-shift by the session
        self.erg = Erg(ftp=self.profile["ftp"])
        self.resume_file = RESUME
        try:
            self.resume = json.loads(RESUME.read_text())
        except (OSError, ValueError):
            self.resume = None       # {"name", "steps": [[seconds, watts]], "active", "date", "saved"}
        self._had_workout = False
        self.workouts = load_workouts(Path(__file__).resolve().parent / "workouts")
        self.bike_sims = True        # assume hill simulation works until the bike says otherwise
        self.res_range = (1.0, 32.0)  # replaced by the bike's own range on connect
        self.level_sent = None       # level last sent to the bike
        self.target_level = None     # level the bike is heading to
        self.target_since = 0.0
        self.last_step = 0.0
        self.level_format = 3        # bytes in a resistance command: 3 (level x10, 16-bit) or 2 (8-bit)
        Path("rides").mkdir(exist_ok=True)
        self.resumed = None if getattr(args, "no_bike", False) else resumable_state()
        if getattr(args, "no_bike", False):
            # no bike, no ride: nothing is recorded (the path only says where the rides and the coach's files live)
            self.csv_path = Path("rides").resolve() / "ride_no_bike.csv"
            self.csv = csv.writer(open(os.devnull, "w"))
            self.events_csv = csv.writer(open(os.devnull, "w"))
        elif self.resumed:
            # Picking up a ride that a crash interrupted: same files, appended.
            self.csv_path = Path(self.resumed["ride"])
            self.live.load_ride(self.csv_path)       # calories so far and the graph's last ten minutes
            self.csv = csv.writer(open(self.csv_path, "a", newline="", buffering=1))
            self.events_csv = csv.writer(open(self.csv_path.with_name(self.csv_path.stem + "_events.csv"), "a",
                                              newline="", buffering=1))
        else:
            stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
            self.csv_path = Path("rides").resolve() / f"ride_{stamp}.csv"   # absolute: stays put if the cwd changes
            n = 2
            while self.csv_path.exists():
                # Two starts in the same minute used to share a name, and the
                # second silently overwrote the first ride's file.
                self.csv_path = Path("rides").resolve() / f"ride_{stamp}_{n}.csv"
                n += 1
            self.csv = csv.writer(open(self.csv_path, "w", newline="", buffering=1))
            self.csv.writerow(["time", "power_w", "cadence_rpm", "bike_speed_kmh", "bike_distance_m", "resistance",
                               "virtual_speed_kmh", "virtual_distance_m", "grade_pct", "gear", "hill_shift", "erg_w"])
            self.events_csv = csv.writer(open(self.csv_path.with_name(self.csv_path.stem + "_events.csv"), "w",
                                              newline="", buffering=1))
            self.events_csv.writerow(["time", "event"])
        self.ghost = Ghost(Path(self.csv_path).parent, exclude=self.csv_path)
        # Personal bests: past rides read once (quickly, only new ones), then tracked live.
        self.bests_data = bests.load(bests.file_for(Path(self.csv_path).parent))
        for secs, w, ride in bests.scan_rides(self.bests_data, Path(self.csv_path).parent, skip=self.csv_path):
            log.info(f"Personal best from past rides: {bests.label(secs)} {w} W ({ride})")
        bests.save(self.bests_data)
        self.bests = bests.Tracker(self.bests_data, Path(self.csv_path).stem, self.on_record)
        if self.resumed:                     # efforts before the interruption still count, silently
            self.bests.quiet = True
            for sec_w in bests.ride_seconds(self.csv_path):
                if sec_w is None:
                    self.bests._break()
                else:
                    self.bests.add(sec_w[0], sec_w[1])
            self.bests.quiet = False
        self.pb_flash = None                 # the latest record callout, for the panel and the Pixel
        self.ms_before, self.ms_seen = None, set()   # lifetime totals before this ride, milestones announced
        self._ftp_from_bests()

    def status(self):
        r, secs = self.ride, int(time.monotonic() - self.started)
        return {"name": self.args.broadcast, "elapsed": f"{secs // 60}:{secs % 60:02d}",
                "no_bike": bool(getattr(self.args, "no_bike", False)),
                "bike": bool(self.bike and self.bike.is_connected),
                "watch": max(self.seen["power"], self.seen["cadence"]), "kinomap": self.seen["kinomap"],
                "level": r.resistance, "gear": self.gear, "hill_shift": round(self.hill_shift),
                "auto": self.auto.enabled and not self.erg.on, "auto_last": self.auto.last_action,
                "climbing": self.auto.climbing, "band": [self.auto.low, self.auto.high],
                "focus": self.focus_track.status(self.focus, r.cadence, r.power, self.auto.limited) if self.focus else None,
                "wbal": self.wbal.status() if self.wbal else None,
                "session": ({"cue": (self.session_out or {}).get("cue", ""), "pace": (self.session_out or {}).get("pace"),
                             **self.session.status()} if self.session else None),
                "erg": self.erg.target, "erg_source": self.erg.source,
                "ftp": self.profile["ftp"], "ftp_source": self.profile["ftp_source"],
                "test": self.test.status(time.monotonic()) if self.test else None,
                "ghost": self.ghost.status(),
                "route": self.route_ride.status(self.ride.vdistance) if self.route_ride else None,
                "workout": self.erg.workout_status(time.monotonic()),
                "resume": self.resume_offer(),
                "workouts": [w["name"] for w in self.workouts], "grade": round(r.grade, 1),
                "power": int(r.power), "cadence": int(r.cadence), "speed": round(r.road_kmh(), 1),
                "distance": round(r.road_m() / 1000, 2),
                **self.live.status(time.time()),
                "bests": self.bests.status(),
                "pb": self.pb_flash if self.pb_flash and time.time() - self.pb_flash["t"] < 12 else None,
                "events": list(self.events)}

    # ── crash recovery ───────────────────────────────────────────────────────
    def snapshot(self, running=True):
        """What a restarted bridge needs to carry on the same ride."""
        if getattr(self.args, "no_bike", False):
            return                            # no ride to carry on
        now = time.monotonic()
        w = self.erg.workout
        write_state({
            "running": running, "pid": os.getpid(), "ride": str(self.csv_path), "saved_at": time.time(),
            "vdistance": self.ride.vdistance, "grade": self.ride.grade, "gear": self.gear,
            "moving_for": time.time() - self.moving_since if self.moving_since else None,
            "route": {"id": self.route_ride.route.id, "offset": self.route_ride.offset,
                      "started": self.route_started} if self.route_ride else None,
            "auto": self.auto.enabled, "climbing": self.auto.climbing and not self.auto.climb_auto,
            "erg": self.erg.target, "erg_source": self.erg.source,
            "workout": {"name": w["name"], "steps": w["steps"], "elapsed": w.get("active") or (now - w["started"]),
                        "adaptive_state": self.erg.adaptive_state()} if w else None,
        })

    def restore(self, st):
        now = time.monotonic()
        self.ride.vdistance = st.get("vdistance", 0.0)
        self.ride.grade = st.get("grade", 0.0)
        self.gear = st.get("gear", 0)
        self.auto.enabled = st.get("auto", True)
        if st.get("climbing"):
            self.auto.set_climbing(True)
        w = st.get("workout")
        if w:
            self.erg.workout = {"name": w["name"], "steps": [tuple(x) for x in w["steps"]],
                                "started": now - w["elapsed"], "active": w["elapsed"], "last": now,
                                **w.get("adaptive_state", {})}
            self.erg.set(st.get("erg"), st.get("erg_source", ""), now)
            self.erg._advance_workout(now)     # land on the current step's watts right away
        elif st.get("erg"):
            self.erg.set(st["erg"], st.get("erg_source", ""), now)
        paused = time.time() - st.get("saved_at", time.time())
        if st.get("moving_for") is not None:
            self.moving_since = time.time() - st["moving_for"] - paused
        if st.get("route"):
            try:
                self.route_ride = routes.RouteRide(routes.load(st["route"]["id"]), st["route"]["offset"])
                self.route_started = st["route"]["started"] + paused
                self.ghost.use_route(st["route"]["id"])
                self.start_session(self.route_ride.route, resumed=True)
            except (OSError, ValueError, KeyError):
                pass
        gap = int(time.time() - st.get("saved_at", time.time()))
        self.event(f"Resumed the ride after an interruption (~{gap} s): {self.ride.vdistance / 1000:.2f} km, "
                   f"gear {self.gear:+d}" + (f", ERG {self.erg.target} W" if self.erg.on else ""))

    async def run_snapshots(self):
        n = 0
        while True:
            await asyncio.sleep(5)
            self.snapshot()
            n += 1
            if n % 3 == 0:                   # every 15 s: any lifetime milestone crossed mid-ride?
                await self.check_milestones()

    async def check_milestones(self):
        """Lifetime totals from past rides (read once, in the background) plus this
        ride so far: announce each milestone the moment it's crossed."""
        import milestones
        loop = asyncio.get_running_loop()
        if self.ms_before is None:
            try:
                self.ms_before = await loop.run_in_executor(None, lambda: milestones.compute(
                    Path(self.csv_path).parent, self.profile.get("weekly_rides", 3), exclude=Path(self.csv_path).stem))
                self.ms_seen = {e["key"] for e in self.ms_before["earned"]}
            except Exception as e:
                log.info(f"Milestones unavailable: {e}")
                self.ms_before = {}
            return
        if not self.ms_before or self.live.moving_s < 60:
            return
        t = self.ms_before["totals"]
        now = {"rides": t["rides"] + (1 if self.live.moving_s >= 60 else 0),
               "km": t["km"] + self.ride.road_m() / 1000, "hours": t["hours"] + self.live.moving_s / 3600,
               "kcal": t["kcal"] + self.live.kcal, "longest_min": max(t["longest_min"], self.live.moving_s / 60)}
        for tier in milestones.TIERS:
            if tier[1] not in now:
                continue
            for n in tier[2]:
                key = f"{tier[0]}:{n}"
                if key not in self.ms_seen and now[tier[1]] >= n:
                    self.ms_seen.add(key)
                    text = f"{tier[4]} Milestone: {milestones._label(tier, n)}!"
                    self.pb_flash = {"t": time.time(), "text": text, "secs": 0, "watts": 0, "final": True}
                    self.event(text)

    async def supervised(self, name, fn):
        """Keep one part of the bridge alive: if it hits an error it logs it and
        starts again a second later, instead of dying silently while the rest
        carries on half-broken."""
        while True:
            try:
                await fn()
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("%s crashed", name)
                self.event(f"{name} hit an error and restarted ({type(e).__name__}: {e})")
                await asyncio.sleep(1)

    def on_record(self, kind, secs, watts, prev):
        name = bests.label(secs)
        was = f" (was {prev} W)" if prev else ""
        if kind == "new":
            text = f"🏆 New {name} best: {watts} W{was} - keep going!"
        else:
            text = f"🏆 {name} personal best: {watts} W{was}"
        self.pb_flash = {"t": time.time(), "text": text, "secs": secs, "watts": watts, "final": kind == "final"}
        self.event(text)
        if kind == "final" and secs == 1200:
            self._ftp_from_bests()

    def _ftp_from_bests(self):
        """A 20-minute best says FTP is at least 95% of it: raise FTP (never lower it)."""
        r = self.bests_data["records"].get("1200")
        if not r:
            return
        new = int(round(r["watts"] * bests.FTP_FROM_20MIN))
        if new > self.profile["ftp"]:
            old = self.profile["ftp"]
            self.profile = rider.set_ftp(self.profile, new, f"95% of a {r['watts']} W 20-min best")
            self.auto.power_cap = self.args.upshift_cap_w or 0.9 * self.profile["ftp"]
            self.event(f"FTP raised {old} -> {new} W from your 20-min best; workouts rescale to it")

    def event(self, msg):
        log.info(msg)
        self.events.appendleft(f"{dt.datetime.now():%H:%M:%S}  {msg}")
        if hasattr(self, "events_csv"):
            self.events_csv.writerow([dt.datetime.now().isoformat(timespec="seconds"), msg])

    # ── the bike side ───────────────────────────────────────────────────────
    async def find_bike(self):
        while True:
            log.info("Looking for the bike (pedal to wake it; phone and watch must not be connected to it)")
            dev = await BleakScanner.find_device_by_filter(
                lambda d, a: (d.name or "").upper().startswith(self.args.name),
                timeout=2.5 if any(self.seen.values()) else 4)
            if dev:
                return dev
            # Rest the radio between searches. Scanning back to back starves the
            # connections the Mac is serving: on 2026-09-25 (16:11-16:13) the watch
            # and Kinomap dropped together three times, only while the bike was
            # asleep and the search never paused.
            # With the watch or Kinomap already connected, search even more rarely.
            await asyncio.sleep(15 if any(self.seen.values()) else 6)

    def on_bike_data(self, _, data: bytearray):
        data = bytes(data)
        ok = self.ride.update(parse_indoor_bike_data(data))
        r = self.ride
        # Kinomap gets the bike's packet with speed and distance replaced by the
        # virtual ones; the S29's own speed comes from cadence alone.
        out = rewrite_ibd(data, r.road_kmh(), r.road_m()) if r.use_virtual else data
        self.push(FTMS, IBD, out, kind=int.from_bytes(data[0:2], "little"))
        if ok:
            self.live.add(time.time(), r.power, r.cadence, r.road_kmh(), r.grade, self.gear)
            self.bests.add(time.time(), r.power)
            self.csv.writerow([dt.datetime.now().isoformat(timespec="seconds"),
                               int(r.power), r.cadence, r.speed, r.distance, r.resistance,
                               round(r.road_kmh(), 2), round(r.road_m(), 1), r.grade, self.gear,
                               round(self.hill_shift, 2), self.erg.target or ""])

    def on_bike_control(self, _, data: bytearray):
        data = bytes(data)
        if len(data) >= 3 and data[0] == 0x80:
            ok = data[2] == 0x01
            self.event(f"Bike {'accepted' if ok else 'REFUSED'} {OPCODES.get(data[1], hex(data[1]))}"
                       + ("" if ok else f" (code {data[2]})"))
            if data[1] == 0x00:
                self.have_control = ok
                return  # our own control request; Kinomap already got its answer
            if data[1] in (0x04, 0x11):
                return  # Kinomap was already answered when the command was translated
        self.push(FTMS, CONTROL, data)

    def on_bike_status(self, _, data: bytearray):
        self.push(FTMS, STATUS, bytes(data))

    async def run_bike(self):
        while True:
            dev = await self.find_bike()
            try:
                async with BleakClient(dev, disconnected_callback=lambda _: self.event("Bike disconnected")) as c:
                    self.bike = c
                    for uuid in (FEATURE, RES_RANGE, PWR_RANGE):
                        try:
                            self.static[uuid] = bytes(await c.read_gatt_char(uuid))
                        except Exception:
                            pass
                    await c.start_notify(IBD, self.on_bike_data)
                    await c.start_notify(STATUS, self.on_bike_status)
                    await c.start_notify(CONTROL, self.on_bike_control)
                    self.event(f"Bike connected ({dev.name}). Recording to {self.csv_path}")
                    self.describe_features()
                    # Take control of the bike ourselves, on every (re)connection.
                    # Kinomap asks once when it connects; after the bike sleeps or
                    # drops, that grant is gone and every later command is ignored.
                    self.have_control = False
                    self.level_sent = None  # re-send the current hill after a reconnect
                    await c.write_gatt_char(CONTROL, b"\x00", response=True)
                    while c.is_connected:
                        await asyncio.sleep(1)
            except Exception as e:
                log.warning("Bike connection error: %s", e)
            self.bike = None
            await asyncio.sleep(2)

    # ── the broadcast side ──────────────────────────────────────────────────
    def push(self, svc, char, value: bytes, kind=None):
        """Queue an update. Sensor readings are coalesced (only the newest of each
        kind is kept); control replies are all kept, in order. Safe to call from
        CoreBluetooth's thread."""
        with self.outbox_lock:
            if char in (CONTROL, STATUS):
                self.ordered.append((svc, char, bytes(value)))
            else:
                self.latest[(char, kind)] = (svc, bytes(value))

    def flush(self):
        """Send what's queued, stopping the moment macOS says its Bluetooth queue
        is full; the rest waits for the next pass instead of being thrown away.
        Before this, every update was sent immediately and 5-8 per 5 s were lost
        (2026-09-25, 17:06-17:09) until the watch and Kinomap gave up at once."""
        if not self.server:
            return
        with self.outbox_lock:
            ordered = list(self.ordered)
            latest = list(self.latest.items())
        sent_ordered = 0
        for svc, char, value in ordered:
            if not self._send(svc, char, value):
                self.send_retries += 1
                break
            sent_ordered += 1
        else:
            for key, (svc, value) in latest:
                if not self._send(svc, key[0], value):
                    self.send_retries += 1
                    break
                with self.outbox_lock:
                    if self.latest.get(key, (None, None))[1] == value:
                        del self.latest[key]
        with self.outbox_lock:
            for _ in range(sent_ordered):
                self.ordered.popleft()

    def _send(self, svc, char, value):
        c = self.server.get_characteristic(char)
        if c is None:
            return True
        c.value = bytearray(value)
        targets = self.targets(char)
        if not targets:
            return True  # nobody to send to: the value is stored for reads
        from Foundation import NSData
        pm = self.server.peripheral_manager_delegate.peripheral_manager
        data = NSData.dataWithBytes_length_(bytes(value), len(value))
        return bool(pm.updateValue_forCharacteristic_onSubscribedCentrals_(data, c.obj, targets))

    def subscribers(self, char):
        c = self.server.get_characteristic(char) if self.server else None
        try:
            return list(c.obj.subscribedCentrals() or []) if c is not None else []
        except Exception:
            return []

    def watch_ids(self):
        """Devices subscribed to power or speed/cadence: the watch. Kinomap
        never subscribes to those (bluetooth-debug.log, 2026-09-25)."""
        return {x.identifier().UUIDString() for ch in (CP_MEAS, CSC_MEAS) for x in self.subscribers(ch)}

    def targets(self, char):
        """Who gets an update. The watch also subscribes to the smart-bike
        channels, which doubled every bike packet and kept macOS's send queue
        full (77 of 82 checks on the 17:41 ride). It records power from the
        power channel, so smart-bike traffic goes to Kinomap only - unless
        --watch-ftms puts the old behaviour back."""
        subs = self.subscribers(char)
        if char in (IBD, CONTROL, STATUS, TRAINING) and not self.args.watch_ftms:
            watch = self.watch_ids()
            keep = [x for x in subs if x.identifier().UUIDString() not in watch]
            # The watch subscribes to bike data too, and if that goes quiet it
            # decides the sensor is gone: with none sent it dropped every 40 s
            # (2026-09-26, 04:36-04:40). Once a second keeps it happy at a
            # fraction of the traffic; Kinomap still gets every packet.
            if char == IBD and time.monotonic() - self.watch_ibd_at >= 1.0:
                extra = [x for x in subs if x.identifier().UUIDString() in watch]
                if extra:
                    self.watch_ibd_at = time.monotonic()
                    keep += extra
            return keep
        return subs

    def kinomap_count(self):
        watch = self.watch_ids()
        return sum(1 for x in self.subscribers(IBD) if x.identifier().UUIDString() not in watch)

    async def run_outbox(self):
        while True:
            await asyncio.sleep(0.05)
            try:
                self.flush()
            except Exception as e:
                log.warning("send error: %s", e)

    def on_read(self, characteristic, **_):
        uuid = str(characteristic.uuid).lower()
        if uuid == CP_FEAT:
            return bytearray((0x08).to_bytes(4, "little"))       # crank revolution data supported
        if uuid == CSC_FEAT:
            return bytearray((0x03).to_bytes(2, "little"))       # wheel + crank data supported
        if uuid == SENSOR_LOC:
            return bytearray([0x0D])                             # rear hub, as trainers report
        if uuid == TRAINING:
            return bytearray([0x00, 0x01])                       # idle
        if uuid == FEATURE and len(self.static.get(FEATURE, b"")) >= 8:
            # Advertise hill simulation to Kinomap even though the S29 lacks it:
            # without this bit Kinomap never sends grades (seen 16:29-16:30, only
            # "resistance 0"), and the bridge turns every grade into a level.
            raw = bytearray(self.static[FEATURE])
            raw[4:8] = (int.from_bytes(raw[4:8], "little") | 1 << 13 | 1 << 3).to_bytes(4, "little")
            # bit 3: power target too - the bridge's virtual ERG holds it
            return raw
        return bytearray(self.static.get(uuid, characteristic.value or b"\x00"))

    def on_write(self, characteristic, value, **_):
        # Only the FTMS control point is writable: Kinomap asking for resistance.
        if str(characteristic.uuid).lower() != CONTROL:
            return
        value = bytes(value)
        if value[:1] == b"\x01":
            # FTMS "Reset". Kinomap sends it on connecting; forwarded, it reboots
            # the S29 and every connection through the bridge drops with it
            # (seen 2026-09-25 14:52: all three listeners lost, distance back to
            # 0). Answer it here as done and leave the bike alone.
            self.event("Kinomap asked to reset the bike: answered locally, bike left running")
            self.push(FTMS, CONTROL, b"\x80\x01\x01")
            return
        if value[:1] == b"\x00":
            # "Request control": the bridge already holds it; say yes.
            self.event("Kinomap took control")
            self.push(FTMS, CONTROL, b"\x80\x00\x01")
            return
        # Everything below reaches the bike only as a command it is known to
        # handle: a resistance level inside its own range, or start/stop.
        # 2026-09-25 16:23: Kinomap sent "set resistance 0", the S29 (levels
        # 1-16) refused it, rebooted a second later, and took the watch and
        # Kinomap down with it. So nothing is forwarded unchecked.
        op = value[0]
        if op == 0x11 and len(value) >= 5 and self.route_ride:
            self.push(FTMS, CONTROL, b"\x80\x11\x01")    # riding our own route: Kinomap's hills don't apply
            return
        if op == 0x11 and len(value) >= 5:
            if self.bike_sims:
                self.event(f"Kinomap: {describe_command(value)}")
            else:
                value = self.hill_to_level(int.from_bytes(value[3:5], "little", signed=True) / 100)
                self.push(FTMS, CONTROL, b"\x80\x11\x01")  # tell Kinomap it's handled
                if value is None:
                    return
        elif op == 0x04:
            # Kinomap's own resistance request, in tenths. Clamp into the bike's range.
            raw = int.from_bytes(value[1:3], "little", signed=True) if len(value) >= 3 else value[1]
            if raw <= 0:
                # Kinomap sends 0 when a ride starts; taken literally it drops the
                # bike to its easiest level and throws away the flat-road setting.
                self.event("Kinomap asked for resistance 0 - ignored (keeping the current level)")
                self.push(FTMS, CONTROL, b"\x80\x04\x01")
                return
            self.hill_level = raw / 10
            self.hill_shift = 0.0
            value = self.set_level(self.hill_level + self.gear, f"Kinomap asked for resistance {raw / 10:g}")
            self.push(FTMS, CONTROL, b"\x80\x04\x01")
            if value is None:
                return
        elif op == 0x05 and len(value) >= 3:
            watts = int.from_bytes(value[1:3], "little", signed=True)
            self.erg.set(watts, "Kinomap", time.monotonic())
            self.event(f"Kinomap: hold {self.erg.target} W (ERG, held by the bridge)")
            self.push(FTMS, CONTROL, b"\x80\x05\x01")
            return
        elif op in (0x07, 0x08):
            self.event(f"Kinomap: {describe_command(value)}")
        else:
            # Target power (ERG) and anything else: the S29 can't do it. Say so
            # to Kinomap and leave the bike alone.
            self.event(f"Kinomap: {describe_command(value)} - not supported by the bike, not sent")
            self.push(FTMS, CONTROL, bytes([0x80, op, 0x02]))
            return
        if not (self.bike and self.bike.is_connected):
            self.event("  ...but the bike isn't connected; command dropped")
            return
        fut = asyncio.run_coroutine_threadsafe(self.forward(value), self.loop)
        fut.add_done_callback(lambda f: f.exception() and self.event(f"  ...send failed: {f.exception()}"))

    def send_to_bike(self, cmd):
        if cmd and self.bike and self.bike.is_connected:
            fut = asyncio.run_coroutine_threadsafe(self.forward(cmd), self.loop)
            fut.add_done_callback(lambda f: f.exception() and self.event(f"  ...send failed: {f.exception()}"))

    def climbing(self, on):
        """Panel / menu button: stays on until turned off."""
        self.auto.set_climbing(on)
        lo, hi = self.auto.normal_band
        self.event(f"Climbing mode {'on: 30-45 rpm' if on else f'off: back to {lo:.0f}-{hi:.0f} rpm'}")

    def refresh_focus(self, force=False):
        """Today's focus from the coach plan (checked every minute: a plan can be set mid-day, and the day
        and FTP can change). Applies it to auto-shift and notes it in the ride's events."""
        now = time.monotonic()
        if not force and now - self.focus_checked < 60:
            return
        self.focus_checked = now
        if self.wbal is None or self.wbal_ftp != self.profile["ftp"]:
            try:                                     # CP and W' for the live balance (again when FTP changes)
                e = cp_mod.estimate(cp_mod.best_curve(Path(self.csv_path).parent), self.profile["ftp"])
                bal = self.wbal.bal / self.wbal.w if self.wbal else 1.0
                self.wbal = cp_mod.WBal(e["cp"], e["w_prime"])
                self.wbal.bal = self.wbal.w * bal
                self.wbal_ftp = self.profile["ftp"]
            except Exception as ex:
                log.warning(f"W' balance: {ex}")
        levels = None
        try:
            import coach, morning, skills
            d = coach.load(coach.file_for(Path(self.csv_path).parent))
            plan = d["plans"].get(coach.today()) or {}
            mo = morning.assess(morning.load(Path(self.csv_path).parent.parent)) or {}
            levels = skills.levels_for(d, skills.step_today(d, coach.today(), mo.get("level")))   # the skill ladders
        except Exception as e:                   # a broken coach file mustn't stop the ride
            log.warning(f"focus: couldn't read the coach plan ({e})")
            plan = {}
        self.focus_levels = levels
        f = focus.resolve(plan.get("focus"), self.profile["ftp"], (self.args.cadence_low, self.args.cadence_high),
                          plan.get("verdict"), levels)
        if f != self.focus:
            first = self.focus is None
            self.focus = f
            self.auto.set_focus(f["rpm"], f["watts"])
            self._applied = None                     # a session segment in progress re-applies its own ranges
            if not first:
                self.focus_track.reset()
            self.event(f"Focus - {focus.label(f)}")

    def erg_set(self, watts):
        """From the panel: hold a wattage, or None to go back to hills."""
        now = time.monotonic()
        self.erg.workout = None
        if watts is None and self.test:
            self.test.finish(now, "ERG turned off")
            if self.test.result and not getattr(self, "test_applied", True):
                self.ftp_test_tick(now, 0, 0)
            self.test = None
            self.erg.min_cadence = 55
        self.erg.set(watts, "panel" if watts else "", now)
        if watts:
            self.event(f"ERG: holding {self.erg.target} W")
        else:
            self.event("ERG off: back to hills and auto-shift")
            base = self.hill_level if self.hill_level is not None else self.flat_level()
            self.set_level(base + self.hill_shift + self.gear, "Hills")

    # ── resuming a workout that stopped before it finished ─────────────────
    def _write_resume(self):
        try:
            if self.resume is None:
                self.resume_file.unlink(missing_ok=True)
            else:
                tmp = self.resume_file.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.resume)); os.replace(tmp, self.resume_file)
        except OSError:
            pass

    def resume_tick(self):
        """Once a second: remember how far into the workout the rider is; forget it once it finishes by itself."""
        import coach
        w = self.erg.workout
        if w and not self.test and w["name"] != coach.TEST_NAME:
            self._had_workout = True
            active = w.get("active", 0.0)
            if active >= RESUME_AFTER and (not self.resume or abs(active - self.resume.get("active", -99)) >= 5
                                           or self.resume.get("name") != w["name"]):
                self.resume = {"name": w["name"], "steps": [[d, watts] for d, watts in w["steps"]],
                               "active": round(active, 1), "date": dt.date.today().isoformat(), "saved": round(time.time()),
                               "adaptive_state": self.erg.adaptive_state()}
                self._write_resume()
        elif self._had_workout:
            self._had_workout = False
            if self.erg.source == "workout finished" and self.resume:     # ended by itself: nothing left to resume
                self.resume = None
                self._write_resume()

    def resume_offer(self):
        """What can be picked up again: today's unfinished workout, when nothing is running."""
        s = self.resume
        if not s or self.erg.workout or s.get("date") != dt.date.today().isoformat():
            return None
        total = sum(d for d, _ in s["steps"])
        if s["active"] >= total - 5:
            return None
        t, step = 0.0, len(s["steps"])
        for i, (d, _) in enumerate(s["steps"]):
            if s["active"] < t + d:
                step = i + 1
                break
            t += d
        return {"name": s["name"], "elapsed": int(s["active"]), "total": int(total), "left": int(total - s["active"]),
                "step": step, "steps": len(s["steps"])}

    def workout_resume(self):
        """Pick the saved workout up at the same block and second. The clock waits for the pedals."""
        if not self.resume_offer():
            return False
        s, now = self.resume, time.monotonic()
        self.test = None
        self.erg.start_workout({"name": s["name"], "steps": [{"minutes": d / 60, "watts": w} for d, w in s["steps"]]}, now)
        self.erg.workout["active"] = float(s["active"])
        self.erg.workout.update(s.get("adaptive_state", {}))
        self.erg._advance_workout(now)               # the right block's watts, straight away
        m, sec = divmod(int(s["active"]), 60)
        self.event(f"Workout resumed: {s['name']} at {m}:{sec:02d}")
        return True

    def resume_discard(self):
        self.resume = None
        self._write_resume()

    def reload_workouts(self):
        """After the builder saves or deletes one."""
        self.workouts = load_workouts(Path(__file__).resolve().parent / "workouts")

    def workout_start_id(self, wid):
        for i, w in enumerate(self.workouts):
            if w.get("id") == wid:
                self.workout_start(i)
                return True
        return False

    def coach_test_start(self):
        """The 6-minute morning diagnostic: fixed watts, whatever the FTP."""
        import coach
        self.test = None
        self.erg.start_workout({"name": coach.TEST_NAME, "steps": coach.TEST_STEPS}, time.monotonic())
        self.event("Morning diagnostic started: 2 min 60 W, 2 min 90 W, 1 min 120 W, 1 min easy")

    def workout_start(self, index):
        if 0 <= index < len(self.workouts):
            saved = self.workouts[index]
            if saved.get("blocks"):
                import workouts as workout_builder
                saved = {**saved, "steps": workout_builder.flatten(saved["blocks"])}
            w = rider.workout_watts(saved, self.profile["ftp"])
            self.test = None
            self.erg.start_workout(w, time.monotonic())
            self.event(f"Workout started: {w['name']} (at FTP {self.profile['ftp']} W)")

    # ── riding a planned route ──────────────────────────────────────────────
    def route_start(self, rid):
        route = routes.load(rid)
        self.route_ride = routes.RouteRide(route, self.ride.vdistance)
        self.route_fed, self.route_started = None, time.time()
        s = route.stats()
        self.event(f"Route started: {route.id} at {self.ride.vdistance:.0f} m - {route.name}, "
                   f"{s['km']} km, {s['climb_m']} m of climbing")
        self.ghost.use_route(route.id)
        self.ghost_name = None
        self.start_session(route)
        self.feed_route()

    def route_stop(self, why="stopped"):
        if self.route_ride:
            self.end_session()
            self.event(f"Route {why}: {self.route_ride.route.name}")
            self.route_ride = self.route_fed = self.route_started = None
            self.ghost.route_id, self.ghost.match, self.ghost.points = None, None, []
            self.hill_to_level(0.0)

    def feed_route(self):
        """Once a second while riding a route: the road's grade at your
        distance becomes the hill, in 0.5% steps."""
        rr = self.route_ride
        if not rr:
            return
        if rr.finished(self.ride.vdistance):
            g = self.ghost.gap()
            self.route_stop("finished" + (f" - {abs(g[0])} s {'ahead of' if g[0] < 0 else 'behind'} your ghost"
                                          if g and g[0] is not None else ""))
            return
        grade = round(rr.route.grade_at(rr.along(self.ride.vdistance)) * 2) / 2
        if grade != self.route_fed:
            self.route_fed = grade
            self.hill_to_level(grade)

    # ── sessions on a route: climb goals, efforts, part-route focus; every climb recorded ──
    def start_session(self, route, resumed=False):
        at = self.route_ride.along(self.ride.vdistance) if (resumed and self.route_ride) else 0.0
        self.climb_rec = session.ClimbRecorder(route, start_at=at)
        self.session, self.session_out, self.session_gear, self._applied = None, None, None, None
        try:
            import coach
            plan = coach.load(coach.file_for(Path(self.csv_path).parent))["plans"].get(coach.today()) or {}
            ses = plan.get("session") or {}
            if ses.get("route_id") != route.id:
                return
            segs = session.check(route, ses["segments"])
        except Exception as e:                     # a bad session mustn't stop the ride
            self.event(f"Session not loaded: {e}")
            return
        rpm = tuple(self.focus["rpm"]) if self.focus else (self.args.cadence_low, self.args.cadence_high)
        self.session = session.Runner(route, segs, self.profile["ftp"], self.ride.mass,
                                      lambda f: focus.resolve(f, self.profile["ftp"], rpm, None, getattr(self, "focus_levels", None)),
                                      start_at=at)
        if resumed:                                # what was done before the interruption still counts
            try:
                f = Path(self.csv_path).with_name(Path(self.csv_path).stem + "_session.json")
                self.session.results = json.loads(f.read_text()).get("results", [])
            except (OSError, ValueError):
                pass
        self.event(f"Session on this route: " + "; ".join(s["name"] for s in segs))

    def session_tick(self):
        rr, r = self.route_ride, self.ride
        if not rr:
            return
        t, d = time.monotonic(), rr.along(r.vdistance)
        if self.climb_rec:
            rec = self.climb_rec.update(t, d, r.power, r.cadence, r.road_kmh() / 3.6, self.gear)
            if rec:
                self.save_climb(rec)
        if not self.session:
            return
        out = self.session.update(t, d, r.power, r.cadence, r.grade)
        for m in self.session.log:
            self.event("Session: " + m)
        self.session.log.clear()
        base = self.focus or {"rpm": [self.args.cadence_low, self.args.cadence_high], "watts": None}
        rpm, watts = out["rpm"] or base["rpm"], out["watts"] if out["watts"] is not None else base["watts"]
        want = (tuple(rpm), tuple(watts) if watts else None)
        if want != self._applied:
            self.auto.set_focus(rpm, watts)
            self.auto.watt_hold = 5 if out["watts"] else 15      # a goal in progress steers sooner
            self._applied = want
        if out["shift_to_watts"]:
            if self.session_gear is None:
                self.session_gear = self.gear
            self.gear_for_watts(*out["shift_to_watts"])
        if out["restore_gear"] and self.session_gear is not None:
            if self.session_gear != self.gear:
                self.shift(self.session_gear - self.gear, "Session: back to your gear")
            self.session_gear = None
        self.session_out = out
        if self.session.results:
            self.save_session()

    def gear_for_watts(self, watts, cadence):
        """Shift straight into the gear that makes `watts` at `cadence` on this road - the way a rider clicks
        up three gears at the foot of an effort instead of one at a time."""
        base = (self.hill_level if self.hill_level is not None else self.flat_level()) + self.hill_shift
        target = round(session.level_for(watts, cadence) - base)
        if target != self.gear:
            self.shift(target - self.gear, f"Session: gear for {watts:.0f} W at {cadence:.0f} rpm")
            self.auto.manual_shift()                 # let the legs meet the new gear before judging it

    def save_climb(self, rec):
        rr = self.route_ride
        rec = {"date": dt.date.today().isoformat(), "ride": Path(self.csv_path).stem, "route_id": rr.route.id,
               "route": rr.route.name, "ended": round(time.time()), **rec}   # when: insights.py finds the watch's heart rate
        f = Path(self.csv_path).parent / "climbs.json"
        try:
            have = json.loads(f.read_text()) if f.exists() else []
        except ValueError:
            have = []
        have.append(rec)
        tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(have, indent=1)); tmp.replace(f)
        m, sec = divmod(rec["seconds"], 60)
        self.event(f"Climb {rec['n']} ({rec['length_m'] / 1000:.2f} km at {rec['avg_grade']}%): {m}:{sec:02d}, "
                   f"{rec['avg_w']} W, {rec['avg_rpm']} rpm, {rec['vam']} m/h up")

    def save_session(self):
        if not (self.session and self.route_ride):
            return
        f = Path(self.csv_path).with_name(Path(self.csv_path).stem + "_session.json")
        data = {"route_id": self.route_ride.route.id, "route": self.route_ride.route.name,
                "segments": [{k: v for k, v in s.items() if k in ("type", "name", "start_m", "end_m", "at_m", "seconds",
                              "count", "on_s", "off_s", "watts", "rpm")} for s in self.session.segs],
                "results": self.session.results}
        tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(data, indent=1)); tmp.replace(f)

    def end_session(self):
        if self.session:
            self.save_session()
            self.event("Session over: " + (", ".join(
                f"{x['name']} {'made' if x.get('made') is True else ('%d/%d' % (x['made'], len(x['efforts'])) if x['type'] == 'efforts' else 'missed')}"
                for x in self.session.results) or "nothing reached"))
        if self.session_gear is not None and self.session_gear != self.gear:
            self.shift(self.session_gear - self.gear, "Session: back to your gear")
        self.session = self.climb_rec = self.session_out = self.session_gear = None
        if self.focus:
            self.auto.set_focus(self.focus["rpm"], self.focus["watts"])
        self.auto.watt_hold, self._applied = 15, None

    def feed_ghost(self):
        r = self.ride
        if not r.use_virtual or r.vdistance <= 0:
            return
        if self.route_ride:
            self.ghost.add(self.route_ride.along(r.vdistance), time.time() - self.route_started, r.grade)
        else:
            if self.moving_since is None:
                self.moving_since = time.time()
            self.ghost.add(r.vdistance, time.time() - self.moving_since, r.grade)
        name = self.ghost.match.name if self.ghost.match else None
        if name != self.ghost_name:
            if name:
                when = dt.datetime.strptime(name[:20], "ride_%Y-%m-%d_%H%M")
                what = "this route" if self.route_ride else "the route"
                self.event(f"Ghost: racing your ride of {what} from {when:%a %b %-d at %-I:%M %p}")
            elif self.ghost_name:
                self.event("Ghost: the road no longer matches that ride - ghost dropped")
            self.ghost_name = name

    def ftp_test_start(self):
        now = time.monotonic()
        self.erg.workout = None
        self.test = RampTest(self.profile["ftp"], now)
        self.test_applied = False
        # ERG's "cadence under 55 -> ease off" guard would cap the ramp before he
        # reaches their limit; the test has its own end (under 50 rpm for 10 s).
        self.erg.min_cadence = 45
        self.erg.set(self.test.target(now), "FTP test", now)
        self.event(f"FTP test started: 5 min warm-up at {self.test.warm_w} W, then the ramp from "
                   f"{self.test.start_w} W, +10 W a minute until you can't hold it")

    def ftp_test_stop(self):
        if self.test and self.test.phase in ("warm-up", "ramp"):
            self.test.finish(time.monotonic(), "stopped with the button")

    def ftp_test_tick(self, now, power, cadence):
        tgt = self.test.update(now, power, cadence)
        if self.test.result and not self.test_applied:
            self.test_applied = True
            old = self.profile["ftp"]
            self.profile = rider.set_ftp(self.profile, self.test.result, "ramp test")
            self.auto.power_cap = self.args.upshift_cap_w or 0.9 * self.profile["ftp"]
            self.event(f"FTP test done ({self.test.reason}): best minute {self.test.best_1min:.0f} W "
                       f"-> FTP {self.test.result} W (was {old} W). Workouts now scale to it. Cooling down.")
        elif self.test.phase == "cool-down" and not self.test.result and not self.test_applied:
            self.test_applied = True
            self.event(f"FTP test ended early ({self.test.reason}): the ramp needs at least 4 minutes, "
                       f"so FTP stays {self.profile['ftp']} W. Cooling down.")
        if tgt is None:
            self.test = None
            self.erg.min_cadence = 55
            self.erg_set(None)
        elif tgt != self.erg.target:
            self.erg.target = tgt
            self.erg.samples.clear()

    def manual_level(self, level):
        """Set an exact level (testing)."""
        self.send_to_bike(self.set_level(level, "Panel"))

    def shift(self, delta, why=None):
        """The panel's gear buttons. A gear is an offset on top of whatever the
        hill asks for, and it stays when the hill changes - like shifting on a
        real bike. With virtual speed on, a harder gear at the same cadence means
        more watts and so more speed; an easier one keeps you spinning up a climb."""
        lo, hi = self.res_range
        base = (self.hill_level if self.hill_level is not None else self.flat_level()) + self.hill_shift
        clamp = lambda g: int(round(min(hi, max(lo, base + g))))
        new = self.gear + delta
        if why is not None and delta < 0 and new < self.args.min_gear:
            new = max(new, self.args.min_gear)   # automatic shifting never goes easier than the floor
            if new >= self.gear:
                return False
        # No phantom gears: a shift that can't change the bike's level (already
        # at level 1 or the maximum) doesn't happen.
        if clamp(new) == clamp(self.gear):
            return False
        moved = new - self.gear
        self.gear = new
        if self.ride.grade <= -1:
            # Gears taken on a descent are handed back when the road turns up.
            self.descent_gears = max(0, self.descent_gears + moved)
        if why is None:                      # a hand shift from the panel
            self.auto.manual_shift()
            why = "Gear"
            if delta > 0 and self.ride.grade >= 2 and not self.auto.climbing:
                # Shifting harder by hand on a climb = standing and driving it.
                # Stay in climbing mode until the crest.
                self.auto.set_climbing(True, auto=True)
                self.event(f"Climbing mode on (hand shift harder at {self.ride.grade:+.0f}%): 30-45 rpm until the top")
            elif delta < 0 and self.auto.climb_auto:
                self.auto.set_climbing(False)
                self.event("Climbing mode off (hand shift easier): back to 65-80 rpm")
        self.send_to_bike(self.set_level(base + self.gear, f"{why} -> gear {self.gear:+d}"))
        return True

    def flat_level(self):
        lo, hi = self.res_range
        return self.args.base_level if self.args.base_level is not None else lo + 0.25 * (hi - lo)

    def hill_to_level(self, grade):
        if self.erg.on:
            if self.erg.source == "Kinomap":
                # Kinomap sending grades again means it left its ERG workout.
                self.erg.set(None, "", time.monotonic())
                self.event("Kinomap switched back to hills: ERG off")
            else:
                # Speed follows the road and the hill is tracked, so turning ERG
                # off lands on the right level; the watts stay fixed meanwhile.
                return self._hill_to_level(grade, apply=False)
        return self._hill_to_level(grade)

    def _hill_to_level(self, grade, apply=True):
        """The S29 accepts a resistance level but ignores hill simulation, so the
        bridge turns Kinomap's grade into a level: flat rides at --base-level,
        each 1% of climb adds --per-percent levels, descents take them away."""
        lo, hi = self.res_range
        # Defaults scale with the bike's range: flat a quarter of the way up,
        # each 1% of grade another 1/20th of the range (about 1.5 levels on a 1-32 bike).
        per = self.args.per_percent if self.args.per_percent is not None else (hi - lo) / 20
        if self.hill_level is None or self.grace_grade is None or abs(grade - self.grace_grade) >= 1.0:
            # A route's grade changes all the time; only a real change (1%+) gives
            # the auto-shifter its settling grace, or it would never judge anything.
            self.auto.hill_changed()
            self.grace_grade = grade
        now = time.monotonic()
        if grade <= -1:
            self.descent_left_at = None
        elif self.ride.grade <= -1:
            self.descent_left_at = now
        if self.descent_gears and grade > -1 and self.descent_left_at and now - self.descent_left_at > 60:
            self.descent_gears = 0           # a minute on the flat: those gears are the rider's now
        if self.descent_gears and grade >= 1:
            # Stacking (2026-09-26): spinning down a descent piles on gears, and
            # carried into the next climb they'd put the rider at level 12 at the bottom.
            # Hand them back the moment the road turns up, like a rider would.
            back = self.descent_gears
            self.gear -= back
            self.descent_gears = 0
            self.event(f"Road turns up ({grade:+.0f}%): handed back {back} gear{'s' if back > 1 else ''} "
                       f"from the descent -> gear {self.gear:+d}")
        if self.auto.climb_auto and grade < 1:
            self.auto.set_climbing(False)
            self.event(f"Over the top ({grade:+.0f}%): climbing mode off, back to "
                       f"{self.auto.normal_band[0]:.0f}-{self.auto.normal_band[1]:.0f} rpm")
        self.ride.grade = grade
        self.hill_level = self.flat_level() + grade * per
        # Shift at the bottom of the hill, the way a rider does, instead of
        # waiting for cadence to die halfway up: one gear easier per
        # --hill-shift-every % of climb (up to 4), and on descents one harder
        # per 3% down (up to 2) so there's something to push against. Tied to
        # the grade, so cresting the hill gives the gears back by itself.
        # Kept fractional and rounded once with the level: whole-gear steps
        # made resistance saw-tooth (+1% was level 6, +2% level 5).
        every = self.args.hill_shift_every
        if every and grade > 0:
            new_shift = -min(4.0, grade / every)
        elif every and grade < 0:
            new_shift = min(2.0, -grade / 3)
        else:
            new_shift = 0.0
        note = ""
        if round(new_shift) != round(self.hill_shift):
            moved = round(new_shift) - round(self.hill_shift)
            note = f", shifted {abs(moved)} {'easier' if moved < 0 else 'harder'} for the hill"
        self.hill_shift = new_shift
        gear = f", gear {self.gear:+d}" if self.gear else ""
        if not apply:
            return None
        return self.set_level(self.hill_level + self.hill_shift + self.gear,
                              f"{'Road' if self.route_ride else 'Kinomap'}: hill {grade:+.1f}%{note}{gear}")

    def set_level(self, level, why):
        """Choose the level the bike should be at. It isn't sent here: ramp_step
        walks the bike there one level at a time (see run_ramp). Returns None
        so callers have nothing to forward."""
        lo, hi = self.res_range
        level = int(round(min(hi, max(lo, level))))
        if level != self.target_level:
            self.target_level = level
            self.target_since = time.monotonic()
            self.event(f"{why} -> resistance level {level}")
        return None

    def level_command(self, level):
        if self.level_format == 3:
            return bytes([0x04]) + int(level * 10).to_bytes(2, "little", signed=True)
        return bytes([0x04, level])

    def ramp_step(self, now):
        """One step toward the target level, or None. A new grade used to jump
        the bike several levels at once - a wall under the pedals. Now it moves
        one level per --ramp seconds, and only after the target has held still
        for 0.8 s, so a grade flickering between two values doesn't make the
        bike flicker with it. After a (re)connect the bike's level is unknown,
        so the first command goes straight to the target."""
        t = self.target_level
        if t is None or t == self.level_sent:
            return None
        if self.level_sent is None:
            step = t
        else:
            if now - self.target_since < 0.8 or now - self.last_step < self.args.ramp:
                return None
            step = self.level_sent + (1 if t > self.level_sent else -1)
        self.level_sent, self.last_step = step, now
        return self.level_command(step)

    async def run_ramp(self):
        while True:
            await asyncio.sleep(0.2)
            if self.bike and self.bike.is_connected:
                self.send_to_bike(self.ramp_step(time.monotonic()))

    async def forward(self, value: bytes):
        if not self.have_control:
            await self.bike.write_gatt_char(CONTROL, b"\x00", response=True)
            await asyncio.sleep(0.3)
        await self.bike.write_gatt_char(CONTROL, value, response=True)

    def describe_features(self):
        raw = self.static.get(FEATURE, b"")
        if len(raw) >= 8:
            target = int.from_bytes(raw[4:8], "little")
            can = [name for bit, name in ((2, "resistance"), (3, "power"), (13, "hill simulation"))
                   if target >> bit & 1]
            self.event("Bike accepts: " + (", ".join(can) if can else "no resistance control over FTMS"))
            self.bike_sims = bool(target >> 13 & 1)
        rr = self.static.get(RES_RANGE, b"")
        if len(rr) >= 6:
            lo, hi, step = (int.from_bytes(rr[i:i + 2], "little", signed=True) / 10 for i in (0, 2, 4))
            self.res_range = (lo, hi)
            self.event(f"Resistance range: {lo:g} to {hi:g} (step {step:g})")

    async def run_server(self):
        s = BlessServer(name=self.args.broadcast, loop=self.loop)
        s.read_request_func = self.on_read
        s.write_request_func = self.on_write
        R, W, N, I = Prop.read, Prop.write, Prop.notify, Prop.indicate
        readable, rw = Perm.readable, Perm.readable | Perm.writeable
        gatt = {
            CPS: {CP_MEAS: {"Properties": N, "Permissions": readable, "Value": None},
                  CP_FEAT: {"Properties": R, "Permissions": readable, "Value": None},
                  SENSOR_LOC: {"Properties": R, "Permissions": readable, "Value": None}},
            CSC: {CSC_MEAS: {"Properties": N, "Permissions": readable, "Value": None},
                  CSC_FEAT: {"Properties": R, "Permissions": readable, "Value": None}},
            FTMS: {FEATURE: {"Properties": R, "Permissions": readable, "Value": None},
                   IBD: {"Properties": N, "Permissions": readable, "Value": None},
                   TRAINING: {"Properties": R | N, "Permissions": readable, "Value": None},
                   RES_RANGE: {"Properties": R, "Permissions": readable, "Value": None},
                   PWR_RANGE: {"Properties": R, "Permissions": readable, "Value": None},
                   CONTROL: {"Properties": W | I, "Permissions": rw, "Value": None},
                   STATUS: {"Properties": N, "Permissions": readable, "Value": None}},
        }
        if self.args.watch_only:
            del gatt[FTMS]  # leaves a plain power meter + speed/cadence sensor
        await s.add_gatt(gatt)
        await s.start()
        self.server = s
        self.event(f"Broadcasting as '{self.args.broadcast}'"
                   + (" (watch only)" if self.args.watch_only else ": connect Kinomap and the watch to it"))

    async def run_sensors(self):
        """The watch-facing sensors update once a second, like real ones."""
        last_print = 0.0
        self.refresh_focus(force=True)
        while True:
            await asyncio.sleep(1)
            r = self.ride
            r.tick()
            self.refresh_focus()
            self.feed_route()
            self.feed_ghost()
            # the workout clock runs only while pedalling with the bike connected: stopping pauses it
            self.erg.tick_clock(time.monotonic(), r.cadence, bool(self.bike and self.bike.is_connected))
            self.resume_tick()
            if self.bike and self.bike.is_connected:
                now = time.monotonic()
                if self.wbal and r.cadence >= 20:
                    self.wbal.add(r.power)
                if self.test:
                    self.ftp_test_tick(now, r.power, r.cadence)
                if self.erg.on:
                    self.erg.ftp = self.profile["ftp"]
                    cur = r.resistance if r.resistance is not None and r.resistance > 0 else self.target_level
                    move = self.erg.update(r.power, r.cadence, now,
                                           cur)
                    if move:
                        cur = cur if cur is not None else 5
                        self.level_sent = cur  # ramp from the bike's actual setting, not an old command
                        why = (f"ERG {self.erg.target} W: {int(r.power)} W at {int(r.cadence)} rpm, "
                               + ("easier" if move < 0 else "harder"))
                        self.set_level(cur + move, why)
                    if not self.erg.on and self.hill_level is not None:
                        self.event("ERG workout finished: back to hills")
                        self.set_level(self.hill_level + self.hill_shift + self.gear, "Hills")
                else:
                    self.session_tick()
                    self.auto.update(r.cadence, power=r.power)
                    if self.focus:
                        self.focus_track.add(self.focus, r.cadence, r.power)
            self.push(CPS, CP_MEAS, r.cycling_power())
            self.push(CSC, CSC_MEAS, r.speed_cadence())
            for key, char, who in (("power", CP_MEAS, "Watch power"), ("cadence", CSC_MEAS, "Watch speed/cadence"),
                                   ("kinomap", None, "Kinomap")):
                n = self.kinomap_count() if char is None else self.listeners(char)
                if n != self.seen[key]:
                    self.event(f"{who} {'connected' if n > self.seen[key] else 'disconnected'}")
                    self.seen[key] = n
            if time.monotonic() - last_print > 5:
                last_print = time.monotonic()
                state = "bike connected" if self.bike and self.bike.is_connected else "waiting for bike"
                log.info("%-16s %4d W  %5.1f rpm  %5.1f km/h  %6.0f m  grade %+.1f%%  gear %+d  level %s"
                         "   listening: power %d, cadence %d, kinomap %d   queue-full waits %d",
                         state, r.power, r.cadence, r.road_kmh(), r.road_m(), r.grade, self.gear, r.resistance,
                         self.listeners(CP_MEAS), self.listeners(CSC_MEAS), self.kinomap_count(), self.send_retries)
                self.send_retries = 0

    def listeners(self, char):
        """How many devices are subscribed to a characteristic right now."""
        return len(self.subscribers(char))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="MRK-S29", help="start of the bike's Bluetooth name")
    ap.add_argument("--wheel", type=int, default=2096,
                    help="wheel circumference in mm; match the watch's setting (default 2096)")
    ap.add_argument("--broadcast", default="SBike Hub",
                    help="name the bridge advertises; macOS only fits 9 characters alongside the sensor types")
    ap.add_argument("--watch-only", action="store_true",
                    help="advertise only as a power meter and speed/cadence sensor, for pairing the watch")
    ap.add_argument("--ui", action="store_true", help="open the control panel in the browser")
    ap.add_argument("--base-level", type=float, default=None,
                    help="resistance level on flat road when Kinomap drives the bike "
                         "(default: a quarter of the way up the bike's range)")
    ap.add_argument("--per-percent", type=float, default=None,
                    help="resistance levels added per 1%% of hill (default: 1/20th of the range)")
    ap.add_argument("--weight", type=float, default=None,
                    help="rider weight in kg, for virtual speed (default: weight_kg in profile.json, else 80)")
    ap.add_argument("--bike-mass", type=float, default=10.0, help="virtual bike weight in kg (default 10)")
    ap.add_argument("--bike-speed", action="store_true",
                    help="pass the S29's own cadence-based speed through instead of virtual speed")
    ap.add_argument("--no-auto", action="store_true", help="start with automatic shifting off")
    ap.add_argument("--cadence-low", type=float, default=65,
                    help="auto-shift easier below this rpm (default 65 while training up)")
    ap.add_argument("--cadence-high", type=float, default=80,
                    help="auto-shift harder after holding above this rpm (default 80)")
    ap.add_argument("--upshift-cap-w", type=float, default=None,
                    help="above these watts, only 90+ rpm earns another harder gear (default 90%% of FTP)")
    ap.add_argument("--up-hold", type=float, default=3,
                    help="seconds above --cadence-high before shifting harder (default 3)")
    ap.add_argument("--min-gear", type=int, default=-2,
                    help="auto-shift never goes easier than this gear (default -2: level 3 on the flat)")
    ap.add_argument("--hill-shift-every", type=float, default=3.0,
                    help="shift one gear easier at the start of a climb per this many %% of grade "
                         "(default 3; 0 turns it off)")
    ap.add_argument("--watch-ftms", action="store_true",
                    help="also send smart-bike data to the watch (old behaviour; use if the watch loses power)")
    ap.add_argument("--ramp", type=float, default=1.2,
                    help="seconds between one-level resistance steps (default 1.2)")
    ap.add_argument("--port", type=int, default=8729)
    ap.add_argument("--no-bike", action="store_true",
                    help="no smart bike: the coach, training load, lifting and dashboard only - no Bluetooth at all")
    ap.add_argument("--no-remote", action="store_true",
                    help="panel on this Mac only: no phone remote over Wi-Fi")
    ap.add_argument("-v", action="store_true", help="debug logging")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.v else logging.INFO,
                        format="%(asctime)s  %(message)s", datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(), logging.FileHandler("bridge.log")])
    cb = logging.FileHandler("bluetooth-debug.log")
    cb.setLevel(logging.DEBUG)
    cb.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", "%H:%M:%S"))
    blog = logging.getLogger("bless")
    blog.setLevel(logging.DEBUG)
    blog.propagate = False  # keep the Terminal and bridge.log readable
    blog.addHandler(cb)
    # Keep macOS from napping this process when its window is in the background
    # or the Mac is idle: App Nap delays Bluetooth updates until the watch gives
    # up on the sensor. The token must stay referenced for the whole run.
    from Foundation import NSProcessInfo
    import Foundation as F
    opts = (getattr(F, "NSActivityUserInitiated", 0x00FFFFFF | (1 << 20))
            | getattr(F, "NSActivityLatencyCritical", 0xFF00000000)
            | getattr(F, "NSActivityIdleSystemSleepDisabled", 1 << 20))
    _awake = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(opts, "S-Bike Hub bike bridge")  # noqa: F841
    b = Bridge(args)
    import panel
    try:
        await panel.serve(b, args.port, lan=not args.no_remote)
    except OSError:
        print(f"Port {args.port} is busy: the bridge is probably already running.")
        if args.ui:
            webbrowser.open(f"http://127.0.0.1:{args.port}")
        return
    if args.no_bike:
        log.info("No-bike mode: coach, training load, lifting and the dashboard - Bluetooth stays off")
    else:
        await b.run_server()
    if b.resumed and not args.no_bike:
        b.restore(b.resumed)
    elif args.ui:
        webbrowser.open(f"http://127.0.0.1:{args.port}")   # no new browser tab on an automatic restart
    b.snapshot()
    # Closing the Terminal window (SIGHUP) does NOT stop the bridge: Terminal is
    # only there because macOS gives it the Bluetooth permission. The window's
    # output goes to the log from then on; stop with the panel or the menu icon.
    # A normal kill (SIGTERM) is a deliberate stop: stop cleanly so the watchdog
    # leaves it alone.
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGHUP, window_closed, b)
    loop.add_signal_handler(signal.SIGTERM, b.stop.set)
    tasks = [asyncio.create_task(b.supervised(n, f)) for n, f in
             ((("Bike link", b.run_bike), ("Sensors", b.run_sensors), ("Sender", b.run_outbox),
               ("Resistance ramp", b.run_ramp), ("Crash snapshots", b.run_snapshots)) if not args.no_bike else ())]
    await b.stop.wait()
    g = b.ghost.gap()
    if g and g[0] is not None:
        b.event(f"Ghost result: {abs(g[0])} s {'ahead of' if g[0] < 0 else 'behind'} {b.ghost.match.name}")
    b.bests.finish()                     # an effort still going when the ride ends
    b.event("Stopping")
    try:                                 # the ride's post: infographic, caption, pack for Claude
        import posts
        st = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, posts.make, b.csv_path), 60)
        if st:
            log.info(f"Ride post ready: {posts.folder(b.csv_path)} (open /posts)")
    except Exception as e:
        log.info(f"Couldn't make the ride post: {e}")
    b.snapshot(running=False)
    for t in tasks:
        t.cancel()
    try:
        await b.server.stop()
    except Exception:
        pass
    if b.bike and b.bike.is_connected:
        await b.bike.disconnect()
    try:
        import report
        out = report.build(b.csv_path)
        if out:
            print(f"Ride report: {out}")
            webbrowser.open(out.resolve().as_uri())
    except Exception as e:
        print(f"(No ride report: {e})")
    print("Stopped. Ride saved in ./rides")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped. Ride saved in ./rides")
