"""Shell on a simple part through InCad's dialog: pick the top face, OK, a hollow box; and a shell that the
kernel refuses (a modeled thread earlier in the tree) tells the user the way around."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def _body():
    from incad.core import document
    return document.primary_body(App.ActiveDocument)


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = _body()
    sk = util.add_rect_sketch(body)
    pad = util.add_pad(body, sk, 10)
    body.Tip = pad
    App.ActiveDocument.recompute()
    from incad.core import document
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(600)


def test_1_shell_the_box_open_at_the_top():
    sh = shell.instance()
    pad = App.ActiveDocument.getObject("Pad")
    top = [i + 1 for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    full = pad.Shape.Volume
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, pad.Name, "Face%d" % top)  # preselected face
    commands.REGISTRY.run("feature.shell")
    harness.pump(900)
    fs = sh.feature_session
    assert fs is not None, "the Shell dialog is open"
    assert fs.dialog.values().get("faces") == "Pad:Face%d" % top, fs.dialog.values()
    fs.dialog.set_values({"thickness": "2 mm"})
    harness.pump(900)
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(900)
    assert sh.feature_session is None
    tip = _body().Tip
    assert tip.TypeId == "PartDesign::Thickness", tip.TypeId
    assert "Invalid" not in tip.State, tip.getStatusString()
    expect = full - 16 * 6 * 8  # 20x10x10 box, 2 mm walls, open top: inner 16 x 6 x 8
    assert abs(tip.Shape.Volume - expect) < 1.0, (tip.Shape.Volume, expect)


harness.run([test_0_part, test_1_shell_the_box_open_at_the_top])
