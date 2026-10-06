"""The SBT hex app icon: every page links the manifest and icons, and they're served."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json
import panel, mapserver


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    page = panel.with_app_icon("text/html; charset=utf-8", b"<html><head><title>x</title></head><body></body></html>")
    check("a page gets the manifest, tab icon and home-screen icon", b'rel="manifest"' in page and b"apple-touch-icon" in page and page.count(b"</head>") == 1)
    check("added once only", panel.with_app_icon("text/html", page) == page)
    check("JSON is left alone", panel.with_app_icon("application/json", b"{}") == b"{}")
    code, ctype, body, _ = asyncio.run(mapserver.handle(None, b"GET", "/manifest.webmanifest", b"", "127.0.0.1"))
    m = json.loads(body)
    check(f"manifest served ({m['short_name']})", code == 200 and "manifest" in ctype and m["display"] == "standalone")
    for icon in m["icons"]:
        code, ctype, body, _ = asyncio.run(mapserver.handle(None, b"GET", icon["src"], b"", "127.0.0.1"))
        check(f"{icon['src']} served ({len(body)} bytes)", code == 200 and len(body) > 1000)
    code, *_ = asyncio.run(mapserver.handle(None, b"GET", "/web/icons/apple-touch-icon.png", b"", "127.0.0.1"))
    check("tablet home-screen icon served", code == 200)
    import remote
    phone = ("192.168.1.40", 5000)
    check("an unpaired tablet can fetch the icon and manifest (nothing else)", remote.allowed(phone, {}, b"/web/icons/apple-touch-icon.png")
          and remote.allowed(phone, {}, b"/manifest.webmanifest") and not remote.allowed(phone, {}, b"/coach") and not remote.allowed(phone, {}, b"/web/coach.html")
          and not remote.allowed(phone, {}, b"/web/icons/../../coach.json"))
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
