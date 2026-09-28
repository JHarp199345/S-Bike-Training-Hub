"""strava.py - post rides to Strava through your own Strava API app.

Strava's public API can't attach photos, so the infographic goes on from the
phone (save it, then add it in the Strava app). What this does:

  - update the ride the COROS watch already synced (found by start time):
    title and caption. No duplicate activities.
  - if there is no synced copy, upload the ride itself as a Virtual Ride
    (TCX: power, cadence, virtual speed/distance; route rides carry their
    real map and elevation) with the title and caption.

Setup, once: create an app at strava.com/settings/api (Authorization Callback
Domain: 127.0.0.1), paste its Client ID and Secret on the /posts page, press
Connect and approve on Strava. Tokens live in strava.json beside the rides
folder (kept out of git) and refresh by themselves.
"""
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

API = "https://www.strava.com/api/v3"
AUTH = "https://www.strava.com/oauth/authorize"
TOKEN = "https://www.strava.com/oauth/token"
SCOPE = "activity:read_all,activity:write"
CALLBACK = "http://127.0.0.1:8729/strava/callback"


class StravaError(Exception):
    pass


def _http(method, url, data=None, headers=None, raw=None, timeout=30):
    """(status, parsed JSON). Separate so tests can stand in for Strava."""
    body = raw
    if data is not None and raw is None:
        body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None
    except OSError as e:
        raise StravaError(f"couldn't reach Strava ({e})")


class Strava:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.cfg = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.cfg = {}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cfg, indent=1))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    # ── setup ────────────────────────────────────────────────────────────────
    @property
    def has_app(self):
        return bool(self.cfg.get("client_id") and self.cfg.get("client_secret"))

    @property
    def connected(self):
        return bool(self.cfg.get("refresh_token"))

    def status(self):
        return {"app": self.has_app, "connected": self.connected,
                "athlete": self.cfg.get("athlete_name"), "callback_domain": "127.0.0.1"}

    def set_app(self, client_id, client_secret):
        cid, sec = str(client_id).strip(), str(client_secret).strip()
        if not cid.isdigit() or len(sec) < 20:
            raise StravaError("That doesn't look like a Strava Client ID (a number) and Client Secret (a long code)")
        self.cfg = {"client_id": cid, "client_secret": sec}
        self._save()

    def forget(self):
        self.cfg = {}
        self._save()

    def auth_url(self):
        if not self.has_app:
            raise StravaError("Add your Strava app's Client ID and Secret first")
        self.cfg["state"] = uuid.uuid4().hex
        self._save()
        return AUTH + "?" + urllib.parse.urlencode({
            "client_id": self.cfg["client_id"], "redirect_uri": CALLBACK, "response_type": "code",
            "approval_prompt": "auto", "scope": SCOPE, "state": self.cfg["state"]})

    def finish_auth(self, code, state, scope):
        if not state or state != self.cfg.get("state"):
            raise StravaError("That approval didn't come from this Mac's Connect button - try Connect again")
        if "activity:write" not in (scope or ""):
            raise StravaError("Strava needs the 'upload/edit activities' permission ticked - try Connect again")
        code_, j = _http("POST", TOKEN, {"client_id": self.cfg["client_id"], "client_secret": self.cfg["client_secret"],
                                         "code": code, "grant_type": "authorization_code"})
        if code_ != 200 or not j or "refresh_token" not in j:
            raise StravaError(f"Strava refused the connection ({(j or {}).get('message', code_)})")
        self._store_tokens(j)
        a = j.get("athlete") or {}
        self.cfg["athlete_name"] = " ".join(x for x in (a.get("firstname"), a.get("lastname")) if x)
        self.cfg.pop("state", None)
        self._save()

    def _store_tokens(self, j):
        self.cfg["access_token"], self.cfg["refresh_token"] = j["access_token"], j["refresh_token"]
        self.cfg["expires_at"] = j["expires_at"]

    def _token(self):
        if not self.connected:
            raise StravaError("Connect Strava first")
        if time.time() > self.cfg.get("expires_at", 0) - 120:
            c, j = _http("POST", TOKEN, {"client_id": self.cfg["client_id"], "client_secret": self.cfg["client_secret"],
                                         "grant_type": "refresh_token", "refresh_token": self.cfg["refresh_token"]})
            if c != 200 or not j or "access_token" not in j:
                raise StravaError("Strava wouldn't renew the connection - press Connect again")
            self._store_tokens(j)
            self._save()
        return self.cfg["access_token"]

    def _api(self, method, path, data=None, raw=None, headers=None):
        h = {"Authorization": f"Bearer {self._token()}", **(headers or {})}
        c, j = _http(method, API + path, data=data, raw=raw, headers=h)
        if c == 401:
            raise StravaError("Strava says this connection isn't allowed any more - press Connect again")
        if c >= 400:
            raise StravaError(f"Strava said {c}: {(j or {}).get('message', '')} {(j or {}).get('errors', '')}".strip())
        return j

    # ── posting ──────────────────────────────────────────────────────────────
    def find_activity(self, start, minutes):
        """The synced ride that overlaps this one (the watch starts within minutes of the bridge)."""
        t0 = int(start.timestamp())
        acts = self._api("GET", f"/athlete/activities?after={t0 - 1800}&before={t0 + 1800}&per_page=20") or []
        best, gap = None, None
        for a in acts:
            if a.get("sport_type", a.get("type")) not in ("Ride", "VirtualRide", "EBikeRide", "Workout"):
                continue
            try:
                s = dt.datetime.fromisoformat(a["start_date"].replace("Z", "+00:00")).timestamp()
            except (KeyError, ValueError):
                continue
            g = abs(s - t0)
            if g <= 15 * 60 and (gap is None or g < gap):
                best, gap = a, g
        return best

    def update(self, activity_id, title, caption):
        self._api("PUT", f"/activities/{activity_id}", data={"name": title, "description": caption})
        return f"https://www.strava.com/activities/{activity_id}"

    def upload(self, tcx, title, caption, external_id):
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in (("data_type", "tcx"), ("name", title), ("description", caption), ("trainer", "1"),
                     ("external_id", external_id)):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{external_id}.tcx\"\r\n"
                     f"Content-Type: application/xml\r\n\r\n".encode() + tcx.encode() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        j = self._api("POST", "/uploads", raw=b"".join(parts),
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        up = j["id"]
        for _ in range(30):                              # Strava processes uploads in the background
            if j.get("error"):
                raise StravaError(f"Strava couldn't take the file: {j['error']}")
            if j.get("activity_id"):
                aid = j["activity_id"]
                try:
                    self._api("PUT", f"/activities/{aid}", data={"sport_type": "VirtualRide"})
                except StravaError:
                    pass
                return f"https://www.strava.com/activities/{aid}"
            time.sleep(2)
            j = self._api("GET", f"/uploads/{up}")
        raise StravaError("Strava is still processing the upload - it'll appear in your feed shortly")

    def post(self, s, ride_csv, allow_upload=True):
        """Title + caption onto the synced ride, or upload the ride if there isn't one."""
        start = dt.datetime.fromisoformat(_first_time(ride_csv))
        act = self.find_activity(start, s["stats"]["minutes"])
        if act:
            return {"how": "updated", "url": self.update(act["id"], s["title"], s["caption"]),
                    "note": f"Updated \"{act.get('name')}\" (synced by the watch). Add the picture from the Strava app."}
        if not allow_upload:
            raise StravaError("No synced ride found at that time on Strava")
        url = self.upload(tcx_for(ride_csv, s), s["title"], s["caption"], Path(ride_csv).stem)
        return {"how": "uploaded", "url": url, "note": "Uploaded as a Virtual Ride. Add the picture from the Strava app."}


def _first_time(ride_csv):
    import csv
    with open(ride_csv, newline="") as f:
        for r in csv.DictReader(f):
            return r["time"]
    raise StravaError("That ride file is empty")


def tcx_for(ride_csv, s):
    """The ride as TCX: power, cadence, virtual speed and distance; a route ride
    gets real positions and elevation along the route at each distance."""
    import csv
    route = None
    if s.get("route"):
        try:
            import routes
            route = routes.load(s["route"]["id"])
        except (OSError, ValueError, ImportError):
            route = None
    offset = None
    pts, seen = [], set()
    with open(ride_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r["time"] in seen:
                continue
            seen.add(r["time"])
            pts.append(r)
    if not pts:
        raise StravaError("That ride file is empty")
    tz = dt.datetime.now().astimezone().tzinfo
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
           'xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">',
           '<Activities><Activity Sport="Biking">']
    t0 = dt.datetime.fromisoformat(pts[0]["time"]).replace(tzinfo=tz).astimezone(dt.timezone.utc)
    out.append(f"<Id>{t0.strftime('%Y-%m-%dT%H:%M:%SZ')}</Id>")
    out.append(f'<Lap StartTime="{t0.strftime("%Y-%m-%dT%H:%M:%SZ")}"><TotalTimeSeconds>{len(pts)}</TotalTimeSeconds>'
               f'<DistanceMeters>{float(pts[-1].get("virtual_distance_m") or 0):.1f}</DistanceMeters>'
               f'<Calories>{s["stats"]["kcal"]}</Calories><Intensity>Active</Intensity>'
               f'<TriggerMethod>Manual</TriggerMethod><Track>')
    for r in pts:
        t = dt.datetime.fromisoformat(r["time"]).replace(tzinfo=tz).astimezone(dt.timezone.utc)
        d = float(r.get("virtual_distance_m") or 0)
        pos = ""
        if route:
            if offset is None:
                offset = d
            along = d - offset
            if 0 <= along <= route.length:
                lat, lon, _ = route.position_at(along)
                pos = (f"<Position><LatitudeDegrees>{lat:.6f}</LatitudeDegrees><LongitudeDegrees>{lon:.6f}</LongitudeDegrees>"
                       f"</Position><AltitudeMeters>{route.elevation_at(along):.1f}</AltitudeMeters>")
        out.append(f"<Trackpoint><Time>{t.strftime('%Y-%m-%dT%H:%M:%SZ')}</Time>{pos}"
                   f"<DistanceMeters>{d:.1f}</DistanceMeters><Cadence>{int(float(r.get('cadence_rpm') or 0))}</Cadence>"
                   f"<Extensions><ns3:TPX><ns3:Speed>{float(r.get('virtual_speed_kmh') or 0) / 3.6:.2f}</ns3:Speed>"
                   f"<ns3:Watts>{int(float(r.get('power_w') or 0))}</ns3:Watts></ns3:TPX></Extensions></Trackpoint>")
    out.append(f"</Track><Notes>{escape(s['title'])}</Notes></Lap><Creator xsi:type=\"Device_t\" "
               "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><Name>S-Bike Hub</Name></Creator>"
               "</Activity></Activities></TrainingCenterDatabase>")
    return "\n".join(out)
