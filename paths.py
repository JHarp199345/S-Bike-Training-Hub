"""paths.py - where the hub keeps your data (2026-10-11).

  CODE   the app's own files: Python modules, web pages, sample workouts, bike profiles.
  DATA   your training: coach.json, profile.json, rides/, activities/, routes/, settings and caches.

How DATA is chosen, first match wins:
  1. S_BIKE_HUB_DATA, when set: an explicit folder (for moving your own data deliberately).
  2. The code folder, when it already holds data: every existing GitHub install keeps working from its own folder,
     untouched. Nobody's data is moved.
  3. A per-user data folder, for packaged installs (the package ships a .packaged marker): updating the app then
     never touches your training. macOS ~/Library/Application Support/S-Bike Hub; Windows %APPDATA%/S-Bike Hub;
     Linux $XDG_DATA_HOME/s-bike-hub (default ~/.local/share/s-bike-hub).
  4. Otherwise the code folder (a fresh GitHub checkout behaves exactly as before).
"""
import os
import shutil
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
MARKERS = ("rides", "coach.json", "profile.json")      # signs that a folder already holds someone's training


def user_folder():
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "S-Bike Hub"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "S-Bike Hub"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "s-bike-hub"


def resolve(code=CODE, env=None):
    env = os.environ if env is None else env
    if env.get("S_BIKE_HUB_DATA"):
        return Path(env["S_BIKE_HUB_DATA"]).expanduser().resolve()
    if any((code / m).exists() for m in MARKERS):
        return code
    if (code / ".packaged").exists():
        return user_folder()
    return code


DATA = resolve()


def packaged(code=CODE):
    return (code / ".packaged").exists()


def seed(data=None, code=CODE):
    """Make the data folder ready: create it, and give a new one the sample workouts to start from."""
    data = Path(data or DATA)
    data.mkdir(parents=True, exist_ok=True)
    if data != code and not (data / "workouts").exists() and (code / "workouts").is_dir():
        shutil.copytree(code / "workouts", data / "workouts")
    return data
