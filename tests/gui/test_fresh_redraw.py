"""A sketch's view redraws as the mouse moves (the user: drawing lagged; FreeCAD postponed redraws while moves kept
coming — incad.ui.fresh_redraw): a move in an open sketch is drawn before the move returns, at most every
REDRAW_S."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import fresh_redraw  # noqa: E402

ST = {}


def renders_on_move(vp, n=5):
    """Redraws that happened inside n mouse moves (no event loop in between: a posted paint waits)."""
    from PySide6.QtTest import QTest
    from incad.qt import QtCore
    before = ST["count"][0]
    for i in range(n):
        time.sleep(fresh_redraw.REDRAW_S + 0.005)
        QTest.mouseMove(vp, QtCore.QPoint(200 + 7 * i, 200 + 5 * i))
    return ST["count"][0] - before


class _Paints:
    """Paint events the view's viewport gets (a redraw is one)."""

    def __init__(self, vp):
        from incad.qt import QtCore

        class F(QtCore.QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QtCore.QEvent.Paint:
                    ST["count"][0] += 1
                return False
        self.f = F()
        vp.installEventFilter(self.f)


def counter(view):
    ST["count"] = [0]
    ST["paints"] = _Paints(view.graphicsView().viewport())


def test_0_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    counter(Gui.ActiveDocument.ActiveView)


def test_1_in_a_sketch_each_move_is_drawn():
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    Gui.Selection.addSelection(doc.Name, xy.Name)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    vp = Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    fresh_redraw.detach_all()
    harness.pump(300)
    without = renders_on_move(vp)
    fresh_redraw.attach_all()
    harness.pump(300)
    with_it = renders_on_move(vp)
    assert with_it >= 4 and with_it > without, (without, with_it)


def test_9_cleanup():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_part, test_1_in_a_sketch_each_move_is_drawn, test_9_cleanup])
