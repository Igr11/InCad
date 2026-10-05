#!/bin/zsh
# Model tests inside FreeCAD without a window (freecadcmd), with throwaway settings.
# Optional argument: file pattern, e.g. test_safe.py
REPO="${0:A:h:h}"
TMP="$(mktemp -d)"
INCAD_REPO="$REPO" INCAD_TEST_PATTERN="${1:-test_*.py}" INCAD_LOG="$TMP/incad.log" PYTHONDONTWRITEBYTECODE=1 \
  /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -u "$TMP/user.cfg" "$REPO/tests/headless_main.py"
