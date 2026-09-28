"""fit.py - read Garmin/COROS .fit activity files (standard library only).

A FIT file is a header, then records: "definition" records describe a message
layout, "data" records fill it in. We keep the messages training needs:

  record  (20)  second by second: time, heart rate, power, cadence, speed,
                distance, altitude
  session (18)  the summary: sport, start, time, distance, climbing, HR
  lap     (19)  laps (kept raw)

read(path_or_bytes) -> {"sport", "sub_sport", "start", "records": [...], "session": {...}}
Timestamps become Unix seconds. Unknown messages and developer fields are skipped.
"""
import struct
from pathlib import Path

FIT_EPOCH = 631065600                          # 1989-12-31 00:00 UTC, in Unix seconds

# base type code -> (struct char, size, invalid value)
BASE = {0x00: ("B", 1, 0xFF), 0x01: ("b", 1, 0x7F), 0x02: ("B", 1, 0xFF), 0x83: ("h", 2, 0x7FFF),
        0x84: ("H", 2, 0xFFFF), 0x85: ("i", 4, 0x7FFFFFFF), 0x86: ("I", 4, 0xFFFFFFFF), 0x07: (None, 1, None),
        0x88: ("f", 4, None), 0x89: ("d", 8, None), 0x0A: ("B", 1, 0x00), 0x8B: ("H", 2, 0x0000),
        0x8C: ("I", 4, 0x00000000), 0x0D: (None, 1, None), 0x8E: ("q", 8, 0x7FFFFFFFFFFFFFFF),
        0x8F: ("Q", 8, 0xFFFFFFFFFFFFFFFF), 0x90: ("Q", 8, 0x0000000000000000)}

# message number -> {field number: (name, scale, offset)}
FIELDS = {
    20: {253: ("timestamp", 1, 0), 0: ("lat", 1, 0), 1: ("lon", 1, 0), 2: ("altitude", 5, 500), 3: ("heart_rate", 1, 0),
         4: ("cadence", 1, 0), 5: ("distance", 100, 0), 6: ("speed", 1000, 0), 7: ("power", 1, 0),
         78: ("enhanced_altitude", 5, 500), 73: ("enhanced_speed", 1000, 0), 13: ("temperature", 1, 0)},
    18: {253: ("timestamp", 1, 0), 2: ("start_time", 1, 0), 5: ("sport", 1, 0), 6: ("sub_sport", 1, 0),
         7: ("total_elapsed_time", 1000, 0), 8: ("total_timer_time", 1000, 0), 9: ("total_distance", 100, 0),
         11: ("total_calories", 1, 0), 16: ("avg_heart_rate", 1, 0), 17: ("max_heart_rate", 1, 0),
         18: ("avg_cadence", 1, 0), 20: ("avg_power", 1, 0), 22: ("total_ascent", 1, 0), 23: ("total_descent", 1, 0),
         14: ("avg_speed", 1000, 0), 124: ("enhanced_avg_speed", 1000, 0), 34: ("normalized_power", 1, 0)},
    19: {253: ("timestamp", 1, 0), 2: ("start_time", 1, 0), 7: ("total_elapsed_time", 1000, 0),
         8: ("total_timer_time", 1000, 0), 9: ("total_distance", 100, 0), 15: ("avg_heart_rate", 1, 0)},
    0: {0: ("type", 1, 0), 1: ("manufacturer", 1, 0), 4: ("time_created", 1, 0)},
}
SPORTS = {0: "generic", 1: "running", 2: "cycling", 4: "fitness_equipment", 5: "swimming", 10: "training",
          11: "walking", 17: "hiking", 13: "alpine_skiing"}


class FitError(ValueError):
    pass


def read(src):
    data = Path(src).read_bytes() if not isinstance(src, (bytes, bytearray)) else bytes(src)
    if len(data) < 12:
        raise FitError("too short to be a FIT file")
    hsize = data[0]
    if data[8:12] != b".FIT":
        raise FitError("not a FIT file")
    size = struct.unpack_from("<I", data, 4)[0]
    pos, end = hsize, min(len(data), hsize + size)
    defs, out = {}, {"records": [], "sessions": [], "laps": [], "file_id": {}}
    last_ts = None
    while pos < end:
        h = data[pos]; pos += 1
        if h & 0x80:                                          # compressed-timestamp data record
            local = (h >> 5) & 0x03
            offset = h & 0x1F
            if last_ts is not None:
                ts = (last_ts & ~0x1F) + offset
                if offset < (last_ts & 0x1F):
                    ts += 0x20
                last_ts = ts
            d = defs.get(local)
            if d is None:
                raise FitError("data before its definition")
            msg, pos = _data(data, pos, d)
            if last_ts is not None:
                msg.setdefault("timestamp", last_ts)
            _keep(out, d["num"], msg)
            continue
        local = h & 0x0F
        if h & 0x40:                                          # definition record
            dev = bool(h & 0x20)
            arch = data[pos + 1]
            endian = ">" if arch == 1 else "<"
            num = struct.unpack_from(endian + "H", data, pos + 2)[0]
            nf = data[pos + 4]
            pos += 5
            fields = []
            for _ in range(nf):
                fnum, fsize, btype = data[pos], data[pos + 1], data[pos + 2]
                fields.append((fnum, fsize, btype)); pos += 3
            devsize = 0
            if dev:
                nd = data[pos]; pos += 1
                for _ in range(nd):
                    devsize += data[pos + 1]; pos += 3
            defs[local] = {"num": num, "endian": endian, "fields": fields, "devsize": devsize}
        else:                                                 # normal data record
            d = defs.get(local)
            if d is None:
                raise FitError("data before its definition")
            msg, pos = _data(data, pos, d)
            if "timestamp" in msg:
                last_ts = msg["timestamp"]
            _keep(out, d["num"], msg)
    sess = out["sessions"][-1] if out["sessions"] else {}
    for key in ("timestamp", "start_time"):
        if key in sess:
            sess[key] += FIT_EPOCH
    for r in out["records"]:
        if "timestamp" in r:
            r["timestamp"] += FIT_EPOCH
        if "enhanced_altitude" in r and "altitude" not in r:
            r["altitude"] = r["enhanced_altitude"]
        if "enhanced_speed" in r and "speed" not in r:
            r["speed"] = r["enhanced_speed"]
    start = sess.get("start_time") or (out["records"][0]["timestamp"] if out["records"] and "timestamp" in out["records"][0] else None)
    return {"sport": SPORTS.get(sess.get("sport"), str(sess.get("sport"))), "sport_code": sess.get("sport"),
            "sub_sport": sess.get("sub_sport"), "start": start, "session": sess,
            "records": out["records"], "laps": out["laps"]}


def _data(data, pos, d):
    names = FIELDS.get(d["num"])
    msg = {}
    for fnum, fsize, btype in d["fields"]:
        raw = data[pos:pos + fsize]; pos += fsize
        if names is None or fnum not in names:
            continue
        ch, bsize, invalid = BASE.get(btype, BASE.get(btype & 0x1F | (btype & 0x80), (None, 1, None)))
        if ch is None or fsize != bsize:
            continue                                          # arrays and strings aren't needed here
        v = struct.unpack(d["endian"] + ch, raw)[0]
        if invalid is not None and v == invalid:
            continue
        name, scale, offset = names[fnum]
        msg[name] = v / scale - offset if (scale != 1 or offset) else v
    pos += d["devsize"]
    return msg, pos


def _keep(out, num, msg):
    if num == 20:
        out["records"].append(msg)
    elif num == 18:
        out["sessions"].append(msg)
    elif num == 19:
        out["laps"].append(msg)
    elif num == 0:
        out["file_id"] = msg
