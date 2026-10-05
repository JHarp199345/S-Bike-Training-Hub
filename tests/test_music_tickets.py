"""Playback tickets stay bounded: expired ones go, and the oldest go past the cap (video and audio alike)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import time
import music


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    s = music.Store.__new__(music.Store); s.tickets = {}
    old = s.issue("plex", {"id": "1", "resource": "/a", "video": True}, ttl=-1)     # already expired
    s._pruned = 0
    fresh = s.issue("plex", {"id": "2", "resource": "/b", "video": True})
    check("an expired video ticket is dropped when the next one is issued", old not in s.tickets and fresh in s.tickets)
    s.MAX_TICKETS = 50
    first = s.issue("plex", {"id": "x", "resource": "/x"}, ttl=10)
    for i in range(80):
        s.issue("ibroadcast", {"id": str(i), "resource": "/t"})
    check(f"past the cap the oldest go ({len(s.tickets)} kept of 82 issued)", len(s.tickets) <= 50 and first not in s.tickets)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
