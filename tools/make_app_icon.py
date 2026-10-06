"""Draws the SBT hex logo as SVG: gold bevelled hexagon, faceted colour mosaic, SBT, and the name.

Usage: python3 tools/make_app_icon.py web/icons   (then render the PNG sizes from the SVGs in a browser)
"""
import math, random, sys
from pathlib import Path

PALETTE = ["#2e333b", "#2b3037", "#31363e", "#292d34", "#30353d"]          # charcoal slate, barely faceted

def hexpts(cx, cy, r):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(0, 360, 60)]

def poly(pts):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

def shade(hexcol, f):
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    c = lambda v: max(0, min(255, int(v * f)))
    return f"#{c(r):02x}{c(g):02x}{c(b):02x}"

def mosaic(rng, cx, cy, r):
    s, h = 92, 92 * math.sqrt(3) / 2
    out = []
    rows = int(2 * r / h) + 4
    for j in range(-2, rows):
        y0 = cy - r - h + j * h
        off = (j % 2) * s / 2
        for i in range(-2, int(2 * r / s) + 4):
            x0 = cx - r - s + i * s + off
            for tri in ([(x0, y0), (x0 + s, y0), (x0 + s / 2, y0 + h)], [(x0 + s / 2, y0 + h), (x0 + s, y0), (x0 + 1.5 * s, y0 + h)]):
                col = shade(rng.choice(PALETTE), rng.uniform(0.92, 1.08))
                out.append(f'<polygon points="{poly(tri)}" fill="{col}" stroke="{col}" stroke-width="1.2"/>')
    return "\n".join(out)

def mountains(words, scale):
    """The Hub's two peaks (the 40x32 mark from the app header) standing behind SBT, grounded on the gold rule."""
    k = (15.0 if words else 17.0) * scale
    base = (600 if words else 700) * scale + 512 * (1 - scale)
    x0 = 512 - 20.5 * k
    tx = lambda x: x0 + x * k
    ty = lambda y: base - (30 - y) * k
    back = [(1, 30), (17, 3), (27, 20), (32, 12), (40, 30)]
    front = [(8, 30), (21, 11), (33, 30)]
    pts = lambda ps: " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in ps)
    return f'''<g clip-path="url(#inside)" filter="url(#lift)">
    <polygon points="{pts(back)}" fill="url(#peak1)" stroke="#0c5f66" stroke-opacity=".6" stroke-width="{3 * scale:.1f}" stroke-linejoin="round"/>
    <polygon points="{pts(front)}" fill="url(#peak2)" stroke="#123f7a" stroke-opacity=".6" stroke-width="{3 * scale:.1f}" stroke-linejoin="round"/>
    <polygon points="{tx(17):.1f},{ty(3):.1f} {tx(14.2):.1f},{ty(7.7):.1f} {tx(17):.1f},{ty(6.6):.1f} {tx(19.3):.1f},{ty(6.9):.1f}" fill="#eafcff" fill-opacity=".85"/>
  </g>'''


def logo(words=True, size=1024, scale=1.0, bg=True, seed=29):
    rng = random.Random(seed)
    cx = cy = 512
    R = 455 * scale
    words_svg = ""
    sbt_y = 640 if not words else 552
    sbt_size = 300 if not words else 236
    if words:
        k = scale
        words_svg = f'''
  <g font-family="'Avenir Next','Avenir','Futura','Helvetica Neue',Arial,sans-serif" text-anchor="middle" filter="url(#lift)">
    <line x1="{512 - 330 * k:.0f}" y1="{600 * k + 512 * (1 - k):.0f}" x2="{512 + 330 * k:.0f}" y2="{600 * k + 512 * (1 - k):.0f}" stroke="url(#gold)" stroke-width="{5 * k:.1f}" stroke-linecap="round"/>
    <text x="512" y="{664 * k + 512 * (1 - k):.0f}" font-size="{50 * k:.1f}" font-weight="700" letter-spacing="{5 * k:.1f}" fill="url(#gold)">STATIONARY BIKE</text>
    <text x="512" y="{722 * k + 512 * (1 - k):.0f}" font-size="{50 * k:.1f}" font-weight="700" letter-spacing="{5 * k:.1f}" fill="url(#gold)">TRAINING HUB</text>
    <text x="512" y="{790 * k + 512 * (1 - k):.0f}" font-size="{44 * k:.1f}" font-weight="600" letter-spacing="{16 * k:.1f}" fill="url(#goldsoft)">EXCELSIOR</text>
  </g>'''
    sy = sbt_y * scale + 512 * (1 - scale)
    background = '''<rect width="1024" height="1024" fill="url(#bg)"/>''' if bg else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="{size}" height="{size}">
  <title>SBT Hub</title>
  <defs>
    <radialGradient id="bg" cx="50%" cy="40%" r="75%"><stop offset="0" stop-color="#2a2f3a"/><stop offset="1" stop-color="#0d0f14"/></radialGradient>
    <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff3c8"/><stop offset=".38" stop-color="#ecc56c"/><stop offset=".62" stop-color="#b9862f"/><stop offset="1" stop-color="#f1d68c"/></linearGradient>
    <linearGradient id="goldsoft" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f7e2a4"/><stop offset="1" stop-color="#c99a45"/></linearGradient>
    <linearGradient id="bevel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff0bd"/><stop offset=".25" stop-color="#e2b45a"/><stop offset=".5" stop-color="#8f6524"/><stop offset=".75" stop-color="#e6bf6a"/><stop offset="1" stop-color="#7a5418"/></linearGradient>
    <linearGradient id="peak1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5fe6e9"/><stop offset="1" stop-color="#109aa0"/></linearGradient>
    <linearGradient id="peak2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6db8ff"/><stop offset="1" stop-color="#1f6fd1"/></linearGradient>
    <linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".28"/><stop offset=".45" stop-color="#fff" stop-opacity=".04"/><stop offset="1" stop-color="#000" stop-opacity=".25"/></linearGradient>
    <radialGradient id="plate" cx="50%" cy="{(sy if not words else sy + 70 * scale) / 10.24:.1f}%" r="42%"><stop offset="0" stop-color="#000" stop-opacity=".55"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
    <clipPath id="inside"><polygon points="{poly(hexpts(cx, cy, R - 44 * scale))}"/></clipPath>
    <filter id="lift" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="{6 * scale:.1f}" stdDeviation="{6 * scale:.1f}" flood-color="#000" flood-opacity=".7"/></filter>
    <filter id="drop" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="{18 * scale:.1f}" stdDeviation="{20 * scale:.1f}" flood-color="#000" flood-opacity=".55"/></filter>
  </defs>
  {background}
  <g filter="url(#drop)">
    <polygon points="{poly(hexpts(cx, cy, R - 18 * scale))}" fill="url(#bevel)" stroke="url(#bevel)" stroke-width="{36 * scale:.1f}" stroke-linejoin="round"/>
  </g>
  <polygon points="{poly(hexpts(cx, cy, R - 30 * scale))}" fill="none" stroke="#fff4cf" stroke-opacity=".55" stroke-width="{3 * scale:.1f}" stroke-linejoin="round"/>
  <polygon points="{poly(hexpts(cx, cy, R - 44 * scale))}" fill="#3a2810" stroke="#4a3212" stroke-width="{10 * scale:.1f}" stroke-linejoin="round"/>
  <g clip-path="url(#inside)">
    {mosaic(rng, cx, cy, R)}
    <rect width="1024" height="1024" fill="url(#gloss)"/>
    <rect width="1024" height="1024" fill="url(#plate)"/>
  </g>
  <polygon points="{poly(hexpts(cx, cy, R - 44 * scale))}" fill="none" stroke="#2a1b08" stroke-opacity=".8" stroke-width="{4 * scale:.1f}" stroke-linejoin="round"/>
  {mountains(words, scale)}
  <text x="512" y="{sy:.0f}" text-anchor="middle" font-family="'Avenir Next','Avenir','Futura','Helvetica Neue',Arial,sans-serif" font-weight="800" font-size="{sbt_size * scale:.0f}" letter-spacing="{4 * scale:.1f}" fill="url(#gold)" stroke="#4a300c" stroke-width="{5 * scale:.1f}" paint-order="stroke" filter="url(#lift)">SBT</text>
  {words_svg}
</svg>
'''

out = Path(sys.argv[1])
(out / "sbt-hex.svg").write_text(logo(words=True))
(out / "sbt-hex-plain.svg").write_text(logo(words=False))
(out / "sbt-hex-maskable.svg").write_text(logo(words=True, scale=0.8))
(out / "sbt-hex-tab.svg").write_text(logo(words=False, bg=False))
