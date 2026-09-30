"""erg.py - hold a target wattage on a bike that can't.

The S29 accepts a resistance level, not a power target (its FTMS feature list
has no power-target bit). ERG mode closes the loop here instead, in zones around
the target (the rider's design, 2026-09-30 - the old +/-7% band moved every 3 s and felt hectic):

    green   90-120% of target    hold: no shifting (extra room on top, to encourage the work)
    yellow  80-90% / 120-140%    shift one level after 2 minutes there
    red     65-80% / 140-160%    after 30 seconds
    black   beyond that          after 8 seconds
    cadence under the floor for 5 s -> easier, whatever the target says (the rider always wins)

Power is judged on a 10-second average; after a shift it waits 15 s for the legs to settle.
The workout clock runs only while the rider pedals with the bike connected: stop and it pauses
(auto-pause), and it can be paused by hand.

The last rule is the safety valve: a trainer that keeps adding resistance to
a rider who is slowing down drives the cadence to zero. The rider always wins.

Workouts are lists of steps, each a duration and a wattage, run in order.
"""
import collections
import json
from pathlib import Path


class Erg:
    ZONES = [("green", 0.90, 1.20, None), ("yellow", 0.80, 1.40, 120.0), ("red", 0.65, 1.60, 30.0), ("black", 0.0, 9e9, 8.0)]

    def __init__(self, band=0.07, every=15.0, min_cadence=55):
        self.band = band                  # kept for callers; the zones above decide now
        self.every = every                # seconds to settle after a shift
        self.min_cadence = min_cadence    # below this for 5 s, only ever easier
        self.zone, self.zone_side, self.zone_since = "green", 0, None
        self.low_since = None
        self.paused = False               # paused by hand
        self.auto_paused = False          # paused because the rider stopped (or the bike dropped)
        self.target = None                # watts, or None when ERG is off
        self.source = ""
        self.samples = collections.deque()
        self.last_move = 0.0
        self.workout = None               # {"name", "steps": [(seconds, watts)], "started": t}

    @property
    def on(self):
        return self.target is not None

    def set(self, watts, source, now):
        self.target = None if watts is None else max(30, min(400, int(watts)))
        self.source = source
        self.samples.clear()
        self.last_move = now              # give the rider a moment before the first move

    GEAR = (0.72, 0.17)                   # the S29: watts = (a + b x level) x cadence (session.S29_W)

    def predict(self, watts, level, move):
        """The watts one gear from here at the same cadence."""
        a, b = self.GEAR
        return watts * (a + b * (level + move)) / max(0.1, a + b * level)

    def update(self, power, cadence, now, level=None):
        """-1, 0 or +1 levels. `level` (the bike's current resistance) lets it look before it shifts."""
        if not self.on:
            return 0
        self.tick_clock(now, cadence, True)   # pedalling time moves the workout clock (the bridge also ticks it each second)
        self._advance_workout(now)
        if not self.on:
            return 0
        if self.paused:
            return 0
        if self.source in ("FTP test", "Kinomap"):
            return self._strict(power, cadence, now)   # max efforts that follow a target exactly; workouts and held watts use zones
        self.samples.append((now, power, cadence))
        while self.samples and now - self.samples[0][0] > 10:
            self.samples.popleft()
        if len(self.samples) < 3 or cadence < 20:
            return 0
        avg_p = sum(p for _, p, _ in self.samples) / len(self.samples)
        avg_c = sum(c for _, _, c in self.samples) / len(self.samples)
        zone, side = self.classify(avg_p)
        if (zone, side) != (self.zone, self.zone_side) or self.zone_since is None:
            self.zone, self.zone_side, self.zone_since = zone, side, now
        self.low_since = (self.low_since or now) if avg_c < self.min_cadence else None
        if now - self.last_move < self.every:
            return 0
        move = 0
        if self.low_since is not None and now - self.low_since >= 5:
            move = -1                     # the legs are bogging down: easier
        else:
            wait = next(w for name, _, _, w in self.ZONES if name == zone)
            if wait is not None and now - self.zone_since >= wait:
                move = side
                # Look before shifting: yellow is still on the road, so a shift out of it must land in green or
                # yellow - never throw the rider off the road. From red or black, only shift if it gets closer.
                if level is not None:
                    after = self.predict(avg_p, level, move)
                    new_zone, _ = self.classify(after)
                    closer = abs(after / self.target - 1) < abs(avg_p / self.target - 1)
                    ok = new_zone in ("green", "yellow") if zone == "yellow" else closer
                    if not ok:
                        move = 0
                        self.zone_since = now     # hold, and look again after another full wait
        if move:
            self.last_move = now
            self.samples.clear()
            self.zone_since = now
            self.low_since = None
        return move

    def _strict(self, power, cadence, now):
        """Tight control (the original): +/-7% on a 4-second average, a move every 3 s - for tests and held watts."""
        self.samples.append((now, power, cadence))
        while self.samples and now - self.samples[0][0] > 4:
            self.samples.popleft()
        if now - self.last_move < 3.0 or len(self.samples) < 3 or cadence < 20:
            return 0
        avg_p = sum(p for _, p, _ in self.samples) / len(self.samples)
        avg_c = sum(c for _, _, c in self.samples) / len(self.samples)
        move = -1 if avg_c < self.min_cadence else +1 if avg_p < self.target * (1 - self.band) else -1 if avg_p > self.target * (1 + self.band) else 0
        if move:
            self.last_move = now
            self.samples.clear()
        return move

    def classify(self, watts):
        """(zone, side): side +1 = under target (a harder gear), -1 = over (easier), 0 = green."""
        r = watts / self.target if self.target else 1.0
        for name, lo, hi, _ in self.ZONES:
            if lo <= r <= hi:
                return name, (0 if name == "green" else (1 if r < 1 else -1))
        return "black", (1 if r < 1 else -1)

    def tick_clock(self, now, cadence, connected):
        """Once a second: the workout clock advances only while the rider pedals with the bike connected."""
        w = self.workout
        if not w:
            return
        dt = min(5.0, max(0.0, now - (w.get("last") or now)))
        w["last"] = now
        running = connected and cadence >= 15 and not self.paused
        self.auto_paused = not running and not self.paused
        if running:
            w["active"] = w.get("active", 0.0) + dt

    # ── workouts ────────────────────────────────────────────────────────────
    def start_workout(self, workout, now):
        steps = [(float(s["minutes"]) * 60, float(s["watts"])) for s in workout["steps"]]
        self.workout = {"name": workout["name"], "steps": steps, "started": now, "active": 0.0, "last": now}
        self.paused = False
        self.set(steps[0][1], f"workout '{workout['name']}'", now)

    def stop_workout(self, now):
        self.workout = None
        self.set(None, "", now)

    def workout_status(self, now):
        w = self.workout
        if not w:
            return None
        elapsed = w.get("active", now - w["started"])     # pedalling time, not wall time: stopping pauses it
        total = sum(d for d, _ in w["steps"])
        t = 0
        for i, (d, watts) in enumerate(w["steps"]):
            if elapsed < t + d:
                return {"name": w["name"], "step": i + 1, "steps": len(w["steps"]), "watts": watts,
                        "step_left": int(t + d - elapsed), "left": int(total - elapsed),
                        "elapsed": round(elapsed, 1), "total": int(total),          # the game view draws the workout ahead
                        "paused": getattr(self, "paused", False), "auto_paused": getattr(self, "auto_paused", False),
                        "zone": getattr(self, "zone", "green"),
                        "zone_for": round(now - self.zone_since) if getattr(self, "zone_since", None) else 0,
                        "blocks": [[int(d2), int(w2)] for d2, w2 in w["steps"]]}
            t += d
        return None

    def _advance_workout(self, now):
        if not self.workout:
            return
        s = self.workout_status(now)
        if s is None:                     # finished
            self.workout = None
            self.target, self.source = None, "workout finished"
        elif s["watts"] != self.target:
            self.target = int(s["watts"])
            self.samples.clear()


def load_workouts(folder):
    out = []
    for f in sorted(Path(folder).glob("*.json")):
        try:
            w = json.loads(f.read_text())
            if w.get("steps"):
                w["id"] = f.stem
                out.append(w)
        except (OSError, ValueError):
            pass
    return out
