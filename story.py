"""story.py - everything worth telling about one ride, for posts and infographics.

build(ride_csv) gathers what the bridge already saved - the ride file, its
events, the personal-best records, the fitness numbers, other rides - into
one dictionary:

  stats       time, distance, climbing, watts (avg/NP/max), cadence, kcal, load
  zones       seconds in each power zone
  highlights  the best things about this ride, most impressive first, each
              written the friendly-but-competitive way ("🏆 New 5-min best")
  compare     how it ranks against the last 30 days and all rides
  streak      days in a row, rides this week vs last
  fitness     fitness/fatigue/form after the ride, and the gain from it
  route, ghost, workout, ftp_test   when they happened
  title, caption, challenge          ready-to-post text

Everything stays on this Mac; posting is a separate, deliberate step.
"""
import csv
import json
import datetime as dt
import re
from pathlib import Path

import bests
import fitness
import live
import report
import rider

ZONES = [(0.55, "Z1", "Recovery", "#6b7280"), (0.75, "Z2", "Endurance", "#3b82f6"),
         (0.90, "Z3", "Tempo", "#22c55e"), (1.05, "Z4", "Threshold", "#eab308"),
         (1.20, "Z5", "VO2max", "#f97316"), (99, "Z6", "Anaerobic", "#ef4444")]


def _events(path):
    # Share the tolerant, recording-bounded event reader used by adherence.
    import adherence
    return [(t.isoformat(), e) for t, e in adherence._events(path)]


def _fmt_min(m):
    m = round(m)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


def zones(seconds, ftp):
    out = {z[1]: 0 for z in ZONES}
    for p in seconds:
        if p is None or p[1] <= 0:
            continue
        f = p[1] / ftp
        for top, key, *_ in ZONES:
            if f < top:
                out[key] += 1
                break
    return out


def _rides_before(rides_dir, stem, profile):
    """Loads of every ride, split into the ones before this one and this one."""
    allr = fitness.all_rides(rides_dir, profile, Path(rides_dir).resolve().parent / "fitness_cache.json")
    return [r for r in allr if r["ride"] < stem], next((r for r in allr if r["ride"] == stem), None), allr


def build(path):
    path = Path(path)
    rides_dir = path.parent
    profile = rider.load(rides_dir.resolve().parent / "profile.json")
    rows = report.load(path)
    events = _events(path)
    a = report.analyse(rows, events)
    if a is None:
        return None
    before, me, allr = _rides_before(rides_dir, path.stem, profile)
    if not me:
        return None
    ftp = me["ftp"]
    secs = bests.ride_seconds(path)
    kj = me["avg"] * me["minutes"] * 60 / 1000
    ev = [e for _, e in events]
    start = a["start"]

    # --- the ride's own numbers
    stats = {"date": f"{start:%A %B} {start.day}", "start": start.strftime("%H:%M"), "minutes": me["minutes"],
             "time": _fmt_min(me["minutes"]), "km": round(a["km"], 1), "climb_m": round(a["climb_m"]),
             "avg_kmh": round(a["avg_kmh"], 1), "avg_w": me["avg"], "np_w": me["np"], "max_w": round(a["max_w"]),
             "avg_cadence": round(a["avg_cad"]), "kcal": round(live.kcal_from_kj(kj)), "kj": round(kj),
             "load": round(me["tss"]), "if": me["if"], "ftp": ftp,
             "auto_shifts": a["auto_easier"] + a["auto_harder"], "hand_shifts": a["hand"]}
    zsecs = zones(secs, ftp)
    zone_list = [{"zone": k, "name": n, "color": c, "seconds": zsecs[k]} for _, k, n, c in ZONES]

    # --- what happened
    route = ghost = workout = ftp_test = None
    for e in ev:
        m = re.match(r"Route started: (\S+) at [\d.]+ m - (.+?), ([\d.]+) km, (\d+) m of climbing", e)
        if m:
            route = {"id": m.group(1), "name": m.group(2), "km": float(m.group(3)), "climb_m": int(m.group(4))}
        m = re.match(r"Ghost result: (\d+) s (ahead of|behind) (\S+)", e)
        if m:
            ghost = {"seconds": int(m.group(1)), "ahead": m.group(2) == "ahead of", "vs": m.group(3)}
        m = re.match(r"Workout started: (.+?) \(at FTP", e)
        if m:
            workout = m.group(1)
        m = re.match(r"FTP test done.*?FTP (\d+) W", e)
        if m:
            ftp_test = int(m.group(1))
    if route:
        try:
            import routes
            r = routes.load(route["id"])
            route["points"] = [[round(p[0], 5), round(p[1], 5)] for p in r.points[:: max(1, len(r.points) // 400)]]
            route["profile"] = r.profile(200.0)
        except (OSError, ValueError, ImportError):
            pass

    # --- records set on this ride
    recs = bests.load(bests.file_for(rides_dir))
    efforts = bests.best_efforts(secs)
    pbs = []
    for s, lab in bests.DURATIONS:
        rec = recs["records"].get(str(s))
        if rec and rec["ride"] == path.stem:
            prev = next((l["prev"] for l in reversed(recs["log"]) if l["secs"] == s and l["ride"] == path.stem), None)
            pbs.append({"secs": s, "label": lab, "watts": rec["watts"], "prev": prev})
    best_efforts = [{"secs": s, "label": lab, "watts": round(efforts[s][0]),
                     "record": (recs["records"].get(str(s)) or {}).get("watts")} for s, lab in bests.DURATIONS if s in efforts]

    # --- how it ranks
    month_ago = (start.date() - dt.timedelta(days=30)).isoformat()
    recent = [r for r in before if r["date"] >= month_ago]
    def rank(key, pool):
        return 1 + sum(1 for r in pool if r[key] > me[key])
    compare = {"rides_before": len(before), "month_rides": len(recent) + 1,
               "longest_ever": all(me["minutes"] > r["minutes"] for r in before) and bool(before),
               "hardest_ever": all(me["tss"] > r["tss"] for r in before) and bool(before),
               "load_rank_month": rank("tss", recent), "np_rank_month": rank("np", recent),
               "minutes_rank_month": rank("minutes", recent)}
    climbs = []
    for r in recent[-40:]:
        try:
            o = report.analyse(report.load(rides_dir / f"{r['ride']}.csv"), [])
            if o:
                climbs.append(o["climb_m"])
        except Exception:
            pass
    compare["most_climbing_month"] = a["climb_m"] >= 20 and all(a["climb_m"] > c for c in climbs)

    # --- streak and week
    days = sorted({r["date"] for r in allr if r["date"] <= start.date().isoformat() and r["minutes"] >= 10})
    streak, d = 0, start.date()
    while d.isoformat() in days:
        streak += 1
        d -= dt.timedelta(days=1)
    wk0 = start.date() - dt.timedelta(days=start.weekday())
    this_week = [r for r in allr if wk0.isoformat() <= r["date"] <= start.date().isoformat()]
    last_week = [r for r in allr if (wk0 - dt.timedelta(days=7)).isoformat() <= r["date"] < wk0.isoformat()]
    week = {"rides": len(this_week), "minutes": round(sum(r["minutes"] for r in this_week)),
            "load": round(sum(r["tss"] for r in this_week)), "last_week_load": round(sum(r["tss"] for r in last_week))}

    # --- fitness after this ride
    chart = fitness.chart(allr, today=start.date(), ahead=0)
    fit = None
    if chart:
        t, y = chart[-1], chart[-2] if len(chart) > 1 else {"ctl": 0}
        fit = {"fitness": round(t["ctl"], 1), "fatigue": round(t["atl"], 1), "form": round(t["tsb"], 1),
               "gain": round(t["ctl"] - y["ctl"], 1)}

    # --- highlights, most impressive first
    hl = []
    if ftp_test:
        hl.append((100, "🧪", f"FTP test: {ftp_test} W", "new training zones set"))
    if len(pbs) >= 3:                    # several records: one line, so the other highlights still fit
        top = max(pbs, key=lambda p: p["secs"])
        others = " · ".join(f"{p['label']} {p['watts']} W" for p in sorted(pbs, key=lambda p: -p["secs"])[1:])
        up = f"+{top['watts'] - top['prev']} W" if top["prev"] else "first on record"
        hl.append((91, "🏆", f"New {top['label']} best: {top['watts']} W", up))
        hl.append((90, "🏆", f"{len(pbs) - 1} more records", others))
    else:
        for pb in sorted(pbs, key=lambda p: -p["secs"]):
            up = f"+{pb['watts'] - pb['prev']} W" if pb["prev"] else "first on record"
            hl.append((90 + pb["secs"] / 1200, "🏆", f"New {pb['label']} best: {pb['watts']} W", up))
    if ghost:
        if ghost["ahead"]:
            hl.append((80, "👻", f"Beat my ghost by {ghost['seconds']} s", route["name"] if route else "same road as last time"))
        else:
            hl.append((30, "👻", f"Ghost won by {ghost['seconds']} s", "rematch coming"))
    if compare["hardest_ever"]:
        hl.append((75, "🔥", "Hardest ride yet", f"load {stats['load']}"))
    if compare["longest_ever"]:
        hl.append((74, "⏱", "Longest ride yet", stats["time"]))
    if compare["most_climbing_month"]:
        hl.append((70, "⛰", f"Most climbing this month: {stats['climb_m']} m", ""))
    if route:
        hl.append((60, "🗺", route["name"], f"{route['km']:.1f} km · {route['climb_m']} m up"))
    try:
        import adherence
        adh = adherence.for_ride(path)
    except Exception:
        adh = None
    if adh:
        hl.append((65 if adh["grade"] in "AB" else 40, "🎯", f"{adh['workout']}: grade {adh['grade']}",
                   f"{round(adh['score'] * 100)}% on target"))
    elif workout:
        hl.append((55, "🎯", workout, "workout done"))
    try:
        import focus
        foc = focus.for_ride(rows, events)
    except Exception:
        foc = None
    if foc and foc["minutes"] >= 5 and not adh:
        hl.append((58 if foc["both_pct"] >= 70 else 35, "🎚", f"{foc['focus']}: {foc['both_pct']}% in range",
                   f"cadence {foc['rpm_pct']}%" + (f" · watts {foc['watts_pct']}%" if foc["watts_pct"] is not None else "")))
    try:                                  # how hard the rider said it was
        import coach
        rpe = (coach.load(coach.file_for(rides_dir))["ratings"].get(path.stem) or {}).get("rpe")
    except Exception:
        rpe = None
    # the route's session (climb goals, efforts) and every climb ridden, against your previous times on it
    try:
        ses = json.loads(path.with_name(path.stem + "_session.json").read_text())
    except (OSError, ValueError):
        ses = None
    try:
        all_climbs = json.loads((rides_dir / "climbs.json").read_text())
    except (OSError, ValueError):
        all_climbs = []
    climbs_here = [c for c in all_climbs if c.get("ride") == path.stem]
    mmss = lambda x: f"{int(x) // 60}:{int(x) % 60:02d}"
    for r in (ses or {}).get("results", []):
        if r["type"] == "climb_time":
            hl.append((76 if r["made"] else 42, "⛰", f"{r['name']} in {mmss(r['took_s'])}",
                       f"goal {mmss(r['goal_s'])} {'✅' if r['made'] else '- ' + mmss(r['took_s'] - r['goal_s']) + ' over'} · {r['avg_w']} W"))
        elif r["type"] == "efforts":
            hl.append((70 if r["made"] == len(r["efforts"]) else 44, "🔥", f"{r['name']}: {r['made']} of {len(r['efforts'])}",
                       " · ".join(f"{e['avg_w']} W" for e in r["efforts"])))
    for c in climbs_here:
        before = [x for x in all_climbs if x.get("route_id") == c["route_id"] and x["n"] == c["n"]
                  and x.get("ride") != path.stem and x.get("ride", "") < path.stem]
        if before and c["seconds"] < min(x["seconds"] for x in before):
            hl.append((72, "⚡", f"Climb {c['n']}: fastest yet, {mmss(c['seconds'])}",
                       f"previous best {mmss(min(x['seconds'] for x in before))} · {c['avg_w']} W"))
    if streak >= 2:
        hl.append((50 + streak, "📅", f"{streak}-day streak", "keep it rolling"))
    if compare["month_rides"] >= 3 and compare["load_rank_month"] <= 3 and not compare["hardest_ever"]:
        place = {1: "Biggest", 2: "2nd-biggest", 3: "3rd-biggest"}[compare["load_rank_month"]]
        hl.append((45, "📈", f"{place} ride of the month", f"load {stats['load']}"))
    if fit and fit["gain"] > 0:
        hl.append((20, "💪", f"Fitness +{fit['gain']}", f"now {fit['fitness']}"))
    if stats["kcal"] >= 100:
        hl.append((15, "🍩", f"{stats['kcal']} kcal", f"≈ {stats['kcal'] // 250} donut{'s' if stats['kcal'] // 250 != 1 else ''}" if stats["kcal"] >= 250 else "burned"))
    try:                                  # lifetime milestones this ride earned
        import milestones
        ms = milestones.compute(rides_dir, profile.get("weekly_rides", 3), today=start.date())
        for e in milestones.new_on(path.stem, ms):
            if e["key"] != "rides:1":
                hl.append((85, e["icon"], f"Milestone: {e['name']}", "unlocked"))
        streaks = ms["streaks"]
        if streaks["weeks"] >= 2:
            hl.append((49, "🗓", f"{streaks['weeks']} weeks on goal", f"{streaks['goal']}+ rides a week"))
    except Exception:
        pass
    hl.sort(key=lambda h: -h[0])
    highlights = [{"icon": i, "text": t, "detail": d} for _, i, t, d in hl]

    # --- words
    if route:
        title = f"{route['name']} 🚴"
    elif workout:
        title = f"{workout} ✅"
    elif ftp_test:
        title = f"FTP test: {ftp_test} W 🧪"
    else:
        part = "Morning" if start.hour < 12 else "Afternoon" if start.hour < 17 else "Evening"
        title = f"{part} ride 🚴"
    if pbs:
        top = max(pbs, key=lambda p: p["secs"])
        challenge = f"New {top['label']} best at {top['watts']} W. Think you can hold that? 😏"
    elif ghost and ghost["ahead"]:
        challenge = f"Beat my own ghost by {ghost['seconds']} s. Want to race it?"
    elif route:
        challenge = f"Who's in for {route['name']} next time? 🙋"
    elif stats["climb_m"] >= 150:
        challenge = f"{stats['climb_m']} m of climbing. Who's joining the next hill day?"
    else:
        challenge = "Who's riding this week? Come along 🙌"
    lines = [f"{h['icon']} {h['text']}" + (f" ({h['detail']})" if h["detail"] else "") for h in highlights[:5]]
    caption = "\n".join(lines + ["", f"{stats['time']} · {stats['km']} km · {stats['climb_m']} m up · "
                                     f"{stats['avg_w']} W avg · {stats['kcal']} kcal", "", challenge,
                                 "", "Ridden on my own offline bike bridge 🛠"])

    forecast = None
    try:
        forecast = json.loads(path.with_suffix(".ftp-test.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"ride": path.stem, "ftp_forecast": forecast, "stats": stats, "zones": zone_list, "highlights": highlights, "pbs": pbs,
            "best_efforts": best_efforts, "compare": compare, "streak": streak, "week": week, "fitness": fit,
            "route": route, "ghost": ghost, "workout": workout, "ftp_test": ftp_test,
            "title": title, "caption": caption, "challenge": challenge, "adherence": adh, "focus": foc,
            "session": ses, "climbs": climbs_here, "rpe": rpe,
            "power": [round(p[1]) if p else None for p in secs][:: max(1, len(secs) // 600)],
            "elevation": _elevation(rows)}


def _elevation(rows):
    """Virtual elevation from grade x distance, for the profile strip."""
    out, ele, last = [], 0.0, None
    for r in rows:
        if last is not None and r["dist"] > last:
            ele += (r["dist"] - last) * r["grade"] / 100
        last = r["dist"]
        out.append((round(r["dist"]), round(ele, 1)))
    step = max(1, len(out) // 300)
    return out[::step]
