"""places.py - find a town or a mountain by name, offline.

The names come out of the downloaded map itself: every zoom-12 tile's
"places" layer (cities, towns, villages, neighbourhoods) and its named peaks.
Each map piece is read once, in the background, and the result is cached next
to it as <piece>.places.json, so a new piece becomes searchable a minute or so
after it finishes downloading.

Search ignores accents and case ("beziers" finds Béziers). Results are ranked
by how well the name matches plus how big the place is (peaks by height), so
"ventoux" finds the mountain before the hamlets named after it.
"""
import gzip
import json
import math
import threading
import unicodedata
from pathlib import Path

import mvt

ZOOM = 12
KINDS = {"locality", "neighbourhood", "macrohood", "region", "country"}
POI_KINDS = {"peak", "volcano", "saddle", "mountain_pass"}
KIND_WEIGHT = {"country": 6, "region": 4, "locality": 3, "peak": 2, "volcano": 2, "saddle": 2,
               "mountain_pass": 2, "macrohood": 1, "neighbourhood": 0}

_lock = threading.Lock()
_index = {}                 # piece path -> list of places
_building = set()


def fold(s):
    """Lower case, no accents, hyphens as spaces: how names are compared."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().replace("-", " ").replace("'", " ")


def _tile_range(bounds, z):
    w, s, e, n = bounds
    k = 2 ** z
    def xy(lon, lat):
        lat = max(-85.0, min(85.0, lat))
        return (int((lon + 180) / 360 * k),
                int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * k))
    x0, y1 = xy(w, s)
    x1, y0 = xy(e, n)
    return range(max(0, x0), min(k - 1, x1) + 1), range(max(0, y0), min(k - 1, y1) + 1)


def _lonlat(z, x, y, px, py, extent):
    k = 2 ** z
    fx, fy = (x + px / extent) / k, (y + py / extent) / k
    return fx * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * fy))))


def build(part):
    """Every named place and peak in one map piece."""
    out, seen = [], set()
    xs, ys = _tile_range(part.bounds, ZOOM)
    for x in xs:
        for y in ys:
            raw = part.get(ZOOM, x, y)
            if not raw:
                continue
            try:
                layers = mvt.points(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw, {"places", "pois"})
            except (ValueError, IndexError, OSError):
                continue
            for layer, feats in layers.items():
                for props, (px, py, ext) in feats:
                    kind, name = props.get("kind"), props.get("name")
                    if not name or not isinstance(name, str):
                        continue
                    if (layer == "places" and kind not in KINDS) or (layer == "pois" and kind not in POI_KINDS):
                        continue
                    if not (0 <= px <= ext and 0 <= py <= ext):
                        continue                           # buffer copy of a neighbour's feature
                    lon, lat = _lonlat(ZOOM, x, y, px, py, ext)
                    key = (name, kind, round(lat, 2), round(lon, 2))
                    if key in seen:
                        continue
                    seen.add(key)
                    en = props.get("name:en")
                    out.append({"name": name, "en": en if isinstance(en, str) and en != name else None,
                                "kind": kind, "lat": round(lat, 5), "lon": round(lon, 5),
                                "pop": int(props.get("population") or 0),
                                "rank": int(props.get("population_rank") or 0),
                                "ele": int(props["elevation"]) if isinstance(props.get("elevation"), (int, float)) else None})
    return out


def _cache_path(part):
    return part.path.with_suffix(".places.json")


def _load_or_build(part):
    cp = _cache_path(part)
    try:
        if cp.exists() and cp.stat().st_mtime >= part.path.stat().st_mtime:
            data = json.loads(cp.read_text())
        else:
            data = build(part)
            tmp = cp.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False))
            tmp.replace(cp)
    except (OSError, ValueError):
        data = []
    for p in data:
        p["_f"] = fold(p["name"]) + ("|" + fold(p["en"]) if p.get("en") else "")
    with _lock:
        _index[str(part.path)] = data
        _building.discard(str(part.path))


def ensure(mapset):
    """Start indexing any map piece that isn't indexed yet. Returns how many are still being read."""
    todo = []
    with _lock:
        for part in mapset.parts:
            k = str(part.path)
            if k not in _index and k not in _building:
                _building.add(k)
                todo.append(part)
        pending = len(_building)
    for part in todo:
        threading.Thread(target=_load_or_build, args=(part,), daemon=True).start()
    return pending


def _all():
    with _lock:
        return [p for data in _index.values() for p in data]


def _public(p):
    return {k: v for k, v in p.items() if not k.startswith("_")}


def _importance(p):
    """How notable a place is, on the population-rank scale (0-12). Peaks count by height."""
    if p["kind"] in POI_KINDS or p["kind"] == "volcano":
        return (p["ele"] or 0) / 300               # Mont Ventoux (1910 m) ~ a town of 10-20k
    return p["rank"] + (1 if p["kind"] == "locality" else 0)


def _match(q, f):
    """How well the typed text matches a folded name: 6 exact, 4 starts a word, 1 anywhere."""
    best = 0
    for n in f.split("|"):
        if n == q:
            return 6
        if n.startswith(q) or (" " + q) in (" " + n):
            best = max(best, 4)
        elif q in n:
            best = max(best, 1)
    return best


_big = None


def _near(p):
    """'near Lyon' for small places, so two hamlets with the same name can be told apart."""
    global _big
    if _big is None or len(_big[0]) != len(_index):
        _big = (dict(_index), [b for b in _all() if b["kind"] == "locality" and b["rank"] >= 7])
    if p["kind"] == "locality" and p["rank"] >= 8:
        return None
    cl = math.cos(math.radians(p["lat"]))
    best = min(_big[1], key=lambda b: (b["lon"] - p["lon"]) ** 2 * cl * cl + (b["lat"] - p["lat"]) ** 2, default=None)
    if not best or best["name"] == p["name"]:
        return None
    km = math.hypot((best["lon"] - p["lon"]) * 111.2 * cl, (best["lat"] - p["lat"]) * 111.2)
    return f"{round(km)} km from {best['name']}" if km > 3 else f"in {best['name']}"


def search(q, limit=8):
    q = fold(q.strip())
    if len(q) < 2:
        return []
    scored = []
    for p in _all():
        m = _match(q, p["_f"])
        if m:
            scored.append((-(m + _importance(p)), p["name"], p))
    scored.sort(key=lambda t: t[:2])
    out, seen = [], set()
    for *_, p in scored:
        key = (p["name"], p["kind"], round(p["lat"], 1), round(p["lon"], 1))
        if key not in seen:
            seen.add(key)
            out.append({**_public(p), "near": _near(p)})
        if len(out) >= limit:
            break
    return out


def nearest(lat, lon, max_km=20):
    """The town nearest a point (preferring real towns over hamlets), or None.
    A named summit right there wins: the top of Ventoux is "Mont Ventoux"."""
    best, best_score = None, None
    cl = math.cos(math.radians(lat))
    peaks = [(math.hypot((p["lon"] - lon) * 111.2 * cl, (p["lat"] - lat) * 111.2), p)
             for p in _all() if p["kind"] in POI_KINDS and abs(p["lat"] - lat) < 0.02]
    peaks = [t for t in peaks if t[0] <= 1.5]
    if peaks:
        d, p = min(peaks, key=lambda t: t[0])
        return {**_public(p), "km": round(d, 1)}
    for p in _all():
        if p["kind"] not in ("locality", "neighbourhood", "macrohood"):
            continue
        dx, dy = (p["lon"] - lon) * 111.2 * cl, (p["lat"] - lat) * 111.2
        d = math.hypot(dx, dy)
        if d > max_km:
            continue
        score = d / (1 + 0.15 * p["rank"])          # a big town a bit further away beats a hamlet next door
        if best_score is None or score < best_score:
            best, best_score = p, score
    if not best:
        return None
    d = math.hypot((best["lon"] - lon) * 111.2 * cl, (best["lat"] - lat) * 111.2)
    return {**_public(best), "km": round(d, 1)}
