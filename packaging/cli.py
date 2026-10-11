"""s_bike_hub.cli - the commands a packaged install provides (packaging/build_package.py copies this in).

  s-bike-training-hub   the AI assistant's connection (MCP over stdio), named after the package so `uvx
                        s-bike-training-hub` works; it starts the hub app by itself when the app isn't running
  s-bike-hub            the hub app (the same options as running bridge.py from a checkout)
  s-bike-hub-maps       download maps and route data (setup_maps.py)

The app's modules sit in this package folder and import each other by their plain names, so the folder goes on
sys.path before they run. Your data lives in your own data folder (paths.py), never in the package.
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _run(script, argv=None):
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    sys.argv = [str(HERE / script)] + list(sys.argv[1:] if argv is None else argv)
    runpy.run_path(str(HERE / script), run_name="__main__")


def mcp():
    _run("mcp_server.py")


def hub():
    _run("bridge.py")


def maps():
    _run("setup_maps.py")
