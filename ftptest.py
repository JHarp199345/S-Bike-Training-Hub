"""ftptest.py - a ramp test that measures FTP instead of guessing it.

    warm-up    5 min at ~50% of the current FTP estimate
    ramp       from ~55% of the estimate, +10 W every minute, held by ERG
    the end    cadence under 50 for 10 s, or power under 85% of the target
               for 15 s (after the first 20 s of a step), or the Stop button
    cool-down  5 min easy

FTP = 75% of the best 1-minute average power reached - the standard ramp-test
estimate (it's what Zwift and TrainerRoad use). The ramp has to run at least
4 minutes for the number to mean anything; stopped earlier, there's no result.

Everything here is measured power from the bike. The S29 estimates power from
resistance and cadence rather than measuring force, so the result is exact for
this bike - the same bike every workout uses - even if a power meter would
read a little differently.
"""
import collections

WARMUP, RAMP, COOLDOWN, DONE = "warm-up", "ramp", "cool-down", "done"


class RampTest:
    def __init__(self, estimate, now, warmup=300, step=60, increment=10, cooldown=300):
        self.estimate = estimate
        self.warm_w = max(60, round(estimate * 0.5 / 5) * 5)
        self.start_w = max(70, round(estimate * 0.55 / 10) * 10)
        self.cool_w = max(50, round(estimate * 0.45 / 5) * 5)
        self.warmup, self.step, self.increment, self.cooldown = warmup, step, increment, cooldown
        self.phase, self.phase_at = WARMUP, now
        self.window = collections.deque()       # (t, watts) for the rolling 60 s average
        self.best_1min = 0.0
        self.low_cad_since = self.low_pow_since = self.stopped_since = None
        self.started_at = now
        self.prediction = self.preview(estimate)
        self.result = None                      # FTP in watts, once the ramp ends
        self.reason = ""

    @staticmethod
    def preview(estimate):
        """Same prescription as the controller; prediction is frozen before testing."""
        warm = max(60, round(estimate * 0.5 / 5) * 5)
        start = max(70, round(estimate * 0.55 / 10) * 10)
        cool = max(50, round(estimate * 0.45 / 5) * 5)
        peak = round(estimate / 0.75)
        minutes = max(4, int(max(0, peak - start) // 10) + 1)
        return {"warmup_s": 300, "warm_w": warm, "start_w": start,
                "increment_w": 10, "step_s": 60, "cooldown_s": 300, "cool_w": cool,
                "predicted_ftp": estimate, "predicted_peak_w": peak,
                "predicted_ramp_minutes": minutes, "basis": "Current FTP estimate only",
                "confidence": "Low: a baseline forecast, not an independently validated prediction",
                "blocks": [[300, warm]] + [[60, start + 10 * i] for i in range(minutes)] + [[300, cool]]}

    def comparison(self):
        return {"prediction": self.prediction, "actual_ftp": self.result,
                "error_w": self.result - self.prediction["predicted_ftp"] if self.result is not None else None,
                "reason": self.reason}

    def target(self, now):
        t = now - self.phase_at
        if self.phase == WARMUP:
            return self.warm_w
        if self.phase == RAMP:
            return self.start_w + self.increment * int(t // self.step)
        if self.phase == COOLDOWN:
            return self.cool_w
        return None

    def update(self, now, power, cadence):
        """Once a second. Returns the ERG target in watts, or None when finished."""
        t = now - self.phase_at
        if self.phase == WARMUP and t >= self.warmup:
            self.phase, self.phase_at = RAMP, now
        elif self.phase == RAMP:
            self.window.append((now, power))
            while self.window and now - self.window[0][0] > 60:
                self.window.popleft()
            if len(self.window) >= 55:          # a full minute of readings
                self.best_1min = max(self.best_1min, sum(p for _, p in self.window) / len(self.window))
            tgt = self.target(now)
            self.low_cad_since = (self.low_cad_since or now) if 0 < cadence < 50 else None
            self.stopped_since = (self.stopped_since if self.stopped_since is not None else now) if cadence <= 0 and power <= 0 else None
            into_step = t % self.step
            weak = power < 0.85 * tgt and into_step >= 20
            self.low_pow_since = (self.low_pow_since or now) if weak else None
            if self.stopped_since is not None and now - self.stopped_since >= 5:
                self.finish(now, "pedaling stopped for 5 seconds")
            elif self.low_cad_since and now - self.low_cad_since >= 10:
                self.finish(now, "cadence fell under 50 rpm")
            elif self.low_pow_since and now - self.low_pow_since >= 15:
                self.finish(now, f"couldn't hold {tgt} W")
        elif self.phase == COOLDOWN and t >= self.cooldown:
            self.phase = DONE
        return self.target(now)

    def finish(self, now, reason):
        """End the ramp (also the Stop button) and work out FTP."""
        if self.phase == WARMUP:                # stopped before the ramp: no result, just cool down
            self.phase, self.phase_at, self.reason = COOLDOWN, now, reason
            return
        if self.phase != RAMP:                  # already cooling down or done
            return
        ramp_secs = now - self.phase_at
        self.reason = reason
        if ramp_secs >= 240 and self.best_1min > 0:
            self.result = round(0.75 * self.best_1min)
        self.phase, self.phase_at = COOLDOWN, now

    def status(self, now):
        t = now - self.phase_at
        s = {"phase": self.phase, "target": self.target(now), "best_1min": round(self.best_1min),
             "result": self.result, "reason": self.reason, "estimate": self.estimate,
             "elapsed": max(0, int(now - self.started_at)), "protocol": self.prediction,
             "comparison": self.comparison()}
        if self.phase == WARMUP:
            s["left"] = int(self.warmup - t)
        elif self.phase == RAMP:
            s["step_left"] = int(self.step - t % self.step)
            s["minutes"] = int(t // 60)
        elif self.phase == COOLDOWN:
            s["left"] = int(self.cooldown - t)
        return s
