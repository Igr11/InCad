#!/bin/zsh
# Widget + headless suites (no FreeCAD window). The GUI suite is tests/run_gui.sh.
HERE="${0:A:h}"
"$HERE/run_widgets.sh" && "$HERE/run_headless.sh"
