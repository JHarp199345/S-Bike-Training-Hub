"""bests.py - personal bests: the best average power held for 5 s, 1, 5 and 20 min.

Every ride is turned into one power reading per second. A dropout of up to 5 s
is filled with the last reading; a longer gap (bike asleep, a stop) splits the
ride, so no best ever averages across a break. The best average over each
duration is the ride's best for it; the best of all rides is the record.

During a ride the Tracker keeps those averages live. The moment one beats the
record there's a callout; when the effort ends (the average drops back, or
the duration has passed again) the final number is announced and saved.

A new 20-minute best raises FTP to 95% of it - only ever up: a ride is not a
test, so an easy day never lowers it. ERG workouts are in % of FTP, so they
rescale by themselves.

bests.json (kept out of git, it's personal) holds the records, every record
ever set, and which rides have been read.
"""
import collections
import csv
import datetime as dt
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILE = HERE / "bests.json"
DURATIONS = [(5, "5 s"), (60, "1 min"), (300, "5 min"), (1200, "20 min")]
MAX_FILL = 5              # seconds of dropout filled with the last reading
FTP_FROM_20MIN = 0.95


def label(secs):
    return dict(DURATIONS)[secs]


# ── past rides ───────────────────────────────────────────────────────────────

def ride_seconds(path):
    """[(epoch second, watts), ...] one per second, gaps up to MAX_FILL filled;
    a None marks a longer break."""
    per = collections.OrderedDict()
    try:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    t = int(dt.datetime.fromisoformat(r["time"]).timestamp())
                    per.setdefault(t, []).append(float(r["power_w"] or 0))
                except (ValueError, KeyError, TypeError):
                    continue
    except OSError:
        return []
    out, prev = [], None
    for t, ws in sorted(per.items()):
        w = sum(ws) / len(ws)
        if prev is not None:
            gap = t - prev[0]
            if gap > MAX_FILL + 1:
                out.append(None)
            else:
                out.extend((s, prev[1]) for s in range(prev[0] + 1, t))
        out.append((t, w))
        prev = (t, w)
    return out


def best_efforts(seconds):
    """{secs: (watts, start epoch)} - the best average for each duration."""
    best = {}
    segments, cur = [], []
    for p in seconds:
        if p is None:
            segments.append(cur); cur = []
        else:
            cur.append(p)
    segments.append(cur)
    for seg in segments:
        if not seg:
            continue
        pre = [0.0]
        for _, w in seg:
            pre.append(pre[-1] + w)
        for secs, _ in DURATIONS:
            for i in range(secs, len(seg) + 1):
                avg = (pre[i] - pre[i - secs]) / secs
                if avg > best.get(secs, (0, 0))[0]:
                    best[secs] = (avg, seg[i - secs][0])
    return best


# ── the records file ─────────────────────────────────────────────────────────

def file_for(rides_dir):
    """The records live beside the rides they come from - so a test bridge
    working in a scratch folder can never touch the real records."""
    return Path(rides_dir).resolve().parent / "bests.json"


def load(path=None):
    path = Path(path) if path else FILE
    try:
        d = json.loads(path.read_text())
        d.setdefault("records", {}); d.setdefault("log", []); d.setdefault("scanned", [])
    except (OSError, ValueError):
        d = {"records": {}, "log": [], "scanned": []}
    d["_path"] = str(path)
    return d


def save(d):
    path = Path(d.get("_path") or FILE)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v for k, v in d.items() if k != "_path"}, indent=1))
    tmp.replace(path)


def record(d, secs, watts, ride, when):
    """Store a new record for secs if it beats the old one. Returns the old watts (or None)."""
    old = d["records"].get(str(secs))
    if old and watts <= old["watts"]:
        return False
    d["records"][str(secs)] = {"watts": round(watts), "ride": ride, "date": when}
    d["log"].append({"secs": secs, "watts": round(watts), "prev": old["watts"] if old else None,
                     "ride": ride, "date": when})
    return old["watts"] if old else None


def scan_rides(d, rides_dir, skip=None):
    """Read every past ride not read yet; returns the records they set."""
    new = []
    for p in sorted(Path(rides_dir).glob("ride_*.csv"), key=lambda q: q.name):
        if p.name.endswith("_events.csv") or p.stem in d["scanned"]:
            continue
        if skip and p.resolve() == Path(skip).resolve():
            continue
        for secs, (w, t) in sorted(best_efforts(ride_seconds(p)).items()):
            when = dt.datetime.fromtimestamp(t).isoformat(timespec="minutes")
            if record(d, secs, w, p.stem, when) is not False:
                new.append((secs, round(w), p.stem))
        d["scanned"].append(p.stem)
    return new


# ── live, during the ride ────────────────────────────────────────────────────

class Tracker:
    """Rolling averages for each duration, second by second, against the records.
    on_record(kind, secs, watts, prev) is called with kind "new" the moment a
    record falls and "final" with the effort's peak when it's over."""

    def __init__(self, d, ride_name, on_record=None):
        self.d, self.ride = d, ride_name
        self.on_record = on_record or (lambda *a: None)
        self.buf = collections.deque(maxlen=max(s for s, _ in DURATIONS))
        self.sums = {s: 0.0 for s, _ in DURATIONS}
        self.ride_best = {s: 0.0 for s, _ in DURATIONS}
        self.active = {}                     # secs -> {"peak", "prev", "since"}
        self._sec, self._acc = None, []
        self.last_t = None
        self.quiet = False

    def best(self, secs):
        r = self.d["records"].get(str(secs))
        return r["watts"] if r else 0

    def add(self, t, watts):
        """A bike reading at epoch time t."""
        sec = int(t)
        if self._sec is None:
            self._sec = sec
        if sec != self._sec:
            w = sum(self._acc) / len(self._acc) if self._acc else 0.0
            self._second(self._sec, w)
            gap = sec - self._sec
            if gap > MAX_FILL + 1:
                self._break()
            else:
                for s in range(self._sec + 1, sec):
                    self._second(s, w)
            self._sec, self._acc = sec, []
        self._acc.append(watts)

    def _break(self):
        self.finish()
        self.buf.clear()
        self.sums = {s: 0.0 for s, _ in DURATIONS}

    def _second(self, sec, w):
        for secs in self.sums:
            self.sums[secs] += w
            if len(self.buf) >= secs:
                self.sums[secs] -= self.buf[-secs]
        self.buf.append(w)
        self.last_t = sec
        for secs, _ in DURATIONS:
            if len(self.buf) < secs:
                continue
            avg = self.sums[secs] / secs
            self.ride_best[secs] = max(self.ride_best[secs], avg)
            a = self.active.get(secs)
            if a:
                if avg > a["peak"]:
                    a["peak"] = avg
                elif avg < a["peak"] * 0.97 or sec - a["since"] > secs:
                    self._final(secs)
            elif avg > self.best(secs) + 0.5:
                prev = self.best(secs) or None
                self.active[secs] = {"peak": avg, "prev": prev, "since": sec}
                if not self.quiet:
                    self.on_record("new", secs, round(avg), prev)

    def _final(self, secs):
        a = self.active.pop(secs)
        when = dt.datetime.fromtimestamp(a["since"]).isoformat(timespec="minutes")
        record(self.d, secs, a["peak"], self.ride, when)
        save(self.d)
        if not self.quiet:
            self.on_record("final", secs, round(a["peak"]), a["prev"])

    def finish(self):
        """End of the ride (or a break): settle any effort still going."""
        for secs in list(self.active):
            self._final(secs)

    def now(self, secs):
        return self.sums[secs] / secs if len(self.buf) >= secs else None

    def status(self):
        return [{"secs": s, "label": lab, "best": self.best(s),
                 "ride": round(self.ride_best[s]) if self.ride_best[s] else None,
                 "now": round(self.now(s)) if self.now(s) is not None else None,
                 "live": s in self.active}
                for s, lab in DURATIONS]
