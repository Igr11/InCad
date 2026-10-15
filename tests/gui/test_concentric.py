"""Sketch ▸ Concentric (user request): click two circles / arcs / ellipses and their centres are tied — real clicks in
an open sketch, for two circles and for an arc with an ellipse."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtWidgets  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def _click_sketch(sk, x, y):
    """A real left click at sketch point (x, y)."""
    from incad.qt import QtCore, QtGui
    from incad.ui import dof_handles
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    pos = QtCore.QPointF(*dof_handles.screen(view, vp, sk.getGlobalPlacement().multVec(App.Vector(x, y, 0))))
    L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
    for kind, button, buttons, ms in ((QtCore.QEvent.MouseMove, N, N, 250), (QtCore.QEvent.MouseButtonPress, L, L, 60),
                                      (QtCore.QEvent.MouseButtonRelease, L, N, 600)):
        QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, pos, QtCore.QPointF(vp.mapToGlobal(pos.toPoint())),
                                                                button, buttons, QtCore.Qt.NoModifier))
        harness.pump(ms)


def _centres_tied(sk, a, b):
    return any(c.Type == "Coincident" and {(c.First, c.FirstPos), (c.Second, c.SecondPos)} == {(a, 3), (b, 3)}
               for c in sk.Constraints)


def test_0_sketch():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    ST["doc"] = App.ActiveDocument.Name
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    shell.instance().plane_panel.button("XY_Plane").click()
    harness.pump(1200)
    assert Gui.ActiveDocument.getInEdit() is not None


def test_1_the_button_is_on_the_ribbon():
    button = shell.instance().ribbon.button("sketch.concentric")
    assert button is not None and button.isVisible(), shell.instance().ribbon.tab_names()


def test_2_two_circles_clicked_become_concentric():
    sk = Gui.ActiveDocument.getInEdit().Object
    a = sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10))
    b = sk.addGeometry(Part.Circle(App.Vector(30, 5, 0), App.Vector(0, 0, 1), 4))
    App.ActiveDocument.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    commands.REGISTRY.run("sketch.concentric")
    harness.pump(500)
    _click_sketch(sk, 10, 0)   # on the big circle
    _click_sketch(sk, 34, 5)   # on the small one
    harness.pump(600)
    App.ActiveDocument.recompute()
    assert _centres_tied(sk, a, b), [(c.Type, c.First, c.FirstPos, c.Second, c.SecondPos) for c in sk.Constraints]
    ca, cb = sk.Geometry[a].Center, sk.Geometry[b].Center
    assert (ca - cb).Length < 1e-6, (ca, cb)
    ST["a"], ST["b"] = a, b


def test_3_an_arc_and_an_ellipse_too():
    sk = Gui.ActiveDocument.getInEdit().Object
    from PySide6.QtTest import QTest
    from incad.qt import QtCore
    QTest.keyClick(Gui.getMainWindow(), QtCore.Qt.Key_Escape)  # the tool may stay on: end it
    harness.pump(400)
    arc = sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(60, 0, 0), App.Vector(0, 0, 1), 6), 0.3, 2.6))
    ell = sk.addGeometry(Part.Ellipse(App.Vector(78, 30, 0), App.Vector(70, 34, 0), App.Vector(70, 30, 0)))
    App.ActiveDocument.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    import math
    commands.REGISTRY.run("sketch.concentric")
    harness.pump(500)
    _click_sketch(sk, 60 + 6 * math.cos(1.4), 6 * math.sin(1.4))  # on the arc
    _click_sketch(sk, 70, 34)                                        # the ellipse's top
    harness.pump(600)
    App.ActiveDocument.recompute()
    assert _centres_tied(sk, arc, ell), [(c.Type, c.First, c.FirstPos, c.Second, c.SecondPos) for c in sk.Constraints]


def test_4_cleanup():
    shell.instance().sketches.finish()
    harness.pump(800)
    App.closeDocument(ST["doc"])
    harness.pump(400)


harness.run([test_0_sketch, test_1_the_button_is_on_the_ribbon, test_2_two_circles_clicked_become_concentric,
             test_3_an_arc_and_an_ellipse_too, test_4_cleanup])
