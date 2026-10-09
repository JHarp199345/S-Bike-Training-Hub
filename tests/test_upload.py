"""Adding watch files from the Coach page: .fit and .tcx accepted, anything else refused, duplicates noticed."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools" / "demo"))
import asyncio, datetime as dt, json, tempfile, threading, types, urllib.request, urllib.error
import panel, fitwrite

tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / "rides").mkdir()


class FakeBridge:
    profile = {"ftp": 180, "ftp_source": "test"}
    csv_path = tmp / "rides" / "ride_x.csv"
    workouts = []
    args = types.SimpleNamespace(no_bike=True)
    def event(self, m): pass


loop = asyncio.new_event_loop()
loop.run_until_complete(panel.serve(FakeBridge(), 18791, lan=False))
threading.Thread(target=loop.run_forever, daemon=True).start()


def up(name, data):
    req = urllib.request.Request(f"http://127.0.0.1:18791/api/activities/upload?name={name}", method="POST", data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


fitwrite.run(tmp / "r.fit", dt.datetime(2026, 9, 1, 7).timestamp(), 600, 145, 400)
fit = (tmp / "r.fit").read_bytes()
ok = True
for label, cond in [
    ("a .fit run is added to activities/", up("morning_run.fit", fit) == (200, {"imported": ["morning_run.fit"], "already": []}) and (tmp / "activities" / "morning_run.fit").exists()),
    ("the same file again is noticed, not duplicated", up("morning_run.fit", fit)[1].get("already") == ["morning_run.fit"]),
    ("an empty TCX without a workout is refused", up("ride.tcx", b'<?xml version="1.0"?><TrainingCenterDatabase xmlns="x"></TrainingCenterDatabase>')[0] == 400),
    ("a renamed photo is refused", up("fake.fit", b"\x89PNG" + b"0" * 40)[0] == 400),
    ("other file types are refused", up("notes.txt", b"hello")[0] == 400),
    ("paths can't escape the folder", up("..%2F..%2Fcoach.fit", fit)[1].get("imported") in (["coach.fit"], [], None) and not (tmp / "coach.fit").exists()),
]:
    ok &= bool(cond); print(("PASS " if cond else "FAIL ") + label)
html = (pathlib.Path(__file__).resolve().parent.parent / "web" / "coach.html").read_text()
c = 'id="importfiles"' in html and "/api/activities/upload" in html
ok &= c; print(("PASS " if c else "FAIL ") + "the Coach page has the Add watch files control")
loop.call_soon_threadsafe(loop.stop)
sys.exit(0 if ok else 1)
