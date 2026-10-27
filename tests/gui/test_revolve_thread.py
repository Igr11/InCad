"""Revolve ▸ Cut through a tapped Hole's modeled thread, in the dialog, on the user's part (gui/data/p2_test.FCStd:
Sketch5 is a slot over the hole's rim). The kernel can't cut through the thread: the revolve goes before the Hole by
itself, and on OK the part is whole, cut, with its threads (incad.core.thread_order)."""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def dialog():
    fs = shell.instance().feature_session
    return fs.dialog if fs is not None else None


def wait(cond, seconds=90):
    end = time.time() + seconds
    while time.time() < end:
        harness.pump(300)
        if cond():
            return True
    return False


def test_0_open_the_users_part():
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["tmp"] = tempfile.mkdtemp()
    path = os.path.join(ST["tmp"], "p2_test.FCStd")
    shutil.copy(os.path.join(os.environ["INCAD_REPO"], "tests", "gui", "data", "p2_test.FCStd"), path)
    App.openDocument(path)
    harness.pump(2000)
    doc = App.ActiveDocument
    ST["before"] = document.primary_body(doc).Tip.Shape.Volume


def test_1_revolve_cut_over_the_tapped_hole_goes_before_it():
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Sketch004")
    commands.REGISTRY.run("feature.revolve")
    assert wait(lambda: dialog() is not None and shell.instance().feature_session.feature is not None)
    assert list(dialog().field("operation")._buttons) == ["join", "cut", "new_solid"]  # the user: no Auto
    QTest.mouseClick(dialog().field("operation").button("cut"), QtCore.Qt.LeftButton)

    def placed():
        f = shell.instance().feature_session.feature
        return f is not None and f.TypeId == "PartDesign::Groove" and f in body.Group \
            and body.Group.index(f) < body.Group.index(doc.Hole)
    assert wait(placed), [o.Name for o in body.Group]
    harness.pump(1500)
    assert dialog()._error.text() == "", dialog()._error.text()
    f = shell.instance().feature_session.feature
    assert f.BaseFeature is doc.Extrude001, f.BaseFeature.Name
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    assert wait(lambda: shell.instance().feature_session is None)
    harness.pump(1500)
    tip = body.Tip
    assert tip is doc.ThreadChamfer, tip.Name
    assert not [o.Name for o in body.Group if "Invalid" in o.State]
    assert tip.Shape.isValid()
    assert tip.Shape.Volume < ST["before"] - 100, (tip.Shape.Volume, ST["before"])
    assert tip.Visibility and body.Visibility  # the finished part is on screen, threads and the cut
    App.closeDocument(doc.Name)
    shutil.rmtree(ST["tmp"], ignore_errors=True)


harness.run([test_0_open_the_users_part, test_1_revolve_cut_over_the_tapped_hole_goes_before_it])
