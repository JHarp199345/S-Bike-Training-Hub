"""journey.py - a fictional athlete lives a 12-week sprint-triathlon program on a real hub, for the README.

Everything goes through the hub the way real use does: the welcome setup, the program builder, morning
check-ins, watch files for every ride, swim and run (written as .fit, read by the hub's own importer),
lifting check-offs, Sunday check-ins, missed sessions with reasons. The hub runs under a fake clock
(libfaketime) that this script moves forward one day at a time, so every page sees the athlete's "today".
No numbers are drawn on the screenshots: everything shown is what the hub calculated.

At each checkpoint it calls tools/demo/shots.js to photograph the Coach.

  python3 tools/demo/journey.py [--out DIR] [--no-shots]

Needs Linux with libfaketime (apt install faketime) and Node Playwright (for the screenshots).
The athlete, Jordan Lee, is invented; any resemblance is coincidence.
"""
import argparse
import datetime as dt
import json
import os
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
        hard = any(k in name for k in ("race", "brick", "steady", "openers"))
        pace = self.run_pace - (55 if "race" in name or "brick" in name else 25 if hard else 0)
        hr = 150 - self.fitness + (14 if hard else 0)
        secs = s["minutes"] * 60 * self.rng.uniform(0.96, 1.04)
        if "run / walk" in name or "hop test" in name:
            pace, hr = pace + 70, hr - 6
        fitwrite.run(self.acts / f"{day}_{at:%H%M}_run.fit", at.timestamp(), secs, hr, pace)

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--until", help="stop after this date (YYYY-MM-DD), for checking a stretch")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    hub = Hub(out)
    hub.build()
    hub.set_time(dt.datetime.combine(PRE, dt.time(7, 0)))
    hub.start()
    log = open(out / "journey.log", "w")
    say = lambda *m: (print(*m, flush=True), print(*m, file=log, flush=True))
    try:
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
        # ── twelve weeks, day by day ──
        day = START
        week_done = week_plan = 0
        stop = dt.date.fromisoformat(args.until) if args.until else RACE + dt.timedelta(days=1)
        while day <= stop:
            hub.set_time(dt.datetime.combine(day, dt.time(6, 30)))
            a.sick = any(k[0] == day and k[1] is None and v[0] == "sick" for k, v in MISS.items())
            if day == dt.date(2026, 6, 25):
                a.shin = 6
            elif day == dt.date(2026, 6, 29):
                a.shin = 3
            elif day == dt.date(2026, 7, 6):
                a.shin = 2
            a.shoulder = 7 if dt.date(2026, 7, 8) <= day <= dt.date(2026, 7, 10) else 4 if day <= dt.date(2026, 7, 13) and day > dt.date(2026, 7, 10) else 2
            checkin(day, a)
            week = api(f"/api/coach/week?date={day.isoformat()}")["week"]
            today = next(x for x in week if x["date"] == day.isoformat())
            at = dt.datetime.combine(day, dt.time(6, 45))
            hard_today = 0
            for i, s in enumerate(today["sessions"]):
                sp = s.get("sport")
                if sp in (None, "rest") or not s.get("minutes"):
                    if sp == "other" and "Race day" in (s.get("name") or ""):
                        race(a, day)
                    continue
                week_plan += s["minutes"]
                miss = MISS.get((day, sp)) or MISS.get((day, None))
                if miss:
                    continue
                if sp == "ride":
                    a.ride(day, s, at)
                elif sp == "run":
                    a.run(day, s, at)
                elif sp == "swim":
                    a.swim(day, s, at)
                elif sp == "gym":
                    api("/api/coach/lifting/log", {"date": day.isoformat(), "session_index": 0, "rpe": 6, "wellness": 7})
                week_done += s["minutes"]
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
            a.fatigue = max(2.0, min(8.0, a.fatigue * 0.7 + 1.0 + 1.2 * hard_today))
            # the next morning, say why anything was missed (as the athlete would on the calendar)
            prev = day - dt.timedelta(days=1)
            for (d0, sp), (why, note) in MISS.items():
                if d0 == prev:
                    pw = api(f"/api/coach/week?date={prev.isoformat()}")["week"]
                    pd = next(x for x in pw if x["date"] == prev.isoformat())
                    for i, s in enumerate(pd["sessions"]):
                        if s.get("missed") and (sp is None or s.get("sport") == sp):
                            api("/api/coach/missed", {"date": prev.isoformat(), "index": i, "reason": why, "note": note})
            if day.weekday() == 0 or a.shin >= 6 or a.shoulder >= 6:
                assistant_review(day, a, say)
            if day.weekday() == 6:
                api("/api/coach/weekly", {"sunday": day.isoformat(), "legs": round(a.fatigue), "feet": a.shin, "shoulders": 3,
                                          "week": 8 if week_done >= 0.85 * max(1, week_plan) else 6,
                                          "hops_left": 22, "hops_right": 21 if a.shin < 5 else 15,
                                          "run_response": "resolved" if a.shin < 5 else "pulling",
                                          "note": "Good week." if week_done >= 0.85 * max(1, week_plan) else "Lost a couple of sessions."})
                a.week_passes(week_done / max(1, week_plan))
                say(f"week ending {day}: planned {week_plan} min, done {week_done} min, ftp {a.ftp}, easy pace {a.run_pace:.0f} s/km")
                week_done = week_plan = 0
            if day in CHECKPOINTS and not args.no_shots:
                hub.set_time(dt.datetime.combine(day, dt.time(19, 30)))
                shots(out, day, CHECKPOINTS[day])
            day += dt.timedelta(days=1)
        say("done:", out)
    finally:
        hub.stop()


def assistant_review(day, a, say):
    """What the athlete's AI assistant does with the hub's evidence (scripted here; in real use the assistant
    reads get_today / get_recent_weeks and calls set_plan): while the running gate holds, the coming week's runs
    become easy rides of the same length; after a shoulder flare-up, swims become easy rides for a few days."""
    gate = (api(f"/api/coach/block?date={day.isoformat()}").get("running_gate") or {}).get("status")
    shoulder = a.shoulder >= 6
    changed = []
    for k in range(0, 8):
        d0 = day + dt.timedelta(days=k)
        week = api(f"/api/coach/week?date={d0.isoformat()}")["week"]
        dd = next(x for x in week if x["date"] == d0.isoformat())
        ss = [s_ for s_ in dd["sessions"] if s_.get("sport")]
        new, swapped = [], []
        for s_ in ss:
            s_ = {k2: v for k2, v in s_.items() if k2 not in ("completion", "missed", "missed_reason")}
            hold_run = s_["sport"] == "run" and gate == "hold"
            hold_swim = s_["sport"] == "swim" and shoulder and k <= 4
            if (hold_run or hold_swim) and not s_.get("completion"):
                m = s_.get("minutes") or 30
                why = ("Running is on hold while the shin's accumulated load clears" if hold_run else
                       "Shoulder pinching on the catch: no swimming for a few days")
                new.append({"sport": "ride", "minutes": m, "name": f"Easy ride (instead of: {s_.get('name')})",
                            "steps": [f"{m} min easy, 60-65% FTP, smooth cadence"], "note": why + " - swapped by your assistant.",
                            "shape": s_.get("shape")})
                swapped.append(s_.get("name"))
            else:
                new.append(s_)
        if swapped:
            api("/api/coach/plan", {"date": d0.isoformat(), "sessions": new,
                                    "note": "Assistant: " + "; ".join(f"{n} -> easy ride" for n in swapped)})
            changed.append(f"{d0}: {', '.join(swapped)}")
    if changed:
        say(f"assistant on {day}: running gate {gate}, shoulder {a.shoulder}/10 -> " + " | ".join(changed))


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
