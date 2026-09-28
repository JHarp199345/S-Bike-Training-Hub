"""watchdog.py - decides when the menu icon should restart the bridge.

Kept apart from menubar.py so it can be tested without a menu bar.

    crashed  the state file says the bridge was running, but its process is gone
             -> restart it; it resumes the same ride (bridge.resumable_state)
    frozen   the process is alive but hasn't answered for 20 s
             -> kill it and restart, which also resumes

A deliberate stop (Stop button, closing the Terminal window) writes
running=false, so neither case fires. Restarts are rate-limited: three in ten
minutes means something is badly wrong, and restarting forever would only hide
it - the watchdog stops and says so.
"""


class Watchdog:
    def __init__(self, hang_after=20, grace=30, max_restarts=3, window=600):
        self.hang_after = hang_after      # seconds without an answer before "frozen"
        self.grace = grace                # seconds to leave a fresh restart alone
        self.max_restarts, self.window = max_restarts, window
        self.silent_since = None
        self.restarts = []                # times of recent restarts
        self.quiet_until = 0.0
        self.gave_up = False

    def tick(self, now, answering, state, alive):
        """Called every few seconds. Returns None, "restart" or "kill_and_restart"."""
        if answering:
            self.silent_since = None
            return None
        if not state.get("running") or now < self.quiet_until or self.gave_up:
            return None
        if alive:
            if self.silent_since is None:
                self.silent_since = now
            if now - self.silent_since < self.hang_after:
                return None
            action = "kill_and_restart"
        else:
            action = "restart"
        self.restarts = [t for t in self.restarts if now - t < self.window]
        if len(self.restarts) >= self.max_restarts:
            self.gave_up = True
            return "give_up"
        self.restarts.append(now)
        self.quiet_until = now + self.grace
        self.silent_since = None
        return action

    def reset(self):
        """The rider started the bridge by hand: forget past trouble."""
        self.__init__(self.hang_after, self.grace, self.max_restarts, self.window)
