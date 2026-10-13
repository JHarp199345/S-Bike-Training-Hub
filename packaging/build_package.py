"""Build the one-package release: the hub app and its MCP server as `s-bike-training-hub` on PyPI.

  python packaging/build_package.py --version 1.11.0        # stages build/pypkg, then builds dist/*.whl and .tar.gz

Only an explicit list of the app's own files is copied in (Python modules, web pages, sample workouts, bike
profiles, regions.json, the licence): never anyone's data. A .packaged marker makes an installed copy keep its data
in the user's data folder (paths.py). The README carries the MCP Registry's ownership line.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
NEVER = {"coach.json", "profile.json", "music.json", "music_library.json", "remote.json", "state.json", "bests.json",
         "strava.json", "theme.json", "weather_cache.json", "fitness_cache.json", "course_forms.json"}
DIRS = {"web": {"scenes"}, "bike_profiles": set()}
SAMPLE_WORKOUTS = ["1-erg-check.json", "2-zone2-45.json", "3-zone2-60.json", "4-steady-blocks.json", "5-hard-5x3.json",
                   "downhill-spin-25-min.json"]   # only these: a builder's own workouts never ship
FILES = ["regions.json", "LICENSE"]
README = """# S-Bike Training Hub

A free, open-source, local training hub for cycling, running, swimming and lifting, with an MCP server so your AI
assistant can set you up, read your training and plan it with you. Your data stays on your computer.

**Install and connect your assistant in one line** (needs [uv](https://docs.astral.sh/uv/)):

    claude mcp add --scope user s-bike-hub -- uvx s-bike-training-hub@latest

Then ask your assistant: "Set me up with S-Bike Training Hub." It starts the hub app for you and walks you through
setup one question at a time. The app is at http://127.0.0.1:8729 once it's running.

- `s-bike-hub` starts the app yourself (smart-bike control: tested on a Merach S29; everything else works without a bike).
- `s-bike-hub-maps` downloads offline maps and route data (optional, large).
- Your data lives in your own data folder (macOS ~/Library/Application Support/S-Bike Hub), never in the package.

Source, guide and changelog: https://github.com/JHarp199345/S-Bike-Training-Hub

Optional games: https://jharp199345.itch.io/monster-chase
Community: https://www.strava.com/clubs/2379636
Optional support: https://ko-fi.com/jharp199345

Game packs are separate downloads, never bundled with the Hub.

Estimates are labelled as estimates; this is training support, not medical advice.

mcp-name: io.github.JHarp199345/s-bike-hub
"""


def dependencies():
    out = []
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.append(line)
    return out


def stage(version, out):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("version is like 1.11.0")
    if out.exists():
        shutil.rmtree(out)
    pkg = out / "s_bike_hub"
    pkg.mkdir(parents=True)
    for f in sorted(ROOT.glob("*.py")):
        shutil.copy2(f, pkg / f.name)
    for d, skip in DIRS.items():
        if (ROOT / d).is_dir():
            shutil.copytree(ROOT / d, pkg / d, ignore=lambda folder, names, skip=skip: [n for n in names if n in skip or n in NEVER or n.startswith(".") or n.endswith("-preview.html")])
    (pkg / "workouts").mkdir()
    for f in SAMPLE_WORKOUTS:
        shutil.copy2(ROOT / "workouts" / f, pkg / "workouts" / f)
    for f in FILES:
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, pkg / f if f != "LICENSE" else out / f)
    leaked = [p.name for p in pkg.rglob("*") if p.name in NEVER]
    if leaked:
        raise SystemExit(f"refusing to package personal files: {leaked}")
    shutil.copy2(HERE / "cli.py", pkg / "cli.py")
    (pkg / "__init__.py").write_text(f'"""S-Bike Training Hub, packaged."""\n__version__ = "{version}"\n')
    (pkg / ".packaged").write_text("This copy was installed from a package: data lives in the user's data folder (paths.py).\n")
    (out / "README.md").write_text(README)
    deps = ", ".join(f"'{d}'" for d in dependencies())   # TOML literal strings: markers contain double quotes
    (out / "pyproject.toml").write_text((HERE / "pyproject.template.toml").read_text().replace("@VERSION@", version).replace("@DEPENDENCIES@", deps))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--dist", default=str(ROOT / "dist"))
    ap.add_argument("--stage-only", action="store_true")
    a = ap.parse_args()
    out = stage(a.version, ROOT / "build" / "pypkg")
    if a.stage_only:
        print(out)
        return
    builder = shutil.which("uv")
    cmd = [builder, "build", "--out-dir", a.dist, str(out)] if builder else [sys.executable, "-m", "build", "--outdir", a.dist, str(out)]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
