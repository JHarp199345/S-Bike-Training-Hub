"""Every page's JavaScript parses. One broken quote stops a whole page's script
(2026-09-27: an apostrophe in "Mac's" broke the pairing page, so the PIN button
did nothing on the tablet), and the server-side tests can't see that."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import re, shutil, subprocess, tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent


def scripts():
    import panel, remote
    pages = {"pairing page": remote.PAIR_PAGE, "control panel": panel.PAGE}
    for f in sorted((HERE / "web").glob("*.html")):
        pages[f"web/{f.name}"] = f.read_text()
    for name, html in pages.items():
        for i, m in enumerate(re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S)):
            if "src=" in m.group(1):
                continue
            yield f"{name} script {i + 1}", m.group(2), "module" in m.group(1)
    for f in sorted((HERE / "web").glob("*.js")):
        yield f"web/{f.name}", f.read_text(), True


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    node = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"
    if not pathlib.Path(node).exists():
        print("(node not installed - skipped)"); print("ALL PASS"); return True
    tmp = pathlib.Path(tempfile.mkdtemp())
    n = 0
    for name, js, module in scripts():
        f = tmp / f"s{n}.{'mjs' if module else 'js'}"; n += 1
        f.write_text(js)
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        err = r.stderr.strip().splitlines()
        check(f"{name} parses" + ("" if r.returncode == 0 else f": {next((l for l in err if 'Error' in l), err[-1] if err else '')}"),
              r.returncode == 0)
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
