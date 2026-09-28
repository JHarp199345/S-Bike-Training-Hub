#!/usr/bin/env python3
"""report.py - what a ride on the S29 actually was.

    .venv/bin/python report.py                 # the latest ride
    .venv/bin/python report.py rides/ride_X.csv

Writes rides/<ride>_report.html next to the ride, adds a row to
rides/summary.csv (the trend across rides), and refreshes rides/gearing.json.

Two things in here are groundwork rather than finished features:

  Gearing (planned improvement 6): for each kind of hill, which resistance
  level the rider actually held 70-80 rpm at. Pooled across every ride in
  rides/gearing.json. The bridge doesn't use it yet; once there are a few
  rides' worth, it can set the flat level and hill steepness to the rider.

  Fatigue (planned improvement 7): cadence and power in the first, middle and
  last third of the ride. A steady fall is the drift the auto-shifter should
  eventually expect instead of only reacting to.
"""
import csv
import datetime as dt
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from live import kcal_from_kj
import bests

HERE = Path(__file__).resolve().parent
RIDES = HERE / "rides"
BAND = (70, 80)
BUCKETS = [(-99, -3, "descent (< -3%)"), (-3, -1, "slight descent"), (-1, 1, "flat"),
           (1, 3, "gentle climb (1-3%)"), (3, 5, "climb (3-5%)"), (5, 99, "steep (5%+)")]


def num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def load(path):
    """One row per second (the last reading in each second)."""
    by_sec = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            by_sec[row["time"]] = row
    rows = []
    for t in sorted(by_sec):
        r = by_sec[t]
        rows.append({
            "t": dt.datetime.fromisoformat(t),
            "power": num(r.get("power_w")), "cadence": num(r.get("cadence_rpm")),
            "level": int(num(r.get("resistance"))),
            "speed": num(r.get("virtual_speed_kmh"), num(r.get("bike_speed_kmh", r.get("speed_kmh")))),
            "dist": num(r.get("virtual_distance_m"), num(r.get("bike_distance_m", r.get("distance_m")))),
            "grade": num(r.get("grade_pct")), "gear": int(num(r.get("gear"))),
            "erg": num(r.get("erg_w"), 0.0) or None,
        })
    return rows


def normalized_power(powers):
    if len(powers) < 30:
        return statistics.fmean(powers) if powers else 0
    roll = [statistics.fmean(powers[i - 29:i + 1]) for i in range(29, len(powers))]
    return statistics.fmean(p ** 4 for p in roll) ** 0.25


def bucket(g):
    for lo, hi, name in BUCKETS:
        if lo <= g < hi:
            return name
    return "flat"


def analyse(rows, events):
    ride = [r for r in rows if r["cadence"] > 0]
    if len(ride) < 30:
        return None
    secs = len(ride)
    powers = [r["power"] for r in ride]
    cads = [r["cadence"] for r in ride]
    in_band = sum(BAND[0] <= c <= BAND[1] for c in cads) / secs
    climb = sum(max(0.0, r["grade"]) / 100 * r["speed"] / 3.6 for r in rows)
    dist = max((r["dist"] for r in rows), default=0) - min((r["dist"] for r in rows), default=0)
    thirds = [ride[i * secs // 3:(i + 1) * secs // 3] for i in range(3)]
    fatigue = [(statistics.fmean(r["cadence"] for r in th), statistics.fmean(r["power"] for r in th)) for th in thirds]
    gearing = defaultdict(lambda: {"secs": 0, "cad": [], "held": Counter()})
    for r in ride:
        g = gearing[bucket(r["grade"])]
        g["secs"] += 1
        g["cad"].append(r["cadence"])
        if BAND[0] <= r["cadence"] <= BAND[1]:
            g["held"][r["level"]] += 1
    erg = [r for r in ride if r["erg"]]
    erg_err = statistics.fmean(abs(r["power"] - r["erg"]) / r["erg"] for r in erg) if erg else None
    ev = [e for _, e in events]
    return {
        "start": rows[0]["t"], "minutes": secs / 60, "avg_w": statistics.fmean(powers), "np_w": normalized_power(powers),
        "max_w": max(powers), "avg_cad": statistics.fmean(cads), "in_band": in_band,
        "km": dist / 1000, "avg_kmh": statistics.fmean(r["speed"] for r in ride), "climb_m": climb,
        "levels": Counter(r["level"] for r in ride), "fatigue": fatigue, "gearing": gearing,
        "erg_secs": len(erg), "erg_err": erg_err,
        # Event wording from bridge.py: "Auto: cadence 62 rpm, under 70 -> gear -1 -> ...",
        # "Auto: cadence unsteady (...)", "Auto: heart rate ...", "Gear -> gear +1 -> ...".
        "auto_easier": sum(e.startswith("Auto:") and any(k in e for k in ("under", "unsteady", "heart rate")) for e in ev),
        "auto_harder": sum(e.startswith("Auto:") and "over" in e for e in ev),
        "hand": sum(e.startswith("Gear -> gear") for e in ev),
        "hill_shifts": sum("for the hill" in e for e in ev),
        "drops": sum(e.startswith("Watch power disconnected") for e in ev),
        "series": [(r["t"], r["power"], r["cadence"]) for r in rows],
    }


def svg_chart(series, w=720, h=180):
    if len(series) < 2:
        return ""
    t0 = series[0][0]
    xs = [(t - t0).total_seconds() for t, _, _ in series]
    span = max(xs) or 1
    def line(vals, top, color):
        pts = " ".join(f"{x / span * w:.1f},{h - v / top * (h - 10):.1f}" for x, v in zip(xs, vals))
        return f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{pts}"/>'
    pmax = max(max(p for _, p, _ in series), 50)
    band = (f'<rect x="0" y="{h - 80 / 120 * (h - 10):.1f}" width="{w}" height="{10 / 120 * (h - 10):.1f}" '
            f'fill="#22c55e" opacity="0.12"/>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Power and cadence over the ride">'
            f'{band}{line([p for _, p, _ in series], pmax * 1.1, "#a855f7")}'
            f'{line([c for _, _, c in series], 120, "#38bdf8")}</svg>'
            f'<div class="legend"><span style="color:#a855f7">■ watts (0–{pmax * 1.1:.0f})</span> '
            f'<span style="color:#38bdf8">■ cadence (0–120 rpm)</span> '
            f'<span style="color:#22c55e">■ 70–80 rpm band</span></div>')


def update_gearing(all_rides):
    """Pool 'level held in band' per hill type across every ride."""
    pool = defaultdict(Counter)
    for a in all_rides:
        for name, g in a["gearing"].items():
            pool[name].update(g["held"])
    out = {}
    for lo, hi, name in BUCKETS:
        c = pool.get(name)
        if c and sum(c.values()) >= 60:
            out[name] = {"best_level": c.most_common(1)[0][0], "seconds_in_band": sum(c.values()),
                         "by_level": dict(sorted(c.items()))}
    (RIDES / "gearing.json").write_text(json.dumps(out, indent=2))
    return out


def efforts_table(a):
    """This ride's best efforts beside the all-time records; a trophy where this ride set it."""
    rows = []
    for secs, lab in bests.DURATIONS:
        mine = a.get("efforts", {}).get(secs)
        rec = a.get("records", {}).get(str(secs))
        if not mine:
            continue
        pb = rec and rec["ride"] == a.get("ride_name")
        rows.append(f"<tr><td>{lab}</td><td><b>{mine[0]:.0f} W</b>{' 🏆 new personal best' if pb else ''}</td>"
                    f"<td>{rec['watts'] if rec else '–'} W</td></tr>")
    if not rows:
        return ""
    return ("<h2>Best efforts</h2><table><tr><th>Held for</th><th>This ride</th><th>Personal best</th></tr>"
            + "".join(rows) + "</table>")


def html(name, a, learned):
    f = a["fatigue"]
    drift = (f[2][0] - f[0][0]) / f[0][0] * 100 if f[0][0] else 0
    lv = "".join(f"<tr><td>{l}</td><td>{s // 60}:{s % 60:02d}</td></tr>" for l, s in sorted(a["levels"].items()))
    gear_rows = ""
    for lo, hi, nm in BUCKETS:
        g = a["gearing"].get(nm)
        if not g or g["secs"] < 20:
            continue
        best = g["held"].most_common(1)[0][0] if g["held"] else "–"
        pooled = learned.get(nm, {}).get("best_level", "not enough yet")
        gear_rows += (f"<tr><td>{nm}</td><td>{g['secs'] // 60}:{g['secs'] % 60:02d}</td>"
                      f"<td>{statistics.fmean(g['cad']):.0f}</td><td>{best}</td><td>{pooled}</td></tr>")
    erg = (f"<p>ERG: {a['erg_secs'] // 60} min held, off target by {a['erg_err'] * 100:.0f}% on average.</p>"
           if a["erg_err"] is not None else "")
    return f"""<!doctype html><meta charset="utf-8"><title>Ride {name}</title>
<style>body{{background:#0b0f14;color:#eef1f5;font:15px/1.5 -apple-system,sans-serif;max-width:760px;margin:0 auto;padding:24px 16px}}
h1{{margin:0}}.sub{{color:#8b98a8}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}}
.k{{background:#151b23;border-radius:12px;padding:12px}}.k b{{display:block;font-size:26px}}.k span{{color:#8b98a8;font-size:13px}}
table{{border-collapse:collapse;width:100%;margin:8px 0 18px}}td,th{{border-bottom:1px solid #1f2733;padding:6px;text-align:left}}
th{{color:#8b98a8;font-weight:600}}.legend{{font-size:13px;color:#8b98a8;margin:4px 0 18px}}</style>
<h1>Ride report</h1><div class="sub">{a['start']:%A %B %-d, %Y · %H:%M} · {name}</div>
<div class="grid">
<div class="k"><b>{a['minutes']:.0f} min</b><span>pedalling</span></div>
<div class="k"><b>{a['avg_w']:.0f} W</b><span>average · {a['np_w']:.0f} W normalized</span></div>
<div class="k"><b>{a['avg_cad']:.0f} rpm</b><span>average cadence</span></div>
<div class="k"><b>{a['in_band'] * 100:.0f}%</b><span>of the time at 70–80 rpm</span></div>
<div class="k"><b>{a['km']:.1f} km</b><span>virtual · {a['avg_kmh']:.1f} km/h avg</span></div>
<div class="k"><b>{a['climb_m']:.0f} m</b><span>virtual climbing</span></div>
<div class="k"><b>{kcal_from_kj(a['avg_w'] * a['minutes'] * 60 / 1000):.0f} kcal</b><span>{a['avg_w'] * a['minutes'] * 60 / 1000:.0f} kJ of work at the pedals</span></div>
</div>
{efforts_table(a)}
{__import__("adherence").report_html(a["adherence"]) if a.get("adherence") else ""}
{svg_chart(a['series'])}
<h2>Shifting</h2><p>Auto-shift: {a['auto_easier']} easier, {a['auto_harder']} harder · by hand: {a['hand']} ·
hill shifts at the bottom of climbs: {a['hill_shifts']} · watch drops: {a['drops']}</p>{erg}
<h2>Fatigue</h2><p>Cadence by third of the ride: {f[0][0]:.0f} → {f[1][0]:.0f} → {f[2][0]:.0f} rpm ({drift:+.0f}%) ·
power {f[0][1]:.0f} → {f[1][1]:.0f} → {f[2][1]:.0f} W.</p>
<h2>Gearing</h2><p class="sub">The level you held 70–80 rpm at most, on each kind of road. "All rides" pools every ride
so far; the bridge will use it to fit the gears to you once there's enough.</p>
<table><tr><th>Road</th><th>Time</th><th>Avg rpm</th><th>This ride</th><th>All rides</th></tr>{gear_rows}</table>
<h2>Time at each resistance level</h2><table><tr><th>Level</th><th>Time</th></tr>{lv}</table>"""


def build(path):
    path = Path(path)
    rows = load(path)
    ev_path = path.with_name(path.stem + "_events.csv")
    events = [(r["time"], r["event"]) for r in csv.DictReader(open(ev_path))] if ev_path.exists() else []
    a = analyse(rows, events)
    if a is None:
        return None
    a["efforts"] = bests.best_efforts(bests.ride_seconds(path))
    a["records"] = bests.load(bests.file_for(path.parent))["records"]
    a["ride_name"] = path.stem
    try:
        import adherence
        a["adherence"] = adherence.for_ride(path)
    except Exception:
        a["adherence"] = None
    others = []
    for p in sorted(RIDES.glob("ride_*.csv")):
        if p.name.endswith(("_events.csv", "_report.csv")):
            continue
        try:
            o = analyse(load(p), [])
            if o:
                others.append(o)
        except Exception:
            pass
    learned = update_gearing(others)
    out = path.with_name(path.stem + "_report.html")
    out.write_text(html(path.stem, a, learned))
    summary = RIDES / "summary.csv"
    new = not summary.exists()
    done = set()
    if not new:
        done = {r["ride"] for r in csv.DictReader(open(summary))}
    if path.stem not in done:
        with open(summary, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["ride", "date", "minutes", "avg_w", "np_w", "avg_cadence", "pct_70_80", "virtual_km",
                            "climb_m", "cadence_drift_pct"])
            fa = a["fatigue"]
            w.writerow([path.stem, f"{a['start']:%Y-%m-%d %H:%M}", round(a["minutes"], 1), round(a["avg_w"]),
                        round(a["np_w"]), round(a["avg_cad"]), round(a["in_band"] * 100), round(a["km"], 2),
                        round(a["climb_m"]), round((fa[2][0] - fa[0][0]) / fa[0][0] * 100 if fa[0][0] else 0)])
    return out


def latest():
    rides = [p for p in sorted(RIDES.glob("ride_*.csv"), key=lambda p: p.stat().st_mtime)
             if not p.name.endswith("_events.csv")]
    return rides[-1] if rides else None


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else latest()
    out = build(target) if target else None
    print(out if out else "Not enough riding in that file for a report (needs 30 s of pedalling).")
