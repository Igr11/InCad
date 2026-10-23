"""3D Line in the window (the user's idea): the cube of points round the origin shows with the dialog; clicks on
cube points add the line's points; on a construction line the place under the pointer slides with grey distances
to the cube points either side; OK makes the line, and Sweep runs a circle along it."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.ui.line3d_tool import viewport_of  # noqa: E402
from incad.core import commands, document, line3d, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui import dof_handles as dh  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def test_0_new_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)


def click(p):
    """Hover then press at the screen place of p (a 3D point); what the press took."""
    ring = s()._overlay
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    x, y = dh.screen(view, vp, p)
    ring.hover(view, vp, x, y)
    hit = ring._hover
    took = ring.press(view, vp, x, y)
    ring.release()
    harness.pump(500)
    return hit, took


def test_1_click_points_of_the_cube():
    r = commands.REGISTRY.run("feature.line3d")
    harness.pump(1200)
    assert r.ok and dialog() is not None, r.error
    d = dialog()
    d.set_values({"size": "40 mm", "step": "10 mm", "shape": "through", "layer": "xy", "at": "20 mm"})
    d._emit()
    harness.pump(800)
    ring = s()._overlay
    assert ring is not None and ring.root is not None, "no cube"
    Gui.SendMsgToActiveView("ViewFit")
    Gui.ActiveDocument.ActiveView.viewTop()
    harness.pump(600)
    taken = []
    for p in (V(-20, -20, 20), V(0, -10, 20), V(10, 10, 20), V(20, 20, 20)):  # the top layer, seen from above
        hit, took = click(p)
        assert took and hit is not None and hit["kind"] == "point", (p, hit)
        taken.append(hit["point"])
    pts = line3d.parse_points(d.values()["points"])
    assert len(pts) == 4 and all(abs(a[2] - 20) < 1e-9 for a in pts), pts
    assert "4 points" in d.field("points").count.text(), d.field("points").count.text()
    # drag the second point: a click without a move changes nothing; dragged, it lands on a cube point, then on a
    # free place of a construction line
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    before = d.values()["points"]
    x, y = dh.screen(view, vp, V(0, -10, 20))
    ring.hover(view, vp, x, y)
    assert ring._hover is not None and ring._hover["kind"] == "grab", ring._hover
    assert ring.press(view, vp, x, y) and ring.dragging()
    ring.release()
    harness.pump(400)
    assert d.values()["points"] == before and "4 points" in d.field("points").count.text(), d.values()["points"]
    assert ring.press(view, vp, x, y)
    for t in (0.3, 0.7, 1.0):
        tx, ty = dh.screen(view, vp, V(0, -10 + 10 * t, 20))
        ring.move(tx, ty)
        harness.pump(150)
    ring.release()
    harness.pump(900)
    pts = line3d.parse_points(d.values()["points"])
    assert len(pts) == 4 and pts[1] == (0.0, 0.0, 20.0), pts
    f = s().feature_session.feature
    assert f.Shape.distToShape(__import__("Part").Vertex(V(0, 0, 20)))[0] < 1e-6, "the line not through the moved point"
    x, y = dh.screen(view, vp, V(0, 0, 20))
    assert ring.press(view, vp, x, y)
    tx, ty = dh.screen(view, vp, V(3.5, 0, 20))  # on the X line through (0, 0, 20): free
    ring.move(tx, ty)
    harness.pump(200)
    ring.release()
    harness.pump(900)
    pts = line3d.parse_points(d.values()["points"])
    assert abs(pts[1][0] - 3.5) < 0.6 and pts[1][1:] == (0.0, 20.0), pts
    # on a construction line between two cube points: slides freely, grey distances shown
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    x, y = dh.screen(view, vp, V(13, 20, 20))
    ring.hover(view, vp, x, y)
    h = ring._hover
    assert h is not None and h["kind"] == "line" and abs(h["point"][0] - 13) < 0.5, h
    assert ring._hover_sep.getNumChildren() >= 4, ring._hover_sep.getNumChildren()  # point, rubber line, 2 labels
    harness.pump(400)
    # the working layer: At's arrows move it a step of the cube; XZ goes through the last point
    d.step_buttons("at")[0].click()
    harness.pump(300)
    assert d.values()["at"] == "30 mm", d.values()["at"]
    d.step_buttons("at")[1].click()
    harness.pump(300)
    from PySide6.QtTest import QTest as T
    vp.setFocus()
    harness.pump(200)
    T.keyClick(vp, QtCore.Qt.Key_Backtab, QtCore.Qt.ShiftModifier)  # Shift+Tab: the layer a step down (the user)
    harness.pump(300)
    assert d.values()["at"] == "10 mm", d.values()["at"]
    T.keyClick(vp, QtCore.Qt.Key_Tab)  # Tab: back up
    harness.pump(300)
    assert d.values()["at"] == "20 mm", d.values()["at"]
    T.keyClick(vp, QtCore.Qt.Key_Tab)  # the top layer already: it stays in the cube
    harness.pump(300)
    assert d.values()["at"] == "20 mm", d.values()["at"]
    d.field("layer").button("xz").click()
    harness.pump(500)
    last = line3d.parse_points(d.values()["points"])[-1]
    assert d.values()["at"] == "%g mm" % last[1], (d.values()["at"], last)
    Gui.ActiveDocument.ActiveView.viewFront()
    harness.pump(400)
    hit = ring._snap(view, vp, *dh.screen(view, vp, V(0, last[1], 10)))
    assert hit is not None and abs(hit["point"][1] - last[1]) < 1e-9, hit  # on that layer
    d.field("layer").button("xy").click()
    harness.pump(300)
    top_dir = ring._depth_dir
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    assert ring._depth_dir is not None and ring._depth_dir.getAngle(top_dir) > 0.5, "the depths not redrawn"
    if os.environ.get("INNCAD_SHOT"):
        view.saveImage(os.environ["INNCAD_SHOT"].replace(".png", "_layer.png"), 900, 600, "Current")
    with_comb = ring.root.getNumChildren()
    d.set_values({"curvature": False})
    d._emit()
    harness.pump(900)
    assert ring.root.getNumChildren() == with_comb - 1, (with_comb, ring.root.getNumChildren())  # no comb
    d.set_values({"curvature": True})
    d._emit()
    harness.pump(900)
    assert ring.root.getNumChildren() == with_comb
    f = s().feature_session.feature
    ST["during"] = (f is not None and f.Visibility, f is not None and f.ViewObject.Visibility,
                    f is not None and not f.Shape.isNull(), f is not None and f.State)
    if os.environ.get("INNCAD_SHOT"):
        d.grab().save(os.environ["INNCAD_SHOT"])
        view.saveImage(os.environ["INNCAD_SHOT"].replace(".png", "_view.png"), 900, 600, "Current")
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert s().feature_session is None, (d.error_text(), s().feature_session.feature)
    line = [o for o in document.primary_body(doc()).Group if "InCadLine3D" in o.PropertiesList][0]
    assert not line.Shape.isNull() and line.Shape.Edges[0].Curve.TypeId == "Part::GeomBSplineCurve", line.Shape
    assert s()._overlay is None or s()._overlay.root is None, "the cube stays after OK"
    ST["line"] = line.Name
    vo = line.ViewObject
    assert line.Visibility and vo is not None and vo.Visibility, (line.Visibility, vo and vo.TypeId)
    assert vo.TypeId != "Gui::ViewProviderPythonFeature", vo.TypeId
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["vo"] = (vo.DisplayMode, vo.listDisplayModes(), vo.LineColor, vo.LineWidth, line.Shape.BoundBox,
                getattr(vo, "Proxy", None))
    if os.environ.get("INNCAD_SHOT"):
        Gui.ActiveDocument.ActiveView.saveImage(os.environ["INNCAD_SHOT"].replace(".png", "_after.png"), 900, 600,
                                                "Current")
    assert all(ST["during"][:3]), ST["during"]
    assert ST["vo"][0] == "Wireframe", ST["vo"]


def test_2_from_an_open_sketch():
    """The Sketch tab has 3D Line too (the user): from inside a sketch, the sketch is finished and 3D Line opens."""
    commands.REGISTRY.run("sketch.start")
    harness.pump(1200)
    if s().sketches.editing() is None:  # a plane to pick first: the XY plane
        from incad.core import document as d
        s().sketches.start_on(d.primary_body(doc()).Origin.OriginFeatures[3])
        harness.pump(1200)
    assert s().sketches.editing() is not None, "no sketch open"
    r = commands.REGISTRY.run("feature.line3d")
    harness.pump(1500)
    assert r.ok, r.error
    assert s().sketches.editing() is None and s().feature_session is not None, (s().sketches.editing(),
                                                                                 s().feature_session)
    assert s().feature_session.kind.TITLE == "3D Line"
    s().feature_session.cancel()
    harness.pump(500)


def test_9_cleanup():
    if s().feature_session is not None:
        s().feature_session.cancel()
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_new_part, test_1_click_points_of_the_cube, test_2_from_an_open_sketch, test_9_cleanup])
