"""journey.py - a fictional athlete lives a 12-week sprint-triathlon program on a real hub, for the README.

Everything goes through the hub the way real use does: the welcome setup, the program builder, morning
check-ins, watch files for every ride, swim and run (written as .fit, read by the hub's own importer),
lifting check-offs, Sunday check-ins, missed sessions with reasons. The hub runs under a fake clock
(libfaketime) that this script moves forward one day at a time, so every page sees the athlete's "today".
No numbers are drawn on the screenshots: everything shown is what the hub calculated.

At each checkpoint it saves the hub's data and the athlete's state (out/saves/NAME), then calls
tools/demo/shots.js to photograph the Coach. A re-run can start from any save point instead of week 0:
the hub is rebuilt from the current code, the saved data is laid over it, that checkpoint is
photographed again and the journey continues from the next day.

  python3 tools/demo/journey.py [--out DIR] [--no-shots] [--until DATE] [--from NAME|latest] [--list]

Needs Linux with libfaketime (apt install faketime) and Node Playwright (for the screenshots).
The athlete, Jordan Lee, is invented; any resemblance is coincidence.
"""
import argparse
import datetime as dt
import json
import os
import pickle
import random
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path[:0] = [str(HERE)]
import fitwrite  # noqa: E402
sys.path.insert(0, str(REPO))
from coaching_review import run_hold  # noqa: E402

PORT = 18850
URL = f"http://127.0.0.1:{PORT}"
FAKETIME = "/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1"

PRE = dt.date(2026, 5, 4)          # three easy weeks of history before the program
START = dt.date(2026, 5, 25)       # program week 1 (Monday)
RACE = dt.date(2026, 8, 16)        # race day (Sunday), end of week 12
PERSON = {"unit": "lb", "weight": 174, "age": 36, "hr_rest": 58, "hr_max": None,
          "sports": ["bike", "swim", "run", "lift"],
          "experience": {"bike": "returning", "swim": "returning", "run": "new", "lift": "returning"},
          "smart_bike": False, "return_to_run": False, "start": "fresh", "ftp": 175, "css": "2:05", "run5k": None,
          "runs_now": False, "run_minutes": 40, "run_niggles": False,
          "rules": ["No barbell work on the day before a long ride"]}

# What happens that isn't in the plan: (date, sport or None) -> missed reason, and journal lines
MISS = {(dt.date(2026, 6, 10), "swim"): ("busy", "Work ran late, pool closed"),
        (dt.date(2026, 6, 26), "run"): ("sore", "Left shin still tender - swapped for rest"),
        (dt.date(2026, 6, 30), None): ("sick", "Head cold"),
        (dt.date(2026, 7, 1), None): ("sick", "Still congested"),
        (dt.date(2026, 7, 9), "swim"): ("sore", "Right shoulder pinching - resting it"),
        (dt.date(2026, 7, 22), "swim"): ("travel", "Work trip, no pool")}
JOURNAL = {dt.date(2026, 5, 26): "First FTP test done. Harder than I expected, but I paced it.",
           dt.date(2026, 6, 25): "Left shin a bit tender after yesterday's run. Not painful walking.",
           dt.date(2026, 6, 30): "Woke up with a head cold. Taking today and tomorrow off.",
           dt.date(2026, 7, 8): "Front of my right shoulder pinches when I reach forward on the catch. Worse on the last few lengths.",
           dt.date(2026, 7, 13): "Shoulder better. Easy swim felt fine, no pinch with a shorter reach.",
           dt.date(2026, 7, 16): "Biggest week so far and I feel good. Long ride felt easy at the end.",
           dt.date(2026, 8, 6): "Race-pace brick felt fast. Transitions are getting smoother.",
           dt.date(2026, 8, 17): "Finished my first triathlon! Swim was chaos, bike was strong, ran the whole run."}
CHECKPOINTS = {dt.date(2026, 5, 28): "week01", dt.date(2026, 6, 18): "week04", dt.date(2026, 7, 2): "week06",
               dt.date(2026, 7, 16): "week08", dt.date(2026, 7, 30): "week10", dt.date(2026, 8, 14): "week12",
               dt.date(2026, 8, 17): "after"}


class Hub:
    def __init__(self, out):
        self.dir = out / "hub"
        self.clock = out / "clock.txt"
        self.proc = None

    def build(self):
        if self.dir.exists():
            shutil.rmtree(self.dir)
        ignore = shutil.ignore_patterns(".git", "tests", "tools", "docs", "maps", "__pycache__", "*.log", "rides",
                                        "activities", "*.json.bak")
        shutil.copytree(REPO, self.dir, ignore=ignore)
        for f in ("coach.json", "profile.json", "state.json", "bests.json", "bike.json", "theme.json"):
            (self.dir / f).unlink(missing_ok=True)
        (self.dir / "rides").mkdir()
        (self.dir / "activities").mkdir()

    def data_files(self):
        """Everything the hub wrote: files that aren't in the repo, or differ from it."""
        for f in self.dir.rglob("*"):
            rel = f.relative_to(self.dir)
            if not f.is_file() or rel.name == "hub.log" or "__pycache__" in rel.parts:
                continue
            src = REPO / rel
            if not src.is_file() or src.stat().st_size != f.stat().st_size or src.read_bytes() != f.read_bytes():
                yield rel

    def save(self, folder):
        data = folder / "data"
        if folder.exists():
            shutil.rmtree(folder)
        for rel in self.data_files():
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.dir / rel, data / rel)

    def restore(self, folder):
        for f in (folder / "data").rglob("*"):
            if f.is_file():
                dest = self.dir / f.relative_to(folder / "data")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)

    def set_time(self, when):
        self.clock.write_text(when.strftime("%Y-%m-%d %H:%M:%S"))

    def start(self):
        import socket
        for _ in range(40):                       # a previous hub may still be letting go of the port
            with socket.socket() as so:
                if so.connect_ex(("127.0.0.1", PORT)) != 0:
                    break
            time.sleep(0.5)
        env = {**os.environ, "LD_PRELOAD": FAKETIME, "FAKETIME_TIMESTAMP_FILE": str(self.clock),
               "FAKETIME_NO_CACHE": "1", "FAKETIME_DONT_FAKE_MONOTONIC": "1"}
        self.proc = subprocess.Popen([sys.executable, "bridge.py", "--no-bike", "--no-remote", "--port", str(PORT)],
                                     cwd=self.dir, env=env, stdout=open(self.dir / "hub.log", "w"), stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                urllib.request.urlopen(URL + "/api/setup", timeout=2)
                return
            except OSError:
                time.sleep(0.5)
        raise SystemExit("the hub didn't start: see " + str(self.dir / "hub.log"))

    def stop(self):
        if self.proc:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def api(path, body=None, ok=(200,)):
    req = urllib.request.Request(URL + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            raw = r.read()
            try:
                return json.loads(raw)
            except ValueError:
                raise SystemExit(f"{path} -> not JSON: {raw[:300]!r}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:400]
        if e.code in ok:
            return json.loads(msg)
        raise SystemExit(f"{path} -> {e.code}: {msg}")


class Athlete:
    """Jordan's body, simply: FTP, run pace and swim pace improve with consistent training."""

    def __init__(self, acts):
        self.acts = acts
        self.ftp = 175
        self.fitness = 0.0          # bpm lower at the same effort
        self.run_pace = 430         # s/km, easy
        self.swim_25 = 33           # s per 25 m, steady
        self.rng = random.Random(42)
        self.fatigue = 3.0          # legs, 1-10
        self.shin = 2               # feet & bones, 1-10
        self.sick = False
        self.shoulder = 2

    def week_passes(self, completion):
        gain = 0.5 + 0.6 * completion
        self.fitness = min(9, self.fitness + gain * 0.8)
        self.run_pace = max(372, self.run_pace - gain * 4.5)
        self.swim_25 = max(27.5, self.swim_25 - gain * 0.35)

    def ride(self, day, s, at):
        ftp = self.ftp
        steps = (s.get("bike_plan") or {}).get("power_steps") or [{"minutes": s["minutes"], "pct": 62}]
        jitter = self.rng.uniform(0.97, 1.03)
        seq = [(st["minutes"] * 60 * jitter, ftp * st["pct"] / 100 * self.rng.uniform(0.98, 1.02)) for st in steps]
        fitwrite.bike(self.acts / f"{day}_{at:%H%M}_ride.fit", at.timestamp(), seq, ftp, fitness=self.fitness)

    def run(self, day, s, at):
        name = (s.get("name") or "").lower()
        if "calibration" in name:
            # zone 2 the whole way; the first one (a new runner) stops tired at 40 min, later ones finish the hour
            self.calibrations = getattr(self, "calibrations", 0) + 1
            mins = 40 if self.calibrations == 1 else 60
            fitwrite.run(self.acts / f"{day}_{at:%H%M}_run.fit", at.timestamp(), mins * 60, 140 - self.fitness,
                         self.run_pace + 35, hr_drift=max(1.5, 6.0 - 0.6 * self.fitness))
            return mins
        hard = any(k in name for k in ("race", "brick", "steady", "openers"))
        pace = self.run_pace - (55 if "race" in name or "brick" in name else 25 if hard else 0)
        hr = 150 - self.fitness + (14 if hard else 0)
        secs = s["minutes"] * 60 * self.rng.uniform(0.96, 1.04)
        if "run / walk" in name or "hop test" in name:
            pace, hr = pace + 70, hr - 6
        fitwrite.run(self.acts / f"{day}_{at:%H%M}_run.fit", at.timestamp(), secs, hr, pace,
                     hr_drift=max(2.0, 9.0 - 0.7 * self.fitness))
        return secs / 60

    def swim(self, day, s, at):
        per = self.swim_25 - (2.5 if "race" in (s.get("name") or "").lower() else 0)
        lengths = max(8, int(s["minutes"] * 60 * 0.78 / per))
        fitwrite.swim(self.acts / f"{day}_{at:%H%M}_swim.fit", at.timestamp(), lengths, sec_per_length=per,
                      hr=int(138 - self.fitness))


def checkin(day, a, extra=None):
    body = {"date": day.isoformat(), "legs": round(a.fatigue), "feet": a.shin, "shoulders": getattr(a, "shoulder", 2),
            "sleep": a.rng.choice([6, 7, 7, 8, 8]), "breathing": 3 if not a.sick else 6,
            "motivation": a.rng.choice([7, 8, 8, 9]), "gut": "no" if a.sick else "go"}
    if day in JOURNAL:
        body["journal"] = JOURNAL[day]
    body.update(extra or {})
    return api("/api/coach/checkin", body)


def saves_in(out):
    folder = out / "saves"
    found = []
    for meta in folder.glob("*/meta.json"):
        m = json.loads(meta.read_text())
        found.append((m["day"], meta.parent.name))
    return [name for _, name in sorted(found)]


def save_point(hub, out, name, a, st):
    folder = out / "saves" / name
    hub.save(folder)
    (folder / "athlete.pkl").write_bytes(pickle.dumps(a.__dict__))
    (folder / "meta.json").write_text(json.dumps({"day": st["day"].isoformat(), "week_done": st["week_done"],
                                                  "week_plan": st["week_plan"]}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--until", help="stop after this date (YYYY-MM-DD), for checking a stretch")
    ap.add_argument("--from", dest="resume", help="start from a save point (a checkpoint name, or 'latest')")
    ap.add_argument("--list", action="store_true", help="list the save points and exit")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    saved = saves_in(out)
    if args.list:
        for name in saved:
            print(name, json.loads((out / "saves" / name / "meta.json").read_text())["day"])
        return
    if args.resume:
        name = saved[-1] if args.resume == "latest" and saved else args.resume
        if name not in saved:
            raise SystemExit(f"no save point {args.resume!r}; have: {', '.join(saved) or 'none'}")
    hub = Hub(out)
    hub.build()
    log = open(out / "journey.log", "a" if args.resume else "w")
    say = lambda *m: (print(*m, flush=True), print(*m, file=log, flush=True))
    try:
        if args.resume:
            folder = out / "saves" / name
            hub.restore(folder)
            meta = json.loads((folder / "meta.json").read_text())
            a = Athlete.__new__(Athlete)
            a.__dict__.update(pickle.loads((folder / "athlete.pkl").read_bytes()))
            a.acts = hub.dir / "activities"
            st = {"day": dt.date.fromisoformat(meta["day"]), "week_done": meta["week_done"], "week_plan": meta["week_plan"]}
            hub.set_time(dt.datetime.combine(st["day"], dt.time(19, 30)))
            hub.start()
            say(f"resumed from {name} ({st['day']}) with the current code")
            if not args.no_shots:
                shots(out, st["day"], name)
            st["day"] += dt.timedelta(days=1)
        else:
            hub.set_time(dt.datetime.combine(PRE, dt.time(7, 0)))
            hub.start()
            a = setup(hub, say)
            st = {"day": START, "week_done": 0, "week_plan": 0}
        stop = dt.date.fromisoformat(args.until) if args.until else RACE + dt.timedelta(days=1)
        while st["day"] <= stop:
            live_day(hub, a, st, say)
            day = st["day"]
            if day in CHECKPOINTS:
                hub.set_time(dt.datetime.combine(day, dt.time(19, 30)))
                save_point(hub, out, CHECKPOINTS[day], a, st)
                if not args.no_shots:
                    shots(out, day, CHECKPOINTS[day])
            st["day"] += dt.timedelta(days=1)
        say("done:", out)
    finally:
        hub.stop()


def setup(hub, say):
    api("/api/setup", PERSON)
    api("/api/theme", {"theme": api("/api/theme")["theme"]})
    a = Athlete(hub.dir / "activities")
    # ── three weeks of easy history ──
    day = PRE
    while day < START:
        hub.set_time(dt.datetime.combine(day, dt.time(6, 30)))
        checkin(day, a)
        wd = day.weekday()
        at = dt.datetime.combine(day, dt.time(18, 0))
        if wd in (1, 5):
            a.ride(day, {"minutes": 45 if wd == 5 else 35}, at)
        elif wd == 3:
            a.swim(day, {"minutes": 25}, at)
        elif wd in (0, 4):
            a.run(day, {"minutes": 20, "name": "easy run / walk"}, at)
        if wd == 6:
            api("/api/coach/weekly", {"sunday": day.isoformat(), "legs": 3, "feet": 2, "shoulders": 3, "week": 7,
                                      "hops_left": 20, "hops_right": 20, "run_response": "resolved",
                                      "note": "Easy week, getting back into it."})
        day += dt.timedelta(days=1)
    # ── the program, built the evening before week 1 ──
    hub.set_time(dt.datetime.combine(START - dt.timedelta(days=1), dt.time(19, 0)))
    api("/api/coach/event", {"date": RACE.isoformat(), "name": "Lakeside Sprint Triathlon", "kind": "race", "sport": "tri",
                             "note": "750 m swim · 20 km bike · 5 km run"})
    fields = {"start": START.isoformat(), "target": RACE.isoformat(), "sport": "tri", "hours": 4,
              "goal": "Lakeside Sprint Triathlon", "outcome": "Finish strong and enjoy it", "assessment": "week",
              "priorities": {"ride": "improve", "swim": "improve", "run": "improve", "gym": "maintain"},
              "starter_enabled": True, "starter_level": "moderate", "starter_equipment": "basic", "neutral_forecast": True,
              "schedule_options": {"available_days": [0, 1, 2, 3, 4, 5, 6], "rest_days": [6]}}
    draft = api("/api/coach/program-builder", fields)
    did = draft.get("draft_id") or draft.get("id") or (draft.get("draft") or {}).get("id")
    api("/api/coach/program-builder", {"action": "accept", "draft_id": did})
    prog = api("/api/coach/program-builder")
    say("program:", [(p["stage"], p["start"], p["end"]) for p in prog["phases"]], "running hold:", prog["running_hold"])
    return a


def live_day(hub, a, st, say):
    """One day of Jordan's life: check in, let the assistant review, train, report, and on Sunday look back."""
    day = st["day"]
    hub.set_time(dt.datetime.combine(day, dt.time(6, 30)))
    a.sick = any(k[0] == day and k[1] is None and v[0] == "sick" for k, v in MISS.items())
    if day == dt.date(2026, 6, 25):
        a.shin = 6
    elif day == dt.date(2026, 6, 29):
        a.shin = 3
    elif day == dt.date(2026, 7, 6):
        a.shin = 2
    a.shoulder = 7 if dt.date(2026, 7, 8) <= day <= dt.date(2026, 7, 10) else 4 if dt.date(2026, 7, 10) < day <= dt.date(2026, 7, 13) else 2
    # the hub asks for the hop test before a run: the athlete does it in the morning check-in
    week = api(f"/api/coach/week?date={day.isoformat()}")["week"]
    today = next(x for x in week if x["date"] == day.isoformat())
    runs_today = any(s_.get("sport") == "run" for s_ in today["sessions"])
    checkin(day, a, {"hops_left": 22, "hops_right": 21 if a.shin < 5 else 9} if runs_today else None)
    # the morning conversation with the assistant, before anything is done today
    assistant_review(day, a, say)
    week = api(f"/api/coach/week?date={day.isoformat()}")["week"]
    today = next(x for x in week if x["date"] == day.isoformat())
    at = dt.datetime.combine(day, dt.time(6, 45))
    hard_today = 0
    trained, stopped = [], []
    for i, s in enumerate(today["sessions"]):
        sp = s.get("sport")
        if sp in (None, "rest") or not s.get("minutes"):
            if sp == "other" and "Race day" in (s.get("name") or ""):
                race(a, day)
            continue
        st["week_plan"] += s["minutes"]
        if MISS.get((day, sp)) or MISS.get((day, None)):
            continue
        if sp == "ride":
            a.ride(day, s, at)
        elif sp == "run":
            ran = a.run(day, s, at)
            if "calibration" in (s.get("name") or "").lower() and ran < 58:
                stopped.append(day)
        elif sp == "swim":
            a.swim(day, s, at)
        elif sp == "gym":
            api("/api/coach/lifting/log", {"date": day.isoformat(), "session_index": 0, "rpe": 6, "wellness": 7})
        trained.append((i, s))
        st["week_done"] += s["minutes"]
        hard_today += s.get("tier") in ("moderate", "hard")
        at += dt.timedelta(minutes=s["minutes"] + 5)
    if day == START:
        api("/api/calibration", {"capacity": "ftp", "value": 182, "kind": "test", "date": day.isoformat(),
                                 "note": "Ramp test, week 1"})
        a.ftp = 182
    if day == START + dt.timedelta(days=2):
        api("/api/calibration", {"t400": 492, "t200": 231, "date": day.isoformat()})
    if day == dt.date(2026, 7, 6):
        api("/api/calibration", {"capacity": "ftp", "value": 191, "kind": "test", "date": day.isoformat(),
                                 "note": "Ramp test, week 7"})
        a.ftp = 191
    # the evening: a quick report on each run (the end-of-workout response the hub learns from)
    hub.set_time(dt.datetime.combine(day, dt.time(20, 0)))
    for d0 in stopped:      # the coach page asks why the calibration stopped before the hour
        api("/api/calibration", {"calibration_run": d0.isoformat(), "reason": "tired"}, ok=(200, 400))
        say(f"{d0}: running calibration stopped at 40 min - 'I was too tired to keep going'")
    for i, s in trained:
        if s.get("sport") != "run":
            continue
        name = (s.get("name") or "").lower()
        building = s.get("phase") in ("base", "build") or any(k in name for k in ("easy", "steady", "long"))
        body = {"date": day.isoformat(), "session_index": i, "rpe": 4 if building else 7,
                "effort": "too_easy" if building and a.shin <= 2 and day >= dt.date(2026, 7, 6) else "as_intended"}
        if day == dt.date(2026, 6, 24):
            body["symptoms"] = [{"location": "below_knee", "side": "left", "severity": 3}]
            body["note"] = "Front of the left shin got tight in the last ten minutes."
        r = api("/api/coach/session-report", body, ok=(200, 400))
        if r.get("error"):
            say(f"session report {day} #{i}: {r['error']}")
    a.fatigue = max(2.0, min(5.0, a.fatigue * 0.6 + 1.2 + 0.8 * hard_today))   # well-managed: legs 2-5
    # the next morning, say why anything was missed (as the athlete would on the calendar)
    prev = day - dt.timedelta(days=1)
    for (d0, sp), (why, note) in MISS.items():
        if d0 == prev:
            pw = api(f"/api/coach/week?date={prev.isoformat()}")["week"]
            pd = next(x for x in pw if x["date"] == prev.isoformat())
            for i, s in enumerate(pd["sessions"]):
                if s.get("missed") and (sp is None or s.get("sport") == sp):
                    api("/api/coach/missed", {"date": prev.isoformat(), "index": i, "reason": why, "note": note})
    if day == dt.date(2026, 7, 6):
        # the shin has been quiet for a week: Jordan confirms it with the assistant
        for key, e in (api("/api/coach/session-report").get("reports") or {}).items():
            if any(x.get("severity", 0) > 0 for x in e.get("symptoms", [])):
                api("/api/coach/progression", {"action": "resolve_symptom", "report_key": key, "resolved": True,
                                               "note": "No shin tenderness for a week; hop test even."})
    if day.weekday() == 6:
        good = st["week_done"] >= 0.85 * max(1, st["week_plan"])
        api("/api/coach/weekly", {"sunday": day.isoformat(), "legs": round(a.fatigue), "feet": a.shin, "shoulders": 3,
                                  "week": 8 if good else 6, "hops_left": 22, "hops_right": 21 if a.shin < 5 else 15,
                                  "run_response": "resolved" if a.shin < 5 else "pulling",
                                  "note": "Good week." if good else "Lost a couple of sessions."})
        a.week_passes(st["week_done"] / max(1, st["week_plan"]))
        rem = ((api("/api/load").get("systems") or {}).get("impact", {}).get("tissue") or {}).get("remodeling") or {}
        steps = rem.get("block_learning") or []
        say(f"week ending {day}: planned {st['week_plan']} min, done {st['week_done']} min, ftp {a.ftp}, "
            f"easy pace {a.run_pace:.0f} s/km, running block {rem.get('reference_points')} pts, carrying {rem.get('score')} blocks"
            + (f" (last change {steps[-1]['date']}: {steps[-1]['why'][:90]})" if steps else ""))
        st["week_done"] = st["week_plan"] = 0


CR = "/api/coach/coaching-review"
LADDER = {"run": ["shorten", "ride", "rest"], "gym": ["ride", "rest"], "swim": ["ride", "rest"]}


def assistant_review(day, a, say):
    """What the athlete's AI assistant does each morning, scripted here with the same tools a real assistant
    uses (get_coaching_review -> preview_coaching_change -> apply_coaching_change after the athlete agrees):

    - capacity: when the hub has repeated, matched evidence that Jordan recovers better than modeled, review it;
    - calendar: every run or lift the 14-day outlook flags, every run inside a running hold, and swims during a
      shoulder flare-up get the lightest fix that passes the hub's checks: shorten, then swap for an easy ride,
      then rest. The hub, not the script, decides whether the draft is safe to apply."""
    rv = api(CR + "?days=14")
    for c in rv["capacity"]["candidates"]:
        if c["status"] == "review_candidate" and c.get("suggested_reference"):
            p = api(CR, {"action": "preview", "kind": "capacity", "target": c["target"],
                         "note": f"{len(c['observations'])} matched sessions recovered better than modeled"}, ok=(200, 400))
            if p.get("draft_id"):
                api(CR, {"action": "apply", "draft_id": p["draft_id"], "approved": True})
                say(f"assistant on {day}: {c['target']} capacity {c['reference']} -> {c['suggested_reference']} "
                    f"({c['direction']}, {len(c['observations'])} sessions)")
                rv = api(CR + "?days=14")
    out = rv["outlook"]
    gate = out["running_gate"]
    reasons = gate.get("reasons") or []
    held, _ = run_hold(gate, day.isoformat())      # the hub's own rule: a due hop test holds only today's run
    last = (day + dt.timedelta(days=13)).isoformat()
    # (date, index) -> step on the ladder
    level = {}
    for row in out["sessions"]:
        key = (row["date"], row["index"])
        if row["sport"] == "run" and held(row["date"]):
            level[key] = 1                            # a hold isn't fixed by a shorter run
        elif row["status"] != "within_projected_limits":
            level[key] = 0
    if a.shoulder >= 6:
        for k in range(5):
            d0 = (day + dt.timedelta(days=k)).isoformat()
            for i, s in enumerate(plan_of(d0)):
                if s.get("sport") == "swim":
                    level[(d0, i)] = 0
    if not level:
        restore(day, a, gate, say)
        progress_running(day, say)
        return
    for _ in range(5):
        changes = {}
        for (d0, i) in level:
            changes.setdefault(d0, None)
        body = []
        for d0 in sorted(changes):
            ss = plan_of(d0)
            new = [replace(s, LADDER[s["sport"]][min(level[(d0, i)], len(LADDER[s["sport"]]) - 1)], gate, a)
                   if (d0, i) in level and s.get("sport") in LADDER else s for i, s in enumerate(ss)]
            body.append({"date": d0, "sessions": new})
        p = api(CR, {"action": "preview", "kind": "calendar", "changes": body}, ok=(200, 400))
        if p.get("error"):
            say(f"assistant on {day}: preview refused: {p['error']}")
            return
        bad = p.get("violations") or []
        if not bad:
            api(CR, {"action": "apply", "draft_id": p["draft_id"], "approved": True})
            why = sorted({r["status"] for r in out["sessions"] if (r["date"], r["index"]) in level} - {"within_projected_limits"})
            say(f"assistant on {day} (running gate {gate.get('status')}: {'; '.join(reasons) or 'clear'}"
                f"{'; forecast ' + ', '.join(why) if why else ''}"
                f"{'; shoulder ' + str(a.shoulder) + '/10' if a.shoulder >= 6 else ''}): " + " | ".join(
                f"{c['date']}: {', '.join(s['name'] for s in c['sessions'])}" for c in p["changes"]))
            return
        bumped = False
        for v in bad:
            vd = v[:10]
            hit = [k for k in level if k[0] == vd] or [k for k in level if k[0] <= vd]
            for k in hit:
                if level[k] < len(LADDER["run"]) - 1:
                    level[k] += 1
                    bumped = True
            if "remaining" in v:
                for row in out["sessions"]:
                    if row["date"] == vd and (vd, row["index"]) not in level and row["date"] <= last:
                        level[(vd, row["index"])] = 0
                        bumped = True
        if not bumped:
            break
    say(f"assistant on {day}: no change passed the hub's checks: " + "; ".join(bad))


def restore(day, a, gate, say):
    """Once the reason is gone, put back what was swapped out: runs when the running gate is open again, swims
    when the shoulder is quiet. Each date is previewed on its own and only kept if the hub's checks pass."""
    restored = []
    for k in range(1, 14):
        d0 = (day + dt.timedelta(days=k)).isoformat()
        ss = plan_of(d0)
        new, back = [], []
        for s in ss:
            note, name = s.get("note") or "", s.get("name") or ""
            was = name.split("(instead of: ", 1)[1].rstrip(")") if "(instead of: " in name else None
            if s.get("sport") == "ride" and was and "running" in note and not run_hold(gate, day.isoformat())[0](d0):
                m = s["minutes"]
                new.append({"sport": "run", "minutes": m, "name": was, "steps": [f"{m} min as planned"],
                            "note": "Back in the plan: the running gate is open again."})
                back.append(was)
            elif s.get("sport") == "ride" and was and "shoulder" in note and a.shoulder <= 3:
                m = s["minutes"]
                new.append({"sport": "swim", "minutes": m, "name": was, "steps": [f"{m} min as planned"],
                            "note": "Back in the plan: the shoulder is quiet."})
                back.append(was)
            else:
                new.append(s)
        if not back:
            continue
        p = api(CR, {"action": "preview", "kind": "calendar", "changes": [{"date": d0, "sessions": new}]}, ok=(200, 400))
        if p.get("draft_id") and not p.get("violations"):
            api(CR, {"action": "apply", "draft_id": p["draft_id"], "approved": True})
            restored.append(f"{d0}: {', '.join(back)}")
        else:
            say(f"assistant on {day}: can't restore {d0} yet: {p.get('error') or '; '.join(p.get('violations') or [])}")
    if restored:
        say(f"assistant on {day}: restored " + " | ".join(restored))


def progress_running(day, say):
    """Fit running to the hub's target for the week (build wave, maintenance, or automatic deload): under it,
    lengthen the long run in 10-minute steps; over it, shorten the coming runs, then swap them for easy rides.
    Every version is previewed; the hub's checks (forecast, holds, deload, weekly cap) decide what is applied."""
    rp = api(CR + "?days=14")["outlook"].get("running_progression") or {}
    status, (lo, hi) = rp.get("status"), rp.get("target_blocks") or (0, 0)
    first, last = rp.get("week") or (day.isoformat(), (day + dt.timedelta(days=6)).isoformat())
    span = (dt.date.fromisoformat(last) - day).days
    runs = [(d0, i, s) for k in range(0, span + 1) for d0 in [(day + dt.timedelta(days=k)).isoformat()] if d0 >= first
            for i, s in enumerate(plan_of(d0)) if s.get("sport") == "run"]
    if status not in ("under_target", "over_target") or not runs:
        return
    why = f"running {rp['planned_week_peak_blocks']} vs the {rp['mode']} target {lo}-{hi} blocks (block {rp['block_points']} pts)"
    if status == "under_target":
        d0, i, s = max(runs, key=lambda r: r[2].get("minutes") or 0)
        base = s.get("minutes") or 30
        best = None
        for m in range(base + 10, min(90, base * 2 + 10) + 1, 10):
            ss = plan_of(d0)
            ss[i] = {**s, "minutes": m, "name": f"Long run, {m} min", "steps": [f"{m} min easy, conversational; walk breaks are fine"],
                     "note": f"Lengthened from {base} min: {why}. Tell me how the next two mornings feel."}
            p = api(CR, {"action": "preview", "kind": "calendar", "changes": [{"date": d0, "sessions": ss}]}, ok=(200, 400))
            peak = ((p.get("after") or {}).get("running_progression") or {}).get("planned_week_peak_blocks")
            if not p.get("draft_id") or p.get("violations") or peak is None or peak > hi:
                if best is None:
                    say(f"assistant on {day}: {d0} long run {m} min refused: "
                        f"{p.get('error') or '; '.join(p.get('violations') or []) or f'runs would reach {peak} vs {hi}'}")
                break
            best = (p, m, peak)
            if peak >= lo:
                break
        if best:
            p, m, peak = best
            api(CR, {"action": "apply", "draft_id": p["draft_id"], "approved": True})
            say(f"assistant on {day}: {why} -> {d0} long run {base} -> {m} min (runs now up to {peak})")
        return
    # over target: the lightest change that fits, run by run from the soonest
    changes, done = {}, []
    for d0, i, s in runs:
        ss = changes.get(d0) or plan_of(d0)
        m = s.get("minutes") or 30
        for how in ("shorten", "ride"):
            trial = list(ss)
            if how == "shorten":
                short = max(15, round(m * 0.5 / 5) * 5)
                if short >= m:
                    continue
                trial[i] = {**s, "minutes": short, "name": f"Easy run, {short} min", "steps": [f"{short} min easy with 4 x 20 s strides"],
                            "note": f"Shortened from {m} min: {why}."}
            else:
                trial[i] = {"sport": "ride", "minutes": m, "name": f"Easy ride (instead of: {s.get('name')})"[:80],
                            "steps": [f"{m} min easy, 60-65% FTP"], "note": f"Swapped by your assistant: {why}; running is deloading."}
            body = [{"date": k, "sessions": v} for k, v in {**changes, d0: trial}.items()]
            p = api(CR, {"action": "preview", "kind": "calendar", "changes": body}, ok=(200, 400))
            bad = [v for v in p.get("violations") or [] if v.startswith(d0)]
            if p.get("draft_id") and not bad:
                changes[d0] = trial
                done.append(f"{d0}: {trial[i]['name']}")
                break
    if changes:
        p = api(CR, {"action": "preview", "kind": "calendar", "changes": [{"date": k, "sessions": v} for k, v in changes.items()]}, ok=(200, 400))
        if p.get("draft_id") and not p.get("violations"):
            api(CR, {"action": "apply", "draft_id": p["draft_id"], "approved": True})
            say(f"assistant on {day}: {why} -> " + " | ".join(done))
        else:
            say(f"assistant on {day}: {why}; no fit passed: {p.get('error') or '; '.join(p.get('violations') or [])}")


def plan_of(date):
    week = api(f"/api/coach/week?date={date}")["week"]
    dd = next(x for x in week if x["date"] == date)
    return [{k: v for k, v in s.items() if k not in ("completion", "missed", "missed_reason")}
            for s in dd["sessions"] if s.get("sport")]


def replace(s, how, gate, a):
    m = s.get("minutes") or 30
    if s["sport"] == "run":
        why = "running is on hold while the accumulated load clears" if gate.get("status") != "open_for_review" else \
            "the forecast puts this run over the planning limit"
    elif s["sport"] == "swim":
        why = "shoulder pinching on the catch: no swimming for a few days"
    else:
        why = "the lifting forecast is over its limit"
    if how == "shorten":
        short = max(15, round(m * 0.6 / 5) * 5)
        return {**s, "minutes": short, "name": f"Easy run, {short} min",
                "steps": [f"{short} min easy, conversational"], "note": f"Shortened from {m} min: {why}."}
    if how == "ride":
        return {"sport": "ride", "minutes": m, "name": f"Easy ride (instead of: {s.get('name')})"[:80],
                "steps": [f"{m} min easy, 60-65% FTP, smooth cadence"], "note": f"Swapped by your assistant: {why}."}
    return {"sport": "rest", "minutes": 0, "name": "Rest", "steps": [], "note": f"Rest instead of {s.get('name')}: {why}."}


def race(a, day):
    t = dt.datetime.combine(day, dt.time(8, 0))
    fitwrite.swim(a.acts / f"{day}_0800_swim.fit", t.timestamp(), 30, sec_per_length=a.swim_25 - 2, rest_every=0, hr=160)
    t += dt.timedelta(minutes=19)
    fitwrite.bike(a.acts / f"{day}_0819_ride.fit", t.timestamp(), [(41 * 60, a.ftp * 0.88)], a.ftp, fitness=a.fitness)
    t += dt.timedelta(minutes=43)
    fitwrite.run(a.acts / f"{day}_0902_run.fit", t.timestamp(), 31 * 60, 168, a.run_pace - 60)


def shots(out, day, name):
    folder = out / "shots" / name
    folder.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "NODE_PATH": subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()}
    subprocess.run(["node", str(HERE / "shots.js"), URL, day.isoformat(), str(folder)], env=env, check=False, timeout=600)


if __name__ == "__main__":
    main()
