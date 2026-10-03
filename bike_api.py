"""bike_api.py - /api/bike/*: the welcome page's bike step and the assistant's tools.

  GET  /api/bike/status      the active bike, any open request, and a sentence for the page
  POST /api/bike/scan        look for bikes; each comes back known, standard or unrecognized
  POST /api/bike/choose      {address}: a known or standard bike becomes the bike (no AI needed)
  POST /api/bike/request     {address, consent: true}: listen to an unrecognized bike and queue
                             the request for the athlete's assistant ("get my bike working")
  GET  /api/bike/request     the request, as the assistant reads it (bikes.brief)
  POST /api/bike/capture     {seconds, label}: record more packets while the athlete pedals
  POST /api/bike/propose     {profile, note}: the assistant's profile, checked and decoded
  POST /api/bike/check       run the guided check with the latest profile (athlete pedaling)
  POST /api/bike/feel        {felt: harder|no_change|unsure}: what the athlete felt
  POST /api/bike/activate    {share}: make it the bike (check passed + felt harder)
  POST /api/bike/cancel      close the request
"""
import asyncio
import json
from pathlib import Path

import bikes
import bike_ble
import bike_check

HERE = Path(__file__).resolve().parent
_last_scan = {}            # address -> identify() entry, from the most recent scan
_busy = {"what": None}     # one radio job at a time: scan, inspect, capture or check


def _base(bridge):
    return Path(bridge.csv_path).parent.parent if getattr(bridge, "csv_path", None) else HERE


def _ok(obj, code=200):
    return code, "application/json", json.dumps(obj, ensure_ascii=False).encode(), {}


def _err(msg, code=400):
    return _ok({"error": msg}, code)


async def _radio(what, coro):
    if _busy["what"]:
        raise bikes.BadProfile(f"The hub is busy with the bike ({_busy['what']}) - try again in a moment.")
    _busy["what"] = what
    try:
        return await coro
    finally:
        _busy["what"] = None


def _event(bridge, msg):
    try:
        bridge.event(msg)
    except Exception:
        pass


async def handle(bridge, method, p, body):
    base = _base(bridge)
    try:
        req = json.loads(body or b"{}") if method == b"POST" else {}
        if not isinstance(req, dict):
            raise ValueError("a JSON object please")
    except ValueError:
        return _err("That request wasn't valid JSON.")
    t = bike_ble.transport()
    try:
        if p == "/api/bike/status":
            st = bikes.setup_status(base)
            st["busy"] = _busy["what"]
            st["sim"] = isinstance(t, bike_ble.Sim)
            return _ok(st)
        if method != b"POST" and p != "/api/bike/request":
            return _err("Use POST.", 405)
        if p == "/api/bike/scan":
            found = await _radio("scanning", t.scan(float(req.get("seconds", 6))))
            out = bikes.identify(found, base)
            _last_scan.clear()
            _last_scan.update({o["device"]["address"]: o for o in out})
            likely = next((o for o in out if o["status"] in ("known", "standard")), None)
            return _ok({"found": out, "likely": likely,
                        "message": (f"Found your {likely['profile']['name']}." if likely and likely["status"] == "known"
                                    else f"Found {likely['device']['name']} - it speaks the standard bike protocol."
                                    if likely else "No bike the hub already knows. If yours is listed, pick it." if out
                                    else "Nothing found. Pedal to wake the bike, and disconnect it from any phone "
                                         "or watch app, then scan again.")})
        if p == "/api/bike/choose":
            found = _last_scan.get(req.get("address"))
            if not found:
                return _err("Scan first, then choose the bike from the list.")
            prof = bikes.choose(base, found)
            _event(bridge, f"Bike set up: {prof['name']} ({found['status']})")
            return _ok({"active": prof, "message": f"Done - the hub will connect to the {prof['name']}."})
        if p == "/api/bike/request" and method == b"POST":
            found = _last_scan.get(req.get("address"))
            if not found:
                return _err("Scan first, then choose the bike from the list.")
            if req.get("consent") is not True:
                return _err("The athlete's OK is needed before asking an assistant for help.")
            insp = await _radio("listening to the bike", bike_ble.inspect(t, found["device"], float(req.get("seconds", 8))))
            r = bikes.open_request(base, found["device"], insp, True)
            _event(bridge, f"Bike setup: request {r['id']} queued for the assistant")
            return _ok({"request": r, "say": "get my bike working",
                        "message": "Open your AI assistant and type: get my bike working"})
        if p == "/api/bike/request":
            return _ok(bikes.brief(bikes.load_request(base)))
        r = bikes.load_request(base)
        if p == "/api/bike/cancel":
            return _ok({"request": bikes.cancel(base)})
        if not r or r["status"] in ("done", "cancelled"):
            return _err("No bike setup request is open. Start one from the welcome page: Your bike → Scan.", 404)
        dev = r["device"]
        if p == "/api/bike/capture":
            secs = max(3.0, min(30.0, float(req.get("seconds", 10))))
            prev = r["status"]
            r["status"] = "capturing"
            r["capturing"] = req.get("label", "")[:80]
            bikes.save_request(base, r)
            try:
                cap = await _radio("recording", bike_ble.capture(t, dev, secs, req.get("label") or f"capture {len(r['captures']) + 1}"))
            finally:
                r = bikes.load_request(base)
                r["status"], r["capturing"] = prev, None
            r["captures"] = (r["captures"] + [cap])[-6:]
            bikes.save_request(base, r)
            return _ok({"capture": cap})
        if p == "/api/bike/propose":
            if not isinstance(req.get("profile"), dict):
                return _err("profile: the profile object (see profile_format in get_bike_setup_request)")
            return _ok(bikes.propose(base, req["profile"], str(req.get("note", ""))))
        if p == "/api/bike/check":
            if req.get("athlete_ready") is not True:
                return _err("Ask the athlete first: are they pedaling steadily and ready for the check? "
                            "Then call again with athlete_ready true.")
            prof = bikes.latest_profile(r)
            if not prof:
                return _err("Propose a profile first.")
            r["status"] = "checking"
            r["check_progress"] = []
            bikes.save_request(base, r)

            def progress(msg):
                cur = bikes.load_request(base)
                if cur:
                    cur["check_progress"] = (cur.get("check_progress") or [])[-8:] + [msg]
                    bikes.save_request(base, cur)
            try:
                res = await _radio("guided check", bike_check.run(dev, prof, t, progress=progress))
            finally:
                r = bikes.load_request(base)
            r["checks"] = (r["checks"] + [res])[-5:]
            r["status"] = "checked"
            r["feel"] = None
            bikes.save_request(base, r)
            nxt = ("Ask the athlete: did the pedals get harder in the middle of the check, then easier again? "
                   "Record it with record_bike_feel." if res.get("resistance_tested") and res["passed"] else
                   "Passed (no resistance control to test). You can activate it." if res["passed"] else
                   "It didn't pass - see problems. Adjust the profile (or capture more data) and propose again.")
            return _ok({"check": res, "next": nxt})
        if p == "/api/bike/feel":
            return _ok({"request": bikes.record_feel(base, req.get("felt"), str(req.get("note", "")))})
        if p == "/api/bike/activate":
            out = bikes.activate(base, bool(req.get("share")))
            _event(bridge, f"Bike set up by the assistant: {out['activated']['name']}")
            return _ok(out)
        return _err("Unknown bike request.", 404)
    except bikes.BadProfile as e:
        return _err(str(e), 422)
    except bike_ble.NoRadio as e:
        return _err(str(e), 503)
    except (ValueError, TypeError) as e:
        return _err(f"That request didn't make sense: {e}")
