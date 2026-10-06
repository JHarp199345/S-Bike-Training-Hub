"""Your music folder as a library: tags and cover art from the files, names as a fallback, tempo, cadence fit, seeking."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import io, os, struct, tempfile, wave
from pathlib import Path

work = Path(tempfile.mkdtemp())
os.environ["HUB_MUSIC_FOLDER"] = str(work / "music")
import musiclibrary as lib
lib.INDEX, lib.CACHE = work / "music_library.json", work / "music_cache"

JPEG = b"\xff\xd8\xff\xe0" + b"cover" * 20


def frame(fid, payload):
    return fid.encode() + struct.pack(">I", len(payload)) + b"\x00\x00" + payload


def id3(**tags):
    names = {"title": "TIT2", "artist": "TPE1", "album": "TALB", "track": "TRCK", "bpm": "TBPM"}
    body = b"".join(frame(names[k], b"\x03" + v.encode()) for k, v in tags.items())
    body += frame("APIC", b"\x00image/jpeg\x00\x03\x00" + JPEG)
    size = len(body)
    ss = bytes([(size >> 21) & 127, (size >> 14) & 127, (size >> 7) & 127, size & 127])
    return b"ID3\x03\x00\x00" + ss + body + b"\xff\xfb\x90\x00" + b"\x00" * 400


def clicks(bpm, seconds=20, rate=11025):
    import numpy as np
    x = np.zeros(int(seconds * rate), dtype=np.float32)
    step = 60 / bpm * rate
    for i in range(int(seconds * bpm / 60)):
        s = int(i * step); x[s:s + 200] = np.random.default_rng(i).standard_normal(200) * 0.8
    return x, rate


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    root = lib.need_folder()
    (root / "Album").mkdir()
    (root / "Album" / "a.mp3").write_bytes(id3(title="Numb", artist="Linkin Park", album="Meteora", track="13/13", bpm="110"))
    (root / "07. Dua Lipa - Houdini.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 400)
    (root / "Album" / "cover.jpg").write_bytes(JPEG)
    (root / ".hidden.mp3").write_bytes(b"x")
    t = lib.describe(root / "Album" / "a.mp3", root)
    check(f"ID3 tags read ({t['title']}, {t['artist']}, {t['album']}, track {t['track']}, {t['bpm']} BPM from the tag)",
          (t["title"], t["artist"], t["album"], t["track"], t["bpm"], t["bpm_source"]) == ("Numb", "Linkin Park", "Meteora", 13, 110, "tag"))
    check("embedded cover art saved to the cache", t["art"] and lib.art_path(t["art"]).read_bytes() == JPEG)
    n = lib.describe(root / "07. Dua Lipa - Houdini.mp3", root)
    check(f"untagged file named from its name ({n['track']}. {n['artist']} - {n['title']})", (n["track"], n["artist"], n["title"]) == (7, "Dua Lipa", "Houdini"))
    check("art path refuses anything but a cache name", lib.art_path("../../etc/passwd") is None)
    for bpm in (87, 128, 174):
        got, conf = lib.tempo_of_samples(*clicks(bpm))
        check(f"tempo of a {bpm} BPM click track: {got} (or its double/half)", got and min(abs(got - bpm), abs(got * 2 - bpm), abs(got / 2 - bpm)) <= 2)
    check("174 BPM fits an 85-95 rpm band at 87 rpm", lib.cadence_of(174, (85, 95)) == (87, True))
    check("87 BPM (half-time) fits too", lib.cadence_of(87, (85, 95)) == (87, True))
    check("128 BPM doesn't fit 85-95 (64 or 128 rpm)", not lib.cadence_of(128, (85, 95))[1])
    lib.measure_tempo = lambda p: (None, None)          # the scan's tempo step is tested above; keep this quick
    lib.scan(wait=True)
    L = lib.library()
    check(f"scan lists the two songs and skips hidden files ({len(L['tracks'])})", len(L["tracks"]) == 2)
    tid = next(x["id"] for x in L["tracks"] if x["title"] == "Numb")
    f = lib.file_for(tid)
    code, mime, body, h = lib.open_range(f, "bytes=10-19")
    check(f"seeking: a byte range comes back as 206 ({h.get('Content-Range')})", code == 206 and body.read() == f.read_bytes()[10:20] and mime == "audio/mpeg")
    body.close()
    check("an unknown song id plays nothing", lib.file_for("0" * 16) is None)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
