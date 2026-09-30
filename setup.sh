#!/bin/zsh
# S-Bike Training Hub setup (macOS). Safe to run again: finished steps are skipped.
#
#   ./setup.sh             everything: Python packages, route planner, maps for regions.json,
#                          3D terrain, the Desktop launcher, the menu-bar icon
#   ./setup.sh --no-maps   just the bike bridge (no route planner or 3D maps)
#   ./setup.sh --no-bike   no smart bike: the coach, training load, lifting and dashboard only
#
# Downloads come from: PyPI (Python packages), GitHub releases (BRouter, pmtiles),
# npm (MapLibre GL), brouter.de (road data), build.protomaps.com (map tiles),
# the AWS open-data terrain tiles (elevation), and protomaps basemaps-assets (fonts).
# Nothing is uploaded anywhere. Big downloads ask first.
set -e
cd "${0:A:h}"
NOBIKE=; [[ $1 == --no-bike ]] && NOBIKE=1
HERE=$PWD
MAPS=${S_BIKE_MAPS:-$HERE/maps}
say(){ print -P "%B==>%b $*"; }
ask(){ print -n "$1 [y/N] "; read -r a; [[ $a == [yY]* ]]; }

[[ $(uname) == Darwin ]] || { echo "This needs macOS (it uses Apple's Bluetooth and drawing libraries)."; exit 1; }

# ── Python ──────────────────────────────────────────────────────────────────
PY=$(command -v python3 || true)
[[ -n $PY ]] || { echo "Install Python 3.11+ first (e.g. brew install python)."; exit 1; }
$PY -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11+ needed (found $($PY -V))."; exit 1; }
if [[ ! -x .venv/bin/python ]]; then
  say "Creating the Python environment (.venv)"
  $PY -m venv .venv
fi
say "Installing Python packages (bleak, bless, pyobjc, rumps)"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# ── Desktop launcher ────────────────────────────────────────────────────────
# Bluetooth permission on macOS belongs to the app that starts the bridge, so it
# starts from Terminal: this launcher, or the menu icon (which opens it).
LAUNCHER="$HOME/Desktop/S-Bike Hub.command"
cat > "$LAUNCHER" <<EOF
#!/bin/zsh
# Double-click to start the S-Bike Hub bike bridge. The control panel opens in your
# browser. Closing this window does NOT stop the bridge: use "Stop bridge" on the
# panel or in the menu-bar icon.
cd "$HERE" && .venv/bin/python bridge.py --ui${NOBIKE:+ --no-bike}
EOF
chmod +x "$LAUNCHER"
say "Made the launcher: ~/Desktop/S-Bike Hub.command"

if [[ $1 != --no-maps && -z $NOBIKE ]]; then
  mkdir -p "$MAPS"/{tools,web/fonts,brouter/segments4,brouter/customprofiles,map,terrain}

  # ── route planner (BRouter) ───────────────────────────────────────────────
  command -v java >/dev/null || { echo "The route planner needs Java: brew install openjdk (then run setup again)."; exit 1; }
  if [[ ! -d $MAPS/tools/brouter/brouter-1.7.10 ]]; then
    say "BRouter 1.7.10 (route planner, ~20 MB)"
    curl -fsSL -o "$MAPS/tools/brouter.zip" https://github.com/abrensch/brouter/releases/download/v1.7.10/brouter-1.7.10.zip
    (cd "$MAPS/tools" && unzip -oq brouter.zip -d brouter && rm brouter.zip)
  fi
  if [[ ! -x $MAPS/tools/pmtiles/pmtiles ]]; then
    ARCH=$( [[ $(uname -m) == arm64 ]] && echo arm64 || echo x86_64 )
    say "pmtiles 1.31.2 (map extractor)"
    curl -fsSL -o "$MAPS/tools/pmtiles.zip" https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles-1.31.2_Darwin_$ARCH.zip
    (cd "$MAPS/tools" && unzip -oq pmtiles.zip -d pmtiles && rm pmtiles.zip)
  fi
  if [[ ! -d $MAPS/web/maplibre ]]; then
    say "MapLibre GL 6.11.2 (3D map engine, ~5 MB)"
    curl -fsSL -o "$MAPS/web/maplibre.tgz" https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-6.11.2.tgz
    (cd "$MAPS/web" && tar -xzf maplibre.tgz package/dist && mv package/dist maplibre && rm -rf package maplibre.tgz)
  fi
  say "Map label fonts (~1.5 MB)"
  for f in "Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic"; do
    mkdir -p "$MAPS/web/fonts/$f"
    for r in 0-255 256-511 512-767 7680-7935 8192-8447; do
      [[ -s "$MAPS/web/fonts/$f/$r.pbf" ]] || curl -fsS --retry 3 -o "$MAPS/web/fonts/$f/$r.pbf" \
        "https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts/${f// /%20}/$r.pbf"
    done
  done

  # ── what regions.json asks for ────────────────────────────────────────────
  PLAN=$(.venv/bin/python - "$MAPS" <<'PYEOF'
import json, math, sys
from pathlib import Path
maps = Path(sys.argv[1])
regs = json.loads(Path("regions.json").read_text())["regions"]
tiles, pieces, terrain = set(), [], set()
for r in regs:
    w, s, e, n = r["bbox"]
    for x in range(math.floor(w / 5) * 5, math.ceil(e / 5) * 5, 5):            # BRouter: 5x5 degree tiles
        for y in range(math.floor(s / 5) * 5, math.ceil(n / 5) * 5, 5):
            tiles.add(f"{'W' if x < 0 else 'E'}{abs(x)}_{'S' if y < 0 else 'N'}{abs(y)}")
    nx, ny = max(1, math.ceil((e - w) / 5)), max(1, math.ceil((n - s) / 5))  # map pieces of <= 5x5 degrees
    for i in range(nx):
        for j in range(ny):
            b = (w + (e - w) * i / nx, s + (n - s) * j / ny, w + (e - w) * (i + 1) / nx, s + (n - s) * (j + 1) / ny)
            slug = r["name"].lower().replace(" ", "-")
            pieces.append((f"{slug}-{i}{j}", ",".join(f"{v:.4f}" for v in b)))
    for z in range(0, 13):                                                       # terrain z0-12
        k = 2 ** z
        def xy(lon, lat):
            lat = max(-85.0, min(85.0, lat))
            return int((lon + 180) / 360 * k), int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * k)
        x0, y1 = xy(w, s); x1, y0 = xy(e, n)
        terrain.update((z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))
(maps / "terrain" / "tiles.txt").write_text("".join(f"{z}/{x}/{y}\n" for z, x, y in sorted(terrain)))
print("TILES=(" + " ".join(sorted(tiles)) + ")")
print("PIECES=(" + " ".join(f"{a}:{b}" for a, b in pieces) + ")")
print(f"NTERRAIN={len(terrain)}")
PYEOF
)
  eval "$PLAN"
  say "Regions in regions.json: road data ${#TILES} tiles (~50-100 MB each), map ${#PIECES} pieces (~0.1-1.5 GB each), terrain $NTERRAIN tiles (~80 KB each)"
  if ask "Download the road data for the route planner?"; then
    for t in $TILES; do
      [[ -s "$MAPS/brouter/segments4/$t.rd5" ]] && continue
      say "road data $t"
      curl -fsSL -o "$MAPS/brouter/segments4/$t.rd5.part" "https://brouter.de/brouter/segments4/$t.rd5" \
        && mv "$MAPS/brouter/segments4/$t.rd5.part" "$MAPS/brouter/segments4/$t.rd5" || echo "   (no road data for $t - likely all sea)"
    done
  fi
  if ask "Download the map (streets, places, buildings) for these regions? This is the big one."; then
    BUILD=$(curl -fsS https://build-metadata.protomaps.dev/builds.json | .venv/bin/python -c "import json,sys; print(json.load(sys.stdin)[-1]['key'])")
    P="$MAPS/tools/pmtiles/pmtiles"
    for pc in $PIECES; do
      name=${pc%%:*}; bbox=${pc#*:}; out="$MAPS/map/$name.pmtiles"
      [[ -s $out ]] && $P show "$out" >/dev/null 2>&1 && { echo "   $name: already done"; continue; }
      for attempt in 1 2 3 4 5 6 7 8 9 10; do               # a dropped connection costs one piece, tried again
        say "map $name (attempt $attempt)"
        rm -f "$out.part"
        if $P extract "https://build.protomaps.com/$BUILD" "$out.part" --bbox=$bbox --maxzoom=14 --download-threads=4 \
           && $P show "$out.part" >/dev/null 2>&1; then mv "$out.part" "$out"; break; fi
        sleep $(( attempt * 15 ))
      done
    done
  fi
  if ask "Download 3D terrain (elevation) for these regions?"; then
    say "terrain: $NTERRAIN tiles"
    cat "$MAPS/terrain/tiles.txt" | xargs -P 8 -I{} sh -c 'f="'"$MAPS"'/terrain/{}.png"; [ -s "$f" ] || { mkdir -p "$(dirname "$f")"; curl -fsS --retry 5 -o "$f" "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{}.png" || rm -f "$f"; }'
  fi
fi

# ── menu-bar icon ───────────────────────────────────────────────────────────
if [[ -z $NOBIKE ]] && ask "Add the 🚲 menu-bar icon (opens at login; starts/stops the bridge, restarts it if it crashes)?"; then
  .venv/bin/python -c "import menubar; menubar.install_login_item()"
  launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.sbikehub.menubar.plist" 2>/dev/null || true
fi

if [[ -n $NOBIKE ]]; then
  say "Done. Start it: double-click 'S-Bike Hub' on your Desktop. The first time, it opens the welcome and a two-minute setup."
else
  say "Done. Start it: double-click 'S-Bike Hub' on your Desktop (or use the menu icon)."
fi
echo "   Optional - coach from Claude: claude mcp add --scope user s-bike-hub -- \"$HERE/.venv/bin/python\" \"$HERE/mcp_server.py\""
