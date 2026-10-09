"""The sketch's Pattern group: InCad's own Rectangular and Circular Pattern dialogs on sketch geometry, picks
made in the sketch, live copies, Cancel leaving the sketch as it was."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, prefs, sketch_patterns as sp  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def sk():
    return Gui.ActiveDocument.getInEdit().Object


def pick(key, sub):
    if dialog().active_pick() != key:
        dialog().field(key).click()
        harness.pump(400)
    assert dialog().active_pick() == key, dialog().active_pick()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, sub)
    harness.pump(900)


def test_0_sketch_with_a_hole_and_two_limits():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    s().plane_panel.button("XY_Plane").click()
    harness.pump(1200)
    k = sk()
    ST["hole"] = k.addGeometry(Part.Circle(App.Vector(6, 5, 0), App.Vector(0, 0, 1), 2))
    k.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, ST["hole"], 3, 6.0))
    k.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, ST["hole"], 3, 5.0))
    ST["left"] = k.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0)), True)
    ST["right"] = k.addGeometry(Part.LineSegment(App.Vector(40, 0, 0), App.Vector(40, 10, 0)), True)
    App.ActiveDocument.recompute()
    harness.pump(300)
    ST["geo"] = k.GeometryCount


def test_1_rectangular_pattern_from_the_ribbon_with_picks_in_the_sketch():
    Gui.Selection.clearSelection()
    res = commands.REGISTRY.run("sketch.rect_pattern")
    harness.pump(1200)
    assert res.ok, res.error
    assert dialog() is not None, "InCad's own dialog, not FreeCAD's array tool"
    assert dialog().values()["geometry"] == "", dialog().values()
    assert "Click the geometry to repeat" in dialog().error_text(), dialog().error_text()
    assert not dialog().ok_button.isEnabled()
    pick("geometry", "Edge%d" % (ST["hole"] + 1))
    w = dialog().field("count1")
    w.setText("3")
    w.editingFinished.emit()
    harness.pump(900)
    assert not dialog().error_text(), dialog().error_text()
    assert sk().GeometryCount == ST["geo"] + 2, sk().GeometryCount  # the preview is real geometry
    assert Gui.ActiveDocument.getInEdit() is not None, "the sketch stays open under the dialog"
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert dialog() is None
    assert len(sp.records(sk())) == 1
    ST["pattern"] = sp.records(sk())[0]["name"]
    assert sk().GeometryCount == ST["geo"] + 2


def test_2_cancel_leaves_the_sketch_as_it_was():
    before = sk().GeometryCount
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge%d" % (ST["hole"] + 1))
    commands.REGISTRY.run("sketch.circ_pattern")
    harness.pump(1200)
    assert dialog().values()["geometry"].endswith("Edge%d" % (ST["hole"] + 1)), "the selection is seeded"
    assert not dialog().error_text(), dialog().error_text()
    assert sk().GeometryCount > before
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert sk().GeometryCount == before, (sk().GeometryCount, before)
    assert len(sp.records(sk())) == 1


def test_3_equal_spacing_between_the_two_lines():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.rect_pattern")
    harness.pump(1000)
    pick("geometry", "Edge%d" % (ST["hole"] + 1))
    dialog().set_values({"fit1": "faces", "count1": "3"})
    harness.pump(500)
    assert dialog().field("from1").isVisible() and not dialog().field("dir1").isVisible()
    pick("from1", "Edge%d" % (ST["left"] + 1))
    pick("to1", "Edge%d" % (ST["right"] + 1))
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    rec = sp.records(sk())[-1]
    last = sp.index_of(sk(), rec["copies"][-1][0])
    assert abs(sp.point_of(sk(), last, 3).x - 34.0) < 1e-3, sp.point_of(sk(), last, 3)


def test_4_the_ribbon_has_both_next_to_mirror():
    rb = s().ribbon
    for cid in ("sketch.rect_pattern", "sketch.circ_pattern", "sketch.mirror"):
        assert rb.button(cid) is not None, cid


def test_5_double_click_on_a_copy_opens_edit_pattern_and_count_changes():
    k = sk()
    rec = sp.find(k, ST["pattern"])
    copy = sp.index_of(k, rec["copies"][0][0])
    Gui.Selection.clearSelection()
    # a double-click in the view lands on a preselected element: emulate FreeCAD's preselection, then the hook
    set_ok = Gui.Selection.setPreselection(k, "Edge%d" % (copy + 1))  # setPreselection(obj, subName, x=0, y=0, z=0, type=1)
    harness.pump(200)
    pre = Gui.Selection.getPreselection()
    seen = (getattr(pre, "Object", None) and pre.Object.Name, list(getattr(pre, "SubElementNames", ()) or ()),
            set_ok, sp.is_copy(k, copy), sp.pattern_of(k, copy))
    view = Gui.ActiveDocument.ActiveView
    handled = s()._dblclick_hook(view, None, 10, 10)
    harness.pump(1200)
    assert handled, "the double-click on a copy is taken; preselection seen: %r" % (seen,)
    assert dialog() is not None and dialog().values()["count1"] == "3", dialog().values()
    w = dialog().field("count1")
    w.setText("5")
    w.editingFinished.emit()
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert len(sp.find(k, ST["pattern"])["copies"]) == 4


def test_6_delete_pattern_leaves_the_original():
    k = sk()
    rec = sp.find(k, ST["pattern"])
    copy = sp.index_of(k, rec["copies"][0][0])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, k.Name, "Edge%d" % (copy + 1))
    harness.pump(300)
    res = commands.REGISTRY.run("sketch.delete_pattern")
    harness.pump(800)
    assert res.ok, res.error
    assert sp.find(k, ST["pattern"]) is None
    assert k.getGeometryId(ST["hole"]) is not None and k.Geometry[ST["hole"]].TypeId == "Part::GeomCircle"
    App.ActiveDocument.undo()
    harness.pump(500)
    assert sp.find(k, ST["pattern"]) is not None, "Delete Pattern is one undo step"
    App.ActiveDocument.redo()
    harness.pump(500)


harness.run([test_0_sketch_with_a_hole_and_two_limits, test_1_rectangular_pattern_from_the_ribbon_with_picks_in_the_sketch,
             test_2_cancel_leaves_the_sketch_as_it_was, test_3_equal_spacing_between_the_two_lines,
             test_4_the_ribbon_has_both_next_to_mirror, test_5_double_click_on_a_copy_opens_edit_pattern_and_count_changes,
             test_6_delete_pattern_leaves_the_original])
