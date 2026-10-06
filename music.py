"""Personal music connections. No athlete data or trainer commands are used here.

Plex streams are proxied in bounded chunks so account credentials never appear
in audio or video URLs sent to the browser. Your own music folder is served by musiclibrary.py. Apple
Music playback stays in Apple's official MusicKit JS player.
"""
# Copyright © 2026 S-Bike Training Hub contributors.
import asyncio
import base64
import ipaddress
import json
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROVIDERS = ("plex", "apple")
UA = "S-Bike-Training-Hub-Music/1.0"
MAX_JSON = 32_000_000
_stores = {}
_stores_lock = threading.Lock()


class MusicError(ValueError):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward account credentials to a redirect destination.
        return None


def server_url(value):
    value = str(value).strip().rstrip("/")
    u = urlsplit(value)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise MusicError("Enter a server address such as https://music.example.com.")
    try: u.port
    except ValueError: raise MusicError("Enter a server address with a valid port.") from None
    try:
        addr = ipaddress.ip_address(u.hostname)
    except ValueError:
        addr = None
    if addr and (addr.is_link_local or addr.is_multicast or addr.is_unspecified):
        raise MusicError("Choose your music server's regular network address.")
    local = u.hostname in ("localhost", "127.0.0.1", "::1") or (addr and addr.is_private) or u.hostname.endswith(".local")
    if u.scheme == "http" and not local:
        raise MusicError("Use HTTPS for a music server outside your home network.")
    return value


def open_remote(url, headers=None, data=None):
    req = Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    try:
        return build_opener(NoRedirect()).open(req, timeout=15)
    except HTTPError as e:
        if e.code in (401, 403):
            raise MusicError("Music access was declined or expired. Reconnect this account.", 401) from None
        if e.code == 416:
            raise MusicError("That playback position is unavailable.", 416) from None
        raise MusicError("The music service could not complete this request. Try again.", 502) from None
    except (URLError, OSError, TimeoutError):
        raise MusicError("Could not reach the music service. Check its address and connection.", 502) from None


def request_json(url, headers=None, data=None, form=False):
    h = {"Accept": "application/json", **(headers or {})}
    raw = None
    if data is not None:
        h["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        raw = (urlencode(data) if form else json.dumps(data)).encode()
    with open_remote(url, h, raw) as r:
        content = r.read(MAX_JSON + 1)
    if len(content) > MAX_JSON:
        raise MusicError("This library is too large to load at once.", 413)
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        raise MusicError("The music server returned an unreadable response.", 502) from None


class StreamBody:
    """A response owned by the HTTP server; always closed on disconnect."""
    def __init__(self, response):
        self.response = response

    def read(self):
        return self.response.read(65536)

    def close(self):
        self.response.close()


class Store:
    def __init__(self, base):
        self.file = Path(base) / "music.json"
        self.lock = threading.RLock()
        self.cache = {}
        self.pending = {}
        self.tickets = {}
        self.server_choices = {}

    def load(self):
        try:
            d = json.loads(self.file.read_text())
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, d):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_name("music.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(d, f)
        os.chmod(tmp, 0o600)
        tmp.replace(self.file)

    def config(self, provider):
        d = self.load().get(provider, {}).copy()
        if provider == "apple":
            d["developer_token"] = os.environ.get("HUB_APPLE_MUSIC_DEVELOPER_TOKEN") or d.get("developer_token", "")
        return d

    def public(self):
        out = {}
        for p in PROVIDERS:
            c = self.config(p)
            ready = bool(c.get("developer_token")) if p == "apple" else True
            connected = bool(c.get("server") and c.get("token")) if p == "plex" else False
            out[p] = {"ready": ready, "connected": connected, "server": c.get("server", ""), "label": c.get("label", ""),
                      "has_secret": bool(c.get("token"))}
        return {"providers": out}

    def configure(self, req):
        p = req.get("provider")
        if p not in PROVIDERS:
            raise MusicError("Choose a listed music source.")
        d = self.load()
        old = d.get(p, {})
        c = old.copy()
        fields = {"plex": ("server", "token"), "apple": ("developer_token",)}[p]
        for k in fields:
            v = str(req.get(k, "")).strip()
            if len(v) > 12000:
                raise MusicError("That setting is too long.")
            if v:
                c[k] = server_url(v) if k == "server" else v
        if p == "apple" and c.get("developer_token"):
            try:
                token = c["developer_token"]
                claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
                if float(claims["exp"]) <= time.time():
                    raise ValueError()
            except (ValueError, KeyError, IndexError, TypeError):
                raise MusicError("Enter a current signed Apple Music developer token.") from None
        # Changing a server invalidates any credentials unless replacements were supplied.
        if c.get("server") != old.get("server"):
            if not str(req.get("token", "")).strip(): c.pop("token", None)
        d[p] = c; self.save(d)
        self.invalidate(p)
        return self.public()

    def invalidate(self, p):
        self.cache.pop(p, None); self.pending.pop(p, None)
        self.tickets = {k: v for k, v in self.tickets.items() if v[0] != p}

    def forget(self, p):
        if p not in PROVIDERS: raise MusicError("Choose a listed music source.")
        d = self.load(); c = d.pop(p, {})
        # Keep publisher settings, remove the athlete's account access.
        if p == "apple" and c.get("developer_token"): d[p] = {"developer_token": c["developer_token"]}
        self.save(d); self.invalidate(p)
        return self.public()

    def plex(self, path):
        c = self.config("plex")
        if not c.get("server") or not c.get("token"): raise MusicError("Connect Plex and choose your music server in Settings.")
        return request_json(c["server"] + path, {"X-Plex-Token": c["token"]}).get("MediaContainer", {})

    def video(self, parent="", offset=0):
        """Browse personal server libraries, never Plex's separately licensed catalog."""
        if not parent:
            rows = self.plex("/library/sections").get("Directory", [])
            return {"items": [{"id": "section:" + str(v["key"]), "title": v.get("title", "Library"), "folder": True}
                              for v in rows if v.get("type") in ("movie", "show")]}
        if not re.fullmatch(r"(section|item):\d+", parent): raise MusicError("Choose a Plex library or show.")
        kind, key = parent.split(":")
        path = "/library/sections/" + key + "/all" if kind == "section" else "/library/metadata/" + key + "/children"
        offset = max(0, min(int(offset), 100000))
        data = self.plex(path + "?" + urlencode({"X-Plex-Container-Start": offset, "X-Plex-Container-Size": 100}))
        rows = data.get("Metadata", []); items = []
        for v in rows:
            title = v.get("title", "Video")
            if v.get("type") in ("show", "season"):
                items.append({"id": "item:" + str(v["ratingKey"]), "title": title, "folder": True})
            elif v.get("type") in ("movie", "episode"):
                choices = [(m, part) for m in v.get("Media", []) for part in m.get("Part", [])
                           if m.get("container", part.get("container")) in ("mp4", "webm")]
                selected = next(((m, part) for m, part in choices if self.plex_part(part.get("key", ""))), None)
                item = {"id": str(v["ratingKey"]), "title": title, "folder": False,
                        "detail": v.get("grandparentTitle", ""), "duration": v.get("duration", 0) / 1000}
                if selected:
                    m, part = selected
                    ticket = self.issue("plex", {"id": item["id"], "resource": part["key"], "video": True})
                    item.update(url="/api/music/stream/" + ticket, codec=m.get("videoCodec", ""), container=m.get("container", part.get("container")))
                else: item["unavailable"] = "This file needs Plex transcoding. Use Plex's player for now."
                items.append(item)
        total = int(data.get("totalSize", offset + len(rows)))
        return {"items": items, "next": offset + len(rows) if rows and offset + len(rows) < total else None}

    @staticmethod
    def plex_part(key):
        return bool(re.fullmatch(r"/library/parts/[A-Za-z0-9_./%+-]+", key)) and ".." not in key

    def playlists(self, p):
        if p == "plex":
            items = self.plex("/playlists?playlistType=audio").get("Metadata", [])
            return [{"id": str(v["ratingKey"]), "name": v.get("title", "Playlist"), "count": v.get("leafCount")} for v in items if v.get("playlistType") == "audio"]
        raise MusicError("Choose a connected music source.")

    def tracks(self, p, pid):
        # Resolve only a real playlist from this account; never accept arbitrary URLs.
        if pid not in {v["id"] for v in self.playlists(p)}: raise MusicError("That playlist is no longer available.", 404)
        if p == "plex":
            songs = self.plex("/playlists/" + quote(pid, safe="") + "/items").get("Metadata", [])
            items = []
            for v in songs:
                parts = [part for media in v.get("Media", []) for part in media.get("Part", [])]
                if v.get("type") == "track" and parts:
                    key = parts[0].get("key", "")
                    if self.plex_part(key):
                        items.append((str(v["ratingKey"]), v.get("title", "Track"), v.get("grandparentTitle", ""), v.get("duration", 0) / 1000, key))
        else:
            raise MusicError("Choose a connected music source.")
        out = []
        for tid, title, artist, duration, resource in items[:5000]:
            ticket = self.issue(p, {"id": tid, "resource": resource})
            out.append({"id": tid, "title": title, "artist": artist, "duration": duration, "url": "/api/music/stream/" + ticket})
        return {"tracks": out}

    MAX_TICKETS = 20000

    def issue(self, provider, data, ttl=86400):
        """A playback ticket (an opaque URL token; the credentials stay here). Expired ones are dropped first, and
        the oldest go when there are too many - video and audio alike, so browsing can't grow memory forever."""
        now = time.time()
        if not getattr(self, "_pruned", 0) or now - self._pruned > 60 or len(self.tickets) >= self.MAX_TICKETS:
            self.tickets = {k: v for k, v in self.tickets.items() if v[2] > now}
            self._pruned = now
        while len(self.tickets) >= self.MAX_TICKETS:
            self.tickets.pop(min(self.tickets, key=lambda k: self.tickets[k][2]))
        ticket = secrets.token_urlsafe(24)
        self.tickets[ticket] = (provider, data, now + ttl)
        return ticket

    def stream(self, ticket, range_header=""):
        item = self.tickets.get(ticket)
        if not item or item[2] < time.time(): raise MusicError("This music queue expired. Select the playlist again.", 404)
        p, track, _ = item
        if p != "plex": raise MusicError("This music queue expired. Select the playlist again.", 404)
        c = self.config(p); url = c["server"] + track["resource"]; h = {"X-Plex-Token": c["token"]}
        if range_header:
            if not re.fullmatch(r"bytes=\d*-\d*", range_header): raise MusicError("Unsupported playback range.", 416)
            h["Range"] = range_header
        r = open_remote(url, h)
        mime = r.headers.get("Content-Type", "video/mp4" if track.get("video") else "audio/mpeg").split(";")[0]
        if track.get("video") and mime == "application/octet-stream": mime = "video/webm" if track["resource"].endswith(".webm") else "video/mp4"
        if not (mime.startswith("audio/") or mime in ("application/octet-stream", "video/mp4", "video/webm", "application/ogg")):
            r.close(); raise MusicError("The music service did not return playable audio.", 502)
        extra = {k: r.headers[k] for k in ("Content-Length", "Content-Range", "Accept-Ranges") if r.headers.get(k)}
        extra.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        return r.status, mime, StreamBody(r), extra

    def connect(self, p):
        if p == "plex":
            d = self.load(); c = d.setdefault(p, {}); c.setdefault("client_id", str(uuid.uuid4())); self.save(d)
            pin = request_json("https://plex.tv/api/v2/pins?strong=true", self.plex_headers(c), data={})
            self.pending[p] = {"id": pin["id"], "expires_at": time.time() + pin.get("expiresIn", 600), "next_poll": time.time() + 3}
            url = "https://app.plex.tv/auth#?" + urlencode({"clientID": c["client_id"], "code": pin["code"], "context[device][product]": "S-Bike Training Hub"})
            return self.connection_card(url, "", 3, "plex")
        raise MusicError("Use this source's connection form.")

    @staticmethod
    def connection_card(url, code, interval, provider):
        host = urlsplit(url).hostname
        if urlsplit(url).scheme != "https" or host != "app.plex.tv":
            raise MusicError("The service returned an unexpected sign-in address.", 502)
        import qr
        return {"url": url, "code": code, "interval": max(3, int(interval)), "qr": qr.svg(url)}

    @staticmethod
    def plex_headers(c):
        return {"X-Plex-Product": "S-Bike Training Hub", "X-Plex-Client-Identifier": c["client_id"], "X-Plex-Version": "1.0"}

    def connect_poll(self, p):
        pending = self.pending.get(p)
        if not pending or pending["expires_at"] < time.time():
            self.pending.pop(p, None); raise MusicError("The sign-in code expired. Click Connect again.", 410)
        if time.time() < pending["next_poll"]: return {"pending": True}
        pending["next_poll"] = time.time() + max(3, pending.get("interval", 5))
        if p == "plex":
            c = self.config(p)
            r = request_json("https://plex.tv/api/v2/pins/" + str(pending["id"]), self.plex_headers(c))
            if not r.get("authToken"): return {"pending": True}
            d = self.load(); d.setdefault(p, {})["account_token"] = r["authToken"]; self.save(d)
            self.pending.pop(p, None)
            return {"connected": True, "servers": self.plex_servers()}
        raise MusicError("Use this source's connection form.")

    def plex_servers(self):
        c = self.config("plex")
        if not c.get("account_token"): raise MusicError("Sign into Plex first.", 401)
        raw = request_json("https://plex.tv/api/v2/resources?includeHttps=1&includeRelay=0", {**self.plex_headers(c), "X-Plex-Token": c["account_token"]})
        choices = {}; out = []
        for resource in raw if isinstance(raw, list) else []:
            if "server" not in resource.get("provides", ""): continue
            for connection in sorted(resource.get("connections", []), key=lambda x: (not x.get("local"), x.get("protocol") != "https")):
                try: address = server_url(connection["uri"])
                except (MusicError, KeyError): continue
                key = secrets.token_urlsafe(18)
                choices[key] = {"server": address, "token": resource.get("accessToken") or c["account_token"], "label": resource.get("name", "Plex")}
                out.append({"id": key, "name": resource.get("name", "Plex") + (" · home network" if connection.get("local") else " · remote"), "server": address})
        self.server_choices = choices
        return out

    def choose_plex(self, key):
        choice = self.server_choices.get(key)
        if not choice: raise MusicError("Refresh Plex's server list and choose again.")
        # Confirm the selected server really accepts this account before saving it.
        request_json(choice["server"] + "/library/sections", {"X-Plex-Token": choice["token"]})
        d = self.load(); d.setdefault("plex", {}).update(choice); self.save(d); self.invalidate("plex")
        return self.public()


def library_request(method, p, q):
    """Your music folder as a library (musiclibrary.py): listing, cover art, files with seeking, folder choice."""
    import musiclibrary as lib
    if p == "/api/music/library" and method == b"GET": return json_response(lib.library())
    if p.startswith("/api/music/library/art/") and method == b"GET":
        f = lib.art_path(p.rsplit("/", 1)[1])
        if not f: raise MusicError("No cover art.", 404)
        return 200, "image/png" if f.suffix == ".png" else "image/jpeg", f.read_bytes(), {"Cache-Control": "max-age=86400"}
    if p.startswith("/api/music/library/file/") and method == b"GET":
        f = lib.file_for(p.rsplit("/", 1)[1])
        if not f: raise MusicError("That song isn't in your music folder any more.", 404)
        try: code, mime, body, extra = lib.open_range(f, q.get("_range", ""))
        except ValueError: raise MusicError("Unsupported playback range.", 416) from None
        return code, mime, StreamBody(body), extra
    if p == "/api/music/library/rescan" and method == b"POST": lib.scan(); return json_response({"scanning": True})
    if p == "/api/music/folder/choose" and method == b"POST":
        chosen = lib.choose_folder()
        return json_response({"folder": chosen, "cancelled": chosen is None})
    tracks = lib.library()["tracks"]
    if p == "/api/music/playlists":
        albums = {}
        for t in tracks: albums.setdefault(t["album"], []).append(t)
        rows = [{"id": "all", "name": "All songs", "count": len(tracks)}]
        rows += [{"id": "album:" + a, "name": a, "count": len(ts)} for a, ts in sorted(albums.items(), key=lambda x: x[0].lower())]
        return json_response({"playlists": rows})
    if p == "/api/music/tracks":
        pl = q.get("playlist", "all")
        pick = tracks if pl == "all" else [t for t in tracks if "album:" + t["album"] == pl]
        return json_response({"tracks": [{**t, "url": "/api/music/library/file/" + t["id"]} for t in pick]})
    raise MusicError("Unknown music request.", 404)


def store_for(bridge):
    base = Path(bridge.csv_path).resolve().parent.parent if getattr(bridge, "csv_path", None) else Path(__file__).resolve().parent
    with _stores_lock:
        return _stores.setdefault(str(base), Store(base))


def json_response(value, code=200):
    return code, "application/json", json.dumps(value).encode(), {"Cache-Control": "no-store"}


async def handle(bridge, method, path, body, host, headers=None, peer=None):
    if not path.startswith("/api/music/"): return None
    import remote
    headers = headers or {}
    p = urlsplit(path).path
    # Setup and all credential-bearing responses are available only on this computer.
    admin = p.startswith(("/api/music/settings", "/api/music/connect", "/api/music/forget", "/api/music/apple", "/api/music/plex", "/api/music/folder", "/api/music/library/rescan"))
    if admin and (not remote.is_local(peer) or urlsplit("http://" + host).hostname not in ("localhost", "127.0.0.1", "::1")):
        return json_response({"error": "Connect music accounts on the computer running the Hub."}, 403)
    origin = headers.get(b"origin", b"").decode()
    if origin and origin != "http://" + host:
        return json_response({"error": "Open music controls from the Hub."}, 403)
    if headers.get(b"sec-fetch-site") == b"cross-site": return json_response({"error": "Open music controls from the Hub."}, 403)
    s = store_for(bridge)
    q = {k: v[0] for k, v in parse_qs(urlsplit(path).query).items()}
    if p.startswith(("/api/music/library", "/api/music/folder/choose")) or (p in ("/api/music/playlists", "/api/music/tracks") and q.get("provider") == "library"):
        q["_range"] = headers.get(b"range", b"").decode()
        try: return await asyncio.to_thread(library_request, method, p, q)
        except MusicError as e: return json_response({"error": str(e)}, e.code)
        except ValueError as e: return json_response({"error": str(e)}, 400)
    def operation():
        with s.lock:
            req = {}
            if method == b"POST":
                if len(body) > 65536: raise MusicError("Music settings are too large.", 413)
                try: req = json.loads(body or b"{}")
                except ValueError: raise MusicError("Could not read music settings.") from None
                if not isinstance(req, dict): raise MusicError("Could not read music settings.")
            if p == "/api/music/folder" and method == b"GET":
                import musicfolder
                return json_response(musicfolder.listing())
            if p == "/api/music/folder/open" and method == b"POST":
                import musicfolder
                try: musicfolder.reveal()
                except ValueError as e: raise MusicError(str(e)) from None
                return json_response({"opened": True})
            if p == "/api/music/settings":
                if method == b"GET": return json_response(s.public())
                if method == b"POST": return json_response(s.configure(req))
            elif p == "/api/music/forget" and method == b"POST": return json_response(s.forget(req.get("provider")))
            elif p == "/api/music/connect" and method == b"POST": return json_response(s.connect(req.get("provider")))
            elif p == "/api/music/connect/poll" and method == b"POST": return json_response(s.connect_poll(req.get("provider")))
            elif p == "/api/music/plex/servers" and method == b"GET": return json_response({"servers": s.plex_servers()})
            elif p == "/api/music/plex/select" and method == b"POST": return json_response(s.choose_plex(req.get("id")))
            elif p == "/api/music/apple" and method == b"GET":
                token = s.config("apple").get("developer_token")
                if not token: raise MusicError("Apple Music is awaiting the Hub's developer setup. Local music is available now.", 424)
                return json_response({"developer_token": token})
            elif p == "/api/music/playlists" and method == b"GET": return json_response({"playlists": s.playlists(q.get("provider"))})
            elif p == "/api/music/tracks" and method == b"GET": return json_response(s.tracks(q.get("provider"), q.get("playlist")))
            elif p == "/api/music/video" and method == b"GET": return json_response(s.video(q.get("parent", ""), q.get("offset", 0)))
            elif p.startswith("/api/music/stream/") and method == b"GET": return s.stream(p.rsplit("/", 1)[1], headers.get(b"range", b"").decode())
            else: return json_response({"error": "Unknown music request."}, 404)
            return json_response({"error": "Method not allowed."}, 405)
    try: return await asyncio.to_thread(operation)
    except MusicError as e: return json_response({"error": str(e)}, e.code)
    except Exception: return json_response({"error": "Music could not load. Check this source's setup and try again."}, 502)
