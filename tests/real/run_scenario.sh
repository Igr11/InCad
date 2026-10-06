#!/bin/zsh
# Real-input robot: runs one scenario (tests/real/scenarios/*.json) against a fresh FreeCAD with InCad, driving
# it with REAL mouse and keyboard events (tests/real/bin). The screen must be free: don't touch the machine.
# Usage: tests/real/run_scenario.sh tests/real/scenarios/<name>.json      (exit 1 on any FAIL)
HERE="${0:A:h}"; REPO="${HERE:h:h}"
FC=/Applications/FreeCAD.app/Contents/MacOS/FreeCAD
SCEN="$1"; [[ -f "$SCEN" ]] || { echo "usage: $0 scenario.json"; exit 2 }
[[ -x "$HERE/bin/click" && -x "$HERE/bin/move" && -x "$HERE/bin/keys" ]] || "$HERE/build_tools.sh" || exit 2
NAME="${SCEN:t:r}"; RUN="$HERE/runs/$NAME-$(date +%H%M%S)"; mkdir -p "$RUN"; OUT="$RUN/fc"
echo "== $NAME  (logs: $RUN)"
crashes_before=$(ls ~/Library/Logs/DiagnosticReports 2>/dev/null | grep -ci '^freecad-')
INCAD_REPO="$REPO" INCAD_LOG="$RUN/incad.log" FC_OUT="$OUT" INCAD_SCENARIO="$SCEN" PYTHONDONTWRITEBYTECODE=1 \
  "$FC" -u "$RUN/user.cfg" "$HERE/driver.py" >"$RUN/fc.log" 2>&1 &
PID=$!
for i in {1..90}; do [[ -f "$OUT.ready" ]] && break; kill -0 $PID 2>/dev/null || break; sleep 1; done
[[ -f "$OUT.ready" ]] || { echo "FAIL FreeCAD did not come up — $RUN/fc.log"; kill $PID 2>/dev/null; exit 1 }
sleep 1
echo '{}' > "$RUN/memo.json"
fails=0; passes=0
py() { python3 "$HERE/robot_py.py" "$OUT.state" "$RUN/memo.json" "$@" }
driver_cmd() {  # send a command to the driver and wait for it to be done
  rm -f "$OUT.done"; print -r -- "$1" > "$OUT.cmd"
  for i in {1..150}; do [[ -f "$OUT.done" ]] && break; sleep 0.1; done
  [[ -f "$OUT.done" ]] || echo "  (driver did not answer: $1)"
  sleep 0.3
  err=$(py error); [[ -n "$err" ]] && echo "  driver error: $err"
}
shot() { # the FreeCAD window, or the whole screen
  local b=$(osascript -e "tell application \"System Events\" to tell (first process whose unix id is $PID) to get {position, size} of window 1" 2>/dev/null | tr -d ' ')
  if [[ -n "$b" ]]; then screencapture -x -R "$b" "$RUN/$1.png"; else screencapture -x "$RUN/$1.png"; fi
}
# steps, NUL-separated so spaces and colons inside a step survive
steps=("${(@0)$(python3 -c "import json,sys;print('\0'.join(json.load(open(sys.argv[1]))['steps']),end='')" "$SCEN")}")
for step in "${steps[@]}"; do
  kind="${step%%:*}"; arg="${step#*:}"; [[ "$step" == "$kind" ]] && arg=""
  case "$kind" in
    cmd|setup|py|point|ribbon|quit_discard|where) driver_cmd "$step";;
    click|dblclick|rclick)
      xy=$(py spot "$arg") || { echo "FAIL $step -> no such spot (state: $(py brief))"; ((fails++)); shot "fail-$passes-$fails"; continue }
      case $kind in dblclick) b=double;; rclick) b=right;; *) b=left;; esac
      "$HERE/bin/click" ${=xy} $b; sleep 1;;
    move)
      xy=$(py spot "$arg") || { echo "FAIL $step -> no such spot"; ((fails++)); continue }
      "$HERE/bin/move" ${=xy}; sleep 0.5;;
    keys) "$HERE/bin/keys" ${(s:,:)arg}; sleep 0.8;;
    type) "$HERE/bin/keys" ${=$(py keycodes "$arg")}; sleep 0.8;;
    wait) sleep "$arg";;
    memo) py memo "$arg";;
    shot) shot "$arg";;
    expect)
      if py expect "$arg"; then echo "PASS $arg"; ((passes++))
      else echo "FAIL $arg"; echo "     state: $(py brief)"; ((fails++)); shot "fail-$fails"; fi;;
    exited)
      for i in $(seq 1 "${arg:-30}"); do kill -0 $PID 2>/dev/null || break; sleep 1; done
      if kill -0 $PID 2>/dev/null; then echo "FAIL still running after ${arg}s"; ((fails++)); else
        wait $PID; rc=$?; sleep 2
        crashes_after=$(ls ~/Library/Logs/DiagnosticReports 2>/dev/null | grep -ci '^freecad-')
        if [[ $rc -eq 0 && $crashes_after -le $crashes_before ]]; then echo "PASS exited cleanly"; ((passes++))
        else echo "FAIL exit $rc, crash reports $crashes_before -> $crashes_after"; ((fails++)); fi
      fi;;
    *) echo "FAIL unknown step kind: $step"; ((fails++));;
  esac
done
kill -0 $PID 2>/dev/null && { pkill -f "$RUN/user.cfg"; sleep 1; kill -9 $PID 2>/dev/null }
grep -E "ERROR|WARNING" "$RUN/incad.log" 2>/dev/null | cut -c1-160 | sed 's/^/  log: /'
echo "== $NAME: $passes passed, $fails failed  ($RUN)"
[[ $fails -eq 0 ]]
