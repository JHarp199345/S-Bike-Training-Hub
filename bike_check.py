"""bike_check.py - the guided check: does a proposed profile really talk to the bike?

The hub runs it, the same way for every bike and every assistant, while the
athlete pedals steadily:

  1. connect and listen      readings must decode to believable cadence and power
  2. nudge resistance        only if the profile has resistance control: a few
                             small steps up from an easy level, held, then back
                             down. Every write goes through bikes.allowed_write and
                             at most one every half second.
  3. watch for the effect    the bike's resistance reading follows, or the watts
                             at the same cadence rise - and the connection stays up
  4. leave it easy           finishes on the easy level, then disconnects

Then the athlete is asked whether it got harder in the middle; the profile only
becomes the bike when the check passed and they felt it (bikes.activate).
"""
import asyncio
import time

import bikes
import bike_ble


class Refused(RuntimeError):
    pass


class SafeConn:
    """The only way the check writes to a bike."""

    def __init__(self, conn, profile):
        self.conn, self.p = conn, profile
        self.sent, self.refused, self.last = [], [], 0.0

    async def write(self, char, value):
        ok, why = bikes.allowed_write(self.p, char, value)
        if not ok:
            self.refused.append({"hex": bytes(value).hex(), "why": why})
            raise Refused(why)
        wait = 0.5 * bike_ble.time_scale() - (time.monotonic() - self.last)
        if wait > 0:
            await asyncio.sleep(wait)
        resp = True
        if self.p["protocol"] == "custom":
            resp = self.p["custom"]["control"]["response"]
        await self.conn.write(char, value, response=resp)
        self.last = time.monotonic()
        self.sent.append({"hex": bytes(value).hex(), "why": why})


def _levels(p):
    r = p["resistance"]
    lo, hi = r["min"], r["max"]
    easy = max(lo, round(lo + 0.15 * (hi - lo)))
    hard = min(hi, max(easy + 2, round(lo + 0.45 * (hi - lo))))
    return easy, hard


def _avg(rows, k):
    v = [r[k] for r in rows if k in r]
    return round(sum(v) / len(v), 1) if v else None


async def run(device, profile, transport=None, listen_s=10.0, hold_s=8.0, progress=None):
    """The check's result: {passed, readings, resistance_tested, effect, sent, problems, ...}."""
    t = transport or bike_ble.transport()
    p = bikes.validate(profile)
    scale = bike_ble.time_scale()
    say = progress or (lambda msg: None)
    res = {"profile_id": p["id"], "at": bikes._now(), "passed": False, "problems": [], "sent": [], "phases": {}}
    rows, phase = [], {"name": "listen"}
    data_char = p["custom"]["data"]["characteristic"] if p["protocol"] == "custom" else bikes.IBD

    def on_data(char, data):
        if char == data_char:
            r = bikes.parse(p, data)
            if r:
                rows.append(dict(r, phase=phase["name"]))
    say("Connecting to the bike")
    try:
        conn = await t.connect(device["address"])
    except Exception as e:
        res["problems"].append(f"Couldn't connect: {e}")
        return res
    safe = SafeConn(conn, p)
    try:
        await conn.start_notify(data_char, on_data)
        if p["protocol"] == "ftms":
            try:
                await conn.start_notify(bikes.FTMS_CONTROL, lambda c, d: None)
            except Exception:
                pass
        say("Listening - keep pedaling steadily")
        await asyncio.sleep(listen_s * scale)
        base = [r for r in rows if r["phase"] == "listen"]
        res["readings"] = {"packets": len(base), "cadence_rpm": _avg(base, "cadence_rpm"), "power_w": _avg(base, "power_w")}
        cad = res["readings"]["cadence_rpm"]
        if len(base) < 5:
            res["problems"].append("Too few readings decoded - the data characteristic or prefix is probably wrong.")
            return res
        if cad is None or not 25 <= cad <= 160:
            res["problems"].append(f"Cadence read as {cad} rpm. If the athlete was pedaling, the cadence field is wrong; "
                                   "if they'd stopped, run the check again while they pedal.")
            return res
        pw = res["readings"]["power_w"]
        if pw is None or not 0 < pw < 1500:
            res["problems"].append(f"Power read as {pw} W at {cad} rpm - check the power field (offset, size, scale).")
            return res
        if p["resistance"].get("none"):
            res["resistance_tested"] = False
            res["passed"] = conn.is_connected
            return res
        easy, hard = _levels(p)
        ctl = p["custom"]["control"]["characteristic"] if p["protocol"] == "custom" else bikes.FTMS_CONTROL
        say(f"Setting an easy level ({easy:g})")
        if p["protocol"] == "ftms":
            await safe.write(ctl, b"\x00")
        else:
            for c in p["custom"]["control"]["init"]:
                await safe.write(ctl, bytes.fromhex(c))
        phase["name"] = "easy"
        await safe.write(ctl, bikes.resistance_command(p, easy))
        await asyncio.sleep(hold_s * scale)
        say(f"A little harder: up to level {hard:g}, one step at a time")
        phase["name"] = "ramp"
        lvl = easy
        while lvl < hard and conn.is_connected:
            lvl = min(hard, lvl + 1)
            await safe.write(ctl, bikes.resistance_command(p, lvl))
        phase["name"] = "hard"
        await asyncio.sleep(hold_s * scale)
        say("Back down to easy")
        phase["name"] = "ramp_down"
        while lvl > easy and conn.is_connected:
            lvl = max(easy, lvl - 1)
            await safe.write(ctl, bikes.resistance_command(p, lvl))
        phase["name"] = "after"
        await asyncio.sleep(2 * scale)
        res["resistance_tested"] = True
        e_rows = [r for r in rows if r["phase"] == "easy"]
        h_rows = [r for r in rows if r["phase"] == "hard"]
        effect = {"easy_level": easy, "hard_level": hard,
                  "easy": {k: _avg(e_rows, k) for k in ("power_w", "cadence_rpm", "resistance")},
                  "hard": {k: _avg(h_rows, k) for k in ("power_w", "cadence_rpm", "resistance")}}
        seen = []
        if effect["easy"]["resistance"] is not None and effect["hard"]["resistance"] is not None \
                and effect["hard"]["resistance"] > effect["easy"]["resistance"]:
            seen.append("the bike's resistance reading rose")
        ep, hp = effect["easy"]["power_w"], effect["hard"]["power_w"]
        ec, hc = effect["easy"]["cadence_rpm"], effect["hard"]["cadence_rpm"]
        if ep and hp and ec and hc and (hp / hc) > 1.1 * (ep / ec):
            seen.append(f"watts per rpm rose {round(100 * ((hp / hc) / (ep / ec) - 1))}%")
        effect["seen"] = seen
        res["effect"] = effect
        if not conn.is_connected:
            res["problems"].append("The bike disconnected during the check - it may have rejected a command. "
                                   "Nothing more was sent.")
        elif not seen:
            res["problems"].append("No change was measured when resistance went up. The command may be wrong "
                                   "(or the bike only changes the feel). Ask the athlete whether it got harder.")
        res["passed"] = conn.is_connected and bool(seen)
        return res
    except Refused as e:
        res["problems"].append(f"The hub refused to send a command: {e}")
        return res
    except Exception as e:
        res["problems"].append(f"The check stopped: {e}")
        return res
    finally:
        res["sent"], res["refused"] = safe.sent, safe.refused
        res["stayed_connected"] = bool(conn.is_connected)
        await conn.disconnect()
        say("Check finished")
