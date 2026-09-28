"""Smart-bike data goes to Kinomap only; power and cadence to the watch."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, types
import bridge as b
from test_hills import make_bridge


class Ident:
    def __init__(s, u): s.u = u
    def UUIDString(s): return s.u
class Central:
    def __init__(s, u): s.i = Ident(u)
    def identifier(s): return s.i
    def __repr__(s): return s.i.u[:4]


async def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    WATCH, KINO = Central("77BE316F"), Central("C61D6C78")      # real IDs from bluetooth-debug.log
    subs = {b.CP_MEAS: [WATCH], b.CSC_MEAS: [WATCH], b.IBD: [WATCH, KINO],
            b.CONTROL: [WATCH, KINO], b.STATUS: [WATCH, KINO], b.TRAINING: [KINO]}
    class CBChar:
        def __init__(s, u): s.u = u
        def subscribedCentrals(s): return subs.get(s.u, [])
    class Char:
        def __init__(s, u): s.uuid = u; s.obj = CBChar(u); s.value = None
    class PM:
        sent = []
        def updateValue_forCharacteristic_onSubscribedCentrals_(s, data, ch, targets):
            s.sent.append((ch.u, list(targets))); return True
    class Server:
        def __init__(s): s.chars = {}; s.peripheral_manager_delegate = types.SimpleNamespace(peripheral_manager=PM())
        def get_characteristic(s, u): return s.chars.setdefault(u, Char(u))
    br = make_bridge(); br.server = Server(); pm = br.server.peripheral_manager_delegate.peripheral_manager
    for ch, v in ((b.IBD, b"\x75\x00"), (b.CP_MEAS, b"\x20\x00"), (b.CSC_MEAS, b"\x03"), (b.CONTROL, b"\x80\x11\x01")):
        br._send(b.FTMS, ch, v)
    got = {u[4:8]: t for u, t in pm.sent}
    check("bike data (2AD2): Kinomap, plus the watch's once-a-second keep-alive", got["2ad2"] == [KINO, WATCH])
    pm.sent.clear(); br._send(b.FTMS, b.IBD, b"\x75\x00")
    check("a second bike packet right after: Kinomap only (watch capped at 1/s)", pm.sent[0][1] == [KINO])
    br.watch_ibd_at -= 1.0; pm.sent.clear(); br._send(b.FTMS, b.IBD, b"\x75\x00")
    check("a second later: the watch gets its next keep-alive", pm.sent[0][1] == [KINO, WATCH])
    check("control replies (2AD9) go to Kinomap only", got["2ad9"] == [KINO])
    check("power and cadence still go to the watch", got["2a63"] == [WATCH] and got["2a5b"] == [WATCH])
    check("counts: watch 1, Kinomap 1", br.listeners(b.CP_MEAS) == 1 and br.kinomap_count() == 1)
    br.args.watch_ftms = True; pm.sent.clear(); br._send(b.FTMS, b.IBD, b"\x75\x00")
    check("--watch-ftms sends bike data to both again", pm.sent[0][1] == [WATCH, KINO]); br.args.watch_ftms = False
    subs[b.IBD] = [WATCH]; pm.sent.clear()
    check("Kinomap not connected: nothing sent, no error", br._send(b.FTMS, b.IBD, b"\x75\x00") and pm.sent == [])
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
