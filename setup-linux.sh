#!/usr/bin/env bash
# S-Bike Training Hub setup (Linux). Safe to run again: finished steps are skipped.
#
#   ./setup-linux.sh             the hub and the bike bridge (needs BlueZ: sudo apt install bluez)
#   ./setup-linux.sh --no-bike   no smart bike: coach, training load, lifting, dashboard
#   add --no-start to install without starting the hub
#
# Downloads come from PyPI (Python packages) only. Nothing is uploaded anywhere.
# The route planner and 3D maps are set up on macOS (setup.sh); everything else works here.
set -e
cd "$(dirname "$0")"
NOBIKE=; NOSTART=
for a in "$@"; do [[ $a == --no-bike ]] && NOBIKE=1; [[ $a == --no-start ]] && NOSTART=1; done
say(){ printf '\033[1m==>\033[0m %s\n' "$*"; }

PY=$(command -v python3 || true)
[[ -n $PY ]] || { echo "Install Python 3.11+ first (e.g. sudo apt install python3 python3-venv)."; exit 1; }
$PY -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11+ needed (found $($PY -V))."; exit 1; }
if [[ ! -x .venv/bin/python ]]; then
  say "Creating the Python environment (.venv)"
  $PY -m venv .venv
fi
say "Installing Python packages (bleak, bless)"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
[[ -n $NOBIKE ]] || command -v bluetoothctl >/dev/null || echo "Note: no BlueZ found - for the bike: sudo apt install bluez (or run with --no-bike)."

cat > s-bike-hub.sh <<EOF
#!/usr/bin/env bash
# Start the S-Bike Hub. The control panel opens in your browser; stop it with "Stop bridge" or Ctrl+C.
cd "$PWD" && .venv/bin/python bridge.py --ui${NOBIKE:+ --no-bike}
EOF
chmod +x s-bike-hub.sh
say "Made the launcher: ./s-bike-hub.sh"
[[ -n $NOSTART ]] && { say "Installed. Start it with ./s-bike-hub.sh"; exit 0; }
say "Starting the hub (the welcome page opens in your browser)"
exec .venv/bin/python bridge.py --ui${NOBIKE:+ --no-bike}
