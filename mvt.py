"""mvt.py - just enough of the Mapbox Vector Tile format to read named points.

The place search reads town and peak names straight out of the downloaded map
tiles, so it needs no extra download and no extra library. A tile is a
protobuf: layers, each with features, keys, values. Only what the search needs
is decoded: a feature's tags and its first point.
"""
import struct


def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s
        if c < 0x80:
            return r, i
        s += 7


def _fields(b):
    """(field number, wire type, value) for each field of one message."""
    i, n = 0, len(b)
    while i < n:
        key, i = _varint(b, i)
        f, w = key >> 3, key & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 2:
            ln, i = _varint(b, i)
            v = b[i:i + ln]; i += ln
        elif w == 1:
            v = b[i:i + 8]; i += 8
        elif w == 5:
            v = b[i:i + 4]; i += 4
        else:
            raise ValueError(f"wire type {w}")
        yield f, w, v


def _value(b):
    for f, w, v in _fields(b):
        if f == 1:
            return v.decode("utf-8", "replace")
        if f == 2:
            return struct.unpack("<f", v)[0]
        if f == 3:
            return struct.unpack("<d", v)[0]
        if f in (4, 5):
            return v
        if f == 6:
            return (v >> 1) ^ -(v & 1)
        if f == 7:
            return bool(v)
    return None


def _packed(b):
    out, i = [], 0
    while i < len(b):
        v, i = _varint(b, i); out.append(v)
    return out


def points(tile, layers):
    """{layer: [(props, (x, y, extent)), ...]} for the point features of the named layers.
    x, y are tile coordinates from 0 to extent."""
    out = {}
    for f, w, lb in _fields(tile):
        if f != 3:
            continue
        name, keys, vals, feats, extent = None, [], [], [], 4096
        for lf, lw, lv in _fields(lb):
            if lf == 1:
                name = lv.decode()
                if name not in layers:
                    break
            elif lf == 2:
                feats.append(lv)
            elif lf == 3:
                keys.append(lv.decode())
            elif lf == 4:
                vals.append(_value(lv))
            elif lf == 5:
                extent = lv
        if name not in layers:
            continue
        got = out.setdefault(name, [])
        for fb in feats:
            tags, geom, gtype = [], [], 0
            for ff, fw, fv in _fields(fb):
                if ff == 2:
                    tags = _packed(fv)
                elif ff == 3:
                    gtype = fv
                elif ff == 4:
                    geom = _packed(fv)
            if gtype != 1 or len(geom) < 3:                  # points only
                continue
            x = (geom[1] >> 1) ^ -(geom[1] & 1)
            y = (geom[2] >> 1) ^ -(geom[2] & 1)
            props = {keys[tags[k]]: vals[tags[k + 1]] for k in range(0, len(tags) - 1, 2)}
            got.append((props, (x, y, extent)))
    return out
