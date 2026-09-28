"""posts.py - a ride's post: the infographic, the caption, and a pack for Claude.

make(ride_csv) writes rides/<ride>_post/:
  card.png        the 1080x1350 infographic (card.py)
  story.json      every number behind it (story.py)
  caption.txt     title + caption, ready for Strava
  for_claude.md   a ready-made prompt with the ride's story, to paste into
                  Claude (or hand to Claude Code) for a custom infographic

The bridge makes the post when a ride ends; the /post pages make one on
demand for any ride.
"""
import io
import json
import zipfile
from pathlib import Path

import card
import story

MIN_MINUTES = 5


def folder(ride_csv):
    p = Path(ride_csv)
    return p.with_name(p.stem + "_post")


def make(ride_csv):
    """Build (or rebuild) the post. Returns the story, or None for a ride too short to post."""
    s = story.build(ride_csv)
    if not s or s["stats"]["minutes"] < MIN_MINUTES:
        return None
    out = folder(ride_csv)
    out.mkdir(exist_ok=True)
    card.render(s, out / "card.png")
    (out / "story.json").write_text(json.dumps(s, indent=1, ensure_ascii=False))
    (out / "caption.txt").write_text(s["title"] + "\n\n" + s["caption"] + "\n")
    (out / "for_claude.md").write_text(claude_prompt(s))
    return s


def load(ride_csv):
    try:
        return json.loads((folder(ride_csv) / "story.json").read_text())
    except (OSError, ValueError):
        return None


def claude_prompt(s):
    st = s["stats"]
    lines = [
        "# Make a ride post infographic",
        "",
        "Make a **friendly but competitive** infographic for my Strava post about this indoor ride. "
        "Portrait, 1080×1350. Celebrate what went well (records first), keep it playful, and end with a line "
        "that invites friends to ride or to try to beat a number. Keep every number exactly as given - don't "
        "round differently or invent stats. Build it as a single self-contained HTML/SVG page I can screenshot, "
        "and also suggest a short Strava title and caption.",
        "",
        f"## {s['title']}",
        f"{st['date']}, {st['start']} · ridden on a Merach S29 through my own bike bridge (virtual speed and hills).",
        "",
        "## Highlights (most impressive first)",
    ]
    lines += [f"- {h['icon']} {h['text']}" + (f" - {h['detail']}" if h["detail"] else "") for h in s["highlights"]] or ["- (none)"]
    lines += ["", "## Numbers",
              f"- Time {st['time']} · virtual distance {st['km']} km · climbing {st['climb_m']} m · avg speed {st['avg_kmh']} km/h",
              f"- Power: avg {st['avg_w']} W, normalized {st['np_w']} W, max {st['max_w']} W · FTP {st['ftp']} W · intensity {st['if']}",
              f"- Cadence avg {st['avg_cadence']} rpm · {st['kcal']} kcal ({st['kj']} kJ of work) · training load {st['load']}",
              f"- Auto-shifts {st['auto_shifts']}, by hand {st['hand_shifts']}",
              "", "## Best efforts this ride (vs personal best)"]
    lines += [f"- {e['label']}: {e['watts']} W (personal best {e['record']} W)" for e in s["best_efforts"]]
    tot = sum(z["seconds"] for z in s["zones"]) or 1
    lines += ["", "## Time in power zones"]
    lines += [f"- {z['zone']} {z['name']}: {round(100 * z['seconds'] / tot)}% ({z['seconds'] // 60} min) - colour {z['color']}"
              for z in s["zones"] if z["seconds"]]
    if s.get("route"):
        lines += ["", f"## Route: {s['route']['name']} ({s['route']['km']} km, {s['route']['climb_m']} m up)"]
    if s.get("ghost"):
        g = s["ghost"]
        lines += [f"- Ghost race: {g['seconds']} s {'ahead of' if g['ahead'] else 'behind'} my last ride here"]
    if s.get("workout"):
        lines += [f"- Workout: {s['workout']}"]
    lines += ["", "## Context",
              f"- Streak: {s['streak']} day(s) in a row · this week {s['week']['rides']} rides, "
              f"{s['week']['minutes']} min, load {s['week']['load']} (last week {s['week']['last_week_load']})"]
    if s.get("fitness"):
        f = s["fitness"]
        lines += [f"- Fitness {f['fitness']} (+{f['gain']} from this ride) · fatigue {f['fatigue']} · form {f['form']}"]
    lines += ["", "## Challenge line to use or improve", f"> {s['challenge']}",
              "", "## Data for charts (JSON)",
              "Power is one value per few seconds in watts (null = stopped); elevation is [metres along, metres up].",
              "```json",
              json.dumps({"power_w": s["power"], "elevation": s["elevation"],
                          "zones": s["zones"], "route_points_lat_lon": (s.get("route") or {}).get("points")},
                         separators=(",", ":")),
              "```", ""]
    return "\n".join(lines)


def zip_bytes(ride_csv):
    out = folder(ride_csv)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ("card.png", "story.json", "caption.txt", "for_claude.md"):
            if (out / f).exists():
                z.write(out / f, f"{Path(ride_csv).stem}/{f}")
    return buf.getvalue()
