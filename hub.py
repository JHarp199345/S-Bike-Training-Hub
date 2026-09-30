"""hub.py - the bike hub without the pages: read everything, set today's plan.

This is how the coach (Claude) works with the hub: plain commands against the
bridge's own API on this Mac, readable text out (or --json).

  hub status                          live numbers, FTP, today's streak and bests
  hub today [--date D]                check-in, diagnostic, verdict, plan
  hub checkins [--days 14]            recent check-ins and diagnostics
  hub checkin --feet 5 --legs 5 --gut easy --note "post-run soreness" ...
  hub plan --verdict easy --note "..." [--workout ID] [--focus cadence|grit|speed|recovery|off] [--date D]
  hub rides [--days 7]                recent rides: time, watts, load
  hub fitness                         fitness, fatigue, form
  hub milestones                      streaks, totals, next up
  hub workouts                        the workout list
  hub workout add FILE.json           {name, note, blocks} from a file
  hub workout start ID                start it now (ERG)
  hub split --total 30 --intervals 3 [--interval-pct 80] [--name N] [--plan] [--ride]
  hub diagnostic                      start the 6-minute morning test now
  hub load                            engine / impact / muscle: fitness, fatigue, zone, week budget, readiness
  hub import URL|FILE ...             add watch activity files (.fit/.tcx) - URLs or local files
  hub steps [DATE=STEPS ...]          daily step counts from the watch (walking counts toward the feet)
  hub capacity SYSTEM WEEK [--note ..]  tune a system's usual week (engine/impact/muscle; "model" clears it)
"""
import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8729"


def call(path, body=None):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except ValueError:
            msg = str(e)
        sys.exit(f"hub: {msg}")
    except OSError:
        sys.exit("hub: the bridge isn't running (start it from the menu icon or the Desktop launcher)")


def show(obj, as_json, text):
    print(json.dumps(obj, indent=1, ensure_ascii=False) if as_json else text)


def fmt_checkin(date, c, plan=None):
    if not c and not plan:
        return f"{date}: no check-in"
    c = c or {}
    bits = []
    if c.get("hr90"):
        bits.append(f"HR@90W {c['hr90']}")
    if c.get("hr120"):
        bits.append(f"HR@120W {c['hr120']}")
    if c.get("hrr") is not None:
        bits.append(f"recovery {c['hrr']} bpm")
    for k, lab in (("feet", "feet/joints"), ("legs", "legs"), ("breathing", "breathing"), ("sleep", "sleep")):
        if c.get(k):
            bits.append(f"{lab} {c[k]}/10")
    if c.get("gut"):
        bits.append(f"gut: {c['gut']}")
    line = f"{date}: " + (", ".join(bits) or "-")
    if c.get("verdict"):
        line += f"\n   verdict: {c['verdict'].upper()} ({'; '.join(c.get('why', []))})"
    if c.get("note"):
        line += f"\n   report: {c['note']}"
    if plan:
        line += f"\n   plan: {plan.get('verdict', '-')}" + (f" · workout {plan['workout']}" if plan.get("workout") else "")
        if plan.get("note"):
            line += f"\n   note: {plan['note']}"
    return line


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hub", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="raw JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("today"); p.add_argument("--date")
    p = sub.add_parser("checkins"); p.add_argument("--days", type=int, default=14)
    p = sub.add_parser("checkin"); p.add_argument("--date")
    for k in ("feet", "legs", "shoulders", "breathing", "sleep", "motivation", "hr90", "hr120", "hr-after"):
        p.add_argument(f"--{k}", type=int)
    p.add_argument("--gut", choices=["go", "easy", "no"]); p.add_argument("--note")
    p = sub.add_parser("plan"); p.add_argument("--date"); p.add_argument("--verdict", choices=["go", "easy", "rest"])
    p.add_argument("--note"); p.add_argument("--workout")
    p.add_argument("--focus", help="cadence, grit, speed, recovery, off - or '' to clear")
    p = sub.add_parser("rides"); p.add_argument("--days", type=int, default=7)
    sub.add_parser("fitness"); sub.add_parser("milestones"); sub.add_parser("workouts"); sub.add_parser("diagnostic")
    sub.add_parser("load")
    p = sub.add_parser("import"); p.add_argument("items", nargs="+")
    p = sub.add_parser("steps"); p.add_argument("days", nargs="*", help="YYYY-MM-DD=steps")
    p = sub.add_parser("capacity"); p.add_argument("system", choices=["engine", "impact", "muscle"]); p.add_argument("week")
    p.add_argument("--note")
    p = sub.add_parser("workout"); p.add_argument("action", choices=["add", "start"]); p.add_argument("arg")
    p = sub.add_parser("split"); p.add_argument("--total", type=float, default=30); p.add_argument("--intervals", type=int, default=3)
    p.add_argument("--interval-pct", type=int, default=80); p.add_argument("--rest-pct", type=int, default=50)
    p.add_argument("--name", default=None); p.add_argument("--plan", action="store_true"); p.add_argument("--ride", action="store_true")
    a = ap.parse_args(argv)
    j = a.json

    if a.cmd == "status":
        s = call("/status")
        b = ", ".join(f"{x['label']} {x['best']} W" for x in s.get("bests", []))
        show(s, j, f"bike {'connected' if s['bike'] else 'asleep'} · {s['power']} W · {s['cadence']} rpm · gear {s['gear']}"
                   f" · ERG {s['erg'] or 'off'}\nFTP {s['ftp']} W ({s['ftp_source']})\nbests: {b}\n"
                   f"this ride: {s['distance']} km, {s['kcal']} kcal" + (f"\nworkout: {s['workout']['name']}" if s.get("workout") else ""))
    elif a.cmd == "today":
        d = call("/api/coach/today" + (f"?date={a.date}" if a.date else ""))
        base = d.get("baseline")
        show(d, j, fmt_checkin(d["date"], d.get("checkin"), d.get("plan"))
             + (f"\n   normal: HR@90W {base['hr90']:.0f}" + (f", recovery {base['hrr']:.0f}" if base.get("hrr") is not None else "")
                + f" ({base['tests']} tests)" if base else "\n   normal: not enough tests yet (3 needed)")
             + f"\n   FTP {d['ftp']} W")
    elif a.cmd == "checkins":
        d = call(f"/api/coach/history?days={a.days}")
        dates = sorted(set(d["checkins"]) | set(d["plans"]))
        show(d, j, "\n".join(fmt_checkin(x, d["checkins"].get(x), d["plans"].get(x)) for x in dates) or "no check-ins yet")
    elif a.cmd == "checkin":
        body = {k: v for k, v in {"date": a.date, "feet": a.feet, "legs": a.legs, "shoulders": a.shoulders, "breathing": a.breathing, "sleep": a.sleep,
                                  "motivation": a.motivation, "hr90": a.hr90, "hr120": a.hr120, "hr_after": a.hr_after,
                                  "gut": a.gut, "note": a.note}.items() if v is not None}
        d = call("/api/coach/checkin", body)
        run = (d.get("systems") or {}).get("running")
        show(d, j, fmt_checkin(d["date"], d.get("checkin"), d.get("plan"))
             + (f"\n   running: {run['verdict'].upper()}" if run else ""))
    elif a.cmd == "plan":
        body = {k: v for k, v in {"date": a.date, "verdict": a.verdict, "note": a.note, "workout": a.workout,
                                  "focus": a.focus}.items() if v is not None}
        d = call("/api/coach/plan", body)
        f = d.get("focus")
        show(d, j, fmt_checkin(d["date"], d.get("checkin"), d.get("plan"))
             + (f"\n   focus: {f['name']} - {f['rpm'][0]}-{f['rpm'][1]} rpm" + (f", {f['watts'][0]}-{f['watts'][1]} W" if f.get("watts") else "") if f else ""))
    elif a.cmd == "rides":
        d = call("/api/fitness")
        since = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
        rows = [r for r in d["rides"] if r["date"] >= since]
        show(rows, j, "\n".join(f"{r['date']} {r['start']}  {r['minutes']:5.1f} min  avg {r['avg']:3d} W  NP {r['np']:3d} W"
                                f"  IF {r['if']:.2f}  load {r['tss']:5.1f}" for r in rows) or "no rides")
    elif a.cmd == "fitness":
        d = call("/api/fitness")
        t = d.get("today") or {}
        show(d, j, f"fitness {t.get('ctl')} · fatigue {t.get('atl')} · form {t.get('tsb')}\n{d['advice']}\n"
                   f"last 7 days: {d['week']['rides']} rides, {d['week']['hours']} h, load {d['week']['tss']}")
    elif a.cmd == "milestones":
        d = call("/api/milestones")
        s, t = d["streaks"], d["totals"]
        show(d, j, f"day streak {s['days']} (best {s['best_days']}) · weeks on goal {s['weeks']} · this week {s['this_week']}/{s['goal']}\n"
                   f"totals: {t['rides']} rides, {t['km']} km, {t['climb_m']} m up, {t['hours']} h, {t['kcal']} kcal\n"
                   "next: " + ", ".join(f"{b['name']} {round(b['progress'] * 100)}%" for b in d["next"]))
    elif a.cmd == "workouts":
        d = call("/api/workouts")
        show(d, j, "\n".join(f"{w['id']:28s} {w['stats']['minutes']:5.0f} min  load {w['stats']['tss']:3d}  {w['name']}"
                             for w in d["workouts"]))
    elif a.cmd == "workout":
        if a.action == "add":
            spec = json.load(open(a.arg))
            d = call("/api/workouts/save", spec)
            show(d, j, f"saved as {d['id']}")
        else:
            d = call(f"/api/workouts/start/{a.arg}", {})
            show(d, j, f"started {a.arg}")
    elif a.cmd == "split":
        T, n = a.total, a.intervals
        shares = [("warmup", "Warm-up", 15), ("ramp", "Ramp", 15)]
        for i in range(n):
            shares.append(("interval", f"Interval {i + 1}", 40 / n))
            if i < n - 1:
                shares.append(("rest", f"Rest {i + 1}", 20 / max(1, n - 1)))
        shares.append(("cooldown", "Cool-down", 10))
        tot = sum(x[2] for x in shares)
        parts = []
        for kind, label, sh in shares:
            p = {"kind": kind, "label": label, "minutes": T * sh / tot}
            if kind == "ramp":
                p.update({"from": 50, "to": min(a.interval_pct, 75)})
            else:
                p["pct"] = {"warmup": 50, "interval": a.interval_pct, "rest": a.rest_pct, "cooldown": 45}[kind]
            parts.append(p)
        d = call("/api/coach/split/save", {"name": a.name or f"{T:.0f} min · {n}x intervals at {a.interval_pct}%",
                                           "parts": parts, "plan": a.plan, "ride": a.ride})
        show(d, j, f"saved as {d['id']}" + (" · set as today's ride" if a.plan else "") + (" · started" if a.ride else ""))
    elif a.cmd == "load":
        d = call("/api/load")
        if not d.get("systems"):
            show(d, j, "no activities yet - import watch files with: hub import URL|FILE"); return
        names = {"engine": "Engine (heart, lungs)", "impact": "Impact (feet, bones)", "muscle": "Muscle (legs)"}
        lines = []
        for x, v in d["systems"].items():
            b = v["week_budget"]
            lines.append(f"{names[x]:22s} {'[tuned ' + str(v['usual_week']) + '/wk] ' if v.get('tuned') else ''}fitness {v['fitness']:5.1f} fatigue {v['fatigue']:5.1f} form {v['form']:6.1f}"
                         f"  ratio {v['acwr'] if v['acwr'] is not None else '-':>4}  {v['zone']:14s} week {v['week_used']:.0f}"
                         + (f" of {b[0]}-{b[1]}" if b else ""))
        r = d.get("readiness")
        if r:
            lines.append(f"bike: {r['verdict'].upper()}" + (f" - limited by {', '.join(r['limited_by'])}" if r["limited_by"] else ""))
            if r.get("running"):
                lines.append(f"running: {r['running']['verdict'].upper()}" + (f" - {'; '.join(r['running']['why'])}" if r["running"]["why"] else ""))
        ts = d["systems"].get("impact", {}).get("tissue")
        if ts:
            model = ts["remodeling"]
            lines.append(f"accumulated running load: {model['score']:.2f} provisional blocks"
                         f" (limit {model['threshold_blocks']:.1f}); plateau {model['plateau_remaining_days']:.1f} days left,"
                         f" then ~{model['descent_days']:.1f} days of faster decline"
                         f"; model-only crossing in {model['below_threshold_in_days']} days without another run")
            for t in ts["tissues"].values():
                lines.append(f"  exploratory {t['name']:22s} {t['days']:5.1f} modeled backlog days ({t['backlog_1000lb_steps']} steps at 1,000 lb; "
                             f"repairs {t['repairs_1000lb_steps_day']}/day)  {t['zone']}")
        lines.append("last 7 days by sport: " + ", ".join(f"{sp} {v['minutes']:.0f} min" for sp, v in d["sports_last7"].items()))
        show(d, j, "\n".join(lines))
    elif a.cmd == "steps":
        if a.days:
            try:
                body = {x.split("=")[0]: int(x.split("=")[1].replace(",", "")) for x in a.days}
            except (IndexError, ValueError):
                sys.exit("give days as YYYY-MM-DD=steps, e.g. 2026-09-27=4491")
            d = call("/api/steps", {"steps": body})
        else:
            d = call("/api/steps")
        show(d, j, "\n".join(f"{k}: {v:,}" for k, v in list(d["steps"].items())[-14:]) or "no step counts yet")
    elif a.cmd == "capacity":
        wk = None if a.week == "model" else float(a.week)
        d = call("/api/load/capacity", {"system": a.system, "usual_week": wk, "note": a.note})
        show(d, j, f"{a.system}: " + (f"tuned to a usual week of {wk:.0f}" if wk else "back to the model's estimate"))
    elif a.cmd == "import":
        import shutil
        urls = [x for x in a.items if x.startswith("https://")]
        files = [x for x in a.items if not x.startswith("https://")]
        out = {"imported": [], "skipped": []}
        if urls:
            out = call("/api/activities/import", {"urls": urls})
        dest = __import__("pathlib").Path(__file__).resolve().parent / "activities"
        dest.mkdir(exist_ok=True)
        for f in files:
            src = __import__("pathlib").Path(f)
            if src.suffix.lower() in (".fit", ".tcx") and src.exists():
                shutil.copy(src, dest / src.name); out["imported"].append(src.name)
            else:
                out["skipped"].append({"file": f, "why": "not a .fit/.tcx file"})
        show(out, j, f"imported {len(out['imported'])}, skipped {len(out['skipped'])}"
             + "".join(f"\n  skipped {x.get('url') or x.get('file')}: {x['why']}" for x in out["skipped"]))
    elif a.cmd == "diagnostic":
        d = call("/api/coach/test/start", {})
        show(d, j, "diagnostic started: 2 min 60 W, 2 min 90 W, 1 min 120 W, 1 min easy")


if __name__ == "__main__":
    main()
