# S-Bike Training Hub setup (Windows 10/11). Safe to run again: finished steps are skipped.
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1            the hub and the bike bridge
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -NoBike    no smart bike: coach, training load, lifting, dashboard
#   add -NoStart to install without starting the hub
#
# Downloads come from PyPI (Python packages) only. Nothing is uploaded anywhere.
# The route planner and 3D maps are set up on macOS (setup.sh); everything else works here.
param([switch]$NoBike, [switch]$NoStart)
Set-Location -Path $PSScriptRoot
function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Fail($m) {
  if ($env:GITHUB_ACTIONS) { Write-Host "::error::$m" }
  Write-Host $m -ForegroundColor Red
  exit 1
}
# Native commands (python, pip) report through their exit code; their warnings on stderr aren't failures.
function Run($exe, [string[]]$argv) {
  $out = & $exe @argv 2>&1
  $code = $LASTEXITCODE
  $out | ForEach-Object { Write-Host $_ }
  if ($code -ne 0) {
    if ($env:GITHUB_ACTIONS) { $out | Select-Object -Last 15 | ForEach-Object { Write-Host "::error::$_" } }
    Fail "'$exe $($argv -join ' ')' failed (exit code $code)"
  }
}

# ── Python ──────────────────────────────────────────────────────────────────
$py = $null; $pyArgs = @()
foreach ($c in @(@("py", "-3"), @("python"), @("python3"))) {
  if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
  $rest = @($c | Select-Object -Skip 1)
  $ok = & $c[0] @rest -c "import sys; print(int(sys.version_info >= (3, 11)))" 2>$null
  if ("$ok".Trim() -eq "1") { $py = $c[0]; $pyArgs = $rest; break }
}
if (-not $py) {
  Fail "Install Python 3.11 or newer first: https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH')."
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Say "Creating the Python environment (.venv)"
  Run $py ($pyArgs + @("-m", "venv", ".venv"))
}
$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Say "Installing Python packages (bleak, bless)"
Run $venv @("-m", "pip", "install", "-q", "--upgrade", "pip")
Run $venv @("-m", "pip", "install", "-q", "-r", "requirements.txt")
# bless pins an old Windows Bluetooth runtime that conflicts with bleak's; it works with bleak's newer one
Run $venv @("-m", "pip", "install", "-q", "--no-deps", "bless==0.3.0")
Run $venv @("-m", "pip", "install", "-q", "pywin32")

# ── Desktop launcher ────────────────────────────────────────────────────────
$flag = if ($NoBike) { " --no-bike" } else { "" }
$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $desktop -or -not (Test-Path $desktop)) { $desktop = $PSScriptRoot }
$launcher = Join-Path $desktop "S-Bike Hub.cmd"
$lines = @(
  "@echo off",
  "rem Double-click to start the S-Bike Hub. The control panel opens in your browser.",
  "rem Stop it with 'Stop bridge' on the panel, or Ctrl+C in this window.",
  "cd /d `"$PSScriptRoot`"",
  ".venv\Scripts\python.exe -X utf8 bridge.py --ui$flag"
)
Set-Content -Path $launcher -Value $lines -Encoding ASCII
Say "Made the launcher: $launcher"

if ($NoStart) { Say "Installed. Start it from the launcher."; exit 0 }
Say "Starting the hub (the welcome page opens in your browser)"
& $venv -X utf8 bridge.py --ui $(if ($NoBike) { "--no-bike" })
