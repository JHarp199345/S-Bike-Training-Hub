"""rider.py - the rider's numbers that everything else scales from.

profile.json (kept out of git: it's personal) holds FTP and where it came
from, plus every past value, so a bad test can be seen and undone.
"""
import datetime as dt
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent / "profile.json"
DEFAULT = {"ftp": 150, "ftp_source": "a starting guess - take the FTP ramp test on the panel", "history": [],
           "weekly_rides": 3, "weight_kg": 80.0}


def load(path=None):
    """The profile; path defaults to the one beside this file. The bridge
    passes the one beside its rides folder, so a test bridge in a scratch
    folder can never change the real FTP."""
    path = Path(path) if path else PATH
    try:
        p = {**DEFAULT, **json.loads(path.read_text())}
    except (OSError, ValueError):
        p = {**DEFAULT, "history": []}
    p["_path"] = str(path)
    return p


def set_ftp(p, watts, source):
    p["history"].append({"ftp": p["ftp"], "source": p["ftp_source"], "until": dt.date.today().isoformat()})
    p["ftp"], p["ftp_source"] = int(watts), f"{source} ({dt.date.today().isoformat()})"
    Path(p.get("_path") or PATH).write_text(json.dumps({k: v for k, v in p.items() if k != "_path"}, indent=2))
    return p


def set_weight(p, kg, date=None):
    """Record a new body weight from `date` on. The earlier weight stays in weight_history, so energy for past
    sessions keeps using what the athlete weighed then."""
    kg = float(kg)
    if not 30 <= kg <= 300:
        raise ValueError("Body weight must be 30-300 kg")
    date = date or dt.date.today().isoformat()
    hist = p.setdefault("weight_history", [])
    if not hist and p.get("weight_kg"):
        hist.append({"from": "0001-01-01", "kg": float(p["weight_kg"])})     # everything before this change
    hist[:] = [h for h in hist if h["from"] != date] + [{"from": date, "kg": round(kg, 1)}]
    hist.sort(key=lambda h: h["from"])
    p["weight_kg"] = round(kg, 1)
    save(p)
    return p


def weight_on(weight_kg, history, date):
    """The body weight in effect on `date` (ISO), from the dated history; else the current weight."""
    past = [h for h in history or [] if h["from"] <= date]
    return past[-1]["kg"] if past else weight_kg


def workout_watts(workout, ftp):
    """Steps may give "pct" (of FTP) or fixed "watts"; return a copy in watts."""
    steps = []
    for s in workout["steps"]:
        w = s["watts"] if "watts" in s else round(s["pct"] / 100 * ftp / 5) * 5
        steps.append({**{k:v for k,v in s.items() if k!="pct"}, "watts": w})
    return {**workout, "steps": steps}


def save(p):
    Path(p.get("_path") or PATH).write_text(json.dumps({k: v for k, v in p.items() if k != "_path"}, indent=2))
