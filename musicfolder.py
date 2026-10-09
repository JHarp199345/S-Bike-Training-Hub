"""musicfolder.py - the athlete's own music folder: drag-and-drop uploads into it, and a listing of what's there.

The folder lives outside the Hub's code (default ~/Music/S-Bike Hub Music), so music never reaches Git. Uploads are
streamed straight to disk (no size cap from the web server's in-memory limit), accepted only from this computer,
checked to be real audio by their first bytes, given a safe name, and never overwrite an existing file.
"""
import os
import re
import secrets
import sys
from pathlib import Path

EXTS = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".aif", ".aiff", ".ogg", ".opus", ".mp4", ".m4v", ".webm", ".mov"}
MAX_BYTES = 1_000_000_000          # 1 GB a file: room for long lossless mixes


def folder():
    import musiclibrary
    return musiclibrary.need_folder()           # the folder the athlete chose in Music settings


def looks_like_audio(ext, head):
    """The first bytes match the format the name claims (roughly; enough to refuse non-audio)."""
    if ext == ".mp3":
        return head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    if ext in (".m4a", ".aac"):
        return head[4:8] == b"ftyp" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xF0 == 0xF0)
    if ext == ".flac":
        return head[:4] == b"fLaC" or head[:3] == b"ID3"
    if ext == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if ext in (".aif", ".aiff"):
        return head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC")
    if ext in (".ogg", ".opus"):
        return head[:4] == b"OggS"
    if ext in (".mp4", ".m4v", ".mov"):
        return head[4:8] in (b"ftyp", b"moov", b"wide", b"mdat", b"free")
    if ext == ".webm":
        return head[:4] == b"\x1a\x45\xdf\xa3"
    return False


def safe_name(name):
    name = Path(str(name)).name
    name = re.sub(r"[\x00-\x1f/\\:]+", " ", name).strip().lstrip(".")
    stem, ext = os.path.splitext(name)
    if ext.lower() not in EXTS or not stem:
        raise ValueError(f"{name or 'That file'} isn't an audio or video file (mp3, m4a, aac, flac, wav, aiff, ogg, opus, mp4, m4v, webm, mov)")
    return stem[:180] + ext.lower()


def target(name):
    """A path in the folder that doesn't exist yet: 'Song.mp3', then 'Song (2).mp3' ..."""
    f = folder()
    stem, ext = os.path.splitext(name)
    dest, n = f / name, 2
    while dest.exists():
        dest, n = f / f"{stem} ({n}){ext}", n + 1
    return dest


async def receive(reader, length, name):
    """Stream an upload body of `length` bytes into the folder. Returns the saved file name."""
    name = safe_name(name)
    if not 0 < length <= MAX_BYTES:
        raise ValueError("That file is empty or larger than 1 GB")
    dest = target(name)
    part = dest.with_name(f".{dest.name}.{secrets.token_hex(4)}.part")
    got, ok = 0, False
    try:
        with open(part, "wb") as out:
            first = True
            while got < length:
                chunk = await reader.read(min(1 << 20, length - got))
                if not chunk:
                    raise ValueError("The upload stopped before it finished")
                if first:
                    if not looks_like_audio(dest.suffix, chunk[:16]):
                        raise ValueError(f"{name} doesn't look like a real {dest.suffix[1:]} file")
                    first = False
                out.write(chunk)
                got += len(chunk)
        final = dest if not dest.exists() else target(name)       # another upload took the name meanwhile
        part.replace(final)
        ok = True
        return final.name
    finally:
        if not ok and part.exists():
            part.unlink()


def reveal():
    """Open the folder in the computer's file manager."""
    import subprocess, sys
    f = folder()
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(f)])
    elif sys.platform.startswith("win"):
        os.startfile(str(f))                    # noqa: windows only
    else:
        subprocess.Popen(["xdg-open", str(f)])


def listing(limit=12):
    import musiclibrary
    f = musiclibrary.folder()
    if not f:
        return {"path": None, "display": None, "count": 0, "megabytes": 0, "recent": [], "choose_supported": sys.platform == "darwin"}
    files = [p for p in f.rglob("*") if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith(".")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return {"path": str(f), "display": str(f).replace(str(Path.home()), "~", 1), "count": len(files),
            "megabytes": round(sum(p.stat().st_size for p in files) / 1e6, 1),
            "recent": [str(p.relative_to(f)) for p in files[:limit]], "choose_supported": sys.platform == "darwin"}
