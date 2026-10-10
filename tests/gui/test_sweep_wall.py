"""Sweep's Wall option through the dialog: a tube with open ends, edited from the Sweep's own row, undone."""
import math
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
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def _body():
    from incad.core import document
    return document.primary_body(App.ActiveDocument)


def _sketch_on(body, role, name):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(next(o for o in body.Origin.OriginFeatures if o.Role == role), "")]
    sk.MapMode = "FlatFace"
    return sk


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = _body()
    prof = _sketch_on(body, "YZ_Plane", "Prof")
    prof.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
    path = _sketch_on(body, "XY_Plane", "Path")
    path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(40, 0, 0)))
    App.ActiveDocument.recompute()
    shell.instance().schedule_refresh()
    harness.pump(600)


def test_1_hollow_sweep_from_the_dialog():
    from incad.features import shapes
    sh = shell.instance()
    commands.REGISTRY.run("feature.sweep")
    harness.pump(800)
    fs = sh.feature_session
    assert fs is not None
    fs.dialog.set_pick("profile", "Prof")
    fs.dialog.set_pick("path", "Path")
    harness.pump(900)
    fs.dialog.set_values({"hollow": True, "wall": "1 mm", "ends": "both_open"})
    harness.pump(900)
    assert fs.dialog.error_text() == "", fs.dialog.error_text()
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(900)
    assert sh.feature_session is None
    body = _body()
    sweep = App.ActiveDocument.getObject("Sweep")
    wall = shapes.wall_of(sweep)
    assert wall is not None and body.Tip is wall
    expect = math.pi * (25 - 16) * 40
    assert abs(wall.Shape.Volume - expect) < 0.02 * expect, (wall.Shape.Volume, expect)
    rows = sh.browser.tree_rows()
    depth = {label: d for d, label, kind, state in rows}
    assert depth.get("SweepWall") == depth.get("Sweep") + 1, rows


def test_2_edit_from_the_sweeps_row_and_undo():
    from incad.features import shapes
    sh = shell.instance()
    sweep = App.ActiveDocument.getObject("Sweep")
    body = _body()
    before = body.Tip.Shape.Volume
    sh.browser.featureActivated.emit("Sweep")  # the double-click on the row
    harness.pump(900)
    fs = sh.feature_session
    assert fs is not None and fs.kind.TITLE == "Sweep"
    v = fs.dialog.values()
    assert v["hollow"] is True and v["wall"] == "1 mm" and v["ends"] == "both_open", v
    fs.dialog.set_values({"ends": "start_closed"})
    harness.pump(900)
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(900)
    after = body.Tip.Shape.Volume  # the cap is the last helper: the tip
    assert body.Tip.TypeId == "PartDesign::Pad" and body.Tip.InCadHelperOf == "Sweep", body.Tip.TypeId
    assert abs((after - before) - math.pi * 16 * 1) < 3.0, (before, after)
    commands.REGISTRY.run("edit.undo")
    harness.pump(900)
    assert body.Tip is shapes.wall_of(sweep) and abs(body.Tip.Shape.Volume - before) < 1e-3
    sh.browser.featureActivated.emit("SweepWall")  # a helper's row opens its Sweep
    harness.pump(900)
    assert sh.feature_session is not None and sh.feature_session.kind.TITLE == "Sweep"
    sh.feature_session.cancel()
    harness.pump(600)


harness.run([test_0_part, test_1_hollow_sweep_from_the_dialog, test_2_edit_from_the_sweeps_row_and_undo])
