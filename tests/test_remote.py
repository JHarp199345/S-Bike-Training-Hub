"""Phone remote: the Mac always gets in; other devices only after pairing with the PIN;
wrong PINs are rate-limited; /stop stays Mac-only; forgetting unpairs everyone.
Also drives the real panel server over a socket from a non-loopback address."""
# macOS only: uses Apple's Bluetooth/drawing libraries (tests/run_all.py skips it elsewhere)
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json, tempfile
import remote

MAC, PHONE = ("127.0.0.1", 50000), ("192.168.1.40", 50000)


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    remote.FILE = pathlib.Path(tempfile.mkdtemp()) / "remote.json"
    pin = remote.pin()
    check(f"a 6-digit PIN is made on first use ({len(pin)} digits)", len(pin) == 6 and pin.isdigit())
    check("the PIN file is private (0600)", oct(remote.FILE.stat().st_mode & 0o777) == "0o600")

    h = lambda **kw: remote.handle(kw.get("peer", PHONE), kw.get("m", b"GET"), kw["p"], kw.get("hd", {}), kw.get("b", b""))
    check("the Mac gets the panel without pairing", h(peer=MAC, p=b"/") is None)
    check("the Mac can stop the bridge", h(peer=MAC, m=b"POST", p=b"/stop") is None)
    r = h(p=b"/")
    check("an unpaired phone asking for the panel is sent to /pair", r[0] == 302 and r[3]["Location"] == "/pair")
    check("an unpaired phone can't shift", h(m=b"POST", p=b"/gear/1")[0] == 401)
    check("an unpaired phone can't read status", h(p=b"/status")[0] == 401)
    check("an unpaired phone can't read the PIN", h(p=b"/remote/info")[0] == 403)

    r = h(m=b"POST", p=b"/pair", b=b"000000" if pin != "000000" else b"111111")
    check("a wrong PIN is refused", r[0] == 403)
    r = h(m=b"POST", p=b"/pair", b=pin.encode())
    check("the right PIN pairs and sets a cookie", r[0] == 200 and "Set-Cookie" in r[3])
    tok = r[3]["Set-Cookie"].split(";")[0].split("=", 1)[1]
    ck = {b"cookie": f"other=1; {remote.COOKIE}={tok}".encode()}
    check(f"the token is long and random ({len(tok)} chars)", len(tok) >= 40)
    check("the paired phone can shift", h(m=b"POST", p=b"/gear/1", hd=ck) is None)
    check("the paired phone gets the ride view and map tiles",
          h(p=b"/ride", hd=ck) is None and h(p=b"/tiles/14/2806/6535", hd=ck) is None)
    check("the paired phone still can't stop the bridge", h(m=b"POST", p=b"/stop", hd=ck)[0] == 403)
    check("the paired phone can't unpair everyone", h(m=b"POST", p=b"/remote/forget", hd=ck)[0] == 403)
    fake = ("y" if tok[0] == "x" else "x") + tok[1:]      # always differs from the real token (1 in 64 started with x)
    check("a made-up token doesn't work", (h(m=b"POST", p=b"/gear/1", hd={b"cookie": f"{remote.COOKIE}={fake}".encode()}) or [None])[0] == 401)

    remote._fails.clear()
    for _ in range(5):
        remote.try_pin("x", now=1000.0)
    tok2, err = remote.try_pin(pin, now=1001.0)
    check(f"5 wrong PINs lock pairing for a minute, even with the right PIN ({err})", tok2 is None and "wait" in err)
    tok2, err = remote.try_pin(pin, now=1061.0)
    check("a minute later the right PIN works again", tok2 is not None)

    h(peer=MAC, m=b"POST", p=b"/remote/forget")
    check("forgetting unpairs the phone", h(m=b"POST", p=b"/gear/1", hd=ck)[0] == 401)
    check("forgetting picks a new PIN file", remote.pin() != pin or len(json.loads(remote.FILE.read_text())["tokens"]) == 0)

    # QR pairing: one-time codes
    remote._fails.clear(); remote._codes.clear()
    import time as _time
    t0 = _time.monotonic()
    code, left = remote.qr_code(now=t0)
    check(f"a QR code is long and random, good for 10 minutes ({len(code)} chars, {left:.0f} s)", len(code) >= 20 and left == 600)
    check("the panel gets the same code while it has time left", remote.qr_code(now=t0 + 100)[0] == code)
    r = h(p=b"/pair?code=" + code.encode())
    check("just opening the QR link doesn't use the code up (link previews can't burn it)",
          r[0] == 200 and code in remote._codes)
    r = h(m=b"POST", p=b"/pair", b=json.dumps({"code": code}).encode())
    check("the page's pairing request with the code pairs the phone", r[0] == 200 and "Set-Cookie" in r[3])
    r = h(m=b"POST", p=b"/pair", b=json.dumps({"code": code}).encode())
    check("a QR code works only once", r[0] == 403)
    fresh, _ = remote.qr_code()
    check("after it's used, the panel shows a fresh code", fresh != code)
    remote._fails.clear()
    tok2, err = remote.try_code(fresh, now=__import__("time").monotonic() + 700)
    check(f"an expired code is refused ({err})", tok2 is None and "expired" in err)
    check("only the Mac can get a QR code", h(p=b"/remote/qr")[0] == 403)
    remote._fails.clear()
    rq = h(peer=MAC, p=b"/remote/qr", hd={b"host": b"127.0.0.1:8729"})
    if rq and rq[0] == 200 and b'"url"' in rq[2]:
        j = json.loads(rq[2])
        import qr
        m = qr.matrix(j["url"])
        check(f"the panel's QR scans to the pairing link ({j['url'][:48]}...)",
              qr.decode_matrix(m) == j["url"] and "/pair?code=" in j["url"] and j["svg"].startswith("<svg"))
    else:
        print("(no Wi-Fi address - skipped the QR scan check)")

    # The real server, reached from this Mac's own LAN address (so not loopback).
    import panel
    lan = next((a for a in remote.lan_addresses() if a[0].isdigit()), None)
    if lan:
        class FakeBridge:
            shifted = []
            def shift(self, d, why=None): self.shifted.append(d)
            def status(self): return {"ok": 1}
        fb = FakeBridge()

        async def go():
            srv = await panel.serve(fb, 18729, lan=True)
            async def req(raw):
                rd, wr = await asyncio.open_connection(lan, 18729)
                wr.write(raw); await wr.drain()
                out = await rd.read(); wr.close(); return out
            a = await req(b"POST /gear/1 HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n")
            p = remote.pin()
            b = await req(b"POST /pair HTTP/1.1\r\nHost: x\r\nContent-Length: 6\r\n\r\n" + p.encode())
            cookie = [l for l in b.split(b"\r\n") if l.lower().startswith(b"set-cookie:")][0].split(b":", 1)[1].split(b";")[0].strip()
            c = await req(b"POST /gear/1 HTTP/1.1\r\nHost: x\r\nCookie: " + cookie + b"\r\nContent-Length: 0\r\n\r\n")
            srv.close(); await srv.wait_closed()
            return a, b, c
        a, b, c = asyncio.run(go())
        check(f"over the network from {lan}: unpaired shift refused (401)", a.startswith(b"HTTP/1.1 401"))
        check("over the network: pairing sets the cookie", b.startswith(b"HTTP/1.1 200") and b"sbikeremote=" in b)
        check("over the network: paired shift reaches the bridge", c.startswith(b"HTTP/1.1 200") and fb.shifted == [1])
    else:
        print("(no network address - skipped the over-the-network part)")
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
