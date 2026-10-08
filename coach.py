"""coach.py - the daily diagnostic, check-ins, today's plan, and time-split workouts.

Morning diagnostic (6 min, ERG, the same watts every day):
    0-2 min  60 W   settle in
    2-4 min  90 W   heart rate at the end of this is the key number
    4-5 min 120 W   how the legs answer a small push
    5-6 min  easy   heart-rate recovery: how far it falls in the 60 s after the push
Then legs (1-10, 10 = wrecked), breathing (1-10) and the gut call
(go / easy / no). Heart rate is read off the watch and typed in on the phone
(no extra Bluetooth); it can be corrected later from COROS.

Verdict: against the rider's own normal - the median of recent tests - once there
are three. Until then the gut call and the legs lead.
    HR at 90 W  6+ bpm above normal       -> fatigue (easy)
    recovery    6+ bpm less than normal   -> fatigue (easy)
    HR 8+ below normal with heavy legs    -> deep fatigue (rest)
    legs 8+ or gut "no"                   -> rest
    legs 6-7 or gut "easy"                -> easy
Today's plan (verdict, note, workout) is written by the coach - Claude,
through the hub command - or picked on the Coach page.

coach.json (beside the rides folder, kept out of git) holds it all.
"""
import datetime as dt
import copy
import json
import statistics
from pathlib import Path

TEST_STEPS = [{"minutes": 2, "watts": 60}, {"minutes": 2, "watts": 90}, {"minutes": 1, "watts": 120},
              {"minutes": 1, "watts": 30}]
TEST_NAME = "Morning diagnostic (6 min)"
VERDICTS = {"go": "Go - train as planned", "easy": "Easy only", "rest": "Rest"}


def file_for(rides_dir):
    return Path(rides_dir).resolve().parent / "coach.json"


def load(path):
    try:
        d = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("checkins", {})
    d.setdefault("plans", {})
    d.setdefault("ratings", {})           # ride id -> {"rpe": 1-10, "at": ...}: how hard the rider said it was
    d["_path"] = str(path)
    return d


def save(d):
    p = Path(d["_path"])
    import schedule_tracking
    try: previous = json.loads(p.read_text())
    except (OSError, ValueError): previous = {}
    # Persist the audit without mutating caller state (including reviewed previews).
    saved = copy.deepcopy(d)
    if "schedule_tracking" in previous:
        saved["schedule_tracking"] = copy.deepcopy(previous["schedule_tracking"])
    schedule_tracking.capture(saved, previous)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v for k, v in saved.items() if k != "_path"}, indent=1))
    tmp.replace(p)


def today():
    return dt.date.today().isoformat()


def _num(v, lo, hi, precision=0):
    if v in (None, ""):
        return None
    v = float(v)
    if not lo <= v <= hi:
        raise ValueError(f"{v:g} is outside {lo}-{hi}")
    return round(v, precision) if precision else round(v)


def record(d, date, fields):
    """Add or update the day's check-in (partial updates are fine)."""
    c = d["checkins"].setdefault(date, {})
    for k, lo, hi in (("hr90", 40, 220), ("hr120", 40, 220), ("hr_after", 30, 220), ("legs", 1, 10), ("feet", 1, 10), ("shoulders", 1, 10), ("hops", 0, 100), ("hops_left", 0, 100), ("hops_right", 0, 100), ("breathing", 1, 10),
                      ("sleep", 1, 10), ("motivation", 1, 10)):
        if k in fields:
            c[k] = _num(fields[k], lo, hi)
    if "hops_left" in fields or "hops_right" in fields:          # the hop test, leg by leg: the worse leg is the number
        sides = [c.get(k) for k in ("hops_left", "hops_right") if c.get(k) is not None]
        c["hops"] = min(sides) if sides else None
    import wellness                                                # validated instruments (Hooper; pain by site)
    c.update(wellness.clean_daily(fields))
    if wellness.hooper_index(c) is not None:
        c["hooper_index"] = wellness.hooper_index(c)
    if "journal" in fields:                                        # the rider's own words: kept, not scored
        c["journal"] = str(fields["journal"] or "").strip()[:4000] or None
    if "gut" in fields:
        if fields["gut"] not in ("go", "easy", "no", None, ""):
            raise ValueError("gut is go, easy or no")
        c["gut"] = fields["gut"] or None
    for k in ("note", "test_ride", "test_at"):
        if k in fields:
            c[k] = str(fields[k])[:500] if fields[k] is not None else None
    if c.get("journal") or c.get("flags"):                        # the journal flags - it asks, never scores
        import journal
        journal.refresh(c)
    top = c.get("hr120") or c.get("hr90")
    if top and c.get("hr_after"):
        c["hrr"] = top - c["hr_after"]                 # heart-rate recovery: end of the push -> 60 s later
    c["verdict"], c["why"] = verdict(d, date)
    import recovery
    recovery.observe_checkin(d,date,c)
    return c


def baseline(d, before):
    """The rider's normal: medians of the last (up to) seven tests before this day."""
    past = [c for day, c in sorted(d["checkins"].items()) if day < before and c.get("hr90")][-7:]
    if len(past) < 3:
        return None
    b = {"tests": len(past), "hr90": statistics.median(c["hr90"] for c in past)}
    hrr = [c["hrr"] for c in past if c.get("hrr") is not None]
    b["hrr"] = statistics.median(hrr) if len(hrr) >= 3 else None
    return b


def verdict(d, date):
    """(go/easy/rest or None, reasons)."""
    import journal
    c = journal.effective(d["checkins"].get(date, {}))    # a confirmed journal flag counts like its slider
    why, level = [], 0                                   # 0 go, 1 easy, 2 rest
    legs, gut = c.get("legs"), c.get("gut")
    if c.get("illness"):
        level = max(level, 1); why.append("journal flag confirmed: feeling ill")
    if legs is not None:
        if legs >= 8:
            level = max(level, 2); why.append(f"legs {legs}/10")
        elif legs >= 6:
            level = max(level, 1); why.append(f"legs {legs}/10")
    if gut == "no":
        level = max(level, 2); why.append("your call: not happening")
    elif gut == "easy":
        level = max(level, 1); why.append("your call: easy only")
    b = baseline(d, date)
    if b and c.get("hr90"):
        diff = c["hr90"] - b["hr90"]
        if diff >= 6:
            level = max(level, 1); why.append(f"heart rate at 90 W {diff:+.0f} vs your normal")
        elif diff <= -8 and (legs or 0) >= 6:
            level = max(level, 2); why.append(f"heart rate {diff:+.0f} below normal with heavy legs (deep fatigue)")
        if b.get("hrr") is not None and c.get("hrr") is not None and c["hrr"] <= b["hrr"] - 6:
            level = max(level, 1); why.append(f"recovery {c['hrr']} bpm vs your normal {b['hrr']:.0f}")
    elif c.get("hr90") and not b:
        why.append(f"building your baseline ({sum(1 for x in d['checkins'].values() if x.get('hr90'))}/3 tests)")
    if legs is None and gut is None and not c.get("hr90"):
        return None, []
    if level == 0 and not [w for w in why if not w.startswith("building")]:
        why.insert(0, "everything looks normal")
    return ["go", "easy", "rest"][level], why


SPORTS = ("ride", "swim", "run", "walk", "gym", "test", "rest", "other")


def set_plan(d, date, verdict_=None, note=None, workout=None, focus_=None, sport=None, minutes=None):
    """focus_: a focus.PRESETS key or a custom {name, rpm, watts|pct}; "" clears it back to the default.
    sport + minutes: the day's marker on the calendar (e.g. swim, 60) - what to do and for how long."""
    import focus
    p = d["plans"].setdefault(date, {})
    if sport is not None or minutes is not None:
        p.pop("sessions", None)  # a new single-session marker replaces an older multi-session schedule
    if sport is not None:
        if sport not in SPORTS and sport != "":
            raise ValueError(f"sport is one of {', '.join(SPORTS)}")
        if sport:
            p["sport"] = sport
        else:
            p.pop("sport", None)
    if minutes is not None:
        m = int(minutes)
        if not 0 <= m <= 600:
            raise ValueError("minutes is 0-600")
        p["minutes"] = m
    if focus_ is not None:
        f = focus.check(focus_)
        if f is None:
            p.pop("focus", None)
        else:
            p["focus"] = f
    if verdict_ is not None:
        if verdict_ not in VERDICTS:
            raise ValueError("verdict is go, easy or rest")
        p["verdict"] = verdict_
    if note is not None:
        p["note"] = str(note)[:1000]
    if workout is not None:
        p["workout"] = workout or None
    p["updated"] = dt.datetime.now().isoformat(timespec="minutes")
    return p


def set_sessions(d, date, sessions, _trusted=False, draft=False):
    """Replace the day's ordered sessions. Each session can carry a compact workout outline."""
    if not isinstance(sessions, list) or len(sessions) > 5:
        raise ValueError("sessions must be a list of at most five")
    clean = []
    for item in sessions:
        if not isinstance(item, dict) or item.get("sport") not in SPORTS:
            raise ValueError(f"session sport is one of {', '.join(SPORTS)}")
        minutes = _num(item.get("minutes", 0), 0, 600, 4) if item.get("sport") in ("ride","swim","run") else int(item.get("minutes", 0))
        if minutes is None or not 0 <= minutes <= 600:
            raise ValueError("session minutes is 0-600")
        steps = item.get("steps") or []
        if not isinstance(steps, list) or len(steps) > 30:
            raise ValueError("session steps must be a list of at most 30")
        entry = {"sport": item["sport"], "minutes": minutes,
                 "name": str(item.get("name") or item["sport"].title())[:80],
                 "steps": [str(step)[:160] for step in steps],
                 "note": str(item.get("note") or "")[:300],
                 "workout": str(item.get("workout") or "")[:120] or None}
        if item.get("route_id"):
            if item["sport"] != "ride": raise ValueError("Routes require cycling sessions")
            import routes, re
            if not isinstance(item["route_id"],str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,120}",item["route_id"]): raise ValueError("Choose a saved route")
            try: entry["route_id"] = routes.load(item["route_id"]).id
            except (OSError,ValueError,KeyError): raise ValueError("Saved route is unavailable")
        if item.get("typed_workout"):
            typed=item["typed_workout"]
            if not isinstance(typed,dict):raise ValueError("typed_workout must be an object")
            repeats=int(typed.get("repeats") or 1)
            if not 1<=repeats<=10:raise ValueError("Repeated blocks must be 1–10")
            entry["typed_workout"]={k:str(typed.get(k) or "")[:6000] for k in ("warmup","main","cooldown")}
            entry["typed_workout"]["repeats"]=repeats
        if item.get("skipped_id") in d.get("skipped_workouts",{}):entry["skipped_id"]=item["skipped_id"]
        if item.get("focus"):
            import focus
            entry["focus"]=focus.check(item["focus"])
        if item["sport"]=="ride" and item.get("bike_plan"):
            snapshot=item["bike_plan"]
            if not isinstance(snapshot,dict):raise ValueError("bike_plan must be an object")
            power=snapshot.get("power_steps")
            if not isinstance(power,list) or not 1<=len(power)<=200:raise ValueError("bike_plan needs 1–200 power steps")
            checked=[]
            for step in power:
                if not isinstance(step,dict):raise ValueError("Power step must be an object")
                minutes_=_num(step.get("minutes"),1/60,360,4)
                if minutes_ is None:raise ValueError("Power step needs duration")
                row={"minutes":minutes_}
                for field,lo,hi in (("watts",0,1500),("pct",0,250),("rpm",21,200)):
                    if step.get(field) is not None:row[field]=_num(step[field],lo,hi)
                if ("watts" in row)==("pct" in row):raise ValueError("Power step needs exactly one of watts or pct")
                if step.get("watts_low") is not None or step.get("watts_high") is not None:
                    lo=_num(step.get("watts_low"),20,1500);hi=_num(step.get("watts_high"),20,1500)
                    if lo is None or hi is None or "watts" not in row or not lo<=row["watts"]<=hi:raise ValueError("Invalid prescribed power band")
                    row.update(watts_low=lo,watts_high=hi)
                if step.get("rpm_low") is not None or step.get("rpm_high") is not None:
                    lo=_num(step.get("rpm_low"),30,200);hi=_num(step.get("rpm_high"),30,200)
                    if lo is None or hi is None or lo>hi:raise ValueError("Invalid prescribed cadence range")
                    row.update(rpm_low=lo,rpm_high=hi)
                for key in ("label","section"):
                    if step.get(key):row[key]=str(step[key])[:80]
                checked.append(row)
            if abs(sum(x["minutes"] for x in checked)-minutes)>.1:raise ValueError("Power steps must match planned duration")
            entry["bike_plan"]={"power_steps":checked,"basis":str(snapshot.get("basis") or "Saved planned power stages")[:600]}
        if item.get("cadence") is not None:
            cadence=item["cadence"]
            if not isinstance(cadence,list) or len(cadence)!=2 or not all(isinstance(v,(int,float)) and 20<v<=200 for v in cadence) or cadence[0]>cadence[1]:
                raise ValueError("Cadence must be an ordered two-value rpm range")
            entry["cadence"]=list(cadence)
        if item.get("swim_recipe") is not None:
            if item["sport"]!="swim":raise ValueError("Swim recipes require a swim session")
            import swim_workouts
            entry["swim_recipe"]=swim_workouts.validate_recipe(item["swim_recipe"])
        if item.get("run_recipe") is not None:
            if item["sport"] != "run": raise ValueError("Running recipes require running sessions")
            import run_workouts
            entry["run_recipe"] = run_workouts.validate(item["run_recipe"])
            recipe = entry["run_recipe"]
            if minutes + .01 < recipe["minutes"] or recipe["time_complete"] and abs(minutes-recipe["minutes"]) > .05:
                raise ValueError("Session duration must match the written running stages")
        if item.get("workout_import_id"):
            import workout_imports
            entry["workout_import_id"]=workout_imports.identifier(item["workout_import_id"])
        if item["sport"] == "swim" and item.get("swim_profile"):
            import programming
            if item["swim_profile"] not in programming.SWIM_PROFILE_IDS:
                raise ValueError("Unknown swim profile")
            entry["swim_profile"] = item["swim_profile"]
        if item["sport"] == "swim" and item.get("swim_plan"):
            snap=item["swim_plan"]
            if not isinstance(snap,dict): raise ValueError("swim_plan must be an object")
            entry["swim_plan"]={k:str(snap[k])[:600] for k in ("why","purpose") if snap.get(k)}
            for key,allowed in (("stroke_mix",("free","back","breast","fly")),("work_mix",("drill_swim","kick","pull","swim"))):
                if key in snap:
                    mix=snap[key]
                    if not isinstance(mix,dict) or any(k not in allowed or not isinstance(v,(int,float)) or not 0<=v<=100 for k,v in mix.items()):
                        raise ValueError("Invalid planned swim ratios")
                    if not 99<=sum(mix.values())<=101: raise ValueError("Planned swim ratios must total 100")
                    entry["swim_plan"][key]={k:float(mix.get(k,0)) for k in allowed}
        if item["sport"] == "gym" and item.get("lifts"):            # planned lifts (lifting.py): checked, and the rider's rules apply
            import lifting
            entry["lifts"] = item["lifts"] if _trusted else lifting.clean(d, item["lifts"], draft=draft)
            if item.get("override"):
                entry["override"] = str(item["override"])[:300]
        if item.get("library_id"):
            import workout_library
            ident=workout_library.identifier(item["library_id"])
            if ident not in d.get("workout_library",{}):raise ValueError("Library workout not found")
            entry["library_id"]=ident
        if item.get("workout_goals"):
            import workout_library
            entry["workout_goals"]=workout_library.clean_goals(item["sport"],item["workout_goals"])
        for key in ("goal_request_id","goal_comparison"):
            if item.get(key):entry[key]=item[key]
        if entry.get("skipped_id"):
            entry = skipped_marker(entry, entry["skipped_id"])
        clean.append(entry)
    p = d["plans"].setdefault(date, {})
    p["sessions"] = clean
    if clean:
        p.pop("sport", None)
        p.pop("minutes", None)
    p["updated"] = dt.datetime.now().isoformat(timespec="minutes")
    return p


# ── dates to plan backward from ──────────────────────────────────────────────
EVENT_KINDS = ("test", "race", "goal")


def add_event(d, date, name, kind="race", sport="bike", note="", detail=None):
    """A date to plan toward: an FTP test, a race, a goal. Returns it (with an id)."""
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        raise ValueError("date is YYYY-MM-DD")
    if kind not in EVENT_KINDS:
        raise ValueError(f"kind is one of {', '.join(EVENT_KINDS)}")
    if sport not in ("bike", "run", "swim", "tri", "other"):
        raise ValueError("sport is bike, run, swim, tri or other")
    ev = {"id": f"{date}-{re.sub(r'[^a-z0-9]+', '-', str(name).lower()).strip('-')[:30]}", "date": str(date),
          "name": str(name)[:80], "kind": kind, "sport": sport, "note": str(note or "")[:300]}
    if detail:                                   # what the race is (programming.py plans backward from it)
        import programming
        det = {"type": detail.get("type") if detail.get("type") in programming.EVENT_TYPES else None}
        if detail.get("distance"):
            det["distance"] = str(detail["distance"])[:30]
        if detail.get("strokes"):
            det["strokes"] = [{"stroke": x.get("stroke"), "m": int(x.get("m") or 0)} for x in detail["strokes"][:12]
                              if x.get("stroke") in ("free", "back", "breast", "fly", "im")]
        ev["detail"] = {k: v for k, v in det.items() if v}
    d.setdefault("events", [])
    d["events"] = [e for e in d["events"] if e["id"] != ev["id"]] + [ev]
    return ev


def remove_event(d, eid):
    before = len(d.get("events", []))
    d["events"] = [e for e in d.get("events", []) if e["id"] != eid]
    return len(d["events"]) < before


def upcoming(d, today=None, running_cleared_in=None):
    """Events from today on, soonest first, each with days to go and what that means for the days before it."""
    today = dt.date.fromisoformat(today) if isinstance(today, str) else (today or dt.date.today())
    out = []
    for e in sorted(d.get("events", []), key=lambda e: e["date"]):
        n = (dt.date.fromisoformat(e["date"]) - today).days
        if n < 0:
            continue
        notes = []
        if e["kind"] == "test":
            notes.append("test day - fresh legs, full warm-up" if n == 0 else
                         "easy rides only from here: the test needs fresh legs" if n <= 2 else
                         f"train normally for {n - 2} more day{'s' if n - 2 != 1 else ''}, then 2 easy days: nothing hard in the last 48 h")
        elif e["kind"] == "race":
            taper = {"run": 3, "bike": 3, "swim": 2, "tri": 7}.get(e["sport"], 3)
            saved_taper=next((p for p in d.get('phase_profiles',[]) if p.get('kind')=='taper' and p['start']<=e['date']<p['end']),None) if (d.get('program_goal') or {}).get('target')==e['date'] else None
            if saved_taper:
                notes.append('saved program: final preparation from '+saved_taper['start']+'; ease workload from recently tolerated training. Race-day readiness still requires review.')
            elif n == 0:
                notes.append("race day")
            elif n <= taper:
                notes.append(f"taper: easy and short until race day (last {taper} days)")
            else:
                notes.append(f"last hard session by {(dt.date.fromisoformat(e['date']) - dt.timedelta(days=taper + 2)).isoformat()}, "
                             f"then {taper} days of taper")
            if e["sport"] in ("run", "tri") and running_cleared_in is not None:
                if running_cleared_in > n:
                    notes.append(f"heads-up: the load model has running cleared in about {running_cleared_in} days - "
                                 f"{running_cleared_in - n} days after this. No running while held; review whether comfortable walking participation is appropriate.")
                else:
                    notes.append(f"model projects the threshold about {n - running_cleared_in} days before the event; this is not clearance or enough preparation by itself. Running remains subject to the full gate.")
        out.append({**e, "days": n, "notes": notes})
    return out


RPE_WORDS = {1: "very easy", 2: "easy", 3: "comfortable", 4: "steady", 5: "working", 6: "hard-ish", 7: "hard",
             8: "very hard", 9: "near max", 10: "all out"}


def rate(d, ride, rpe):
    """The rider's one-tap effort rating for a ride (1-10, how hard the whole ride felt)."""
    import re
    if not re.fullmatch(r"ride_[0-9_\-]{10,30}", ride or ""):
        raise ValueError("ride is an id like ride_2026-09-28_0949")
    rpe = int(rpe)
    if not 1 <= rpe <= 10:
        raise ValueError("rpe is 1-10")
    d["ratings"][ride] = {"rpe": rpe, "at": dt.datetime.now().isoformat(timespec="minutes")}
    return d["ratings"][ride]


ATTEMPT_MIN = 10          # under this many minutes it was an attempt, whatever was planned
ATTEMPT_SHARE = 0.5       # ...and so is anything under half of what the day's plan asked for


def counts(d, date, sport, minutes):
    """Did this count as the day's session? An attempt that was cut short (the rider's rule, 2026-09-30: a
    5-minute ride the app broke is not "today's ride") doesn't: it isn't shown as done and isn't up for rating.
    It counts from 10 minutes, and from half the planned time when that sport was planned."""
    if minutes < ATTEMPT_MIN:
        return False
    p = (d.get("plans") or {}).get(date) or {}
    want = {"bike": "ride"}.get(sport, sport)
    planned = [s.get("minutes") for s in (p.get("sessions") or [p]) if s.get("sport") == want and s.get("minutes")]
    return not planned or minutes >= ATTEMPT_SHARE * max(planned)


def last_ride(rides_dir, min_seconds=300, d=None):
    """The latest ride that counted: {id, date, minutes}. Without `d`, five minutes of pedalling. With the coach
    data, the day's pieces are one ride (stopped, then resumed or restarted) and the whole has to count (see counts)."""
    import csv
    days = {}
    for p in sorted(Path(rides_dir).glob("ride_*.csv"), reverse=True):
        if p.stem.count("_") != 2:
            continue                                  # _events / _session / _report files
        try:
            with open(p, newline="") as f:
                secs = {row["time"] for row in csv.DictReader(f) if float(row.get("cadence_rpm") or 0) > 20}
        except (OSError, ValueError, KeyError):
            continue
        if d is None:
            if len(secs) >= min_seconds:
                return {"id": p.stem, "date": p.stem[5:15], "minutes": round(len(secs) / 60)}
        elif len(secs) >= 60:
            days.setdefault(p.stem[5:15], []).append((p.stem, len(secs)))
    for day in sorted(days, reverse=True):
        total = sum(n for _, n in days[day])
        if counts(d, day, "bike", total / 60):
            return {"id": max(days[day], key=lambda x: x[1])[0], "date": day, "minutes": round(total / 60)}
    return None


MISS_REASONS = ("busy", "sick", "sore", "tired", "travel", "weather", "other")
TRAINABLE = ("ride", "swim", "run", "gym", "walk")


def skipped_marker(session, ident):
    return {"sport":"rest", "minutes":0, "name":session.get("name","Workout"), "steps":[],
            "note":"Cancelled by athlete; original workout retained for restore.", "workout":None, "skipped_id":ident}


def scheduled_view(d, session):
    """Original prescription for display/accounting; storage keeps zero planned dose."""
    ident = session.get("skipped_id")
    original = (d.get("skipped_workouts", {}).get(ident) or {}).get("session")
    if ident and original:
        return {**copy.deepcopy(original), "skipped_id": ident, "cancelled": True}
    return copy.deepcopy(session)


def attach_completions(d, k, sessions, actual):
    """Pair each planned session on day k with what was actually done (completion), sport by sport."""
    used = set()
    gym_index = 0
    for s in sessions:
        if s.get("skipped_id"): continue  # a later same-sport activity is not this cancelled prescription
        if s.get("sport") == "gym":
            log = next((l for l in (d.get("lifting") or {}).get("logs", [])
                        if l.get("date") == k and l.get("session") == s.get("name")
                        and (l.get("inputs") or {}).get("session_index") in (None, gym_index)), None)
            if log is None:   # a lift logged that day under another name still counts for the gym session
                log = next((l for l in (d.get("lifting") or {}).get("logs", []) if l.get("date") == k), None) if gym_index == 0 else None
            gym_index += 1
            if log:
                s["completion"] = {"minutes": log.get("minutes"), "lifting": log}
            continue
        want = {"ride": "bike"}.get(s.get("sport"), s.get("sport"))
        matches = [(n, a) for n, a in enumerate(actual) if n not in used
                   and {"ride": "bike"}.get(a.get("sport"), a.get("sport")) == want
                   and a.get("minutes", 0) >= max(ATTEMPT_MIN, (s.get("minutes") or 0) * ATTEMPT_SHARE)]
        if matches:
            n, a = matches[0]
            used.add(n)
            s["completion"] = a
    return sessions


def mark_missed(d, k, sessions, as_of=None):
    """A planned session on a past day with nothing recorded against it is missed (with the athlete's reason, if given)."""
    as_of = as_of or today()
    reasons = (d.get("missed") or {}).get(k, {})
    for i, s in enumerate(sessions):
        if k < as_of and not s.get("skipped_id") and not s.get("completion") and s.get("sport") in TRAINABLE and (s.get("minutes") or 0) > 0:
            s["missed"] = True
            if reasons.get(str(i)):
                s["missed_reason"] = reasons[str(i)]
    return sessions


def missed_days(d, start, end, done=None, as_of=None):
    """{date: [{index, name, sport, minutes, reason}]} for every missed session from start up to end (exclusive)."""
    out = {}
    day0, day1 = dt.date.fromisoformat(start), dt.date.fromisoformat(min(end, as_of or today()))
    while day0 < day1:
        k = day0.isoformat()
        p = d.get("plans", {}).get(k) or {}
        ss = [scheduled_view(d, s) for s in (p.get("sessions") or ([p] if p.get("sport") else []))]
        if ss:
            mark_missed(d, k, attach_completions(d, k, ss, copy.deepcopy((done or {}).get(k, []))), as_of)
            miss = [{"index": i, "name": s.get("name") or s.get("sport"), "sport": s.get("sport"), "minutes": s.get("minutes"),
                     "reason": "cancelled" if s.get("skipped_id") else (s.get("missed_reason") or {}).get("reason"),
                     "status": "cancelled" if s.get("skipped_id") else "missed"} for i, s in enumerate(ss) if s.get("missed") or s.get("skipped_id")]
            if miss:
                out[k] = miss
        day0 += dt.timedelta(days=1)
    return out


def session_action(d, date, index, action):
    """Skip without losing the plan; delete only unperformed scheduled work."""
    import copy, uuid
    plan=d.get("plans",{}).get(date) or {}
    items=plan.get("sessions") or []
    if date < today() or not isinstance(index,int) or not 0 <= index < len(items):
        raise ValueError("Select an unperformed workout today or later")
    item=items[index]
    # Indexed reports and actual workouts must never be shifted or discarded.
    logs=(d.get("lifting") or {}).get("logs",[])
    has_actual=any(x.get("date")==date and x.get("session")==item.get("name") for x in logs) or date+":"+str(index) in d.get("training_feedback",{})
    if item.get("completion") or has_actual:
        raise ValueError("Keep completed workouts and their reports; edit the recorded workout instead")
    if action=="skip":
        if item.get("skipped_id"):return plan
        ident=uuid.uuid4().hex
        d.setdefault("skipped_workouts",{})[ident]={"date":date,"session":copy.deepcopy(item),"at":dt.datetime.now().isoformat(timespec="seconds")}
        # Zero-dose placeholder keeps all session indices stable; the original is recoverable.
        items[index]=skipped_marker(item, ident)
    elif action=="restore":
        saved=d.get("skipped_workouts",{}).get(item.get("skipped_id"))
        if not saved:raise ValueError("No skipped workout to restore")
        items[index]=copy.deepcopy(saved["session"])
    elif action=="delete":
        if any(x.get("completion") for x in items) or any(x.get("date")==date for x in logs) or any(k.startswith(date+":") for k in d.get("training_feedback",{})):raise ValueError("Cannot shift a day with completed workouts")
        d.setdefault("removed_workouts",[]).append({"date":date,"session":copy.deepcopy(item)})
        items.pop(index)
    else:raise ValueError("action is skip, restore, or delete")
    d.setdefault("session_events", []).append({"date":date,"index":index,"action":action,"name":item.get("name"),"at":dt.datetime.now().isoformat(timespec="seconds")})
    plan["updated"]=dt.datetime.now().isoformat(timespec="minutes")
    return plan


def record_missed(d, date, index, reason, note=""):
    """The athlete says why a session didn't happen. Kept for the coach and the Sunday review."""
    if reason not in MISS_REASONS:
        raise ValueError("reason: one of " + ", ".join(MISS_REASONS))
    p = d.get("plans", {}).get(date) or {}
    ss = p.get("sessions") or ([p] if p.get("sport") else [])
    if not isinstance(index, int) or not 0 <= index < len(ss):
        raise ValueError("no planned session with that index on that day")
    if date >= today():
        raise ValueError("only past sessions can be missed")
    entry = {"reason": reason, "note": str(note or "")[:300], "at": dt.datetime.now().isoformat(timespec="minutes")}
    d.setdefault("missed", {}).setdefault(date, {})[str(index)] = entry
    return entry


def week(d, date, done=None):
    """Monday-Sunday around `date`: each day's plan (sport, minutes, note, verdict) and what was done (done: {date: [...]})."""
    day0 = dt.date.fromisoformat(date)
    mon = day0 - dt.timedelta(days=day0.weekday())
    out = []
    for i in range(7):
        k = (mon + dt.timedelta(days=i)).isoformat()
        p = d["plans"].get(k) or {}
        sessions = p.get("sessions") or ([{"sport": p.get("sport"), "minutes": p.get("minutes"),
                                          "name": p.get("sport", "").title(), "steps": [],
                                          "note": p.get("note") or "", "workout": p.get("workout")}] if p.get("sport") else [])
        sessions = [scheduled_view(d, s) for s in sessions]
        import session_explanations
        for n, session in enumerate(sessions):session["explanation"] = session_explanations.describe(d,k,n,session)
        actual = copy.deepcopy((done or {}).get(k, []))
        attach_completions(d, k, sessions, actual)
        mark_missed(d, k, sessions)
        out.append({"date": k, "sport": p.get("sport") or (sessions[0]["sport"] if sessions else None),
                    "minutes": p.get("minutes") or (sessions[0]["minutes"] if sessions else None),
                    "sessions": sessions, "note": p.get("note"),
                    "verdict": p.get("verdict"), "done": (done or {}).get(k, []),
                    "recovery_day": k < today() and not any(float(a.get("minutes") or 0)>0 for a in actual)
                        and not any(l.get("date")==k for l in (d.get("lifting") or {}).get("logs", []))})
    return out


def day(d, date):
    plan = copy.deepcopy(d["plans"].get(date))
    if plan and plan.get("sessions") is not None: plan["sessions"] = [scheduled_view(d, s) for s in plan["sessions"]]
    return {"date": date, "checkin": d["checkins"].get(date), "plan": plan,
            "baseline": baseline(d, date)}


# ── time-split workouts ─────────────────────────────────────────────────────

def split_parts(intervals):
    """The standard shape: warm-up, ramp, interval 1, rest, ..., interval N, cool-down."""
    parts = [{"kind": "warmup", "label": "Warm-up"}, {"kind": "ramp", "label": "Ramp"}]
    for i in range(intervals):
        parts.append({"kind": "interval", "label": f"Interval {i + 1}"})
        if i < intervals - 1:
            parts.append({"kind": "rest", "label": f"Rest {i + 1}"})
    parts.append({"kind": "cooldown", "label": "Cool-down"})
    return parts


def rebalance(minutes, index, new_value, total, floor=0.25):
    """Set part `index` to new_value; every other part changes in proportion to
    its current size so the total stays the same (the sliding bar chart)."""
    new_value = max(floor, min(total - floor * (len(minutes) - 1), new_value))
    others = [m for i, m in enumerate(minutes) if i != index]
    rest_now, rest_new = sum(others), total - new_value
    out = []
    for i, m in enumerate(minutes):
        if i == index:
            out.append(new_value)
        else:
            out.append(rest_new * (m / rest_now) if rest_now > 0 else rest_new / len(others))
    # keep every part at least `floor` without breaking the total: pin the ones that
    # fell short, take the difference from the rest, and repeat until nothing is short
    pinned = set()
    for _ in range(len(out)):
        short = [i for i, m in enumerate(out) if i != index and i not in pinned and m < floor - 1e-12]
        if not short:
            break
        for i in short:
            out[i] = floor
            pinned.add(i)
        spare = [i for i in range(len(out)) if i != index and i not in pinned]
        excess = sum(out) - total
        pool = sum(out[i] for i in spare)
        for i in spare:
            out[i] -= excess * out[i] / pool if pool else 0
    return out


def split_to_blocks(parts):
    """Coach-page parts (minutes + intensity) -> workout-builder blocks."""
    blocks = []
    for p in parts:
        m = float(p["minutes"])
        if m <= 0:
            continue
        label = {"label": str(p["label"])[:40]} if p.get("label") else {}   # names the part in the report
        if p.get("section"):label["section"] = str(p["section"])[:80]
        if p["kind"] == "ramp":
            blocks.append({"type": "ramp", "minutes": m, **({"from_watts":p["from_watts"],"to_watts":p["to_watts"]} if "from_watts" in p else {"from":p.get("from",50),"to":p.get("to",75)}), **label})
        elif p.get("watts"):
            blocks.append({"type": "steady", "minutes": m, "watts": int(p["watts"]), **({"watts_low":p["watts_low"],"watts_high":p["watts_high"]} if p.get("watts_low") is not None else {}), **label})
        else:
            blocks.append({"type": "steady", "minutes": m, "pct": int(p.get("pct", 60)), **label})
    return blocks
