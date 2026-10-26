"""Work features on a 3D Line that really goes in three dimensions (the user: a sketch at the line's start for a loft;
check the 3D line in real 3D): every point of the line changes x, y and z, its segments are skew to every axis. A
Point field shows the line's ends and the points it passes through as markers; a corner of the line is kept as that
corner (the feature follows the line), a point inside a spline as a fixed point. A segment clicked in the view is
an edge; the plane square to it at its end, a circle sketched there and swept along the line: the line hides as a
used sketch does. A double-click on a work plane in the view opens its Work Plane dialog, never a sketch."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, line3d as core_line, prefs  # noqa: E402
from incad.features import line3d, work  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}
POLY = [V(0, 0, 0), V(10, 20, 30), V(40, 10, 50), V(30, -20, 70)]
SPLINE = [V(50, 0, 0), V(60, 15, 20), V(45, 30, 45), V(70, 10, 60)]


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def poly():
    return doc().getObject(ST["poly"])


def _line(points, shape):
    values = dict(line3d.defaults(doc(), body()), shape=shape,
                  points=core_line.format_points([tuple(p) for p in points]))
    f = line3d.create(doc(), body(), None, values)
    doc().recompute()
    return f


def _move_poly(i, p):
    pts = list(POLY)
    pts[i] = p
    line3d.update(doc(), poly(), dict(line3d.read(doc(), poly()),
                                      points=core_line.format_points([tuple(q) for q in pts])))
    doc().recompute()
    return pts


def _settle(ms=10000):
    waited = 0
    while waited < ms:
        fs = s().feature_session
        if fs is None or (not fs._previewing and not fs._timer.isActive()):
            return
        harness.pump(100)
        waited += 100


def _ok(d, what):
    _settle()
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    for _ in range(100):
        if s().feature_session is None:
            break
        harness.pump(100)
    assert s().feature_session is None, "%s: OK refused: %r" % (what, d.error_text())


def normal(f):
    return f.Placement.Rotation.multVec(V(0, 0, 1))


def parallel(a, b):
    a, b = V(a).normalize(), V(b).normalize()
    return abs(abs(a.dot(b)) - 1) < 1e-6


def test_0_part_and_lines():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 10, 10, 5
    box.Placement = App.Placement(V(-30, -30, 0), App.Rotation())  # out of the lines' way
    doc().recompute()
    ST["poly"] = _line(POLY, "polyline").Name
    ST["spline"] = _line(SPLINE, "through").Name
    for p in POLY:  # really 3D: no two segments in one plane with an axis
        assert p.x != 0 or p.y != 0 or p.z != 0 or p == POLY[0]
    e = poly().Shape.Edges
    assert len(e) == 3 and all(abs(x.tangentAt(x.FirstParameter).x) > 1e-3 and abs(x.tangentAt(x.FirstParameter).y)
                               > 1e-3 and abs(x.tangentAt(x.FirstParameter).z) > 1e-3 for x in e), \
        "the test line has a segment along a coordinate plane"
    Gui.SendMsgToActiveView("ViewIsometric")
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)


def _new(kind, mode):
    Gui.Selection.clearSelection()
    commands.REGISTRY.run(kind)
    harness.pump(1000)
    d = dialog()
    assert d is not None
    w = d.field("mode")
    w.setCurrentIndex(w.findData(mode))
    harness.pump(600)
    return d


def _click_marker(p):
    from incad.ui import dof_handles as dh
    from incad.ui.plane_turn import viewport_of
    pk = s()._point_pick
    assert pk is not None, "no markers"
    assert any((p - q).Length < 1e-6 for q in pk.points), ("no marker at", p)
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    x, y = dh.screen(view, vp, p)
    assert s()._point_clicked(vp, x, y) is True, "the marker click was not taken"
    harness.pump(1200)


def _markers(d, key, points):
    QTest.mouseClick(d.field(key), QtCore.Qt.LeftButton)
    harness.pump(800)
    for p in points:
        _click_marker(p)


def _newest(type_id="PartDesign::Plane"):
    return sorted((o for o in body().Group if o.TypeId == type_id), key=lambda o: o.Name)[-1]


def test_1_every_point_of_both_lines_is_a_marker():
    d = _new("work.plane", "parallel_point")
    QTest.mouseClick(d.field("point"), QtCore.Qt.LeftButton)
    harness.pump(800)
    pk = s()._point_pick
    for p in POLY + SPLINE:
        assert pk is not None and any((p - q).Length < 1e-6 for q in pk.points), ("missing marker", p)
    QTest.mouseClick(d.cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)


def test_2_parallel_to_xy_through_a_corner_follows_the_line():
    d = _new("work.plane", "parallel_point")
    xy = [o for o in body().Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    d.set_pick("base", xy.Name)
    harness.pump(800)
    _markers(d, "point", [POLY[1]])
    assert d.values()["point"] == "%s:Vertex2" % ST["poly"], d.values()["point"]
    _ok(d, "Parallel through a 3D Line's corner")
    plane = _newest()
    assert abs(plane.Placement.Base.z - 30) < 1e-6, plane.Placement
    _move_poly(1, V(12, 18, 36))
    assert abs(plane.Placement.Base.z - 36) < 1e-6, ("the plane did not follow the line", plane.Placement)
    _move_poly(1, POLY[1])
    ST["parallel"] = plane.Name


def test_3_normal_to_the_spline_at_a_point_inside():
    d = _new("work.plane", "normal_edge")
    d.set_pick("edge", "%s:Edge1" % ST["spline"])
    harness.pump(800)
    _markers(d, "point", [SPLINE[2]])
    assert d.values()["point"].startswith("@"), d.values()["point"]
    _ok(d, "Normal to the spline at an inner point")
    plane = _newest()
    assert (plane.Placement.Base - SPLINE[2]).Length < 1e-6, plane.Placement
    edge = doc().getObject(ST["spline"]).Shape.Edges[0]
    tangent = edge.tangentAt(edge.Curve.parameter(SPLINE[2]))
    assert abs(tangent.x) > 1e-3 and abs(tangent.y) > 1e-3 and abs(tangent.z) > 1e-3, ("not a 3D tangent", tangent)
    assert parallel(normal(plane), tangent), (normal(plane), tangent)


def test_4_normal_to_a_clicked_segment_at_its_end_follows_the_line():
    from incad.ui import dof_handles as dh
    from incad.ui.plane_turn import viewport_of
    d = _new("work.plane", "normal_edge")
    QTest.mouseClick(d.field("edge"), QtCore.Qt.LeftButton)
    harness.pump(600)
    seg = poly().Shape.Edges[1]  # POLY[1] -> POLY[2], skew to every axis
    Gui.Selection.clearSelection()
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    x, y = dh.screen(view, vp, seg.valueAt((seg.FirstParameter + seg.LastParameter) / 2))
    at = QtCore.QPoint(int(round(x)), int(round(y)))
    QTest.mouseMove(vp, at)
    harness.pump(300)
    QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)  # a real click on the segment
    harness.pump(1000)
    assert d.values()["edge"] == "%s:Edge2" % ST["poly"], d.values()["edge"]
    _markers(d, "point", [POLY[2]])
    assert d.values()["point"] == "%s:Vertex3" % ST["poly"], d.values()["point"]
    _ok(d, "Normal to a 3D Line's segment at its end")
    plane = _newest()
    assert (plane.Placement.Base - POLY[2]).Length < 1e-6, plane.Placement
    assert parallel(normal(plane), POLY[2] - POLY[1]), (normal(plane), POLY[2] - POLY[1])
    moved = V(45, 5, 60)
    _move_poly(2, moved)
    assert (plane.Placement.Base - moved).Length < 1e-6, ("the plane did not follow the line", plane.Placement)
    assert parallel(normal(plane), moved - POLY[1]), "the plane is no longer square to the moved segment"
    _move_poly(2, POLY[2])


def test_5_three_points_on_both_lines():
    d = _new("work.plane", "three_points")
    _markers(d, "points", [POLY[0], POLY[2], SPLINE[2]])
    items = d.values()["points"].split(",")
    assert items[0] == "%s:Vertex1" % ST["poly"] and items[1] == "%s:Vertex3" % ST["poly"], items
    _ok(d, "Three points on the 3D Lines")
    plane = _newest()
    n = (POLY[2] - POLY[0]).cross(SPLINE[2] - POLY[0])
    assert parallel(normal(plane), n), (normal(plane), n)
    assert abs((plane.Placement.Base - POLY[0]).dot(V(n).normalize())) < 1e-6, plane.Placement


def test_6_axis_through_the_lines_ends():
    d = _new("work.axis", "two_points")
    _markers(d, "points", [POLY[0], POLY[3]])
    assert d.values()["points"] == "%s:Vertex1,%s:Vertex4" % (ST["poly"], ST["poly"]), d.values()["points"]
    _ok(d, "Axis through the 3D Line's ends")
    axis = _newest("PartDesign::Line")
    assert parallel(axis.Placement.Rotation.multVec(V(0, 0, 1)), POLY[3] - POLY[0]), axis.Placement


def test_7_double_click_a_work_plane_in_the_view_opens_its_dialog():
    """A real double-click on the plane where it is the frontmost thing: its Work Plane dialog, no sketch."""
    from incad.ui.plane_turn import viewport_of
    plane = doc().getObject(ST["parallel"])
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    dpr = vp.devicePixelRatioF()
    g = plane.Placement
    hit = None
    for u in range(-8, 9, 2):
        for w in range(-8, 9, 2):
            p = g.multVec(V(u, w, 0))
            sx, sy = view.getPointOnViewport(p)
            info = view.getObjectInfo((int(sx), int(sy)))
            if info and info.get("Object") == plane.Name:
                hit = QtCore.QPoint(int(round(sx / dpr)), int(round(vp.height() - sy / dpr)))
                break
        if hit is not None:
            break
    assert hit is not None, "the work plane is frontmost nowhere near its middle"
    Gui.Selection.clearSelection()
    QTest.mouseMove(vp, hit)
    harness.pump(400)
    QTest.mouseDClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, hit)
    harness.pump(1500)
    assert s().sketches.editing() is None, "a sketch started"
    fs = s().feature_session
    assert fs is not None and fs.feature is plane, ("no Work Plane dialog", fs and fs.feature.Name,
                                                    getattr(Gui.Selection.getPreselection(), "ObjectName", None))
    QTest.mouseClick(fs.dialog.cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)


def test_8_sketch_at_the_start_and_sweep_along_the_line():
    """The user's way: a plane square to the line at its start, a circle on it, Sweep along the line; the used line
    hides as a used sketch does."""
    k = work.PLANE
    start = k.create(doc(), body(), None, dict(k.defaults(doc(), body(), None), mode="normal_edge",
                                               edge="%s:Edge1" % ST["poly"], point="%s:Vertex1" % ST["poly"]))
    doc().recompute()
    assert parallel(normal(start), POLY[1] - POLY[0]), normal(start)
    sk = body().newObject("Sketcher::SketchObject", "Ring")
    sk.AttachmentSupport = [(start, "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 2))
    doc().recompute()
    assert poly().Visibility, "the 3D Line is not shown before the Sweep"
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.sweep")
    harness.pump(1000)
    d = dialog()
    assert d is not None, "no Sweep dialog"
    d.set_pick("profile", sk.Name)
    d.set_pick("path", ST["poly"])
    harness.pump(1500)
    _ok(d, "Sweep along the 3D Line")
    sweep = [o for o in body().Group if o.TypeId.startswith("PartDesign::") and "Pipe" in o.TypeId][-1]
    assert "Invalid" not in sweep.State, sweep.getStatusString()
    length = sum(e.Length for e in poly().Shape.Edges)
    assert sweep.Shape.Volume > 0.8 * math.pi * 4 * length, (sweep.Shape.Volume, math.pi * 4 * length)
    assert not poly().Visibility, "the 3D Line the Sweep used stays shown (a used sketch hides)"


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_part_and_lines, test_1_every_point_of_both_lines_is_a_marker,
             test_2_parallel_to_xy_through_a_corner_follows_the_line,
             test_7_double_click_a_work_plane_in_the_view_opens_its_dialog,  # before other planes cover it
             test_3_normal_to_the_spline_at_a_point_inside,
             test_4_normal_to_a_clicked_segment_at_its_end_follows_the_line, test_5_three_points_on_both_lines,
             test_6_axis_through_the_lines_ends,
             test_8_sketch_at_the_start_and_sweep_along_the_line, test_9_cleanup])
