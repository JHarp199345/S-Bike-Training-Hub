# S-Bike Training Hub setup (Windows 10/11). Safe to run again: finished steps are skipped.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1            the hub and the bike bridge
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -NoBike    no smart bike: coach, training load, lifting, dashboard
#   add -NoStart to install without starting the hub
#
# Downloads come from PyPI (Python packages) only. Nothing is uploaded anywhere.
# The route planner and 3D maps are set up on macOS (setup.sh); everything else works here.
param([switch]$NoBike, [switch]$NoStart)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }

# ── Python ──────────────────────────────────────────────────────────────────
$py = $null
foreach ($c in @("py -3", "python", "python3")) {
  try {
    $v = & cmd /c "$c -c ""import sys; print(sys.version_info >= (3, 11))""" 2>$null
    if ($v -eq "True") { $py = $c; break }
  } catch {}
}
if (-not $py) {
  Write-Host "Install Python 3.11 or newer first: https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH')."
  exit 1
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Say "Creating the Python environment (.venv)"
  & cmd /c "$py -m venv .venv"
}
Say "Installing Python packages (bleak, bless)"
& .venv\Scripts\python.exe -m pip install -q --upgrade pip
& .venv\Scripts\python.exe -m pip install -q -r requirements.txt

# ── Desktop launcher ────────────────────────────────────────────────────────
$flag = if ($NoBike) { " --no-bike" } else { "" }
$launcher = Join-Path ([Environment]::GetFolderPath("Desktop")) "S-Bike Hub.cmd"
@"
@echo off
rem Double-click to start the S-Bike Hub. The control panel opens in your browser.
rem Stop it with "Stop bridge" on the panel, or Ctrl+C in this window.
cd /d "$PSScriptRoot"
.venv\Scripts\python.exe -X utf8 bridge.py --ui$flag
"@ | Set-Content -Path $launcher -Encoding ASCII
Say "Made the launcher: Desktop\S-Bike Hub.cmd"

if ($NoStart) { Say "Installed. Start it from the Desktop launcher."; exit 0 }
Say "Starting the hub (the welcome page opens in your browser)"
& .venv\Scripts\python.exe -X utf8 bridge.py --ui$flag
