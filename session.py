"""session.py - training attached to places on a route: climb time goals, efforts, and a focus for part of it.

Asked for on 2026-09-28: easy days can use the gears to make hills disappear, but
on the right day a hill is free resistance work. "The goal is getting up there in
10 minutes - at this gear the speed doesn't make that possible, so we shift up, and
I have to contend with the harder resistance until I get up to speed." Or: "three
efforts of 200 W for 15 s, 3 minutes between, on this climb - in a high gear."

A session is a list of segments on a route (distances in metres along it):

  {"type": "climb_time", "climb": 2 | "start_m", "end_m", "seconds": 600, "rpm": [lo, hi]?}
      Get from start to end in `seconds`. The pace needs a speed; the speed on this
      grade needs watts (the bridge's own physics); auto-shift steers to those watts,
      re-worked every second from what's left - behind pace asks for more.
  {"type": "efforts", "climb": 1 | "at_m", "count": 3, "on_s": 15, "off_s": 180, "watts": 200, "rpm": [55, 70]?}
      Efforts starting where you reach at_m. Each one shifts straight into the gear
      that makes the watts at that cadence (15 s is too short to wait for auto-shift),
      then hands the gear back for the rest.
  {"type": "focus", "climb": 1 | "start_m", "end_m", "focus": "grit" | {...}}
      A different focus (focus.py) for part of the route - big-gear practice on the climbs.

`climbs(route)` finds a route's climbs, so a session can say "climb 2".
The Runner is fed once a second and says what to ask of auto-shift, what to show,
and what happened. Every climb ridden is recorded whether or not it had a goal.
"""
import math

G, CRR, CDA, RHO = 9.81, 0.005, 0.40, 1.2          # as bridge.virtual_speed
S29_W = (0.72, 0.17)                                # watts = (a + b x level) x cadence (tests/test_erg.py)


def watts_for(speed_ms, grade_pct, mass_kg):
    """The watts that hold speed_ms on grade_pct (the inverse of bridge.virtual_speed)."""
    th = math.atan(grade_pct / 100)
    return max(0.0, speed_ms * (mass_kg * G * (math.sin(th) + CRR * math.cos(th)) + 0.5 * RHO * CDA * speed_ms ** 2))


def level_for(watts, cadence):
    """The S29 level that makes `watts` at `cadence`."""
    return (watts / max(cadence, 30) - S29_W[0]) / S29_W[1]


# ── a route's climbs ─────────────────────────────────────────────────────────
def climbs(route, min_grade=3.0, min_len=300.0):
    """Stretches of steady climbing: at least min_len long averaging min_grade or more.
    Found on 100 m averages (so a flat 50 m doesn't split a climb), numbered from 1."""
    prof = route.profile(25.0)
    if len(prof) < 5:
        return []
    avg = []
    for i in range(len(prof)):
        lo, hi = max(0, i - 2), min(len(prof) - 1, i + 2)
        d = prof[hi][0] - prof[lo][0]
        avg.append((prof[hi][1] - prof[lo][1]) / d * 100 if d else 0.0)
    out, i = [], 0
    while i < len(prof):
        if avg[i] >= min_grade * 0.66:
            j = i
            while j + 1 < len(prof) and avg[j + 1] >= min_grade * 0.5:
                j += 1
            s, e = prof[i][0], prof[j][0]
            gain = prof[j][1] - prof[i][1]
            if e - s >= min_len and gain / max(e - s, 1) * 100 >= min_grade:
                out.append({"n": len(out) + 1, "start_m": round(s), "end_m": round(e), "length_m": round(e - s),
                            "gain_m": round(gain), "avg_grade": round(gain / (e - s) * 100, 1),
                            "max_grade": round(max(p[2] for p in prof[i:j + 1]), 1)})
            i = j + 1
        else:
            i += 1
    return out


# ── checking a session ──────────────────────────────────────────────────────
class BadSession(ValueError):
    pass


def _where(seg, cl, route, keys):
    if seg.get("climb") is not None:
        n = int(seg["climb"])
        c = next((x for x in cl if x["n"] == n), None)
        if not c:
            raise BadSession(f"this route has {len(cl)} climb{'s' if len(cl) != 1 else ''}, not a climb {n}")
        return {"start_m": c["start_m"], "end_m": c["end_m"], "at_m": c["start_m"]}
    out = {}
    for k in keys:
        if seg.get(k) is None:
            raise BadSession(f"{seg['type']} needs {k} (or a climb number)")
        v = float(seg[k])
        if not 0 <= v <= route.length + 1:
            raise BadSession(f"{k} {v:.0f} m is off this {route.length:.0f} m route")
        out[k] = v
    return out


def _rpm(v, default):
    if v is None:
        return default
    lo, hi = float(v[0]), float(v[1])
    if not 30 <= lo < hi <= 130:
        raise BadSession("rpm is [low, high] between 30 and 130")
    return [lo, hi]


def check(route, segments):
    """Validate and fill in a session's segments (climb numbers become distances). Returns the clean list."""
    import focus
    if not isinstance(segments, list) or not segments:
        raise BadSession("a session is a list of segments")
    cl = climbs(route)
    out = []
    for seg in segments[:20]:
        t = seg.get("type")
        if t == "climb_time":
            w = _where(seg, cl, route, ("start_m", "end_m"))
            if w["end_m"] - w["start_m"] < 100:
                raise BadSession("a climb goal needs at least 100 m")
            secs = float(seg.get("seconds", 0))
            if not 30 <= secs <= 7200:
                raise BadSession("seconds is between 30 and 7200")
            out.append({"type": t, "name": seg.get("name") or (f"Climb {seg['climb']}" if seg.get("climb") else "Climb"),
                        "start_m": w["start_m"], "end_m": w["end_m"], "seconds": secs, "rpm": _rpm(seg.get("rpm"), None)})
        elif t == "efforts":
            w = _where(seg, cl, route, ("at_m",))
            n, on, off, watts = int(seg.get("count", 3)), float(seg.get("on_s", 15)), float(seg.get("off_s", 180)), float(seg.get("watts", 0))
            if not (1 <= n <= 20 and 5 <= on <= 1200 and 10 <= off <= 1800 and 50 <= watts <= 800):
                raise BadSession("efforts: count 1-20, on_s 5-1200, off_s 10-1800, watts 50-800")
            out.append({"type": t, "name": seg.get("name") or f"{n} x {on:.0f} s at {watts:.0f} W", "at_m": w["at_m"],
                        "count": n, "on_s": on, "off_s": off, "watts": watts, "rpm": _rpm(seg.get("rpm"), [55, 70])})
        elif t == "focus":
            w = _where(seg, cl, route, ("start_m", "end_m"))
            f = focus.check(seg.get("focus"))
            if f is None:
                raise BadSession("a focus segment needs a focus")
            out.append({"type": t, "name": seg.get("name") or (f if isinstance(f, str) else f["name"]),
                        "start_m": w["start_m"], "end_m": w["end_m"], "focus": f})
        else:
            raise BadSession("segment type is climb_time, efforts or focus")
    return out


# ── riding it ───────────────────────────────────────────────────────────────
def _mmss(s):
    s = int(round(abs(s)))
    return f"{s // 60}:{s % 60:02d}"


class Runner:
    """Fed once a second with where you are and what you're doing; says what auto-shift should aim for.

    update() returns {"rpm": [lo, hi] | None, "watts": [lo, hi] | None,  - ranges to steer toward (None: the day's)
                      "shift_to_watts": (watts, cadence) | None,          - shift now into the gear for this
                      "restore_gear": bool,                               - hand back the gear from before
                      "cue": str, "pace": {...} | None}
    """
    def __init__(self, route, segments, ftp, mass_kg, focus_resolve=None, start_at=0.0):
        self.route, self.ftp, self.mass = route, ftp, mass_kg
        # resuming mid-route: segments that began behind you are passed, not re-run
        self.segs = [dict(s, state="passed" if s.get("start_m", s.get("at_m", 0)) < start_at - 5 else "waiting")
                     for s in segments]
        self.resolve = focus_resolve
        self.log = []              # messages for the ride's events
        self.results = []

    def _say(self, msg):
        self.log.append(msg)

    def update(self, t, d, power, cadence, grade):
        out = {"rpm": None, "watts": None, "shift_to_watts": None, "restore_gear": False, "cue": "", "pace": None}
        upcoming = None
        for s in self.segs:
            fn = getattr(self, "_" + s["type"])
            fn(s, t, d, power, cadence, grade, out)
            if s["state"] == "waiting":
                start = s.get("start_m", s.get("at_m"))
                if start > d and (upcoming is None or start < upcoming[0]):
                    upcoming = (start, s)
        if not out["cue"] and upcoming and upcoming[0] - d <= 500:
            s = upcoming[1]
            out["cue"] = f"{s['name']} in {upcoming[0] - d:.0f} m" + (
                f" - goal {_mmss(s['seconds'])}" if s["type"] == "climb_time" else
                f" - {s['count']} x {s['on_s']:.0f} s at {s['watts']:.0f} W, big gear" if s["type"] == "efforts" else "")
        return out

    # climb goal: pace -> speed -> watts, re-worked from what's left every second
    def _climb_time(self, s, t, d, power, cadence, grade, out):
        if s["state"] == "waiting" and s["start_m"] <= d < s["end_m"]:
            s.update(state="on", t0=t, d0=d, w_sum=0.0, c_sum=0.0, n=0, w_max=0.0)
            self._say(f"{s['name']}: goal {_mmss(s['seconds'])} for {(s['end_m'] - s['start_m']) / 1000:.2f} km")
            s["first"] = True
        if s["state"] != "on":
            return
        if d >= s["end_m"]:
            took = t - s["t0"]
            made = took <= s["seconds"]
            r = {"type": "climb_time", "name": s["name"], "goal_s": round(s["seconds"]), "took_s": round(took),
                 "made": made, "avg_w": round(s["w_sum"] / max(s["n"], 1)), "max_w": round(s["w_max"]),
                 "avg_rpm": round(s["c_sum"] / max(s["n"], 1)), "start_m": s["start_m"], "end_m": s["end_m"]}
            self.results.append(r)
            s["state"] = "done"
            self._say(f"{s['name']}: {_mmss(took)} vs goal {_mmss(s['seconds'])} - "
                      + ("made it" if made else f"{_mmss(took - s['seconds'])} over") + f", {r['avg_w']} W average")
            out["restore_gear"] = True
            return
        el = t - s["t0"]
        s["n"] += 1; s["w_sum"] += power; s["c_sum"] += cadence; s["w_max"] = max(s["w_max"], power)
        v_goal = (s["end_m"] - s["start_m"]) / s["seconds"]
        ahead = ((d - s["d0"]) - el * v_goal) / v_goal                  # seconds ahead (+) or behind (-)
        left_m, left_s = s["end_m"] - d, s["seconds"] - el
        v_need = left_m / max(left_s, 15.0)
        # the climb's average grade from here, so the watts don't jump with every ramp
        g = (self.route.elevation_at(s["end_m"]) - self.route.elevation_at(d)) / max(left_m, 1) * 100
        w = min(1.3 * self.ftp, max(0.5 * self.ftp, watts_for(v_need, g, self.mass)))
        out["watts"] = [round(w * 0.95), round(w * 1.05)]
        out["rpm"] = s["rpm"]
        if s.pop("first", False):
            out["shift_to_watts"] = (w, cadence if cadence >= 40 else 70)
        out["pace"] = {"name": s["name"], "goal_s": s["seconds"], "elapsed_s": round(el), "ahead_s": round(ahead),
                       "left_m": round(left_m), "target_w": round(w)}
        out["cue"] = (f"{s['name']}: {_mmss(el)} of {_mmss(s['seconds'])} · {left_m / 1000:.2f} km left · "
                      + (f"{_mmss(ahead)} ahead" if ahead >= 1 else f"{_mmss(ahead)} behind" if ahead <= -1 else "on pace")
                      + f" · hold {w:.0f} W")

    # efforts: on/off by the clock from where they start; each effort shifts straight into its gear
    def _efforts(self, s, t, d, power, cadence, grade, out):
        if s["state"] == "waiting" and d >= s["at_m"]:
            s.update(state="on", t0=t, done=[], cur=None)
            self._say(f"Efforts: {s['name']}")
        if s["state"] != "on":
            return
        el = t - s["t0"]
        period = s["on_s"] + s["off_s"]
        i, into = int(el // period), el % period
        if i >= s["count"]:
            self._close_effort(s)
            s["state"] = "done"
            efforts = s["done"]
            r = {"type": "efforts", "name": s["name"], "target_w": s["watts"], "efforts": efforts,
                 "made": sum(1 for e in efforts if e["avg_w"] >= 0.9 * s["watts"])}
            self.results.append(r)
            self._say(f"Efforts done: {r['made']} of {s['count']} at 90%+ of {s['watts']:.0f} W ("
                      + ", ".join(f"{e['avg_w']} W" for e in efforts) + ")")
            return
        if into < s["on_s"]:
            if s["cur"] is None or s["cur"]["i"] != i:
                self._close_effort(s)
                s["cur"] = {"i": i, "w": 0.0, "c": 0.0, "n": 0}
                out["shift_to_watts"] = (s["watts"], sum(s["rpm"]) / 2)
            c = s["cur"]; c["n"] += 1; c["w"] += power; c["c"] += cadence
            out["watts"] = [round(s["watts"] * 0.95), round(s["watts"] * 1.05)]
            out["rpm"] = s["rpm"]
            out["cue"] = f"Effort {i + 1} of {s['count']}: {s['watts']:.0f} W · {s['on_s'] - into:.0f} s left · now {power:.0f} W"
        else:
            if s["cur"] is not None:
                self._close_effort(s)
                out["restore_gear"] = True
            out["cue"] = (f"Easy · effort {i + 2} of {s['count']} in {_mmss(period - into)}" if i + 1 < s["count"]
                          else "Last effort done - easy now")

    def _close_effort(self, s):
        c = s.get("cur")
        if c and c["n"]:
            s["done"].append({"n": c["i"] + 1, "avg_w": round(c["w"] / c["n"]), "avg_rpm": round(c["c"] / c["n"]), "secs": c["n"]})
        s["cur"] = None

    # a focus for part of the route
    def _focus(self, s, t, d, power, cadence, grade, out):
        inside = s["start_m"] <= d < s["end_m"]
        if inside and s["state"] == "waiting":
            s["state"] = "on"
            self._say(f"{s['name']} from here to {s['end_m'] / 1000:.1f} km")
        if s["state"] == "on" and not inside:
            s["state"] = "done"
            self._say(f"{s['name']} done")
        if s["state"] == "on" and self.resolve and not out["watts"]:
            f = self.resolve(s["focus"])
            out["rpm"], out["watts"] = f["rpm"], f["watts"]
            if not out["cue"]:
                out["cue"] = f"{f['name']}: {f['rpm'][0]}-{f['rpm'][1]} rpm" + (f", {f['watts'][0]}-{f['watts'][1]} W" if f["watts"] else "")

    def status(self):
        return {"segments": [{k: s[k] for k in ("type", "name", "state")} for s in self.segs], "results": self.results}


class ClimbRecorder:
    """Every climb on a route, ridden: time, watts, cadence, speed - goal or not."""
    def __init__(self, route, start_at=0.0):
        self.cl = [c for c in climbs(route) if c["start_m"] >= start_at - 5]     # resumed: only climbs still ahead
        self.cur, self.done = None, []

    def update(self, t, d, power, cadence, speed_ms, gear):
        if self.cur is None:
            c = next((c for c in self.cl if c["start_m"] <= d < c["end_m"] and c["n"] not in {x["n"] for x in self.done}), None)
            if c:
                self.cur = dict(c, t0=t, w=0.0, cad=0.0, n_s=0, w_max=0.0, gears=set())
            return None
        c = self.cur
        if d >= c["end_m"]:
            rec = {k: c[k] for k in ("n", "start_m", "end_m", "length_m", "gain_m", "avg_grade", "max_grade")}
            rec.update(seconds=round(t - c["t0"]), avg_w=round(c["w"] / max(c["n_s"], 1)), max_w=round(c["w_max"]),
                       avg_rpm=round(c["cad"] / max(c["n_s"], 1)),
                       avg_kmh=round(c["length_m"] / max(t - c["t0"], 1) * 3.6, 1),
                       vam=round(c["gain_m"] / max(t - c["t0"], 1) * 3600), gears=sorted(c["gears"]))
            self.done.append(rec)
            self.cur = None
            return rec
        c["n_s"] += 1; c["w"] += power; c["cad"] += cadence; c["w_max"] = max(c["w_max"], power); c["gears"].add(gear)
        return None
