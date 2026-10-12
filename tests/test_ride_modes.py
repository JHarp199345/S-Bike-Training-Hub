"""Ride World modes: a game asks for the hill; the hub clamps it, refuses during a route, and flattens a quiet game."""
import sys, pathlib, time; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from types import SimpleNamespace
import bridge

B = bridge.Bridge
hills, events = [], []
fake = SimpleNamespace(mode=None, route_ride=None, MODE_GRADE=B.MODE_GRADE, MODE_QUIET_S=B.MODE_QUIET_S,
                       hill_to_level=lambda g: hills.append(g), event=lambda e: events.append(e))
call = lambda name, *a: getattr(B, name)(fake, *a)

assert call("mode_grade", 3) == (False, "start a ride mode first")
call("mode_start", "monster-chase", "Monster Chase")
assert fake.mode["name"] == "Monster Chase" and "Ride mode started: Monster Chase" in events
assert call("mode_grade", 3.3) == (True, 3.5) and hills == [3.5], "0.5% steps"
assert call("mode_grade", 3.4) == (True, 3.5) and hills == [3.5], "the same hill isn't sent twice"
assert call("mode_grade", 40) == (True, 15.0) and call("mode_grade", -30) == (True, -10.0), "clamped to the safe range"
fake.route_ride = object()
assert call("mode_grade", 2)[0] is False, "a route sets the hills"
fake.route_ride = None
call("mode_grade", 6)
fake.mode["grade_at"] = time.monotonic() - 10            # the game went quiet
call("feed_mode")
assert hills[-1] == 0.0 and fake.mode["grade"] == 0.0 and any("went quiet" in e for e in events)
call("mode_grade", 4); call("mode_mark", "caught at 12:40")
assert fake.mode["marks"][0]["text"] == "caught at 12:40"
call("mode_end", "escaped")
assert fake.mode is None and hills[-1] == 0.0 and any("escaped" in e for e in events)
print("PASS ride modes: clamped, stepped, refused during a route, flattened when quiet, marked and ended")
