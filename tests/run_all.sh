#!/bin/zsh
# Every test suite. GUI tests open FreeCAD windows: keep hands off mouse and keyboard while they run.
HERE="${0:A:h}"
rc=0
echo "### widgets";  "$HERE/run_widgets.sh"  || rc=1
echo "### headless"; "$HERE/run_headless.sh" || rc=1
echo "### gui";      "$HERE/run_gui.sh"      || rc=1
echo "### quit";     for m in key app window; do INCAD_QUIT=$m "$HERE/run_quit.sh" || rc=1; done
(( rc == 0 )) && echo "ALL SUITES PASSED" || echo "SOME SUITES FAILED"
exit $rc
