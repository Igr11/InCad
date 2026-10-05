#!/bin/zsh
# GUI tests in a real FreeCAD window with throwaway settings (the user's user.cfg is never touched).
# Usage: tests/run_gui.sh tests/gui/test_shell.py   (no argument = every tests/gui/test_*.py)
REPO="${0:A:h:h}"
FC=/Applications/FreeCAD.app/Contents/MacOS/FreeCAD
PY=/Applications/FreeCAD.app/Contents/Resources/bin/python
files=("$@"); (( $#files )) || files=("$REPO"/tests/gui/test_*.py)
rc=0
for f in $files; do
  TMP="$(mktemp -d)"; OUT="$TMP/result.json"
  echo "== ${f:t}"
  INCAD_REPO="$REPO" INCAD_GUI_OUT="$OUT" INCAD_LOG="$TMP/incad.log" PYTHONDONTWRITEBYTECODE=1 \
    "$FC" -u "$TMP/user.cfg" "${f:A}" >"$TMP/fc.log" 2>&1 &
  pid=$!
  for i in {1..180}; do kill -0 $pid 2>/dev/null || break; sleep 1; done
  if kill -0 $pid 2>/dev/null; then
    kill $pid; pkill -f "$TMP/user.cfg"; echo "TIMEOUT — log: $TMP/fc.log"; rc=1; continue
  fi
  if [[ ! -f "$OUT" ]]; then echo "NO RESULT — log: $TMP/fc.log"; tail -20 "$TMP/fc.log"; rc=1; continue; fi
  "$PY" - "$OUT" <<'PY' || rc=1
import json, sys
res = json.load(open(sys.argv[1]))
bad = [r for r in res if not r["ok"]]
for r in res:
    print(("PASS " if r["ok"] else "FAIL ") + r["name"])
    if not r["ok"]:
        print(r["detail"])
print("%d passed, %d failed" % (len(res) - len(bad), len(bad)))
sys.exit(1 if bad or not res else 0)
PY
done
exit $rc
