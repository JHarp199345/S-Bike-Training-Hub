"""Ride World modes: a game asks for the hill; the hub clamps it, eases toward it, refuses during a route, and flattens
a quiet game."""
import sys, pathlib, time; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from types import SimpleNamespace
import bridge

B = bridge.Bridge
hills, events = [], []
fake = SimpleNamespace(mode=None, route_ride=None, MODE_GRADE=B.MODE_GRADE, MODE_QUIET_S=B.MODE_QUIET_S, MODE_RAMP=B.MODE_RAMP,
                       hill_to_level=lambda g: hills.append(g), event=lambda e: events.append(e))
fake._mode_ramp = lambda: B._mode_ramp(fake)
def later(seconds):                                         # pretend time passed since the last hill change
    fake.mode["ramp_at"] -= seconds
call = lambda name, *a: getattr(B, name)(fake, *a)

assert call("mode_grade", 3) == (False, "start a ride mode first")
call("mode_start", "monster-chase", "Monster Chase")
assert fake.mode["name"] == "Monster Chase" and "Ride mode started: Monster Chase" in events
call("mode_grade", 3.3)
assert fake.mode["grade"] == 0.0, "a request doesn't jump: the hill starts where it is"
later(1); assert call("mode_grade", 3.3) == (True, 1.5), "eased at MODE_RAMP % a second, in 0.5% steps"
later(1); call("feed_mode"); assert fake.mode["grade"] == 3.0, "keeps easing once a second without new requests"
later(1); call("feed_mode"); assert fake.mode["grade"] == 3.5 and hills.count(3.5) == 1, "arrives, sent once"
later(1); assert call("mode_grade", 40) == (True, 5.0), "clamped to 15% and still eased: no jolt"
assert fake.mode["target"] == 15.0
fake.mode["ramp"] = fake.mode["target"] = 0.0; later(1)
assert call("mode_grade", -30) == (True, -1.5) and fake.mode["target"] == -10.0, "clamped to -10% and eased"
fake.route_ride = object()
assert call("mode_grade", 2)[0] is False, "a route sets the hills"
fake.route_ride = None
later(1); call("mode_grade", 6); later(1); call("mode_grade", 6)
assert fake.mode["grade"] == 1.5
fake.mode["grade_at"] = time.monotonic() - 10            # the game went quiet
call("feed_mode")
assert hills[-1] == 0.0 and fake.mode["grade"] == 0.0 and any("went quiet" in e for e in events)
call("mode_grade", 4); call("mode_mark", "caught at 12:40")
assert fake.mode["marks"][0]["text"] == "caught at 12:40"
call("mode_end", "escaped")
assert fake.mode is None and hills[-1] == 0.0 and any("escaped" in e for e in events)
print("PASS ride modes: clamped, eased, refused during a route, flattened when quiet, marked and ended")
