import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCADGui as Gui  # noqa: E402


def test_workbench_registered():
    assert "InCadWorkbench" in Gui.listWorkbenches(), sorted(Gui.listWorkbenches())


harness.run([test_workbench_registered])
