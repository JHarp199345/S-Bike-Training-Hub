"""fitwrite.py - write small FIT activity files (runs and pool swims) for the demo athlete.

Just the messages the hub reads (fit.py): file_id, record, length, lap, session. Little-endian,
no developer fields, CRC left zero (the hub doesn't check it; real devices always write one).
"""
import struct

FIT_EPOCH = 631065600
SPORT = {"run": 1, "swim": 5, "bike": 2, "gym": 10}

# (field number, size, base type, scale, offset)
U8, U16, U32, S8 = (1, 0x02), (2, 0x84), (4, 0x86), (1, 0x01)
MSG = {
    "file_id": (0, [("type", 0, U8), ("manufacturer", 1, U16), ("time_created", 4, U32)]),
    "record": (20, [("timestamp", 253, U32), ("heart_rate", 3, U8), ("cadence", 4, U8), ("distance", 5, U32),
                    ("speed", 6, U16), ("power", 7, U16)]),
    "length": (101, [("timestamp", 253, U32), ("message_index", 254, U16), ("start_time", 2, U32),
                     ("total_elapsed_time", 3, U32), ("total_timer_time", 4, U32), ("total_strokes", 5, U16),
                     ("avg_speed", 6, U16), ("swim_stroke", 7, U8), ("avg_swimming_cadence", 9, U8), ("length_type", 12, U8)]),
    "lap": (19, [("timestamp", 253, U32), ("start_time", 2, U32), ("total_elapsed_time", 7, U32),
                 ("total_timer_time", 8, U32), ("total_distance", 9, U32), ("avg_heart_rate", 15, U8)]),
    "session": (18, [("timestamp", 253, U32), ("start_time", 2, U32), ("sport", 5, U8), ("sub_sport", 6, U8),
                     ("total_elapsed_time", 7, U32), ("total_timer_time", 8, U32), ("total_distance", 9, U32),
                     ("avg_heart_rate", 16, U8), ("max_heart_rate", 17, U8), ("avg_cadence", 18, U8),
                     ("total_strokes", 41, U16), ("pool_length", 44, U16), ("pool_length_unit", 46, U8)]),
}
SCALE = {"distance": 100, "speed": 1000, "avg_speed": 1000, "total_elapsed_time": 1000, "total_timer_time": 1000,
         "total_distance": 100, "pool_length": 100}
INVALID = {0x02: 0xFF, 0x84: 0xFFFF, 0x86: 0xFFFFFFFF, 0x01: 0x7F}
FMT = {0x02: "B", 0x84: "H", 0x86: "I", 0x01: "b"}


class Writer:
    def __init__(self):
        self.body = bytearray()
        self.local = {}

    def add(self, kind, **values):
        num, fields = MSG[kind]
        if kind not in self.local:
            lid = len(self.local)
            self.local[kind] = lid
            self.body += bytes([0x40 | lid, 0, 0]) + struct.pack("<H", num) + bytes([len(fields)])
            for _, fnum, (size, btype) in fields:
                self.body += bytes([fnum, size, btype])
        self.body += bytes([self.local[kind]])
        for name, _, (size, btype) in fields:
            v = values.get(name)
            if v is None:
                v = INVALID[btype]
            else:
                if name in ("timestamp", "start_time", "time_created"):
                    v = int(v - FIT_EPOCH)
                v = int(round(v * SCALE.get(name, 1)))
            self.body += struct.pack("<" + FMT[btype], v)

    def bytes(self):
        header = struct.pack("<BBHI4sH", 14, 0x20, 2132, len(self.body), b".FIT", 0)
        return header + bytes(self.body) + b"\x00\x00"


def run(path, start, seconds, hr, pace_s_per_km, cadence=166, hr_drift=8):
    """A steady run: per-second records with heart rate drifting up, distance and cadence."""
    w = Writer()
    w.add("file_id", type=4, manufacturer=294, time_created=start)
    speed = 1000 / pace_s_per_km
    dist = 0.0
    for i in range(int(seconds)):
        dist += speed
        h = hr - 12 + min(12, i / 30) + hr_drift * i / seconds
        w.add("record", timestamp=start + i, heart_rate=round(h), cadence=round(cadence / 2), distance=dist, speed=speed)
    w.add("lap", timestamp=start + seconds, start_time=start, total_elapsed_time=seconds, total_timer_time=seconds,
          total_distance=dist, avg_heart_rate=round(hr))
    w.add("session", timestamp=start + seconds, start_time=start, sport=1, sub_sport=0, total_elapsed_time=seconds,
          total_timer_time=seconds, total_distance=dist, avg_heart_rate=round(hr), max_heart_rate=round(hr + 10),
          avg_cadence=round(cadence / 2))
    open(path, "wb").write(w.bytes())
    return dist


def swim(path, start, lengths, pool_m=25, sec_per_length=30, rest_every=4, rest_s=20, hr=135, strokes=18):
    """Pool lengths of freestyle with a rest at the wall every few lengths."""
    w = Writer()
    w.add("file_id", type=4, manufacturer=294, time_created=start)
    t, idx, active = start, 0, 0
    for n in range(lengths):
        dur = sec_per_length * (1.0 + 0.04 * ((n * 7) % 5 - 2) / 2)
        w.add("length", timestamp=t + dur, message_index=idx, start_time=t, total_elapsed_time=dur, total_timer_time=dur,
              total_strokes=strokes, avg_speed=pool_m / dur, swim_stroke=0, avg_swimming_cadence=round(strokes / dur * 60),
              length_type=1)
        idx += 1; t += dur; active += dur
        w.add("record", timestamp=t, heart_rate=hr, distance=(n + 1) * pool_m, speed=pool_m / dur)
        if rest_every and (n + 1) % rest_every == 0 and n + 1 < lengths:
            w.add("length", timestamp=t + rest_s, message_index=idx, start_time=t, total_elapsed_time=rest_s,
                  total_timer_time=rest_s, total_strokes=0, length_type=0)
            idx += 1; t += rest_s
    total = t - start
    w.add("lap", timestamp=t, start_time=start, total_elapsed_time=total, total_timer_time=total,
          total_distance=lengths * pool_m, avg_heart_rate=hr)
    w.add("session", timestamp=t, start_time=start, sport=5, sub_sport=17, total_elapsed_time=total, total_timer_time=total,
          total_distance=lengths * pool_m, avg_heart_rate=hr, max_heart_rate=hr + 15, avg_cadence=round(strokes / sec_per_length * 60),
          total_strokes=lengths * strokes, pool_length=pool_m, pool_length_unit=0)
    open(path, "wb").write(w.bytes())
    return total


def bike(path, start, steps, ftp, rest_hr=58, fitness=0.0, cadence=86):
    """A ride from power steps [(seconds, watts)]: per-second power, cadence and heart rate that follows the effort
    (a few beats lower as fitness improves), speed from power on the flat."""
    w = Writer()
    w.add("file_id", type=4, manufacturer=294, time_created=start)
    t, dist, hr = 0, 0.0, rest_hr + 30
    for secs, watts in steps:
        for _ in range(int(secs)):
            target = min(188, rest_hr + 40 + 95 * watts / ftp - fitness)
            hr += (target - hr) / 25
            v = (max(watts, 1) / 0.42) ** (1 / 3) * 0.95      # m/s, roughly, on the flat
            dist += v
            w.add("record", timestamp=start + t, heart_rate=round(hr), cadence=cadence, distance=dist, speed=v, power=round(watts))
            t += 1
    w.add("lap", timestamp=start + t, start_time=start, total_elapsed_time=t, total_timer_time=t, total_distance=dist)
    w.add("session", timestamp=start + t, start_time=start, sport=2, sub_sport=6, total_elapsed_time=t, total_timer_time=t,
          total_distance=dist, avg_cadence=cadence)
    open(path, "wb").write(w.bytes())
    return t
