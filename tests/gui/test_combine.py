import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
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
    sk = util.add_rect_sketch(base, 40, 30, "BlockSk")
    base.Tip = util.add_pad(base, sk, 10, "Block")
    tool = doc().addObject("PartDesign::Body", "Pin")
    sk2 = tool.newObject("Sketcher::SketchObject", "PinSk")
    sk2.AttachmentSupport = [(util.xy_plane(tool), "")]
    sk2.MapMode = "FlatFace"
    sk2.addGeometry(Part.Circle(App.Vector(20, 15, 0), App.Vector(0, 0, 1), 4))
    tool.Tip = util.add_pad(tool, sk2, 20, "PinPad")
    doc().recompute()
    ST["base"], ST["tool"] = base.Name, tool.Name
    harness.pump(300)


def select_both():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, ST["base"])
    Gui.Selection.addSelection(doc().Name, ST["tool"])


def test_1_cancel_leaves_nothing():
    names = {o.Name for o in doc().Objects}
    select_both()
    commands.REGISTRY.run("feature.combine")
    harness.pump(1000)
    assert dialog() is not None and not dialog().error_text(), dialog() and dialog().error_text()
    dialog().field("apply_to").button("split").click()
    harness.pump(1000)
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert {o.Name for o in doc().Objects} == names, {o.Name for o in doc().Objects} ^ names


def test_2_cut_with_a_fit_copy():
    undo = len(doc().UndoNames)
    select_both()
    commands.REGISTRY.run("feature.combine")
    harness.pump(1000)
    assert dialog().values()["base"] == ST["base"] and dialog().values()["tools"] == ST["tool"], dialog().values()
    dialog().field("apply_to").button("tool").click()
    harness.pump(1000)
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    base = doc().getObject(ST["base"])
    assert base.Tip.TypeId == "PartDesign::Boolean", base.Tip.TypeId
    assert [b.Label for b in document.bodies(doc()) if b.Label.endswith(" fit")] == ["Pin fit"]
    assert doc().getObject(ST["tool"]) is not None
    assert doc().UndoNames[0] == "Boolean" and len(doc().UndoNames) == undo + 1, doc().UndoNames


harness.run([test_0_setup, test_1_cancel_leaves_nothing, test_2_cut_with_a_fit_copy])
