"""musiclibrary.py - the athlete's music folder as a library: songs, albums, artists, cover art and tempo.

Reads the tags already inside the files (ID3 for mp3, MP4 atoms for m4a/aac, Vorbis comments for flac) with no extra
packages, falls back to the file name ("01. Artist - Title.mp3") and a cover.jpg beside the files, and measures each
song's tempo once (macOS afconvert decodes; numpy finds the beat). Everything it learns stays on this computer, in
music_library.json and music_cache/ next to the app (both ignored by Git). The folder itself is the athlete's choice.

Cadence matching: one beat per pedal stroke is twice the cadence (174 BPM fits 87 rpm), and a half-time song fits at
its own tempo (87 BPM fits 87 rpm), so a song's cadence is whichever of BPM or BPM/2 is nearer the band.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "music_library.json"
CACHE = HERE / "music_cache"
EXTS = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".aif", ".aiff", ".ogg", ".opus"}
MIME = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".flac": "audio/flac", ".wav": "audio/wav",
        ".aif": "audio/aiff", ".aiff": "audio/aiff", ".ogg": "audio/ogg", ".opus": "audio/ogg"}
COVERS = ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg", "front.png", "album.jpg")
VERSION = 1                                         # bump to re-read tags for every file

_lock = threading.RLock()
_scan = {"state": "idle", "done": 0, "total": 0, "tempo_done": 0, "tempo_total": 0}
_thread = None


# ── the chosen folder ────────────────────────────────────────────────────────
def _load():
    try:
        d = json.loads(INDEX.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    tmp = INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    tmp.replace(INDEX)


def folder():
    """The folder the athlete chose (HUB_MUSIC_FOLDER overrides, for tests), or None before they choose one."""
    f = os.environ.get("HUB_MUSIC_FOLDER") or _load().get("folder")
    if not f:
        return None
    f = Path(f).expanduser()
    if os.environ.get("HUB_MUSIC_FOLDER"):
        f.mkdir(parents=True, exist_ok=True)
    return f if f.is_dir() else None


def need_folder():
    f = folder()
    if not f:
        raise ValueError("Choose your music folder first (Music settings, Choose folder).")
    return f


def set_folder(path):
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise ValueError("That folder doesn't exist.")
    if p == Path.home() or p == Path("/") or len(p.parts) < 3:
        raise ValueError("Choose a music folder, not your whole home or disk.")
    with _lock:
        d = _load()
        if d.get("folder") != str(p):
            d.update(folder=str(p), tracks={})            # a new folder starts a fresh index
            _save(d)
    scan()
    return str(p)


def choose_folder():
    """The Mac's own folder picker (on this computer only). Returns the chosen path, or None if cancelled."""
    if sys.platform != "darwin":
        raise ValueError("Choosing a folder here works on a Mac. Elsewhere, set HUB_MUSIC_FOLDER.")
    script = ('set f to choose folder with prompt "Choose the folder with your music" default location '
              f'(POSIX file "{str(folder() or Path.home() / "Music").replace(chr(34), "")}")\nPOSIX path of f')
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return None                                   # cancelled
    return set_folder(r.stdout.strip())


# ── tags ─────────────────────────────────────────────────────────────────────
def _text(enc, b):
    try:
        if enc == 0:
            s = b.decode("latin-1")
        elif enc == 1:
            s = b.decode("utf-16")
        elif enc == 2:
            s = b.decode("utf-16-be")
        else:
            s = b.decode("utf-8")
    except UnicodeDecodeError:
        s = b.decode("latin-1", "replace")
    return s.strip("\x00").split("\x00")[0].strip()


def _syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _id3(f):
    head = f.read(10)
    if len(head) < 10 or head[:3] != b"ID3":
        return {}
    major, flags, size = head[3], head[5], _syncsafe(head[6:10])
    data = f.read(size)
    if flags & 0x80 and major < 4:
        data = data.replace(b"\xff\x00", b"\xff")
    i = 0
    if flags & 0x40 and major >= 3:                    # extended header
        i = (_syncsafe(data[:4]) if major == 4 else struct.unpack(">I", data[:4])[0] + 4)
    names = {"TIT2": "title", "TT2": "title", "TPE1": "artist", "TP1": "artist", "TALB": "album", "TAL": "album",
             "TPE2": "album_artist", "TP2": "album_artist", "TRCK": "track", "TRK": "track", "TBPM": "bpm", "TBP": "bpm"}
    out = {}
    while i < len(data) - 10:
        if major == 2:
            fid, fsize, hdr = data[i:i + 3].decode("latin-1"), int.from_bytes(data[i + 3:i + 6], "big"), 6
        else:
            fid = data[i:i + 4].decode("latin-1")
            fsize = _syncsafe(data[i + 4:i + 8]) if major == 4 else struct.unpack(">I", data[i + 4:i + 8])[0]
            hdr = 10
        if not fid.strip("\x00") or fsize <= 0 or not re.fullmatch(r"[A-Z0-9]{3,4}", fid):
            break
        body = data[i + hdr:i + hdr + fsize]
        i += hdr + fsize
        if fid in names and body:
            out.setdefault(names[fid], _text(body[0], body[1:]))
        elif fid in ("APIC", "PIC") and body and "art" not in out:
            enc = body[0]
            if fid == "PIC":
                j = 5
            else:
                j = body.index(b"\x00", 1) + 2          # mime, then the picture type byte
            term = b"\x00\x00" if enc in (1, 2) else b"\x00"
            k = body.find(term, j)
            while enc in (1, 2) and k != -1 and (k - j) % 2:
                k = body.find(term, k + 1)
            if k != -1:
                out["art"] = body[k + len(term):]
    return out


def _atoms(f, start, end):
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        h = f.read(8)
        if len(h) < 8:
            return
        size, kind = struct.unpack(">I", h[:4])[0], h[4:8]
        hdr = 8
        if size == 1:
            size, hdr = struct.unpack(">Q", f.read(8))[0], 16
        elif size == 0:
            size = end - pos
        if size < hdr:
            return
        yield kind, pos + hdr, pos + size
        pos += size


def _mp4(f):
    f.seek(0, 2)
    total = f.tell()
    out = {}
    names = {b"\xa9nam": "title", b"\xa9ART": "artist", b"\xa9alb": "album", b"aART": "album_artist"}
    for kind, s, e in _atoms(f, 0, total):
        if kind != b"moov":
            continue
        for k2, s2, e2 in _atoms(f, s, e):
            if k2 != b"udta":
                continue
            for k3, s3, e3 in _atoms(f, s2, e2):
                if k3 != b"meta":
                    continue
                for k4, s4, e4 in _atoms(f, s3 + 4, e3):          # meta has 4 bytes of version/flags
                    if k4 != b"ilst":
                        continue
                    for item, s5, e5 in _atoms(f, s4, e4):
                        for k6, s6, e6 in _atoms(f, s5, e5):
                            if k6 != b"data" or e6 - s6 > 20_000_000:
                                continue
                            f.seek(s6 + 8)
                            v = f.read(e6 - s6 - 8)
                            if item in names:
                                out.setdefault(names[item], v.decode("utf-8", "replace").strip())
                            elif item == b"trkn" and len(v) >= 4:
                                out.setdefault("track", str(struct.unpack(">H", v[2:4])[0]))
                            elif item == b"tmpo" and len(v) >= 2:
                                out.setdefault("bpm", str(struct.unpack(">H", v[:2])[0]))
                            elif item == b"covr":
                                out.setdefault("art", v)
    return out


def _flac(f):
    if f.read(4) != b"fLaC":
        return {}
    out, last = {}, False
    while not last:
        h = f.read(4)
        if len(h) < 4:
            break
        last, kind, size = bool(h[0] & 0x80), h[0] & 0x7F, int.from_bytes(h[1:4], "big")
        block = f.read(size)
        if kind == 4:
            n = struct.unpack("<I", block[:4])[0]
            i, count = 4 + n, struct.unpack("<I", block[4 + n:8 + n])[0]
            i += 4
            for _ in range(count):
                ln = struct.unpack("<I", block[i:i + 4])[0]
                k, _, v = block[i + 4:i + 4 + ln].decode("utf-8", "replace").partition("=")
                i += 4 + ln
                key = {"TITLE": "title", "ARTIST": "artist", "ALBUM": "album", "ALBUMARTIST": "album_artist",
                       "TRACKNUMBER": "track", "BPM": "bpm"}.get(k.upper())
                if key:
                    out.setdefault(key, v.strip())
        elif kind == 6 and "art" not in out:
            i = 4
            ml = struct.unpack(">I", block[i:i + 4])[0]; i += 4 + ml
            dl = struct.unpack(">I", block[i:i + 4])[0]; i += 4 + dl + 16
            ln = struct.unpack(">I", block[i:i + 4])[0]
            out["art"] = block[i + 4:i + 4 + ln]
    return out


def read_tags(path):
    """Tags from the file itself, or {} when it has none we can read."""
    ext = path.suffix.lower()
    try:
        with open(path, "rb") as f:
            if ext == ".mp3":
                return _id3(f)
            if ext in (".m4a", ".aac"):
                return _mp4(f) if f.read(8)[4:8] == b"ftyp" else (f.seek(0) or _id3(f))
            if ext == ".flac":
                return _flac(f)
    except (OSError, ValueError, struct.error, IndexError):
        pass
    return {}


def from_name(stem):
    """'01. Linkin Park - Numb' -> track 1, artist, title."""
    m = re.match(r"^\s*(\d{1,3})\s*[.\-_)]\s*(.*)$", stem)
    track, rest = (m.group(1), m.group(2)) if m else (None, stem)
    artist, sep, title = rest.partition(" - ")
    return {"track": track, "artist": artist.strip() if sep else None, "title": (title if sep else rest).strip()}


def _art_from_image(data):
    if data[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    else:
        return None
    key = hashlib.sha1(data).hexdigest()[:16]
    out = CACHE / "art" / f"{key}.{ext}"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return out.name


def art_path(name):
    if not re.fullmatch(r"[0-9a-f]{16}\.(jpg|png)", name or ""):
        return None
    p = CACHE / "art" / name
    return p if p.exists() else None


def _number(v):
    m = re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def describe(path, root):
    """One song's entry: what the file says, filled in from its name and folder."""
    t = read_tags(path)
    n = from_name(path.stem)
    art = _art_from_image(t["art"]) if t.get("art") else None
    if not art:
        for c in COVERS:
            if (path.parent / c).exists():
                try:
                    art = _art_from_image((path.parent / c).read_bytes())
                except OSError:
                    art = None
                if art:
                    break
    rel = str(path.relative_to(root))
    album = t.get("album") or (path.parent.name if path.parent != root else None)
    bpm = _number(t.get("bpm"))
    st = path.stat()
    return {"id": hashlib.sha1(rel.encode()).hexdigest()[:16], "path": rel,
            "title": t.get("title") or n["title"], "artist": t.get("artist") or n["artist"] or "Unknown artist",
            "album": album or "Singles", "album_artist": t.get("album_artist"),
            "track": _number(t.get("track")) or _number(n["track"]), "art": art,
            "bpm": bpm if bpm and 50 <= bpm <= 220 else None, "bpm_source": "tag" if bpm and 50 <= bpm <= 220 else None,
            "size": st.st_size, "mtime": st.st_mtime, "added": st.st_mtime, "v": VERSION}


# ── tempo ────────────────────────────────────────────────────────────────────
def tempo_of_samples(x, rate):
    """Beats per minute of a mono signal: spectral flux onsets, autocorrelation, a gentle preference for ~120."""
    import numpy as np
    x = np.asarray(x, dtype=np.float32)
    if len(x) < rate * 8:
        return None, 0.0
    n_fft, hop = 1024, 256
    frames = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    mag = np.abs(np.fft.rfft(x[idx] * np.hanning(n_fft).astype(np.float32), axis=1))
    flux = np.maximum(0, np.diff(np.log1p(100 * mag), axis=0)).sum(axis=1)
    k = max(1, int(rate / hop * 0.5))
    flux = np.maximum(0, flux - np.convolve(flux, np.ones(k) / k, mode="same"))
    flux -= flux.mean()
    fps = rate / hop
    ac = np.correlate(flux, flux, mode="full")[len(flux) - 1:]
    if ac[0] <= 0:
        return None, 0.0
    lags = np.arange(len(ac))
    lo, hi = int(fps * 60 / 200), int(fps * 60 / 60)
    with np.errstate(divide="ignore"):
        bpm = 60 * fps / np.maximum(lags, 1)
    weight = np.exp(-0.5 * (np.log2(bpm / 120.0) / 0.9) ** 2)
    score = np.where((lags >= lo) & (lags <= hi), ac * weight, -np.inf)
    best = int(np.argmax(score))
    if 0 < best < len(ac) - 1:                         # sub-frame refinement
        a, b, c = ac[best - 1], ac[best], ac[best + 1]
        d = (a - 2 * b + c)
        shift = 0.5 * (a - c) / d if d else 0
    else:
        shift = 0
    confidence = float(ac[best] / ac[0])
    return round(float(60 * fps / (best + shift)), 1), round(confidence, 3)


def measure_tempo(path):
    """Decode up to the middle 90 s with afconvert (macOS) and measure. None when that isn't possible here."""
    import wave
    conv = shutil.which("afconvert")
    if not conv:
        return None, None
    import numpy as np
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "t.wav"
        r = subprocess.run([conv, "-f", "WAVE", "-d", "LEI16@11025", "-c", "1", str(path), str(out)],
                           capture_output=True, timeout=300)
        if r.returncode or not out.exists():
            return None, None
        with wave.open(str(out)) as w:
            rate, frames = w.getframerate(), w.getnframes()
            duration = frames / rate
            start = max(0, frames // 2 - 45 * rate)
            w.setpos(start)
            x = np.frombuffer(w.readframes(min(frames - start, 90 * rate)), dtype="<i2").astype(np.float32) / 32768
    bpm, _ = tempo_of_samples(x, rate)
    return bpm, round(duration, 1)


def cadence_of(bpm, band):
    """The cadence a song fits (BPM or BPM/2, whichever is nearer the band), and whether it's in the band (±2 rpm)."""
    if not bpm or not band:
        return None, False
    lo, hi = band
    mid = (lo + hi) / 2
    fit = min((bpm, bpm / 2), key=lambda c: abs(c - mid))
    return round(fit), lo - 2 <= fit <= hi + 2


# ── the index ────────────────────────────────────────────────────────────────
def _unmeasured(t):
    """Still to measure: no tempo or length yet, and not already tried (a song that can't be measured isn't retried)."""
    return (not t.get("bpm") or not t.get("duration")) and not t.get("tempo_checked")


def _files(root):
    for p in root.rglob("*"):
        if p.suffix.lower() in EXTS and p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
            yield p


def _run_scan():
    global _thread
    try:
        root = need_folder()
        with _lock:
            d = _load()
            known = {t["path"]: t for t in (d.get("tracks") or {}).values()} if d.get("folder") == str(root) else {}
        files = list(_files(root))
        _scan.update(state="reading", done=0, total=len(files), tempo_done=0, tempo_total=0)
        tracks = {}
        for p in files:
            rel = str(p.relative_to(root))
            old = known.get(rel)
            st = p.stat()
            if old and old.get("v") == VERSION and old.get("size") == st.st_size and old.get("mtime") == st.st_mtime:
                tracks[old["id"]] = old
            else:
                try:
                    t = describe(p, root)
                    if old:
                        t["added"] = old.get("added", t["added"])
                    tracks[t["id"]] = t
                except OSError:
                    pass
            _scan["done"] += 1
        with _lock:
            d = _load()
            d.update(folder=str(root), tracks=tracks, scanned=time.time())
            _save(d)
        todo = [t for t in tracks.values() if _unmeasured(t)]
        _scan.update(state="tempo", tempo_total=len(todo))
        for t in todo:
            try:
                bpm, duration = measure_tempo(root / t["path"])
            except (OSError, subprocess.SubprocessError, ValueError):
                bpm, duration = None, None
            with _lock:
                d = _load()
                cur = (d.get("tracks") or {}).get(t["id"])
                if cur is not None:
                    if duration:
                        cur["duration"] = duration
                    if bpm and not cur.get("bpm"):
                        cur.update(bpm=bpm, bpm_source="measured")
                    cur["tempo_checked"] = True
                    _save(d)
            _scan["tempo_done"] += 1
        _scan["state"] = "idle"
    except Exception as e:                              # never take the hub down over a music folder
        _scan.update(state="error", error=str(e))
    finally:
        _thread = None


def scan(wait=False):
    """Index the folder in the background: new and changed files are read, tempo is measured once."""
    global _thread
    with _lock:
        if _thread is None:
            _thread = threading.Thread(target=_run_scan, name="music-library", daemon=True)
            _thread.start()
        t = _thread
    if wait and t:
        t.join()


def library():
    root = folder()
    if not root:
        return {"folder": None, "display": None, "tracks": [], "scan": dict(_scan)}
    d = _load()
    stale = d.get("folder") != str(root) or not d.get("scanned") or time.time() - d.get("scanned", 0) > 300 \
        or any(_unmeasured(t) for t in (d.get("tracks") or {}).values())         # an interrupted tempo pass resumes
    if stale and _scan["state"] in ("idle", "error"):
        scan()
    tracks = sorted((d.get("tracks") or {}).values() if d.get("folder") == str(root) else [],
                    key=lambda t: ((t.get("album_artist") or t["artist"]).lower(), t["album"].lower(), t.get("track") or 0, t["title"].lower()))
    keep = ("id", "title", "artist", "album", "album_artist", "track", "art", "bpm", "bpm_source", "duration", "added")
    return {"folder": str(root), "display": str(root).replace(str(Path.home()), "~", 1),
            "tracks": [{k: t.get(k) for k in keep} for t in tracks], "scan": dict(_scan)}


def file_for(track_id):
    d = _load()
    t = (d.get("tracks") or {}).get(track_id)
    if not t:
        return None
    root = folder()
    if not root:
        return None
    p = (root / t["path"]).resolve()
    if root.resolve() not in p.parents or not p.is_file():
        return None
    return p


class FileSlice:
    """Part of a file, read in chunks by the HTTP server (for seeking in long songs)."""
    def __init__(self, path, start, length):
        self.f = open(path, "rb")
        self.f.seek(start)
        self.left = length

    def read(self, n=65536):
        if self.left <= 0:
            return b""
        b = self.f.read(min(n, self.left))
        self.left -= len(b)
        return b

    def close(self):
        self.f.close()


def open_range(path, range_header=""):
    """(status, mime, FileSlice, headers) for a whole file or a single byte range."""
    size = path.stat().st_size
    start, end = 0, size - 1
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header or "")
    status = 200
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:
            start = max(0, size - int(m.group(2)))
        if start > end or start >= size:
            raise ValueError("range")
        status = 206
    headers = {"Content-Length": str(end - start + 1), "Accept-Ranges": "bytes", "Cache-Control": "no-store",
               "X-Content-Type-Options": "nosniff"}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return status, MIME.get(path.suffix.lower(), "application/octet-stream"), FileSlice(path, start, end - start + 1), headers
