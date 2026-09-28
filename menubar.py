#!/usr/bin/env python3
"""menubar.py - S-Bike Hub in the macOS menu bar.

A bike icon at the top of the screen:  🚲○ bridge off   🚲◐ looking for the bike
🚲● bike connected. The menu starts and stops the bridge, opens the control
panel, flips auto-shift, and turns "start at login" on or off.

This app never touches Bluetooth itself. macOS only lets approved apps use it,
and Terminal is the one that's approved, so the bridge is started the same way
the Desktop icon does it - through Terminal - and this app talks to it over the
control panel's local address.
"""
import json
import os
import plistlib
import subprocess
import urllib.request
from pathlib import Path

import signal
import time

import rumps

from watchdog import Watchdog

HERE = Path(__file__).resolve().parent
PANEL = "http://127.0.0.1:8729"
LAUNCHER = Path.home() / "Desktop" / "S-Bike Hub.command"
AGENT = Path.home() / "Library" / "LaunchAgents" / "com.sbikehub.menubar.plist"


def call(path, post=False, timeout=1.5):
    req = urllib.request.Request(PANEL + path, method="POST" if post else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def bridge_state():
    try:
        return json.loads((HERE / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def status():
    try:
        return call("/status")
    except Exception:
        return None


class SBikeHub(rumps.App):
    def __init__(self):
        super().__init__("S-Bike Hub", title="🚲○", quit_button=None)
        self.toggle = rumps.MenuItem("Start bridge", callback=self.on_toggle)
        self.panel = rumps.MenuItem("Open control panel", callback=lambda _: subprocess.run(["open", PANEL]))
        self.report = rumps.MenuItem("Open last ride report", callback=self.on_report)
        self.climb = rumps.MenuItem("Climbing mode (30-45 rpm)", callback=self.on_climb)
        self.auto = rumps.MenuItem("Auto-shift", callback=self.on_auto)
        self.info = rumps.MenuItem("Bridge is off")
        self.login = rumps.MenuItem("Open this icon when I log in", callback=self.on_login)
        self.login.state = AGENT.exists() and not login_disabled()
        self.menu = [self.info, None, self.toggle, self.panel, self.report, self.auto, self.climb, None, self.login,
                     rumps.MenuItem("Hide this icon (back at next login)", callback=self.on_quit)]
        self.dog = Watchdog()
        self.refresh(None)
        rumps.Timer(self.refresh, 3).start()

    def refresh(self, _):
        s = status()
        self.watch_over(s is not None)
        if s is None:
            self.title, self.toggle.title, self.info.title = "🚲○", "Start bridge", "Bridge is off"
            self.auto.state, self.auto.title = False, "Auto-shift"
            return
        bits = ["bike ✓" if s["bike"] else "bike: pedal to wake",
                "watch ✓" if s["watch"] else "watch –", "Kinomap ✓" if s["kinomap"] else "Kinomap –"]
        self.title = "🚲●" if s["bike"] else "🚲◐"
        self.toggle.title = "Stop bridge"
        self.info.title = "  ·  ".join(bits) + (f"   {s['power']} W  {s['cadence']} rpm" if s["bike"] else "")
        self.auto.state = bool(s.get("auto"))
        self.climb.state = bool(s.get("climbing"))
        self.auto.title = "Auto-shift"

    def watch_over(self, answering):
        """Self-healing: restart a crashed or frozen bridge; it resumes the ride."""
        st = bridge_state()
        action = self.dog.tick(time.monotonic(), answering, st, alive(st.get("pid")))
        if action == "kill_and_restart":
            try:
                os.kill(int(st["pid"]), signal.SIGKILL)   # frozen: SIGKILL keeps its crash state for the resume
            except (OSError, KeyError, ValueError):
                pass
            time.sleep(1)
        if action in ("restart", "kill_and_restart"):
            why = "stopped responding" if action == "kill_and_restart" else "crashed"
            subprocess.run(["open", "-g", str(LAUNCHER)])
            self.info.title = f"Bridge {why}: restarting and resuming the ride…"
            self.notify(f"The bridge {why} and is restarting. Your ride continues.")
        elif action == "give_up":
            self.info.title = "Bridge keeps failing: stopped auto-restarting (see bridge.log)"
            self.notify("The bridge failed 3 times in 10 minutes, so auto-restart has stopped. See bridge.log.")

    def notify(self, text):
        try:
            rumps.notification("S-Bike Hub", "", text)
        except Exception:
            pass

    def on_toggle(self, _):
        if status() is None:
            self.dog.reset()
            # -g: open Terminal in the background so it doesn't jump in front.
            subprocess.run(["open", "-g", str(LAUNCHER)])
            self.info.title = "Starting…"
        else:
            try:
                call("/stop", post=True)
            except Exception:
                pass
            self.info.title = "Stopping…"

    def on_report(self, _):
        rides = sorted((HERE / "rides").glob("ride_*_report.html"), key=lambda p: p.stat().st_mtime)
        if rides:
            subprocess.run(["open", str(rides[-1])])
        else:
            rumps.alert("No ride report yet", "One is made when you stop the bridge after a ride.")

    def on_climb(self, item):
        if status() is not None:
            call("/climb/" + ("off" if item.state else "on"), post=True)
            self.refresh(None)

    def on_auto(self, item):
        if status() is not None:
            call("/auto/" + ("off" if item.state else "on"), post=True)
            self.refresh(None)

    def on_quit(self, _):
        """launchd brings the icon back if it ever stops, so a real Quit has to
        unload it; it comes back at the next login."""
        if AGENT.exists():
            subprocess.Popen(["launchctl", "bootout", f"gui/{os.getuid()}/com.sbikehub.menubar"])
        rumps.quit_application()

    def on_login(self, item):
        """Only about the NEXT login: switching it off never closes the icon now
        (it used to unload it on the spot, which made the icon vanish)."""
        label = f"gui/{os.getuid()}/com.sbikehub.menubar"
        if item.state:
            subprocess.run(["launchctl", "disable", label], capture_output=True)
            item.state = False
            self.notify("The icon stays for now; it won't open by itself at your next login.")
        else:
            if not AGENT.exists():
                install_login_item()
            subprocess.run(["launchctl", "enable", label], capture_output=True)
            item.state = True
            self.notify("The icon will open by itself whenever you log in.")


def login_disabled():
    """Whether 'Open this icon when I log in' was switched off (launchctl disable)."""
    try:
        out = subprocess.run(["launchctl", "print-disabled", f"gui/{os.getuid()}"], capture_output=True,
                             text=True, timeout=3).stdout
        return any("com.sbikehub.menubar" in l and ("true" in l or "disabled" in l) for l in out.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


def install_login_item():
    """Start this menu icon at login and keep it running (not the bridge itself -
    that stays a click)."""
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    AGENT.write_bytes(plistlib.dumps({
        "Label": "com.sbikehub.menubar",
        "ProgramArguments": [str(HERE / ".venv" / "bin" / "python"), str(HERE / "menubar.py")],
        "WorkingDirectory": str(HERE),
        "RunAtLoad": True,
        "KeepAlive": True,                 # closed by macOS or crashed: relaunch it
        "ThrottleInterval": 10,
        "StandardErrorPath": str(HERE / "menubar.log"),
        "StandardOutPath": str(HERE / "menubar.log"),
    }))


if __name__ == "__main__":
    SBikeHub().run()
