"""Boolean: the second solid (the tool) is picked by clicking anywhere on it in the view, as in Inventor (user
request). Real mouse events on the 3D view, not a programmatic selection."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def doc():
    return App.ActiveDocument


def dialog():
    fs = shell.instance().feature_session
    return fs.dialog if fs is not None else None


def _send(kind, pos, button, buttons):
    vp = Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    types = {"press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease,
             "move": QtCore.QEvent.MouseMove}
    ev = QtGui.QMouseEvent(types[kind], pos, QtCore.QPointF(vp.mapToGlobal(pos.toPoint())), button, buttons,
                           QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)
    harness.pump(120)


def click_on(obj_name, points):
    """A real left click on the first of `points` (3D) where the view shows `obj_name`."""
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    for p in points:
        sx, sy = view.getPointOnViewport(p)
        info = view.getObjectInfo((int(sx), int(sy)))
        parent = info.get("ParentObject") if info else None
        names = (info["Object"], getattr(parent, "Name", "")) + tuple((info.get("SubName") or "").split(".")) \
            if info else ()
        if obj_name in names:
            dpr = vp.devicePixelRatioF()
            pos = QtCore.QPointF(sx / dpr, vp.height() - sy / dpr)
            _send("move", pos, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
            _send("press", pos, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
            _send("release", pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
            harness.pump(500)
            return info
    seen = [view.getObjectInfo(tuple(int(c) for c in view.getPointOnViewport(p))) for p in points]
    raise AssertionError("%s is not under any of the points: %s" % (obj_name, seen))


def test_0_a_block_and_a_pin_beside_it():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    base = document.primary_body(doc())
    base.Tip = util.add_pad(base, util.add_rect_sketch(base, 40, 30, "BlockSk"), 10, "Block")
    tool = document.new_solid(doc())
    pin = tool.newObject("PartDesign::AdditiveCylinder", "Pin")
    pin.Radius, pin.Height = 5, 20
    pin.Placement = App.Placement(App.Vector(60, 15, 0), App.Rotation())
    tool.Tip = pin
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    ST.update(base=base.Name, tool=tool.Name, pin=pin.Name)


def test_1_a_click_anywhere_on_the_pin_makes_it_the_tool():
    Gui.Selection.clearSelection()
    harness.pump(200)
    commands.REGISTRY.run("feature.combine")
    harness.pump(1000)
    assert dialog() is not None
    assert dialog().values()["base"] == ST["base"], dialog().values()
    click_on(ST["pin"], [App.Vector(60, 15, 20), App.Vector(60, 15, 10), App.Vector(63, 15, 15),
                         App.Vector(57, 12, 18)])
    assert dialog().values()["tools"] == ST["tool"], (dialog().values(), dialog().error_text())
    assert dialog().values()["base"] == ST["base"], dialog().values()


def test_2_a_click_on_the_base_does_not_make_it_a_tool():
    click_on(ST["base"], [App.Vector(10, 10, 10), App.Vector(20, 15, 10), App.Vector(30, 20, 10)])
    assert dialog().values()["tools"] == ST["tool"], dialog().values()

    shell.instance().feature_session.cancel()
    harness.pump(500)

harness.run([test_0_a_block_and_a_pin_beside_it, test_1_a_click_anywhere_on_the_pin_makes_it_the_tool,
             test_2_a_click_on_the_base_does_not_make_it_a_tool])
