#!/bin/zsh
# All real-input scenarios (tests/real), one FreeCAD each. The screen must be free and unlocked: real mouse and
# keys are used. Keeps the display awake meanwhile; parks the pointer at the end. Exit 1 if any scenario fails.
REPO="${0:A:h:h}"
[[ -x "$REPO/tests/real/bin/click" ]] || "$REPO/tests/real/build_tools.sh" >/dev/null
caffeinate -d -u -w $$ &
rc=0
for f in "$REPO"/tests/real/scenarios/*.json; do
  out=$("$REPO/tests/real/run_scenario.sh" "$f" 2>&1)
  echo "$out" | grep -E "^== .*passed|FAIL|still running|driver error" | cut -c1-160
  echo "$out" | grep -qE "^== .*, 0 failed" || rc=1
done
"$REPO/tests/real/bin/move" 5 5 2>/dev/null
[[ $rc -eq 0 ]] && echo "ROBOT: all scenarios passed" || echo "ROBOT: some scenarios FAILED"
exit $rc
