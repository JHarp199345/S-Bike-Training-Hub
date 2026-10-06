"""Your music folder: drag-and-drop uploads stream to disk, only real audio with safe names, never overwriting, this computer only."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import asyncio, io, json, os, struct, tempfile, wave
from pathlib import Path
from unittest.mock import patch

work = Path(tempfile.mkdtemp())
os.environ["HUB_MUSIC_FOLDER"] = str(work / "music")
import musicfolder, musiclibrary, panel
musiclibrary.INDEX, musiclibrary.CACHE = work / "music_library.json", work / "music_cache"   # never the real index
from test_hills import make_bridge

PORT = 18733


def wav(seconds=0.2):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * int(8000 * seconds))
    return b.getvalue()


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    check("a path is stripped to its file name", musicfolder.safe_name("../../etc/Song.mp3") == "Song.mp3")
    check("a leading dot is dropped, so nothing hides", musicfolder.safe_name(".hidden.mp3") == "hidden.mp3")
    for bad in ("notes.txt", "", "run.sh"):
        try:
            musicfolder.safe_name(bad); check(f"refuses {bad!r}", False)
        except ValueError:
            check(f"refuses {bad!r}", True)
    check("real wav recognised", musicfolder.looks_like_audio(".wav", wav()[:64]))
    check("text renamed .mp3 is not audio", not musicfolder.looks_like_audio(".mp3", b"hello world, not music at all"))

    for platform, supported in [("darwin", True), ("linux", False), ("win32", False)]:
        with patch.object(musicfolder.sys, "platform", platform):
            check(f"folder chooser availability on {platform}", musicfolder.listing()["choose_supported"] is supported)

    srv = await panel.serve(make_bridge(), PORT, lan=False)

    async def up(name, body, host="127.0.0.1"):
        rd, wr = await asyncio.open_connection("127.0.0.1", PORT)
        wr.write(f"POST /api/music/folder/upload?name={name} HTTP/1.1\r\nHost: {host}\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
        await wr.drain(); out = await rd.read(); wr.close()
        head, _, payload = out.partition(b"\r\n\r\n")
        return int(head.split()[1]), json.loads(payload)

    code, r = await up("Warm%20Up.wav", wav())
    check(f"upload saved to the folder ({r.get('saved')})", code == 200 and (work / "music" / "Warm Up.wav").exists())
    check("the reply lists the folder", r["folder"]["count"] == 1)
    code, r = await up("Warm%20Up.wav", wav(0.3))
    check(f"same name again is kept alongside, not overwritten ({r.get('saved')})", code == 200 and r["saved"] == "Warm Up (2).wav"
          and (work / "music" / "Warm Up.wav").stat().st_size < (work / "music" / "Warm Up (2).wav").stat().st_size)
    code, r = await up("fake.mp3", b"#!/bin/sh\necho not music\n" * 10)
    check(f"a fake audio file is refused and nothing is left behind ({r.get('error')})", code == 400
          and not (work / "music" / "fake.mp3").exists() and not list((work / "music").glob(".*part*")))
    code, r = await up("x.wav", wav(), host="evil.example")
    check("another host name is refused", code == 403 and not (work / "music" / "x.wav").exists())
    srv.close()
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
