"""autoshift.py - shift gears for the rider, from cadence.

Riding a smart bike hands-free means something has to shift for you. The rule
is the one an electronic auto-shifting drivetrain uses - keep the legs turning
inside a cadence band (default 65-80 rpm):

    cadence sagging below the band, or ragged and falling  -> shift easier
    cadence spinning above the band                         -> shift harder

Gears don't change speed directly. Virtual speed comes from watts, so a harder
gear at the same cadence means more watts and more road per pedal stroke, and
an easier one means less.

Shifting harder just because cadence is steady would keep adding load with no
ceiling, so it only happens toward a watt range - the day's focus (focus.py,
2026-09-28): inside the cadence range, watts short of the range with legs to
spare earn a harder gear; watts over it with room to spin faster get an easier
one. Cadence always comes first. With no watt range, it's cadence only.
"""
import collections
import statistics
import time


class AutoShift:
    def __init__(self, shift, low=70, high=80, up_hold=15, hr_ceiling=None, clock=time.monotonic,
                 climb_low=30, climb_high=45, power_cap=None):
        self.shift = shift            # callable(delta, reason) -> bool (False if already at the limit)
        self.low, self.high = low, high
        self.normal_band = (low, high)
        self.climb_band = (climb_low, climb_high)   # standing, big gear, driving a hill
        self.climbing = False
        self.climb_auto = False       # True when a hand shift on a hill turned it on (ends at the crest)
        self.up_hold = up_hold        # seconds above `high` before shifting harder
        self.hr_ceiling = hr_ceiling
        self.clock = clock
        self.enabled = True
        self.ema = None
        self.history = collections.deque()   # (t, cadence) for the last 30 s of pedalling
        self.below_since = self.above_since = None
        self.hr_high_since = None
        self.hold_until = 0.0                # no automatic shift before this time
        self.last_action = ""
        self.up_streak = 0                   # harder shifts in a row, for the rev-up pacing
        self.power_cap = power_cap           # watts above which only real spinning earns another gear
        self.last_hill_change = -1e9
        self.watt_band = None                # (lo, hi) W to steer toward inside the cadence range, or None
        self.pw = None                       # smoothed watts
        self.w_low_since = self.w_high_since = None
        self.limited = None                  # "easiest" / "hardest" when the last automatic shift hit the end
        self.watt_hold = 15                  # seconds out of the watt range before shifting for it

    # ── the day's focus ────────────────────────────────────────────────────
    def set_focus(self, rpm=None, watts=None):
        """A cadence range to keep and a watt range to steer toward (None: cadence only)."""
        if rpm:
            self.normal_band = (float(rpm[0]), float(rpm[1]))
            if not self.climbing:
                self.low, self.high = self.normal_band
        self.watt_band = (float(watts[0]), float(watts[1])) if watts else None
        self._reset_timers()

    # ── climbing mode ──────────────────────────────────────────────────────
    def set_climbing(self, on, auto=False):
        """Standing on a climb you may want a big gear at low cadence, and the
        normal band would keep shifting you out of it. Climbing mode swaps the
        band for 30-45 rpm."""
        self.climbing, self.climb_auto = on, (auto and on)
        self.low, self.high = self.climb_band if on else self.normal_band
        self._reset_timers()
        self.history.clear()

    # ── events from the bridge ──────────────────────────────────────────────
    def hill_changed(self):
        """Give the rider a moment to respond to a new grade before judging it."""
        self.last_hill_change = self.clock()
        self.hold_until = max(self.hold_until, self.clock() + 6)
        self._reset_timers()

    def manual_shift(self):
        """The rider shifted by hand: stay out of the way for 30 s."""
        self.hold_until = max(self.hold_until, self.clock() + 30)
        self._reset_timers()

    # ── once a second ───────────────────────────────────────────────────────
    def update(self, cadence, hr=None, power=None):
        now = self.clock()
        if cadence < 20:
            # Coasting or stopped: nothing to judge, and the first strokes after
            # a stop are always slow.
            self.ema = self.pw = None
            self.history.clear()
            self._reset_timers()
            return None
        if self.ema is None:
            # Pedalling again after a stop: the first strokes are always slow.
            # 8 s was too short: in testing it shifted twice while the rider was
            # still getting up to speed (42, 48 rpm) and landed on level 1.
            self.hold_until = max(self.hold_until, now + 15)
        # Smoothing: enough to ignore a single odd stroke, light enough that an
        # up-shift lands ~5 s after cadence crosses the top of the band (0.25 made it ~7-8 s).
        self.ema = cadence if self.ema is None else self.ema + 0.4 * (cadence - self.ema)
        if power is not None:
            self.pw = power if self.pw is None else self.pw + 0.2 * (power - self.pw)
        if now >= self.hold_until:
            # Strokes during a grace period (restart, new hill, just shifted) are
            # the rider adapting, not a verdict on the gear; keep them out of the
            # "unsteady" judgement.
            self.history.append((now, cadence))
        while self.history and now - self.history[0][0] > 30:
            self.history.popleft()

        # Heart rate over the ceiling for 10 s beats everything else.
        if hr and self.hr_ceiling and hr > self.hr_ceiling:
            self.hr_high_since = self.hr_high_since or now
            if now - self.hr_high_since >= 10 and self._may_shift(now):
                return self._do(-1, f"heart rate {hr} over {self.hr_ceiling}", now)
        else:
            self.hr_high_since = None

        if not self._may_shift(now):
            # Grace periods don't count toward "below/above for N seconds": the
            # clock starts once the grace ends, so a ramp-up isn't held against the rider.
            self._reset_timers()
            return None
        self.below_since = (self.below_since or now) if self.ema < self.low else None
        self.above_since = (self.above_since or now) if self.ema > self.high else None

        # Well below the band: shift sooner. If cadence collapses right after the
        # road changed (a climb arriving on top of a heavy gear), drop two at once.
        if self.below_since and now - self.below_since >= (3 if self.ema < self.low - 10 else 5):
            if now - self.last_hill_change <= 25 and self.ema < self.low - 15:
                return self._do(-2, f"cadence collapsed to {self.ema:.0f} rpm after the road changed", now)
            return self._do(-1, f"cadence {self.ema:.0f} rpm, under {self.low}", now)

        # Ragged and sagging over the last 30 s: the "up and down, having a hard
        # time maintaining" pattern.
        if len(self.history) >= 20:
            cads = [c for _, c in self.history]
            mean, spread = statistics.fmean(cads), statistics.pstdev(cads)
            if spread > 10 and mean < self.low + 8:
                return self._do(-1, f"cadence unsteady ({mean:.0f} ± {spread:.0f} rpm)", now)

        # The watt range, inside the cadence range (not while climbing): short of it with legs to spare
        # (7+ rpm above the bottom) -> harder gear, same legs, more watts; over it with room to spin faster
        # (2+ rpm under the top) -> easier gear. (A harder gear at the top of the watt range is blocked below, so
        # the legs speeding up after an easier gear don't bounce it straight back.) Out of range for watt_hold seconds, so hills and surges don't count.
        if self.watt_band and not self.climbing and self.pw is not None and self.low <= self.ema <= self.high:
            wlo, whi = self.watt_band
            self.w_low_since = (self.w_low_since or now) if (self.pw < wlo and self.ema >= self.low + 7) else None
            self.w_high_since = (self.w_high_since or now) if (self.pw > whi and self.ema <= self.high - 2) else None
            if self.w_low_since and now - self.w_low_since >= self.watt_hold:
                return self._do(+1, f"{self.pw:.0f} W, under {wlo:.0f} at {self.ema:.0f} rpm", now)
            if self.w_high_since and now - self.w_high_since >= (5 if self.pw > 1.2 * whi else self.watt_hold):   # well over: sooner
                return self._do(-1, f"{self.pw:.0f} W, over {whi:.0f} at {self.ema:.0f} rpm", now)
        else:
            self.w_low_since = self.w_high_since = None

        # Above the band: shift harder, sooner the harder the rider is spinning (the
        # "rev it" rule): just over the top waits up_hold, +5 rpm ~1.5 s, +10 about a second.
        if self.ema <= self.high:
            self.up_streak = 0               # back in the band: the next run starts quick again
        over = self.ema - self.high
        hold = 1 if over >= 10 else 1.5 if over >= 5 else self.up_hold
        if self.above_since and now - self.above_since >= hold:
            if hr and self.hr_ceiling and hr > self.hr_ceiling - 5:
                return None
            if power and self.power_cap and power >= self.power_cap and over < 10:
                return None                  # heavy already: only real spinning earns another gear
            if power and self.watt_band and power >= self.watt_band[1] and over < 10:
                return None                  # at the top of the watt range: the legs can settle instead
            return self._do(+1, f"cadence {self.ema:.0f} rpm, over {self.high}", now)
        return None

    # ── internals ───────────────────────────────────────────────────────────
    def _may_shift(self, now):
        return self.enabled and now >= self.hold_until

    def _do(self, delta, why, now):
        # Let the new gear settle before judging again. Harder shifts in a row
        # settle 1 s, then 2, then 3 ... (up to 6), like a car getting slower
        # to change as it climbs through the gears; easier shifts settle 10 s.
        if delta > 0:
            self.up_streak += 1
            self.hold_until = now + min(6, self.up_streak)
        else:
            self.up_streak = 0
            self.hold_until = now + 10
        self._reset_timers()
        self.history.clear()
        if not self.shift(delta, "Auto: " + why):
            self.limited = "easiest" if delta < 0 else "hardest"
            return None                      # already in the easiest / hardest gear
        self.limited = None
        self.last_action = f"{'easier' if delta < 0 else 'harder'} - {why}"
        return delta

    def _reset_timers(self):
        self.below_since = self.above_since = None
        self.w_low_since = self.w_high_since = None
