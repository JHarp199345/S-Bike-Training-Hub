"""Locate downloaded map assets consistently for both rendering and route planning."""
import os
from pathlib import Path


def locate(root=None):
    root = Path(root or Path(__file__).resolve().parent)
    if os.environ.get('S_BIKE_MAPS'):
        return Path(os.environ['S_BIKE_MAPS']).expanduser().resolve()
    local = root / 'maps'
    if local.exists():
        return local
    # Earlier installations kept large map downloads beside the application.
    shared = root.parent / 'bikebridge-maps'
    return shared if (shared / 'web' / 'maplibre').is_dir() else local
