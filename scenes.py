"""scenes.py - installable riding scenes (packs).

A pack lives in web/scenes/<id>/ with a manifest.json, its scene code, models and
road.json (see tools/build_halloween_road.py). Scenes are visual only: resistance always
comes from the route the rider planned or picked, or the ERG workout they chose. The scene
shows the ride's distance along its own looping road. Design: docs/design/halloween-ride.md.
"""
import json
from pathlib import Path

SCENES = Path(__file__).resolve().parent / "web" / "scenes"


def listing(folder=None):
    out = []
    for p in sorted(Path(folder or SCENES).glob("*/manifest.json")):
        try:
            out.append({"id": p.parent.name, **json.loads(p.read_text())})
        except (OSError, ValueError):
            pass
    return out
