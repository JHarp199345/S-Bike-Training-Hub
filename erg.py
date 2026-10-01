"""erg.py - hold a target wattage on a bike that can't.

The S29 accepts a resistance level, not a power target (its FTMS feature list
has no power-target bit). ERG mode closes the loop here instead, in zones around
the target (the rider's design, 2026-09-30 - the old +/-7% band moved every 3 s and felt hectic):

    green   100-120% of target   hold: the target is the minimum goal
    yellow  80-100% / 120-140%   shift one level after 2 minutes there
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
import statistics
from pathlib import Path


class Erg:
    ZONES = [("green", 1.00, 1.20, None), ("yellow", 0.80, 1.40, 120.0), ("red", 0.65, 1.60, 30.0), ("black", 0.0, 9e9, 8.0)]

    def __init__(self, band=0.07, every=15.0, min_cadence=55, ftp=180):
        self.band = band                  # kept for callers; the zones above decide now
        self.every = every                # seconds to settle after a shift
        self.min_cadence = min_cadence    # below this for 5 s, only ever easier
        self.zone, self.zone_side, self.zone_since = "green", 0, None
        self.low_since = None
        self.adjust_since, self.adjust_side = None, 0
        self.paused = False               # paused by hand
        self.auto_paused = False          # paused because the rider stopped (or the bike dropped)
        self.target = None                # watts, or None when ERG is off
        self.source = ""
        self.samples = collections.deque()
        self.last_move = 0.0
        self.workout = None               # {"name", "steps": [(seconds, watts)], "started": t}
        self.ftp = ftp
        self.segment_samples = collections.deque()
        self.observed_level = None
        self.level_rates = {}             # measured watts/rpm at settled resistance levels
        self.easier_since = None

    @property
    def easy_block(self):
        source = getattr(self, "source", "")
        ftp = getattr(self, "ftp", 180)
        return source.startswith("workout ") and self.target is not None and self.target <= .75 * ftp

    def zones(self):
        # Easy blocks need room for discrete gears, not a lower power goal.
        # At a planned 90 W this is 90–150 W; it scales with each planned step.
        if self.easy_block:
            ftp = getattr(self, "ftp", 180)
            ceiling = max(1.0, min(5 / 3, .75 * ftp / self.target))
            return [("green", 1.0, ceiling, None), ("yellow", .8, 1.8, 120.0),
                    ("red", .65, 2.0, 30.0), ("black", 0.0, 9e9, 8.0)]
        return self.ZONES

    @property
    def on(self):
        return self.target is not None

    def set(self, watts, source, now):
        self.target = None if watts is None else max(30, min(400, int(watts)))
        self.source = source
        self.easier_since = None
        self.samples.clear()
        self.segment_samples.clear()
        self.last_move = now              # give the rider a moment before the first move
        self.zone, self.zone_side, self.zone_since = "green", 0, None
        self.adjust_since, self.adjust_side = None, 0
        self.low_since = None

    GEAR = (0.72, 0.17)                   # the S29: watts = (a + b x level) x cadence (session.S29_W)

    def predict(self, watts, level, move):
        """The watts one gear from here at the same cadence."""
        if level in self.level_rates and level + move in self.level_rates:
            return watts * self.level_rates[level + move] / self.level_rates[level]
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
        if level is not None and level != self.observed_level:
            if self.observed_level is not None:
                # Physical/manual changes invalidate readings from the previous gear.
                self.samples.clear()
                self.segment_samples.clear()
                self.last_move = now
                self.adjust_since, self.adjust_side = None, 0
                self.low_since = self.easier_since = None
            self.observed_level = level
        if cadence < 20:
            self.segment_samples.clear()
        elif self.workout:
            self.segment_samples.append((now, power, cadence))
            while self.segment_samples and now - self.segment_samples[0][0] > 30:
                self.segment_samples.popleft()
        if self.source in ("FTP test", "Kinomap"):
            return self._strict(power, cadence, now)   # max efforts that follow a target exactly; workouts and held watts use zones
        self.samples.append((now, power, cadence))
        while self.samples and now - self.samples[0][0] > 10:
            self.samples.popleft()
        if len(self.samples) < 3 or cadence < 20:
            return 0
        avg_p = sum(p for _, p, _ in self.samples) / len(self.samples)
        avg_c = sum(c for _, _, c in self.samples) / len(self.samples)
        if level is not None and now - self.last_move >= self.every and avg_c >= self.min_cadence:
            self.level_rates[level] = avg_p / avg_c
        zone, side = self.classify(avg_p)
        if (zone, side) != (self.zone, self.zone_side) or self.zone_since is None:
            self.zone, self.zone_side, self.zone_since = zone, side, now
        # The rider is continuously short of watts even when fluctuations cross
        # the yellow/red boundary. Keep the correction timer until power reaches
        # green or changes sides; the display's zone timer can still restart.
        if side == 0:
            self.adjust_since, self.adjust_side = None, 0
        elif side != self.adjust_side or self.adjust_since is None:
            self.adjust_since, self.adjust_side = now, side
        self.low_since = (self.low_since or now) if avg_c < self.min_cadence else None
        if now - self.last_move < self.every:
            return 0
        move = 0
        if self.low_since is not None and now - self.low_since >= 5:
            move = -1                     # the legs are bogging down: easier
        else:
            wait = next(w for name, _, _, w in self.zones() if name == zone)
            if side > 0 and wait is not None:
                wait = 60.0 if avg_p >= self.target * .95 else min(wait, 15.0)
                if power >= self.target:
                    # A recovered reading is not a reason to shift harder on stale lows.
                    self.adjust_since = now
            if wait is not None and self.adjust_since is not None and now - self.adjust_since >= wait:
                move = side
                # Look before shifting: yellow is still on the road, so a shift out of it must land in green or
                # yellow - never throw the rider off the road. From red or black, only shift if it gets closer.
                if level is not None:
                    after = self.predict(avg_p, level, move)
                    new_zone, _ = self.classify(after)
                    closer = abs(after / self.target - 1) < abs(avg_p / self.target - 1)
                    ok = new_zone in ("green", "yellow") if zone == "yellow" else closer
                    if side > 0 and self.target <= after <= self.target * self.zones()[0][2]:
                        ok = True         # reaching the floor wins over staying equally far below it
                    if not ok:
                        move = 0
                        self.zone_since = now     # hold, and look again after another full wait
                        self.adjust_since = now
            # Prefer the easiest successful gear, after a sustained margin.
            # Only use a measured lower gear here: an untested model can be too optimistic.
            can_ease = (side <= 0 and level is not None and level > 1
                        and level - 1 in self.level_rates
                        and self.predict(avg_p, level, -1) >= self.target * 1.03)
            self.easier_since = (now if self.easier_since is None else self.easier_since) if can_ease else None
            if can_ease and now - self.easier_since >= 30:
                move = -1
        if move:
            self.last_move = now
            self.samples.clear()
            self.zone_since = now
            self.low_since = None
            self.adjust_since, self.adjust_side = None, 0
            self.easier_since = None
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
        for name, lo, hi, _ in self.zones():
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
        blocks = workout.get("blocks") or []
        adaptive = len(blocks) > 1 and (blocks[1].get("type") == "ramp" or
                                      blocks[0].get("label", "").lower() in ("warm-up", "warmup"))
        windows, t = [], 0.0
        for block in blocks:
            duration = float(block.get("minutes") or 0) * 60
            if block.get("type") == "intervals":
                reps = int(block.get("times") or 1)
                duration = reps * float((block.get("on") or {}).get("minutes") or 0) * 60
                duration += (reps if block.get("rest_after_last") else reps - 1) * float((block.get("off") or {}).get("minutes") or 0) * 60
            if block.get("type") == "ramp":
                windows.append((t, t + duration))
            t += duration
        self.workout = {"name": workout["name"], "steps": steps, "started": now, "active": 0.0, "last": now,
                        "adaptive": adaptive, "planned_steps": list(steps), "scale": 1.0,
                        "segment_index": 0, "adjustments": [], "ramp_windows": windows,
                        "easy_program": max(p for _, p in steps) <= .75 * self.ftp}
        self.segment_samples.clear()
        self.paused = False
        self.set(steps[0][1], f"workout '{workout['name']}'", now)

    def stop_workout(self, now):
        self.workout = None
        self.set(None, "", now)

    def workout_status(self, now):
        w = self.workout
        if not w:
            return None
        elapsed = w.get("active") or (now - w["started"])     # pedalling time, not wall time: stopping pauses it
        total = sum(d for d, _ in w["steps"])
        t = 0
        source = getattr(self, "source", "")
        ftp = getattr(self, "ftp", 180)
        for i, (d, watts) in enumerate(w["steps"]):
            if elapsed < t + d:
                easy = source.startswith("workout ") and watts <= .75 * ftp
                ramping = any(a <= elapsed < z for a, z in w.get("ramp_windows", []))
                return {"name": w["name"], "step": i + 1, "steps": len(w["steps"]), "watts": watts,
                        "step_left": int(t + d - elapsed), "left": int(total - elapsed),
                        "elapsed": round(elapsed, 1), "total": int(total),          # the game view draws the workout ahead
                        "paused": getattr(self, "paused", False), "auto_paused": getattr(self, "auto_paused", False),
                        "zone": getattr(self, "zone", "green"),
                        "zone_for": round(now - self.zone_since) if getattr(self, "zone_since", None) else 0,
                        "power_floor": watts,
                        "power_band": [watts, round(max(watts, min(watts * 5 / 3, .75 * ftp)) if easy else watts * 1.4)],
                        "cadence_band": [55, 110] if ramping else [70, 90] if w.get("adaptive") or easy else None,
                        "ramping": ramping,
                        "easy_block": easy,
                        "adaptive": w.get("adaptive", False), "scale": w.get("scale", 1.0),
                        "adjustment": (w.get("adjustments") or [None])[-1],
                        "zones": [[name, lo, hi] for name, lo, hi, _ in self.zones()],
                        "blocks": [[int(d2), int(w2)] for d2, w2 in w["steps"]]}
            t += d
        return None

    def adaptive_state(self):
        w = self.workout or {}
        return {k: w[k] for k in ("adaptive", "planned_steps", "scale", "segment_index", "adjustments", "ramp_windows", "easy_program") if k in w}

    def _adapt_segment(self, old, new):
        w = self.workout
        base = w.get("planned_steps") or w["steps"]
        valid = [(t, p) for t, p, c in self.segment_samples if 70 <= c <= 90]
        # Twenty seconds at the intended rhythm, using the last thirty seconds'
        # median: pauses and isolated power spikes never set the next effort.
        if (not w.get("adaptive") or len(valid) < 20 or valid[-1][0] - valid[0][0] < 19):
            return
        anchor = statistics.median(p for _, p in valid)
        scale = max(1.0, anchor / base[old][1])
        # Keep a planned easy program inside its original easy intensity class.
        # A harder prescribed program retains its planned work targets.
        if w.get("easy_program"):
            peak = max(p for _, p in base) if old == 0 else max(p for _, p in base[new:])
            scale = min(scale, max(1.0, .75 * self.ftp / peak))
        elif old == 0:
            scale = 1.0
        indices = []
        if old == 0:
            indices = list(range(new, len(base)))
            w["scale"] = scale
        elif base[old][0] >= 60 and base[new][1] < base[old][1]:
            # Rebase recovery/cooldown from the completed interval, stopping at
            # the next work interval so repetitions do not ratchet ever upward.
            for i in range(new, len(base)):
                if base[i][1] >= base[old][1]:
                    break
                indices.append(i)
        for i in indices:
            w["steps"][i] = (base[i][0], round(base[i][1] * scale))
        if indices:
            w["adjustments"].append({"after_step": old + 1, "anchor_watts": round(anchor),
                                     "scale": round(scale, 3), "scope": "remaining workout" if old == 0 else "recovery"})

    def _advance_workout(self, now):
        if not self.workout:
            return
        s = self.workout_status(now)
        if s is None:                     # finished
            self.workout = None
            self.target, self.source = None, "workout finished"
            self.segment_samples.clear()
            return
        new = s["step"] - 1
        old = self.workout.get("segment_index", new)
        if new != old:
            self._adapt_segment(old, new)
            self.segment_samples.clear()
            self.workout["segment_index"] = new
            s = self.workout_status(now)
        if s["watts"] != self.target:
            self.target = int(s["watts"])
            self.samples.clear()
            self.zone, self.zone_side, self.zone_since = "green", 0, None
            self.adjust_since, self.adjust_side = None, 0
            self.low_since = None
            self.last_move = now


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
