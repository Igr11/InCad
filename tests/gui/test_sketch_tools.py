import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402


def method():
    for w in QtWidgets.QApplication.allWidgets():
        if isinstance(w, QtWidgets.QComboBox) and w.objectName() == "comboBox1" and w.count():
            return w.currentText()
    return None


def test_0_sketch():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    shell.instance().plane_panel.button("XY_Plane").click()
    harness.pump(1200)
    assert Gui.ActiveDocument.getInEdit() is not None


def test_1_every_variant_starts_with_its_method():
    want = {"sketch.rectangle": "Corner, width, height", "sketch.rectangle_center": "Center, width, height",
            "sketch.rectangle_3pt": "3 corners", "sketch.rectangle_center_3pt": "Center, 2 corners",
            "sketch.circle": "Center", "sketch.circle_3pt": "3 rim points", "sketch.arc": "3 rim points",
            "sketch.arc_center": "Center", "sketch.slot_arc": "Arc ends", "sketch.slot_arc_flat": "Flat ends"}
    for cid in list(actions.SKETCH_VARIANTS) + list(want):
        if cid == "sketch.polygon_n":  # asks for the number of sides in a dialog: answer it
            from incad.qt import QtCore
            QtCore.QTimer.singleShot(600, lambda: QtWidgets.QApplication.activeModalWidget() and
                                     QtWidgets.QApplication.activeModalWidget().accept())
        res = commands.REGISTRY.run(cid)
        harness.pump(500)
        assert res.ok, (cid, res.error)
        if cid in want:
            assert method() == want[cid], (cid, method())
        commands.REGISTRY.run("sketch.stop")
        harness.pump(300)


def test_2_ribbon_split_button_remembers():
    rb = shell.instance().ribbon
    b = rb.button("sketch.rectangle")
    act = [a for a in b.menu().actions() if a.text() == "3-Point Rectangle"][0]
    act.trigger()
    harness.pump(500)
    assert method() == "3 corners", method()
    commands.REGISTRY.run("sketch.stop")
    harness.pump(300)
    assert b.text() == "3-Point Rectangle"


harness.run([test_0_sketch, test_1_every_variant_starts_with_its_method, test_2_ribbon_split_button_remembers])
