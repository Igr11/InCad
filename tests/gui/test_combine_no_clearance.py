"""Boolean ▸ Cut with a tool that can't be grown by the clearance (the user: Cut with a mirrored Solid carrying an
Emboss 'doesn't work'; here a threaded pin): the dialog makes the cut with Clearance 0 mm, shows 0 mm, no error, and
the status line says why. Since only the tool's piece near the base is grown, the threaded pin's piece grows and
the clearance is kept: either way the cut is made without an error (the fallback itself: headless test_combine)."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    base = document.primary_body(doc())
    base.Tip = util.add_pad(base, util.add_rect_sketch(base, 40, 30, "BlockSk"), 10, "Block")
    tool = doc().addObject("PartDesign::Body", "Pin")
    sk = tool.newObject("Sketcher::SketchObject", "PinSk")
    sk.AttachmentSupport = [(util.xy_plane(tool), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(20, 15, 0), App.Vector(0, 0, 1), 4))
    pin = util.add_pad(tool, sk, 20, "PinPad")
    tool.Tip = pin
    doc().recompute()
    from incad.features import thread
    top = [i + 1 for i, fc in enumerate(pin.Shape.Faces) if fc.Surface.TypeId == "Part::GeomCylinder"][0]
    thread.create(doc(), tool, None, dict(thread.defaults(doc(), tool, None), face="%s:Face%d" % (pin.Name, top),
                                          size="M8"))
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["base"], ST["tool"] = base.Name, tool.Name


def test_1_cut_falls_back_to_no_clearance():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, ST["base"])
    Gui.Selection.addSelection(doc().Name, ST["tool"])
    r = commands.REGISTRY.run("feature.combine")
    harness.pump(3000)
    assert r.ok and dialog() is not None, r.error
    assert dialog().values()["operation"] == "cut"
    assert not dialog().error_text(), dialog().error_text()
    kept = not dialog().values()["clearance"].startswith("0 mm")  # the pin's piece near the block grown: kept
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    assert dialog() is None
    tip = doc().getObject(ST["base"]).Tip
    assert tip.TypeId == "PartDesign::Boolean" and "Invalid" not in tip.State, tip.State
    from incad.core import log
    text = open(log.log_path()).read() if hasattr(log, "log_path") else open(os.environ["INCAD_LOG"]).read()
    assert kept or "made with Clearance 0 mm" in text, text[-800:]


def test_9_cleanup():
    App.closeDocument(doc().Name)
    harness.pump(300)


harness.run([test_0_setup, test_1_cut_falls_back_to_no_clearance, test_9_cleanup])
