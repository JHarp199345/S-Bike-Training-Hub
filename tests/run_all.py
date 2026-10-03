"""Run every test on any computer: python tests/run_all.py. Judged by exit status.
Tests marked '# macOS only' are skipped elsewhere (they use Apple's own libraries)."""
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
failed, skipped, passed = [], [], []
for t in sorted(HERE.glob("test_*.py")):
    if sys.platform != "darwin" and "# macOS only" in t.read_text():
        skipped.append(t.name)
        continue
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, str(t)], cwd=HERE.parent, capture_output=True, text=True, timeout=900)
    took = time.monotonic() - t0
    if r.returncode == 0:
        passed.append(t.name)
        print(f"PASS {t.name} ({took:.0f} s)", flush=True)
    else:
        failed.append(t.name)
        print(f"FAIL {t.name} ({took:.0f} s)\n{(r.stdout + r.stderr)[-4000:]}", flush=True)
print(f"\n{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped (macOS only: {', '.join(skipped) or '-'})")
sys.exit(1 if failed else 0)
