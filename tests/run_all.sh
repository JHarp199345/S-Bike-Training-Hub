#!/bin/zsh
# Run every test; judge by exit status rather than a particular success message.
cd "${0:A:h}/.." || exit 1
fail=0
for t in tests/test_*.py; do
  echo "== ${t:t}"
  test_output=$(.venv/bin/python "$t" 2>&1)
  test_result=$?
  if [ "$test_result" -eq 0 ]; then
    echo "PASS ${t:t}"
  else
    print -r -- "$test_output"
    fail=1
  fi
done
exit $fail
