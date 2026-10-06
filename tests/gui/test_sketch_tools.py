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
    assert b.property("incad_cmd") == "sketch.rectangle_3pt", b.property("incad_cmd")  # remembered (label "Rectangle")


def test_3_hide_and_show_constraints_from_the_menu():
    import Part
    import Sketcher
    from incad.core import sketch
    from incad.ui import marking_layout
    sk = Gui.ActiveDocument.getInEdit().Object
    a = sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)))
    sk.addConstraint(Sketcher.Constraint("Horizontal", a))
    sk.addConstraint(Sketcher.Constraint("DistanceX", a, 1, a, 2, 20))
    App.ActiveDocument.recompute()
    assert "sketch.constraints_toggle" in marking_layout.LAYOUT["sketch"]["list"]
    commands.REGISTRY.run("sketch.constraints_toggle")
    harness.pump(400)
    assert sketch.constraints_hidden(sk)
    Gui.ActiveDocument.ActiveView.saveImage(os.environ.get("INCAD_SHOT", "/tmp/incad_sketch.png"), 800, 500, "Current")
    commands.REGISTRY.run("sketch.constraints_show")
    harness.pump(400)
    assert not sketch.constraints_hidden(sk)


def test_4_overall_slot_by_three_clicks():
    sh = shell.instance()
    sk = Gui.ActiveDocument.getInEdit().Object
    before = sk.GeometryCount
    commands.REGISTRY.run("sketch.slot_overall")
    harness.pump(400)
    tool = sh.slot_tool
    assert tool is not None
    view = Gui.ActiveDocument.ActiveView
    pl = sk.getGlobalPlacement()
    for x, y in ((-30, 40), (0, 40), (-15, 44)):
        sx, sy = view.getPointOnViewport(pl.multVec(App.Vector(x, y, 0)))
        tool._event({"Type": "SoLocation2Event", "Position": (int(sx), int(sy))})
        tool._event({"Type": "SoMouseButtonEvent", "Button": "BUTTON1", "State": "DOWN",
                     "Position": (int(sx), int(sy))})
        harness.pump(200)
    App.ActiveDocument.recompute()
    assert sk.GeometryCount == before + 4, (before, sk.GeometryCount)
    import Part
    bb = Part.Compound([g.toShape() for g in sk.Geometry[before:]]).BoundBox
    assert abs(bb.XMin - (-30)) < 0.5 and abs(bb.XMax - 0) < 0.5 and abs(bb.YLength - 8) < 0.5, bb
    sh._on_escape()
    harness.pump(300)
    assert sh.slot_tool is None


def test_5_construction_button_toggles_the_drawing_mode():
    import Part
    sh = shell.instance()
    sk = Gui.ActiveDocument.getInEdit().Object
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.construction")
    harness.pump(300)
    assert sh.construction_mode and sh.ribbon.button("sketch.construction").isChecked()
    g = sk.addGeometry(Part.LineSegment(App.Vector(50, 0, 0), App.Vector(60, 0, 0)))
    App.ActiveDocument.recompute()
    harness.pump(500)
    assert sk.getConstruction(g), "drawn in construction mode"
    commands.REGISTRY.run("sketch.construction")
    harness.pump(300)
    assert not sh.construction_mode and not sh.ribbon.button("sketch.construction").isChecked()
    g2 = sk.addGeometry(Part.LineSegment(App.Vector(50, 5, 0), App.Vector(60, 5, 0)))
    App.ActiveDocument.recompute()
    harness.pump(500)
    assert not sk.getConstruction(g2), "back to normal"



def test_6_one_picked_side_switches_the_whole_polygon():
    from ProfileLib import RegularPolygon
    sk = Gui.ActiveDocument.getInEdit().Object
    first = sk.GeometryCount
    RegularPolygon.makeRegularPolygon(sk, 6, App.Vector(100, 0, 0), App.Vector(110, 0, 0), False)
    App.ActiveDocument.recompute()
    harness.pump(300)
    sides = [i for i in range(first, sk.GeometryCount) if sk.Geometry[i].TypeId == "Part::GeomLineSegment"]
    assert len(sides) == 6, sides
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk.Name, "Edge%d" % (sides[2] + 1))
    commands.REGISTRY.run("sketch.construction")
    harness.pump(500)
    assert all(sk.getConstruction(i) for i in sides), [sk.getConstruction(i) for i in sides]
    assert not shell.instance().construction_mode  # a selection switches geometry, not the drawing mode
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk.Name, "Edge%d" % (sides[4] + 1))
    commands.REGISTRY.run("sketch.construction")
    harness.pump(500)
    assert not any(sk.getConstruction(i) for i in sides), [sk.getConstruction(i) for i in sides]



def test_7_a_polygon_drawn_on_the_origin_keeps_its_centre_there():
    from ProfileLib import RegularPolygon
    sk = Gui.ActiveDocument.getInEdit().Object
    first = sk.GeometryCount
    RegularPolygon.makeRegularPolygon(sk, 6, App.Vector(0, 0, 0), App.Vector(9, 2, 0), False)
    App.ActiveDocument.recompute()
    harness.pump(800)
    circle = [i for i in range(first, sk.GeometryCount) if sk.Geometry[i].TypeId == "Part::GeomCircle"][0]
    tied = [c for c in sk.Constraints if c.Type == "Coincident" and c.First == circle and c.FirstPos == 3
            and c.Second == -1]
    assert len(tied) == 1, [(c.Type, c.First, c.FirstPos, c.Second) for c in sk.Constraints]



def test_8_double_click_with_a_deleted_preselection_is_ignored():
    """FreeCAD can hand back a preselection whose object was just deleted ('Object already deleted' in the log)."""
    from incad.ui import shell

    class Dead:
        def __getattr__(self, name):
            raise RuntimeError("Object already deleted")
    real = Gui.Selection.getPreselection
    Gui.Selection.getPreselection = lambda: Dead()
    try:
        assert shell.instance()._preselected_dimension() == (None, None)
    finally:
        Gui.Selection.getPreselection = real



def test_9_sketch_handlers_ignore_a_sketch_deleted_meanwhile():
    """They run just after a sketch changes; the sketch may be gone by then (an assembly placing parts did it)."""
    from incad.ui import shell
    from incad.core import log
    doc = App.ActiveDocument
    sk = doc.addObject("Sketcher::SketchObject", "Gone")
    doc.removeObject(sk.Name)
    seen = []
    log.set_reporter(lambda level, msg: seen.append(msg))
    try:
        shell.instance()._pin_new_polygons(sk)
        shell.instance()._make_construction(sk)
    finally:
        log.set_reporter(shell.instance()._report)
    assert not seen, seen


harness.run([test_0_sketch, test_1_every_variant_starts_with_its_method, test_2_ribbon_split_button_remembers,
             test_3_hide_and_show_constraints_from_the_menu, test_4_overall_slot_by_three_clicks,
             test_5_construction_button_toggles_the_drawing_mode,
             test_6_one_picked_side_switches_the_whole_polygon,
             test_7_a_polygon_drawn_on_the_origin_keeps_its_centre_there,
             test_8_double_click_with_a_deleted_preselection_is_ignored,
             test_9_sketch_handlers_ignore_a_sketch_deleted_meanwhile])
