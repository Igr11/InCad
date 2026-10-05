#!/bin/zsh
# Widget + headless suites (no FreeCAD window). The GUI suite is tests/run_gui.sh.
HERE="${0:A:h}"
if "$HERE/run_widgets.sh" && "$HERE/run_headless.sh"; then echo "FAST SUITES PASSED"; else echo "FAST SUITES FAILED"; exit 1; fi
