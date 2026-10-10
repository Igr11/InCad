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


def test_2_the_real_part_offers_a_shell_before_the_thread():
    """The user's part: the kernel refuses the shell; the dialog explains and offers 'Shell before Thread';
    the button makes it with the thickest wall that works and says so."""
    from incad.core import document
    sh = shell.instance()
    path = os.path.join(os.environ["INCAD_REPO"], "tests", "gui", "data", "p2_test_reordered.FCStd")
    App.openDocument(path)
    harness.pump(2000)
    sh.schedule_refresh()
    harness.pump(800)
    body = document.primary_body(App.ActiveDocument)
    tip = body.Tip
    top = max((i for i, f in enumerate(tip.Shape.Faces) if abs(f.normalAt(0, 0).z - 1) < 1e-6),
              key=lambda i: tip.Shape.Faces[i].Area) + 1
    n0 = App.ActiveDocument.UndoCount  # before the dialog: its own pending step would count
    commands.REGISTRY.run("feature.shell")
    harness.pump(800)
    fs = sh.feature_session
    assert fs is not None
    fs.dialog.set_pick("faces", "%s:Face%d" % (tip.Name, top))
    fs.dialog.set_values({"thickness": "1.5 mm"})
    harness.pump(9000)
    assert "End of Part above the thread" in fs.dialog.error_text(), fs.dialog.error_text()
    assert fs.dialog.rescue_button.isVisible(), "the way around is offered"
    assert fs.dialog.rescue_button.text() == "Shell before Hole", fs.dialog.rescue_button.text()  # the first
    QTest.mouseClick(fs.dialog.rescue_button, QtCore.Qt.LeftButton)      # modeled thread here is the Hole's
    harness.pump(500)  # the rescue ran inside the click (three thread recomputes); the message is fresh
    assert sh.feature_session is None, "the dialog is gone"
    assert not [o for o in body.Group if o.TypeId == "PartDesign::Thickness"], "no wall works on this part"
    assert App.ActiveDocument.UndoCount == n0, (n0, App.ActiveDocument.UndoCount)
    assert body.Tip is tip and tip.Shape.isValid()
    msg = sh.status.texts()["message"]
    assert "and so do walls of 0.75 mm and 0.375 mm" in msg, msg


harness.run([test_0_part, test_1_shell_the_box_open_at_the_top, test_2_the_real_part_offers_a_shell_before_the_thread])
