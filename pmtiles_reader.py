"""pmtiles_reader.py - read map tiles out of a PMTiles v3 file.

The downloaded maps (france.pmtiles, california.pmtiles) are single-file
archives. The control panel serves /tiles/{z}/{x}/{y} from them so the 3D map
works offline with no map server and no extra software.

Format (PMTiles spec v3): a 127-byte header, then a root directory and leaf
directories (gzip-compressed lists of varint-encoded entries), then tile data.
Tiles are addressed by a Hilbert-curve tile id.
"""
import functools
import gzip
import struct
from pathlib import Path


def zxy_to_tileid(z, x, y):
    """Tile id = number of tiles in all lower zooms + Hilbert index within zoom z."""
    acc = sum(4 ** i for i in range(z))
    n = 1 << z
    d, s = 0, n >> 1
    tx, ty = x, y
    while s > 0:
        rx = 1 if tx & s else 0
        ry = 1 if ty & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:                               # rotate the quadrant
            if rx == 1:
                tx, ty = s - 1 - tx, s - 1 - ty
            tx, ty = ty, tx
        s >>= 1
    return acc + d


def _varint(buf, pos):
    shift = result = 0
    while True:
        b = buf[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, pos
        shift += 7


def _decode_dir(raw):
    n, p = _varint(raw, 0)
    ids, last = [], 0
    for _ in range(n):
        v, p = _varint(raw, p); last += v; ids.append(last)
    runs = []
    for _ in range(n):
        v, p = _varint(raw, p); runs.append(v)
    lens = []
    for _ in range(n):
        v, p = _varint(raw, p); lens.append(v)
    offs = []
    for i in range(n):
        v, p = _varint(raw, p)
        offs.append(offs[i - 1] + lens[i - 1] if v == 0 and i > 0 else v - 1)
    return list(zip(ids, offs, lens, runs))


class PMTiles:
    def __init__(self, path):
        self.path = Path(path)
        self.f = open(self.path, "rb")
        h = self.f.read(127)
        if h[:7] != b"PMTiles" or h[7] != 3:
            raise ValueError(f"{path} is not a PMTiles v3 file")
        (self.root_off, self.root_len, self.meta_off, self.meta_len, self.leaf_off, self.leaf_len,
         self.data_off, self.data_len) = struct.unpack_from("<8Q", h, 8)
        self.internal_comp, self.tile_comp, self.tile_type, self.min_zoom, self.max_zoom = struct.unpack_from("<5B", h, 97)
        mnlon, mnlat, mxlon, mxlat = struct.unpack_from("<4i", h, 102)
        self.bounds = (mnlon / 1e7, mnlat / 1e7, mxlon / 1e7, mxlat / 1e7)

    def _read(self, off, length):
        self.f.seek(off)
        return self.f.read(length)

    @functools.lru_cache(maxsize=256)
    def _dir(self, off, length):
        raw = self._read(off, length)
        if self.internal_comp == 2:
            raw = gzip.decompress(raw)
        return _decode_dir(raw)

    def get(self, z, x, y):
        """The tile's bytes as stored (gzip-compressed vector data), or None."""
        if z < self.min_zoom or z > self.max_zoom:
            return None
        tid = zxy_to_tileid(z, x, y)
        off, length = self.root_off, self.root_len
        for _ in range(4):                        # root + at most 3 levels of leaves
            entries = self._dir(off, length)
            lo, hi = 0, len(entries) - 1
            found = None
            while lo <= hi:                        # last entry with id <= tid
                mid = (lo + hi) // 2
                if entries[mid][0] <= tid:
                    found, lo = entries[mid], mid + 1
                else:
                    hi = mid - 1
            if found is None:
                return None
            eid, eoff, elen, run = found
            if run == 0:                           # a leaf directory
                off, length = self.leaf_off + eoff, elen
                continue
            if tid < eid + run:
                return self._read(self.data_off + eoff, elen)
            return None
        return None

    def covers(self, lon, lat):
        w, s, e, n = self.bounds
        return w <= lon <= e and s <= lat <= n


class MapSet:
    """Several regional archives answering as one map."""

    def __init__(self, folder):
        self.parts, self.pending = [], []
        for p in sorted(Path(folder).glob("*.pmtiles")):
            try:
                self.parts.append(PMTiles(p))
            except (ValueError, OSError, struct.error):
                self.pending.append(p)        # still downloading: its header is written last

    def get(self, z, x, y):
        for p in self.parts:
            t = p.get(z, x, y)
            if t:
                return t
        return None

    @property
    def compressed(self):
        return bool(self.parts) and self.parts[0].tile_comp == 2
