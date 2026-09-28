"""card.py - the ride's infographic: a 1080x1350 PNG (Strava/Instagram portrait).

Drawn with macOS's own graphics (AppKit via PyObjC, already installed for the
menu icon), so real fonts and colour emoji, and nothing to download.

  header      date, title, route shape when there was a route
  big numbers time, distance, climbing / watts, calories, load
  highlights  the story's best moments, records in gold
  chart       power second by second in zone colours, with the elevation behind
  zones       time in each power zone as one bar
  footer      the challenge to friends, streak and fitness
"""
import AppKit
from AppKit import (NSBitmapImageRep, NSGraphicsContext, NSColor, NSBezierPath, NSFont,
                    NSAttributedString, NSMakeRect, NSPNGFileType, NSMutableParagraphStyle)

W, H = 1080, 1350
BG, PANEL, TEXT, DIM, GOLD = "#0b0f14", "#151b23", "#f3f4f6", "#8b98a8", "#eab308"
ZONE_COLOURS = ["#6b7280", "#3b82f6", "#22c55e", "#eab308", "#f97316", "#ef4444"]


def _c(hexs, a=1.0):
    h = hexs.lstrip("#")
    return NSColor.colorWithSRGBRed_green_blue_alpha_(int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


def _font(size, weight="bold"):
    names = {"heavy": "AvenirNext-Heavy", "bold": "AvenirNext-Bold", "demi": "AvenirNext-DemiBold",
             "medium": "AvenirNext-Medium", "regular": "AvenirNext-Regular"}
    return NSFont.fontWithName_size_(names[weight], size) or NSFont.boldSystemFontOfSize_(size)


class Canvas:
    """Top-left coordinates, like a web page."""

    def __init__(self):
        self.rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, W, H, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0)
        self.ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(self.rep)

    def __enter__(self):
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(self.ctx)
        return self

    def __exit__(self, *a):
        NSGraphicsContext.restoreGraphicsState()

    def rect(self, x, y, w, h, colour, radius=0, alpha=1.0):
        _c(colour, alpha).set()
        r = NSMakeRect(x, H - y - h, w, h)
        (NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(r, radius, radius) if radius else NSBezierPath.bezierPathWithRect_(r)).fill()

    def text(self, x, y, s, size, colour=TEXT, weight="bold", width=None, align="left"):
        """Draw text with its top at y; returns its height."""
        para = NSMutableParagraphStyle.alloc().init()
        para.setAlignment_({"left": 0, "center": 1, "right": 2}[align])
        para.setLineBreakMode_(0)
        attrs = {AppKit.NSFontAttributeName: _font(size, weight), AppKit.NSForegroundColorAttributeName: _c(colour),
                 AppKit.NSParagraphStyleAttributeName: para}
        a = NSAttributedString.alloc().initWithString_attributes_(s, attrs)
        width = width or (W - x - 60)
        box = a.boundingRectWithSize_options_((width, 2000), 1 << 0)   # uses line fragment origin
        h = box.size.height
        a.drawWithRect_options_(NSMakeRect(x, H - y - h, width, h), 1 << 0)
        return h

    def text_width(self, s, size, weight="bold"):
        a = NSAttributedString.alloc().initWithString_attributes_(s, {AppKit.NSFontAttributeName: _font(size, weight)})
        return a.size().width

    def poly(self, pts, colour, width=3.0, fill_to=None, alpha=1.0):
        if len(pts) < 2:
            return
        p = NSBezierPath.bezierPath()
        p.moveToPoint_((pts[0][0], H - pts[0][1]))
        for x, y in pts[1:]:
            p.lineToPoint_((x, H - y))
        if fill_to is not None:
            p.lineToPoint_((pts[-1][0], H - fill_to)); p.lineToPoint_((pts[0][0], H - fill_to)); p.closePath()
            _c(colour, alpha).set(); p.fill()
        else:
            p.setLineWidth_(width); p.setLineCapStyle_(1); p.setLineJoinStyle_(1)
            _c(colour, alpha).set(); p.stroke()

    def png(self, path):
        data = self.rep.representationUsingType_properties_(NSPNGFileType, {})
        data.writeToFile_atomically_(str(path), True)


def _zone_colour(w, ftp):
    f = w / (ftp or 180)
    for top, col in zip((0.55, 0.75, 0.90, 1.05, 1.20, 99), ZONE_COLOURS):
        if f < top:
            return col
    return ZONE_COLOURS[-1]


def render(s, out_path):
    st = s["stats"]
    with Canvas() as c:
        c.rect(0, 0, W, H, BG)
        c.rect(0, 0, W, 10, GOLD if s["pbs"] else "#2563eb")
        # header
        c.text(60, 46, f"{st['date'].upper()} · {st['start']}", 24, DIM, "demi")
        right = 60
        if s.get("route") and s["route"].get("points"):
            right = _route_shape(c, s["route"]["points"], W - 60 - 220, 36, 220, 148)
        c.text(60, 82, s["title"], 60, TEXT, "heavy", width=W - 120 - (240 if right != 60 else 0))
        # big numbers
        y = 200
        big = [(st["time"], "TIME"), (f"{st['km']} km", "VIRTUAL DISTANCE"), (f"{st['climb_m']} m", "CLIMBING"),
               (f"{st['avg_w']} W", f"AVG · {st['np_w']} W NP"), (f"{st['kcal']}", "KCAL"), (f"{st['load']}", "TRAINING LOAD")]
        cw = (W - 120 - 2 * 20) / 3
        for i, (v, lab) in enumerate(big):
            x = 60 + (i % 3) * (cw + 20)
            yy = y + (i // 3) * 150
            c.rect(x, yy, cw, 132, PANEL, 22)
            c.text(x, yy + 18, v, 52, TEXT, "heavy", width=cw, align="center")
            c.text(x, yy + 90, lab, 19, DIM, "demi", width=cw, align="center")
        # highlights
        y = 520
        for h in s["highlights"][:4]:
            gold = h["icon"] == "🏆"
            c.rect(60, y, W - 120, 76, "#3a2a06" if gold else PANEL, 20)
            if gold:
                c.rect(60, y, 8, 76, GOLD, 4)
            c.text(88, y + 14, h["icon"], 38, TEXT, "bold", width=60)
            c.text(150, y + 18, h["text"], 32, "#fde68a" if gold else TEXT, "bold", width=560)
            if h["detail"]:
                left = 150 + min(560, c.text_width(h["text"], 32)) + 30     # whatever the headline leaves
                size = 24 if c.text_width(h["detail"], 24, "demi") <= W - 84 - left else 20
                c.text(left, y + (24 if size == 24 else 27), h["detail"], size, GOLD if gold else DIM, "demi",
                       width=W - 84 - left, align="right")
            y += 88
        # chart: power in zone colours, elevation behind
        y = max(y + 10, 880)
        ch = 200
        c.rect(60, y, W - 120, ch + 40, PANEL, 22)
        _power_chart(c, s, 84, y + 20, W - 168, ch)
        # zones bar
        y += ch + 60
        total = sum(z["seconds"] for z in s["zones"]) or 1
        x = 60
        for z in s["zones"]:
            w = (W - 120) * z["seconds"] / total
            if w >= 1:
                c.rect(x, y, w, 26, z["color"])
                if w > 70:
                    c.text(x, y + 30, f"{z['zone']} {round(100 * z['seconds'] / total)}%", 18, DIM, "demi", width=w, align="center")
            x += w
        # footer
        y += 70
        c.text(60, y, s["challenge"], 30, GOLD if s["pbs"] else "#93c5fd", "bold")
        bits = []
        if s["streak"] >= 2:
            bits.append(f"{s['streak']}-day streak")
        if s.get("fitness"):
            bits.append(f"fitness {s['fitness']['fitness']}")
        bits.append(f"FTP {st['ftp']} W")
        c.text(60, H - 58, " · ".join(bits), 22, DIM, "demi")
        c.text(60, H - 58, "S-BIKE HUB", 22, DIM, "heavy", align="right", width=W - 120)
        c.png(out_path)
    return out_path


def _route_shape(c, pts, x, y, w, h):
    """The route drawn as a line in a box (north up)."""
    import math
    lat0 = sum(p[0] for p in pts) / len(pts)
    xs = [p[1] * math.cos(math.radians(lat0)) for p in pts]
    ys = [p[0] for p in pts]
    sx, sy = max(xs) - min(xs) or 1e-6, max(ys) - min(ys) or 1e-6
    k = min((w - 30) / sx, (h - 30) / sy)
    ox, oy = x + (w - sx * k) / 2, y + (h - sy * k) / 2
    line = [(ox + (a - min(xs)) * k, oy + (max(ys) - b) * k) for a, b in zip(xs, ys)]
    c.rect(x, y, w, h, PANEL, 22)
    c.poly(line, "#0b0f14", 12)
    c.poly(line, "#f97316", 6)
    c.rect(line[0][0] - 9, line[0][1] - 9, 18, 18, "#22c55e", 9)
    c.rect(line[-1][0] - 9, line[-1][1] - 9, 18, 18, "#ef4444", 9)
    return x


def _power_chart(c, s, x, y, w, h):
    power = [p for p in s["power"] if p is not None]
    ele = s.get("elevation") or []
    if ele and len(ele) > 2:
        es = [e for _, e in ele]
        lo, hi = min(es), max(es)
        if hi - lo >= 3:
            pts = [(x + i / (len(es) - 1) * w, y + h - (e - lo) / (hi - lo) * h * 0.55) for i, e in enumerate(es)]
            c.poly(pts, "#334155", fill_to=y + h, alpha=0.7)
    if not power:
        return
    top = max(max(power), s["stats"]["ftp"] * 1.2)
    bw = w / len(power)
    for i, p in enumerate(power):
        ph = p / top * h
        c.rect(x + i * bw, y + h - ph, max(bw, 1.2), ph, _zone_colour(p, s["stats"]["ftp"]))
    fy = y + h - s["stats"]["ftp"] / top * h
    for k in range(0, int(w), 18):
        c.rect(x + k, fy, 9, 2, GOLD, alpha=0.8)
    c.text(x + w - 60, fy - 26, "FTP", 18, GOLD, "bold", width=60, align="right")
