"""One appearance setting shared by the Mac panel and paired phone pages."""
import json
from pathlib import Path

FILE = Path(__file__).resolve().parent / "theme.json"
OPTIONS = ("classic", "honeybee", "rattlesnake", "peacock", "harpy_eagle", "cherry_blossom")
ALIASES = {"diamondback": "rattlesnake"}      # an earlier name


def current():
    try:
        name = json.loads(FILE.read_text()).get("theme")
        name = ALIASES.get(name, name)
        return name if name in OPTIONS else "classic"
    except (OSError, ValueError, TypeError):
        return "classic"


def set_theme(name):
    name = ALIASES.get(name, name)
    if name not in OPTIONS:
        raise ValueError("Unknown theme")
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"theme": name}))
    tmp.replace(FILE)
    return name
