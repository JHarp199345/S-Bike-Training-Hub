"""Run every test on any computer: python tests/run_all.py. Judged by exit status.
Tests marked '# macOS only' are skipped elsewhere (they use Apple's own libraries)."""
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE.parent / "test-results.txt"          # read by CI on failure (logs can be hard to reach)
failed, skipped, passed = [], [], []


def note(line):
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(line + "\n")


RESULTS.write_text("", encoding="utf-8")
for t in sorted(HERE.glob("test_*.py")):
    if sys.platform != "darwin" and "# macOS only" in t.read_text():
        skipped.append(t.name)
        continue
    t0 = time.monotonic()
    try:
        r = subprocess.run([sys.executable, str(t)], cwd=HERE.parent, capture_output=True, text=True, timeout=300,
                           encoding="utf-8", errors="replace")
        code, out = r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:
        code, out = "timeout", f"{e.stdout or ''}{e.stderr or ''}\n(no result after 300 s)"
        out = out if isinstance(out, str) else str(out)
    took = time.monotonic() - t0
    if code == 0:
        passed.append(t.name)
        print(f"PASS {t.name} ({took:.0f} s)", flush=True)
        note(f"PASS {t.name}")
    else:
        failed.append(t.name)
        print(f"FAIL {t.name} ({took:.0f} s)\n{out[-4000:]}", flush=True)
        note(f"FAIL {t.name} ({code}): " + " | ".join([x for x in out.strip().splitlines() if x.strip()][-10:]))
        if os.environ.get("GITHUB_ACTIONS"):        # failures readable as annotations, not just in the log
            tail = [x for x in out.strip().splitlines() if x.strip()][-12:]
            print(f"::error title={t.name}::" + " | ".join(tail).replace("%", "%25")[:3500], flush=True)
print(f"\n{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped (macOS only: {', '.join(skipped) or '-'})")
sys.exit(1 if failed else 0)
