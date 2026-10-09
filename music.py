"""Your media: the private folder of audio and video files, nothing else. No athlete data or trainer commands.

The folder is the athlete's choice (musiclibrary.py reads it; musicfolder.py takes uploads). Files are served from
this computer with byte ranges so long songs and videos can seek. Setup (choosing the folder, uploads, rescans) is
available only on this computer; playback works on paired devices too.
"""
# Copyright © 2026 S-Bike Training Hub contributors.
import asyncio
import json
import random
from urllib.parse import parse_qs, urlsplit


class MusicError(ValueError):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


class StreamBody:
    """A response owned by the HTTP server; always closed on disconnect."""
    def __init__(self, response):
        self.response = response

    def read(self):
        return self.response.read(65536)

    def close(self):
        self.response.close()


def json_response(value, code=200):
    return code, "application/json", json.dumps(value).encode(), {"Cache-Control": "no-store"}


def pick(tracks, kind="audio", query="", count=36, seed=None):
    """What the library shows: matches for a search, or a random handful to choose from."""
    pool = [t for t in tracks if (t.get("kind") or "audio") == kind]
    q = (query or "").strip().lower()
    if q:
        hits = [t for t in pool if any(q in (t.get(k) or "").lower() for k in ("title", "artist", "album"))]
        return hits[:200]
    rng = random.Random(seed)
    return rng.sample(pool, min(count, len(pool)))


def library_request(method, p, q):
    import musiclibrary as lib
    if p == "/api/music/library" and method == b"GET":
        return json_response(lib.library())
    if p == "/api/music/library/picks" and method == b"GET":
        info = lib.library()
        kind = q.get("kind") if q.get("kind") in ("audio", "video") else "audio"
        items = pick(info["tracks"], kind, q.get("q", ""), seed=q.get("seed"))
        return json_response({"folder": info["folder"], "display": info["display"], "kind": kind, "query": q.get("q", ""),
                              "items": [{**t, "url": "/api/music/library/file/" + t["id"]} for t in items],
                              "counts": {k: sum(1 for t in info["tracks"] if (t.get("kind") or "audio") == k) for k in ("audio", "video")},
                              "scan": info["scan"]})
    if p.startswith("/api/music/library/art/") and method == b"GET":
        f = lib.art_path(p.rsplit("/", 1)[1])
        if not f:
            raise MusicError("No cover art.", 404)
        return 200, "image/png" if f.suffix == ".png" else "image/jpeg", f.read_bytes(), {"Cache-Control": "max-age=86400"}
    if p.startswith("/api/music/library/file/") and method == b"GET":
        f = lib.file_for(p.rsplit("/", 1)[1])
        if not f:
            raise MusicError("That file isn't in your folder any more.", 404)
        try:
            code, mime, body, extra = lib.open_range(f, q.get("_range", ""))
        except ValueError:
            raise MusicError("Unsupported playback range.", 416) from None
        return code, mime, StreamBody(body), extra
    if p == "/api/music/library/rescan" and method == b"POST":
        lib.scan()
        return json_response({"scanning": True})
    if p == "/api/music/folder/choose" and method == b"POST":
        chosen = lib.choose_folder()
        return json_response({"folder": chosen, "cancelled": chosen is None})
    if p == "/api/music/folder" and method == b"GET":
        import musicfolder
        return json_response(musicfolder.listing())
    if p == "/api/music/folder/open" and method == b"POST":
        import musicfolder
        try:
            musicfolder.reveal()
        except ValueError as e:
            raise MusicError(str(e)) from None
        return json_response({"opened": True})
    raise MusicError("Unknown media request.", 404)


async def handle(bridge, method, path, body, host, headers=None, peer=None):
    if not path.startswith("/api/music/"):
        return None
    import remote
    headers = headers or {}
    p = urlsplit(path).path
    # Choosing the folder, uploads and rescans happen only on this computer.
    admin = p.startswith(("/api/music/folder", "/api/music/library/rescan"))
    if admin and (not remote.is_local(peer) or urlsplit("http://" + host).hostname not in ("localhost", "127.0.0.1", "::1")):
        return json_response({"error": "Set up your media folder on the computer running the Hub."}, 403)
    origin = headers.get(b"origin", b"").decode()
    if origin and origin != "http://" + host:
        return json_response({"error": "Open media controls from the Hub."}, 403)
    if headers.get(b"sec-fetch-site") == b"cross-site":
        return json_response({"error": "Open media controls from the Hub."}, 403)
    q = {k: v[0] for k, v in parse_qs(urlsplit(path).query).items()}
    q["_range"] = headers.get(b"range", b"").decode()
    try:
        return await asyncio.to_thread(library_request, method, p, q)
    except MusicError as e:
        return json_response({"error": str(e)}, e.code)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except Exception:
        return json_response({"error": "Your media could not load. Check the folder and try again."}, 502)
