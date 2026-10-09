"""Your media folder: setup only on this computer, 36 random picks or search, audio vs video, files that seek."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json, os, tempfile
from types import SimpleNamespace

work = pathlib.Path(tempfile.mkdtemp())
os.environ["HUB_MUSIC_FOLDER"] = str(work / "media")
import music, musiclibrary as lib
lib.INDEX, lib.CACHE = work / "music_library.json", work / "music_cache"


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    root = lib.need_folder()
    for i in range(50):
        (root / f"{i:02d}. Artist {i % 5} - Song {i}.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 400)
    for i in range(3):
        (root / f"Ride video {i}.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 400)
    lib.measure_tempo = lambda p: (None, None)
    lib.scan(wait=True)
    tracks = lib.library()["tracks"]
    check("audio and video are both indexed, each with its kind", sum(t["kind"] == "audio" for t in tracks) == 50 and sum(t["kind"] == "video" for t in tracks) == 3)
    picks = music.pick(tracks, "audio", seed="x")
    check("36 random audio picks, stable for the same seed", len(picks) == 36 and [t["id"] for t in picks] == [t["id"] for t in music.pick(tracks, "audio", seed="x")])
    check("a new seed gives a different 36", [t["id"] for t in picks] != [t["id"] for t in music.pick(tracks, "audio", seed="y")])
    check("video picks are videos only", {t["kind"] for t in music.pick(tracks, "video")} == {"video"})
    check("search finds by title or artist", {t["title"] for t in music.pick(tracks, "audio", "song 4")} >= {"Song 4", "Song 40"} and len(music.pick(tracks, "audio", "artist 3")) == 10)
    bridge = SimpleNamespace(csv_path=work / "rides" / "x.csv")
    async def call(path, method=b"GET", peer=("127.0.0.1", 5), host="127.0.0.1:8729", headers=None):
        return await music.handle(bridge, method, path, b"", host, headers or {}, peer)
    code, _, body, _ = asyncio.run(call("/api/music/library/picks?kind=video"))
    check("the picks endpoint serves playable urls", code == 200 and all(i["url"].startswith("/api/music/library/file/") for i in json.loads(body)["items"]))
    check("choosing the folder is refused from another device", asyncio.run(call("/api/music/folder/choose", b"POST", peer=("192.168.1.9", 5)))[0] == 403)
    check("a cross-site request is refused", asyncio.run(call("/api/music/library", headers={b"sec-fetch-site": b"cross-site"}))[0] == 403)
    vid = next(t for t in tracks if t["kind"] == "video")
    code, mime, stream, extra = asyncio.run(call("/api/music/library/file/" + vid["id"], headers={b"range": b"bytes=0-9"}))
    check(f"videos stream with byte ranges ({mime}, {extra.get('Content-Range')})", code == 206 and mime == "video/mp4" and len(stream.read()) == 10)
    stream.close()
    check("removed services answer nothing", asyncio.run(call("/api/music/plex/servers"))[0] == 404)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
