"""Sketch ▸ Overall Dimension in a real window: one click on a slot's side dimensions the slot end to end (40), the
value box opens on it and a typed value changes the slot; two clicks on two circles dimension their outer edges."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def sketch():
    return Gui.ActiveDocument.getInEdit().Object


def click(sk, x, y):
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
    sk = sketch()
    commands.REGISTRY.run("sketch.slot_overall")
    harness.pump(400)
    for x, y in ((-30, 20), (10, 20), (-10, 25)):  # 40 long, 10 wide
        click(sk, x, y)
    shell.instance()._on_escape()
    harness.pump(500)
    ST["arcs"] = [i for i, g in enumerate(sk.Geometry) if g.TypeId == "Part::GeomArcOfCircle"]
    assert len(ST["arcs"]) == 2, ST


def test_1_one_click_on_a_slot_dimensions_it_end_to_end():
    sh = shell.instance()
    sk = sketch()
    res = commands.REGISTRY.run("sketch.dimension_overall")
    assert res.ok, res.error
    harness.pump(400)
    click(sk, -10, 25)  # the slot's upper side
    harness.pump(600)
    dims = [c for c in sk.Constraints if c.Type == "Distance" and c.Name]
    assert len(dims) == 1 and abs(dims[0].Value - 40.0) < 0.5, [(c.Name, c.Value) for c in dims]
    assert sh.slot_tool is None  # one dimension, then the tool ends
    assert sh.value_box is not None and sh.value_box.name == dims[0].Name
    ST["name"] = dims[0].Name


def test_2_a_typed_value_changes_the_slot():
    sh = shell.instance()
    sh.value_box.edit.setText("50")
    sh.value_box.edit.returnPressed.emit()
    harness.pump(800)
    sk = sketch()
    a, b = ST["arcs"]
    c1, c2 = sk.Geometry[a].Center, sk.Geometry[b].Center
    overall = (c2 - c1).Length + 2 * sk.Geometry[a].Radius
    assert abs(overall - 50.0) < 1e-4, overall
    assert abs(sk.Geometry[a].Radius - 5.0) < 0.5, (sk.Geometry[a].Radius, (c2 - c1).Length)  # the width is not what changed


def test_3_two_circles_by_their_outer_edges():
    sk = sketch()
    a = sk.addGeometry(Part.Circle(App.Vector(-30, -20, 0), App.Vector(0, 0, 1), 3))
    b = sk.addGeometry(Part.Circle(App.Vector(10, -20, 0), App.Vector(0, 0, 1), 5))
    App.ActiveDocument.recompute()
    harness.pump(400)
    commands.REGISTRY.run("sketch.dimension_overall")
    harness.pump(400)
    click(sk, -30, -17)
    click(sk, 10, -15)
    harness.pump(600)
    dims = [c for c in sk.Constraints if c.Type == "Distance" and c.Name and c.Name != ST["name"]]
    assert len(dims) == 1 and abs(dims[0].Value - 48.0) < 0.5, [(c.Name, c.Value) for c in dims]
    shell.instance()._on_escape()
    harness.pump(300)


def test_4_the_value_box_switches_a_gap_to_overall_and_centers():
    """FreeCAD's own Dimension on a slot's two arcs measures the gap between them (the user's screenshot): the
    value box offers Centers / Overall / Gap, and Overall turns it into the slot's end-to-end length."""
    import Sketcher
    from PySide6.QtTest import QTest
    from incad.core import sketch as sketches
    sh = shell.instance()
    sk = sketch()
    c1, c2, r = __import__("incad.core.slots", fromlist=["x"]).overall(App.Vector(-30, 60, 0), App.Vector(10, 60, 0),
                                                                        App.Vector(-10, 65, 0))
    a1, a2, l1, l2 = __import__("incad.core.slots", fromlist=["x"]).add(sk, c1, c2, r)
    sk.addConstraint(Sketcher.Constraint("Distance", a1, 0, a2, 0, 20.0))
    sketches.name_new_dimensions(App.ActiveDocument)
    name = sk.Constraints[sk.ConstraintCount - 1].Name
    App.ActiveDocument.recompute()
    harness.pump(400)
    sh.open_value_box(sk, name)
    harness.pump(300)
    box = sh.value_box
    assert set(box.kind_buttons) == {"centers", "overall", "gap"} and box.kind_buttons["gap"].isChecked()
    QTest.mouseClick(box.kind_buttons["overall"], QtCore.Qt.LeftButton)
    harness.pump(600)
    box = sh.value_box
    assert box is not None and box.name == name and box.kind_buttons["overall"].isChecked()
    c = [c for c in sk.Constraints if c.Name == name][0]
    assert abs(c.Value - 40.0) < 1e-4, c.Value
    QTest.mouseClick(box.kind_buttons["centers"], QtCore.Qt.LeftButton)
    harness.pump(600)
    c = [c for c in sk.Constraints if c.Name == name][0]
    assert abs(c.Value - 30.0) < 1e-4 and (c.FirstPos, c.SecondPos) == (3, 3), (c.Value, c.FirstPos)
    sh._close_value_box()
    harness.pump(300)


harness.run([test_0_sketch, test_1_one_click_on_a_slot_dimensions_it_end_to_end, test_2_a_typed_value_changes_the_slot,
             test_3_two_circles_by_their_outer_edges, test_4_the_value_box_switches_a_gap_to_overall_and_centers])
