#!/bin/zsh
# Run every bridge test. Exit status is non-zero if any fails.
cd "${0:A:h}/.." || exit 1
fail=0
for t in tests/test_*.py; do
  echo "== ${t:t}"
  .venv/bin/python "$t" | grep -E "FAIL|ALL PASS|SOME FAILED|Error" || { echo "   (no result)"; fail=1; }
  [ ${pipestatus[1]} -eq 0 ] || fail=1
done
exit $fail
