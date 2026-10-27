"""Rectangles drawn with the real Rectangle tools get a construction centre point (the user: symmetry with one
constraint; the diagonals show only while it is drawn): Rectangle, 3-Point and 3-Point Center get one; the Center
Rectangle keeps FreeCAD's own (no second one); the Rounded Rectangle's sits between its corner arcs' centres. One
Undo takes a rectangle with it. While a rectangle is drawn, its diagonals show
dashed over the rubber band from the first click (the user: orientation; incad.ui.rectangle_preview) and go with the
tool. The model rules: tests/headless."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import rectangle_preview, shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def sk():
    return App.ActiveDocument.getObject(ST["sk"])


def click(p):
    from PySide6.QtTest import QTest
    from incad.qt import QtCore
    from incad.ui import dof_handles as dh
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    x, y = dh.screen(view, vp, p)
    at = QtCore.QPoint(int(round(x)), int(round(y)))
    QTest.mouseMove(vp, at)
    harness.pump(150)
    QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
    harness.pump(400)


def construction(kind):
    return [i for i in range(sk().GeometryCount) if sk().getConstruction(i) and sk().Geometry[i].TypeId == kind]


def draw(cmd, *points):
    """(new non-construction elements, new diagonals, new construction points) after drawing with cmd."""
    g0, d0, p0 = sk().GeometryCount, len(construction("Part::GeomLineSegment")), len(construction("Part::GeomPoint"))
    commands.REGISTRY.run(cmd)
    harness.pump(1200)  # the tool and its mode are set up before the first click
    for p in points:
        click(p)
        harness.pump(300)
    harness.pump(800)
    commands.REGISTRY.run("sketch.stop")
    harness.pump(500)
    drawn = [i for i in range(g0, sk().GeometryCount) if not sk().getConstruction(i)]
    return drawn, len(construction("Part::GeomLineSegment")) - d0, len(construction("Part::GeomPoint")) - p0


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
    k = s().sketches.editing()
    k.addGeometry(Part.LineSegment(V(-60, -60, 0), V(60, -60, 0)))  # two lines to fit the view: no rectangle
    k.addGeometry(Part.LineSegment(V(60, -60, 0), V(60, 60, 0)))
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    ST["sk"] = k.Name


def test_1_every_rectangle_tool():
    for cmd, pts, want in (("sketch.rectangle", (V(-30, 5, 0), V(10, 25, 0)), (0, 1)),
                           ("sketch.rectangle_center", (V(30, -20, 0), V(40, -10, 0)), (0, 1)),  # FreeCAD's point
                           ("sketch.rectangle_3pt", (V(-50, 20, 0), V(-25, 30, 0), V(-30, 45, 0)), (0, 1)),
                           ("sketch.rectangle_center_3pt", (V(30, 30, 0), V(45, 36, 0), V(40, 48, 0)), (0, 1)),
                           # Rounded: FreeCAD's own two corner points + our centre point
                           ("sketch.rectangle_rounded", (V(-45, -45, 0), V(-15, -30, 0), V(-42, -42, 0)), (0, 3))):
        drawn, d, p = draw(cmd, *pts)
        assert len(drawn) >= 4, (cmd, "not drawn", drawn)
        assert (d, p) == want, (cmd, "diagonals, points", d, p)
        assert sk().solve() == 0, cmd


def hover(p):
    from PySide6.QtTest import QTest
    from incad.qt import QtCore
    from incad.ui import dof_handles as dh
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    x, y = dh.screen(view, vp, p)
    QTest.mouseMove(vp, QtCore.QPoint(int(round(x)), int(round(y))))
    harness.pump(300)


def shown():
    """The live diagonals' 4 ends as (x, y), or None while none show."""
    live = rectangle_preview._live
    if live is None or live.switch.whichChild.getValue() != 0:
        return None
    return [tuple(round(c, 1) for c in v.getValue()[:2]) for v in live.points.point.getValues()]


def test_1b_diagonals_while_drawing():
    for cmd, clicks, at in (("sketch.rectangle", [V(-30, -50, 0)], V(10, -40, 0)),
                            ("sketch.rectangle_3pt", [V(20, -55, 0), V(45, -45, 0)], V(42, -35, 0)),
                            ("sketch.rectangle_rounded", [V(-55, 45, 0)], V(-20, 58, 0))):
        commands.REGISTRY.run(cmd)
        harness.pump(1200)
        hover(clicks[0])
        assert shown() is None, (cmd, "before the first click", shown())
        for c in clicks:
            click(c)
        hover(at)
        hover(at + V(1, 1, 0))
        ends = shown()
        assert ends is not None, (cmd, "no diagonals while drawing")
        (a, b), (c, d) = (ends[0], ends[1]), (ends[2], ends[3])
        mid1 = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        mid2 = ((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)
        assert abs(mid1[0] - mid2[0]) < 0.2 and abs(mid1[1] - mid2[1]) < 0.2, (cmd, "they cross in the middle", ends)
        if cmd == "sketch.rectangle":
            assert any(abs(e[0] + 30) < 1.5 and abs(e[1] + 50) < 1.5 for e in ends), (cmd, "from the first corner", ends)
        commands.REGISTRY.run("sketch.stop")
        harness.pump(600)
        assert shown() is None, (cmd, "still shown after the tool")


def test_2_one_undo_takes_a_rectangle_with_it():
    before = sk().GeometryCount
    drawn, d, p = draw("sketch.rectangle", V(-55, 50, 0), V(-45, 55, 0))
    assert len(drawn) == 4 and (d, p) == (0, 1), (drawn, d, p)
    commands.REGISTRY.run("edit.undo")
    harness.pump(700)
    assert sk().GeometryCount == before, (before, sk().GeometryCount)


def test_9_cleanup():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_sketch, test_1_every_rectangle_tool, test_1b_diagonals_while_drawing,
             test_2_one_undo_takes_a_rectangle_with_it, test_9_cleanup])
