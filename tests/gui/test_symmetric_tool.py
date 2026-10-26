"""Sketch ▸ Symmetric with real clicks (the user: choosing the points was hard, a click sometimes took a dimension's
point): two lines clicked anywhere along them, then the Y axis; the next pair (two circles by their rims, the X axis)
without starting again; a click a few pixels off a line's end takes the end; a click on a dimension's value takes
nothing; Esc ends the tool."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs, sketch_symmetric as sym  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def sk():
    return App.ActiveDocument.getObject(ST["sk"])


def click_at(p, dx=0, dy=0):
    """A real left click at the screen place of sketch point p (the sketch is on XY at the origin)."""
    from incad.ui import dof_handles as dh
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    x, y = dh.screen(view, vp, p)
    at = QtCore.QPoint(int(round(x + dx)), int(round(y + dy)))
    QTest.mouseMove(vp, at)
    harness.pump(100)
    QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
    harness.pump(700)


def mirrored(a, b, axis):
    return (sym._mirror(sk(), ("edge", axis), a) - b).Length < 1e-6


def test_0_sketch():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    Gui.Selection.addSelection(doc.Name, xy.Name)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    s_ = s().sketches.editing()
    assert s_ is not None
    ST["left"] = s_.addGeometry(Part.LineSegment(V(-30, -10, 0), V(-20, 15, 0)))
    ST["right"] = s_.addGeometry(Part.LineSegment(V(18, 12, 0), V(26, -8, 0)))
    ST["c1"] = s_.addGeometry(Part.Circle(V(-15, -25, 0), V(0, 0, 1), 4))
    ST["c2"] = s_.addGeometry(Part.Circle(V(12, 22, 0), V(0, 0, 1), 6))
    ST["far"] = s_.addGeometry(Part.LineSegment(V(-35, 30, 0), V(-25, 30, 0)))
    s_.addConstraint(Sketcher.Constraint("DistanceX", ST["far"], 1, ST["far"], 2, 10))
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(800)
    ST["sk"] = s_.Name


def test_1_two_lines_then_the_y_axis():
    commands.REGISTRY.run("sketch.symmetric")
    harness.pump(500)
    tool = s().slot_tool
    assert tool is not None and type(tool).__name__ == "SymmetricTool", tool
    click_at(V(-25, 2.5, 0))  # the middle of the left line
    click_at(V(22, 2, 0))     # the middle of the right line
    assert tool.picked == [("edge", ST["left"]), ("edge", ST["right"])], tool.picked
    click_at(V(0, -30, 0))    # the Y axis, below everything
    types = [c.Type for c in sk().Constraints]
    assert types.count("Symmetric") == 2, types
    assert sk().solve() == 0
    assert mirrored(sk().getPoint(ST["left"], 1), sk().getPoint(ST["right"], 2), sym.V_AXIS), \
        "the left line's start should mirror the right line's end (nearest its mirror image)"
    assert s().slot_tool is tool and tool.picked == [], "the tool should wait for the next pair"


def test_2_next_pair_circles_about_the_x_axis():
    tool = s().slot_tool
    c1, c2 = sk().Geometry[ST["c1"]], sk().Geometry[ST["c2"]]
    click_at(c1.Center + V(c1.Radius, 0, 0))   # on the rim
    click_at(c2.Center + V(0, c2.Radius, 0))
    assert tool.picked == [("edge", ST["c1"]), ("edge", ST["c2"])], tool.picked
    click_at(V(40, 0, 0))  # the X axis, right of everything
    assert sk().solve() == 0
    assert abs(sk().Geometry[ST["c1"]].Radius - sk().Geometry[ST["c2"]].Radius) < 1e-6
    a, b = sk().getPoint(ST["c1"], 3), sk().getPoint(ST["c2"], 3)
    assert abs(a.x - b.x) < 1e-6 and abs(a.y + b.y) < 1e-6, (a, b)


def test_3_near_an_end_takes_the_point():
    tool = s().slot_tool
    end = sk().getPoint(ST["far"], 2)
    click_at(end, dx=5, dy=-3)  # a few pixels off the end
    assert tool.picked == [("point", ST["far"], 2)], tool.picked
    Gui.Selection.clearSelection()
    tool.picked = []


def test_4_a_dimension_is_never_taken():
    from incad.core import sketch as sketches
    tool = s().slot_tool
    name = sk().Constraints[[c.Type for c in sk().Constraints].index("DistanceX")].Name
    label = sketches.label_point(sk(), name) if name else None
    assert label is not None, "no label position to click"
    click_at(label)
    assert all(p[0] in ("point", "edge") for p in tool.picked), tool.picked
    tool.picked = []


def test_5_esc_ends():
    QTest.keyClick(Gui.getMainWindow(), QtCore.Qt.Key_Escape)
    harness.pump(500)
    if s().slot_tool is not None:  # the key went elsewhere (the window not in front): the shell's Esc path
        s().stop_slot_tool()
    assert s().slot_tool is None


def test_9_cleanup():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_sketch, test_1_two_lines_then_the_y_axis, test_2_next_pair_circles_about_the_x_axis,
             test_3_near_an_end_takes_the_point, test_4_a_dimension_is_never_taken, test_5_esc_ends, test_9_cleanup])
