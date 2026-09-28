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


def workout_watts(workout, ftp):
    """Steps may give "pct" (of FTP) or fixed "watts"; return a copy in watts."""
    steps = []
    for s in workout["steps"]:
        w = s["watts"] if "watts" in s else round(s["pct"] / 100 * ftp / 5) * 5
        steps.append({"minutes": s["minutes"], "watts": w})
    return {**workout, "steps": steps}


def save(p):
    Path(p.get("_path") or PATH).write_text(json.dumps({k: v for k, v in p.items() if k != "_path"}, indent=2))
