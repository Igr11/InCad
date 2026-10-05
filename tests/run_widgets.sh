#!/bin/zsh
# Widget tests: plain PySide6 in FreeCAD's bundled Python, offscreen (no window, no FreeCAD).
REPO="${0:A:h:h}"
TMP="$(mktemp -d)"
cd "$REPO/tests" || exit 1
QT_QPA_PLATFORM=offscreen PYTHONPATH="$REPO/InCad:$REPO/tests" PYTHONDONTWRITEBYTECODE=1 INCAD_LOG="$TMP/incad.log" \
  /Applications/FreeCAD.app/Contents/Resources/bin/python -m unittest discover -s widgets -t . -p "${1:-test_*.py}" -v
