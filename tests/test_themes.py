"""The theme choice is saved once on the bridge and served to every page and device; every theme the picker offers
is defined in the stylesheet and known to the server; old names still land somewhere."""
import asyncio
import json
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import mapserver
import themes


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    call = lambda m, body=b"": asyncio.run(mapserver.handle(None, m, "/api/theme", body, "localhost"))
    original = themes.FILE
    try:
        with tempfile.TemporaryDirectory() as folder:
            themes.FILE = pathlib.Path(folder) / "theme.json"
            check("nothing chosen yet: classic", themes.current() == "classic")
            for name in themes.OPTIONS:
                r = call(b"POST", json.dumps({"theme": name}).encode())
                g = json.loads(call(b"GET")[2])["theme"]
                check(f"{name}: saved and served back", r[0] == 200 and g == name)
            r = call(b"POST", b'{"theme":"diamondback"}')
            check("the old name 'diamondback' becomes rattlesnake", r[0] == 200 and themes.current() == "rattlesnake")
            r = call(b"POST", b'{"theme":"unknown"}')
            check("an unknown theme is refused and the choice kept", r[0] == 400 and themes.current() == "rattlesnake")
    finally:
        themes.FILE = original

    for asset, kind in (("theme.css", "text/css"), ("theme.js", "text/javascript")):
        r = asyncio.run(mapserver.handle(None, b"GET", "/web/" + asset, b"", "localhost"))
        check(f"/web/{asset} served as {kind}", r[0] == 200 and r[1] == kind)

    css = (ROOT / "web/theme.css").read_text()
    js = (ROOT / "web/theme.js").read_text()
    picker = set(re.findall(r"^\s{4}(\w+): \[", js, re.M))
    check(f"the picker offers exactly the server's themes ({sorted(picker)})", picker == set(themes.OPTIONS))
    roles = ("--bg", "--card", "--text", "--accent", "--on-accent", "--band", "--bar", "--tile", "--mark")
    for name in themes.OPTIONS:
        if name == "classic":
            continue
        block = " ".join(re.findall(r':root\[data-theme="%s"\][^{]*\{([^}]*)\}' % name, css))
        missing = [r for r in roles if r + ":" not in block]
        check(f"{name} defines every colour role{' - missing ' + ', '.join(missing) if missing else ''}", not missing)

    pages = [p for p in (ROOT / "web").glob("*.html")] + [ROOT / "panel.py", ROOT / "report.py"]
    without = [p.name for p in pages if "/web/theme.css" not in p.read_text() and 'content="0;url=/coach#fitness"' not in p.read_text()]
    check(f"every page loads the theme ({'missing: ' + ', '.join(without) if without else 'all'})", not without)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
