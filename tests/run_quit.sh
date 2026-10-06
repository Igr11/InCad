#!/bin/zsh
# Quitting FreeCAD while InCad is active must end cleanly (exit 0, no crash report).
REPO="${0:A:h:h}"
FC=/Applications/FreeCAD.app/Contents/MacOS/FreeCAD
TMP="$(mktemp -d)"
before=$(ls ~/Library/Logs/DiagnosticReports 2>/dev/null | grep -ci '^freecad-')
INCAD_REPO="$REPO" "$FC" -u "$TMP/user.cfg" "${INCAD_QUIT_SCRIPT:-$REPO/tests/quit/quit_in_incad.py}" >"$TMP/fc.log" 2>&1 &
pid=$!
for i in {1..90}; do kill -0 $pid 2>/dev/null || break; sleep 1; done
if kill -0 $pid 2>/dev/null; then kill $pid; echo "QUIT TIMEOUT — log: $TMP/fc.log"; exit 1; fi
wait $pid; rc=$?
sleep 3
after=$(ls ~/Library/Logs/DiagnosticReports 2>/dev/null | grep -ci '^freecad-')
if [[ $rc -ne 0 || $after -gt $before ]]; then echo "QUIT CRASHED (exit $rc, crash reports $before -> $after) — log: $TMP/fc.log"; exit 1; fi
echo "QUIT CLEAN"
