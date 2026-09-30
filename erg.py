"""erg.py - hold a target wattage on a bike that can't.

The S29 accepts a resistance level, not a power target (its FTMS feature list
has no power-target bit). ERG mode closes the loop here instead: every few
seconds it compares the last few seconds of power with the target and moves
the resistance one level.

    power well under target, legs still turning  -> one level harder
    power well over target                       -> one level easier
    cadence collapsing                           -> easier, whatever the target says

The last rule is the safety valve: a trainer that keeps adding resistance to
a rider who is slowing down drives the cadence to zero. The rider always wins.

Workouts are lists of steps, each a duration and a wattage, run in order.
"""
import collections
import json
from pathlib import Path


class Erg:
    def __init__(self, band=0.07, every=3.0, min_cadence=55):
        self.band = band                  # +/- fraction of target counted as "on target"
        self.every = every                # seconds between adjustments
        self.min_cadence = min_cadence    # below this, only ever easier
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

    def update(self, power, cadence, now):
        """-1, 0 or +1 levels."""
        if not self.on:
            return 0
        self._advance_workout(now)
        if not self.on:
            return 0
        self.samples.append((now, power, cadence))
        while self.samples and now - self.samples[0][0] > 4:
            self.samples.popleft()
        if now - self.last_move < self.every or len(self.samples) < 3 or cadence < 20:
            return 0
        avg_p = sum(p for _, p, _ in self.samples) / len(self.samples)
        avg_c = sum(c for _, _, c in self.samples) / len(self.samples)
        move = 0
        if avg_c < self.min_cadence:
            move = -1
        elif avg_p < self.target * (1 - self.band):
            move = +1
        elif avg_p > self.target * (1 + self.band):
            move = -1
        if move:
            self.last_move = now
            self.samples.clear()
        return move

    # ── workouts ────────────────────────────────────────────────────────────
    def start_workout(self, workout, now):
        steps = [(float(s["minutes"]) * 60, float(s["watts"])) for s in workout["steps"]]
        self.workout = {"name": workout["name"], "steps": steps, "started": now}
        self.set(steps[0][1], f"workout '{workout['name']}'", now)

    def stop_workout(self, now):
        self.workout = None
        self.set(None, "", now)

    def workout_status(self, now):
        w = self.workout
        if not w:
            return None
        elapsed = now - w["started"]
        total = sum(d for d, _ in w["steps"])
        t = 0
        for i, (d, watts) in enumerate(w["steps"]):
            if elapsed < t + d:
                return {"name": w["name"], "step": i + 1, "steps": len(w["steps"]), "watts": watts,
                        "step_left": int(t + d - elapsed), "left": int(total - elapsed),
                        "elapsed": round(elapsed, 1), "total": int(total),          # the game view draws the workout ahead
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
