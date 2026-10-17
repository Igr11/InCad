"""Placing a distance with FreeCAD's Dimension tool: FreeCAD picks horizontal / vertical / aligned from where the
cursor is against the box of the two points and flips the instant the cursor crosses a side of it (the user: "it's
jumping between aligned and axis parallels too fast"). InCad holds the type until the cursor is DEAD_PX past the
side, both ways."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import dimension_place, dof_handles, shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}
L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["doc"])


def sketch():
    return doc().getObject(ST["sk"])


def view():
    return Gui.getDocument(ST["doc"]).ActiveView


def viewport():
    return view().graphicsView().viewport()


def send(kind, pos, button, buttons):
    vp = viewport()
    glob = QtCore.QPointF(vp.mapToGlobal(pos.toPoint()))
    QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, pos, glob, button, buttons, QtCore.Qt.NoModifier))


def screen(x, y):
    """Viewport position (logical px) of sketch point (x, y)."""
    p = sketch().getGlobalPlacement().multVec(App.Vector(x, y, 0))
    return QtCore.QPointF(*dof_handles.screen(view(), viewport(), p))


def move(pos, steps=6):
    """A steady move from the last position to `pos` (FreeCAD reacts to every move event)."""
    start = ST.get("at", pos)
    for k in range(1, steps + 1):
        send(QtCore.QEvent.MouseMove, start + (pos - start) * (k / steps), N, N)
        harness.pump(60)
    ST["at"] = pos
    harness.pump(200)


def last_type():
    return sketch().Constraints[-1].Type


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    ST["doc"] = App.ActiveDocument.Name
    body = document.primary_body(doc())
    sk = util.add_rect_sketch(body, 20, 6, name="Rect")  # its bottom line: the box from (0, 0) to (20, 0)
    doc().recompute()
    ST["sk"] = sk.Name
    s().sketches.edit(sk)
    harness.pump(1200)
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)


def test_1_the_type_holds_until_the_cursor_is_clearly_past_the_side():
    count = len(sketch().Constraints)
    bottom = next(i for i, e in enumerate(sketch().Shape.Edges, 1)
                  if abs(e.Vertexes[0].Point.y) < 1e-9 and abs(e.Vertexes[-1].Point.y) < 1e-9)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sketch().Name, "Edge%d" % bottom)  # the line picked before the tool
    harness.pump(300)
    ST["at"] = screen(10, -2)
    commands.REGISTRY.run("sketch.dimension")  # with a line selected: its dimension follows the cursor at once
    harness.pump(800)
    px = (screen(1, 0) - screen(0, 0)).x()  # logical px per mm
    above = screen(10, 0).y() + 4 * dimension_place.DEAD_PX  # well below the bottom line (outside the rectangle)
    right = screen(20, 0).x()  # the box's right side on screen
    move(QtCore.QPointF(right - 4 * dimension_place.DEAD_PX, above), steps=10)
    assert len(sketch().Constraints) == count + 1, ("the selected line's dimension is being placed",
                                                     [c.Type for c in sketch().Constraints], px)
    assert last_type() == "DistanceX", (last_type(), px)
    near = dimension_place.DEAD_PX / 3
    move(QtCore.QPointF(right + near, above))  # just past the side: FreeCAD alone flips to aligned here
    assert last_type() == "DistanceX", ("held inside the dead zone", last_type(), px)
    move(QtCore.QPointF(right + 2 * dimension_place.DEAD_PX, above))
    assert last_type() == "Distance", ("clearly past: aligned", last_type())
    move(QtCore.QPointF(right - near, above))  # just back over the side
    assert last_type() == "Distance", ("held on the way back too", last_type())
    move(QtCore.QPointF(right - 2 * dimension_place.DEAD_PX, above))
    assert last_type() == "DistanceX", last_type()


def click(pos):
    move(pos)
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    harness.pump(80)
    send(QtCore.QEvent.MouseButtonRelease, pos, L, N)
    harness.pump(500)


def test_2_a_second_line_picked_while_the_first_one_s_length_follows_makes_an_angle():
    """The user (Windows and Mac): angles were hard to dimension. After the first line FreeCAD shows that line's
    length following the cursor; the dead zone held the cursor FreeCAD sees, so the second line under the real
    cursor was not picked. Near other geometry the cursor is never held."""
    import math
    import Sketcher
    Gui.runCommand("Sketcher_StopOperation")
    harness.pump(400)
    if s().value_box is not None:
        s().value_box.close()
        harness.pump(300)
    sk = sketch()
    slanted = sk.addGeometry(Part.LineSegment(App.Vector(20, 0, 0), App.Vector(30, -8, 0)))  # from the corner
    sk.addConstraint(Sketcher.Constraint("Coincident", 0, 2, slanted, 1))
    doc().recompute()
    harness.pump(400)
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    for second, at, want, place in ((1, (20, 3), 90.0, (16, 3)), (slanted, (24, -3.2), 38.66, (24, -1))):
        Gui.Selection.clearSelection()
        count = len(sk.Constraints)
        ST["at"] = screen(10, -6)
        commands.REGISTRY.run("sketch.dimension")
        harness.pump(600)
        click(screen(10, 0))  # the bottom line: its length follows the cursor
        move(screen(10, -4), steps=6)
        move(screen(at[0] - 2, at[1] - 1), steps=8)
        click(screen(*at))  # the other line from the same corner: on the side of the length's box
        move(screen(*place), steps=6)
        click(screen(*place))  # place the angle
        harness.pump(600)
        added = [(c.Type, c.First, c.Second) for c in sk.Constraints[count:]]
        angles = [c for c in sk.Constraints[count:] if c.Type == "Angle"]
        assert len(angles) == 1, (second, added)
        deg = math.degrees(angles[0].Value) % 180
        assert min(abs(deg - want), abs(deg - (180 - want))) < 0.05, (second, deg)
        assert {angles[0].First, angles[0].Second} == {0, second}, (second, added)
        Gui.runCommand("Sketcher_StopOperation")
        harness.pump(400)
        if s().value_box is not None:
            s().value_box.close()
            harness.pump(300)


def test_3_cleanup():
    Gui.runCommand("Sketcher_StopOperation")
    harness.pump(400)
    if s().value_box is not None:
        s().value_box.close()
        harness.pump(300)
    s().sketches.finish()
    harness.pump(800)
    App.closeDocument(ST["doc"])
    harness.pump(500)


harness.run([test_0_setup, test_1_the_type_holds_until_the_cursor_is_clearly_past_the_side,
             test_2_a_second_line_picked_while_the_first_one_s_length_follows_makes_an_angle, test_3_cleanup])
