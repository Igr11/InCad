"""Every Work Plane method through its dialog, as the user works (the user: find all the bugs with planes): picks by
selection and by clicks on the marked points, OK; the reopened dialog shows what was set and OK leaves the plane where
it is; Cancel of an edit puts it back; a row of planes goes with Cancel and with Undo; deleting a row's first plane
leaves the others working."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.features import work  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def box():
    return doc().getObject(ST["box"])


def face_at(z):
    return "Face%d" % [i + 1 for i, f in enumerate(box().Shape.Faces)
                       if abs(f.CenterOfMass.z - z) < 1e-6 and abs(abs(f.normalAt(0, 0).z) - 1) < 1e-9][0]


def edge_between(a, b):
    for i, e in enumerate(box().Shape.Edges):
        ends = [v.Point for v in e.Vertexes]
        if any((x - a).Length < 1e-6 for x in ends) and any((x - b).Length < 1e-6 for x in ends):
            return "Edge%d" % (i + 1)
    raise LookupError((a, b))


def planes():
    return [o for o in body().Group if o.TypeId == "PartDesign::Plane"]


def normal(o):
    return o.Placement.Rotation.multVec(V(0, 0, 1))


def test_0_box():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    b = body().newObject("PartDesign::AdditiveBox", "Box")
    b.Length, b.Width, b.Height = 20, 10, 6
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["box"] = b.Name


def _open(mode):
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("work.plane")
    harness.pump(1000)
    d = dialog()
    assert d is not None, "no Work Plane dialog"
    w = d.field("mode")
    w.setCurrentIndex(w.findData(mode))
    harness.pump(600)
    return d


def _select(d, key, sub):
    """The field active, then a click's selection on the box (or a whole object for a plane / axis row)."""
    d.set_active_pick(key)
    harness.pump(300)
    Gui.Selection.clearSelection()
    if sub.startswith(("Face", "Edge", "Vertex")):
        Gui.Selection.addSelection(doc().Name, body().Name, "%s.%s" % (ST["box"], sub))
    else:
        Gui.Selection.addSelection(doc().Name, body().Name, "%s.%s." % (body().Origin.Name, sub))
    harness.pump(900)
    _settle()


def _markers(d, key, points):
    from incad.ui import dof_handles as dh
    from incad.ui.plane_turn import viewport_of
    QTest.mouseClick(d.field(key), QtCore.Qt.LeftButton)
    harness.pump(800)
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    for p in points:
        pk = s()._point_pick
        assert pk is not None, "no markers for %s" % key
        x, y = dh.screen(view, vp, p)
        assert s()._point_clicked(vp, x, y) is True, ("marker not taken", p)
        harness.pump(500)
    harness.pump(800)


def _settle(ms=10000):
    """Until the dialog's preview is done (a busy machine makes it seconds), at most ms."""
    waited = 0
    while waited < ms:
        fs = s().feature_session
        if fs is None or (not fs._previewing and not fs._timer.isActive()):
            return
        harness.pump(100)
        waited += 100


def _type(d, key, text):
    """Typed as the user does: the field's text replaced, then Tab (Enter is OK)."""
    w = d.field(key)
    w.setFocus()
    w.selectAll()
    QTest.keyClicks(w, text)
    QTest.keyClick(w, QtCore.Qt.Key_Tab)
    harness.pump(1000)  # a typed value previews after the dialog's 600 ms pause (Tab needs the window's focus)
    _settle()


def _ok(d, what):
    _settle()
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    for _ in range(100):  # OK during a preview is taken when the preview ends
        if s().feature_session is None:
            break
        harness.pump(100)
    fs = s().feature_session
    assert fs is None, "%s: OK refused: %r; previewing %s, after %s, then %s, closed %s, timer %s, active %s, applied %s" % (
        what, d.error_text(), fs._previewing, fs._after_preview, fs._then, fs._closed, fs._timer.isActive(),
        d.active_pick(), fs._applied)


def _xy():
    return [o for o in body().Origin.OriginFeatures if o.Role == "XY_Plane"][0]


def _made(what, before):
    new = [o for o in planes() if o.Name not in before]
    assert new, "%s: no plane made" % what
    f = sorted(new, key=lambda o: o.Name)[0]
    assert "Invalid" not in f.State, "%s: %s" % (what, f.getStatusString())
    return f


def _round_trip(what, f, expect):
    """Reopen: the dialog shows what was set; OK unchanged leaves the plane where it was."""
    before = App.Placement(f.Placement)
    s().edit_feature(f)
    harness.pump(1200)
    d = dialog()
    assert d is not None, "%s: no dialog on reopening" % what
    shown = d.values()
    for k, v in expect.items():
        assert shown.get(k) == v, "%s: the dialog shows %s = %r, was %r" % (what, k, shown.get(k), v)
    _ok(d, what + " (reopened)")
    after = f.Placement
    assert (after.Base - before.Base).Length < 1e-6 and after.Rotation.isSame(before.Rotation, 1e-9), \
        "%s: OK on the reopened dialog moved the plane %s -> %s" % (what, before, after)


def _case(what, mode, fill, check, expect):
    before = {o.Name for o in planes()}
    d = _open(mode)
    fill(d)
    _ok(d, what)
    f = _made(what, before)
    check(f)
    _round_trip(what, f, dict(expect, mode=mode))
    ST.setdefault("made", []).append(f.Name)


def test_1_offset():
    def fill(d):
        _select(d, "base", face_at(6))
        d.set_values({"offset": "-2 mm"})
        harness.pump(500)
        _settle()

    def check(f):
        assert abs(f.Placement.Base.z - 4) < 1e-6, f.Placement
    _case("Offset -2 from the top", "offset", fill, check, {"base": "%s:%s" % (ST["box"], face_at(6))})


def test_2_parallel_through_point():
    def fill(d):
        _select(d, "base", "XY_Plane")
        _markers(d, "point", [V(20, 10, 6)])

    def check(f):
        assert abs(f.Placement.Base.z - 6) < 1e-6 and abs(normal(f).z) > 1 - 1e-9, f.Placement
    _case("Parallel through point", "parallel_point", fill, check, {"base": _xy().Name})


def test_3_midplane():
    def fill(d):
        _select(d, "base", face_at(6))
        _select(d, "base2", face_at(0))

    def check(f):
        assert abs(f.Placement.Base.z - 3) < 1e-6, f.Placement
    _case("Midplane", "midplane", fill, check, {"base": "%s:%s" % (ST["box"], face_at(6)),
                                                "base2": "%s:%s" % (ST["box"], face_at(0))})


def test_4_angle_around_edge():
    def fill(d):
        _select(d, "base", face_at(6))
        _select(d, "edge", edge_between(V(0, 0, 6), V(20, 0, 6)))
        d.set_values({"angle": "30 °"})
        harness.pump(900)

    def check(f):
        assert abs(math.degrees(normal(f).getAngle(V(0, 0, 1))) - 30) < 1e-6, normal(f)
    _case("Angle around edge", "angle", fill, check, {"angle": "30 °"})


def test_5_angle_around_an_origin_axis():
    def fill(d):
        _select(d, "base", "XY_Plane")
        _select(d, "edge", "X_Axis")
        d.set_values({"angle": "45 °"})
        harness.pump(900)

    def check(f):
        assert abs(math.degrees(normal(f).getAngle(V(0, 0, 1))) - 45) < 1e-6, normal(f)
    _case("Angle around the X axis", "angle", fill, check, {"angle": "45 °"})


def test_6_three_points():
    def fill(d):
        _markers(d, "points", [V(0, 0, 6), V(20, 0, 6), V(0, 10, 0)])

    def check(f):
        n = normal(f)
        want = (V(20, 0, 0)).cross(V(0, 10, -6)).normalize()
        assert abs(abs(n.dot(want)) - 1) < 1e-6, (n, want)
    _case("Three points", "three_points", fill, check, {})


def test_7_normal_to_edge():
    def fill(d):
        _select(d, "edge", edge_between(V(20, 10, 0), V(20, 10, 6)))
        _markers(d, "point", [V(20, 10, 6)])

    def check(f):
        assert (f.Placement.Base - V(20, 10, 6)).Length < 1e-6 and abs(normal(f).z) > 1 - 1e-9, f.Placement
    _case("Normal to edge at point", "normal_edge", fill, check, {})


def test_8_tangent():
    def fill(d):
        _select(d, "face", face_at(6))
        _markers(d, "point", [V(20, 10, 6)])

    def check(f):
        assert abs(f.Placement.Base.z - 6) < 1e-6 and abs(normal(f).z) > 1 - 1e-9, f.Placement
    _case("Tangent to surface at point", "tangent", fill, check, {})


def test_9_cancel_an_edit_puts_it_back():
    f = doc().getObject(ST["made"][0])
    before = App.Placement(f.Placement)
    s().edit_feature(f)
    harness.pump(1200)
    d = dialog()
    d.set_values({"offset": "-4 mm", "turn_x": "20 °"})
    harness.pump(1500)
    QTest.mouseClick(d.cancel_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert s().feature_session is None
    assert (f.Placement.Base - before.Base).Length < 1e-6 and f.Placement.Rotation.isSame(before.Rotation, 1e-9), \
        ("Cancel left the plane moved", before, f.Placement)


def test_10_a_row_goes_with_cancel_and_with_undo():
    before = {o.Name for o in planes()}
    d = _open("offset")
    _select(d, "base", "XY_Plane")
    _type(d, "count", "3")
    fs = s().feature_session
    print("ROWDEBUG applied", fs._applied, "pending", fs._pending, "previewing", fs._previewing, "feature",
          fs.feature and fs.feature.Name, fs.feature and work._load(fs.feature), "timer", fs._timer.isActive())
    assert len(planes()) == len(before) + 3, ("no preview of the row", "applied", fs._applied, "pending", fs._pending,
                                              d.values(), d.error_text(),
                                              [o.Name for o in planes()], sorted(before))
    QTest.mouseClick(d.cancel_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert {o.Name for o in planes()} == before, ("Cancel left planes", [o.Name for o in planes()])
    d = _open("offset")
    _select(d, "base", "XY_Plane")
    d.set_values({"offset": "10 mm", "count": "3"})
    harness.pump(1500)
    _ok(d, "a row of 3")
    assert len(planes()) == len(before) + 3
    commands.REGISTRY.run("edit.undo")
    harness.pump(1200)
    assert {o.Name for o in planes()} == before, ("Undo left planes", [o.Name for o in planes()])
    commands.REGISTRY.run("edit.redo")
    harness.pump(1200)
    assert len(planes()) == len(before) + 3, "Redo did not bring the row back"
    ST["row"] = sorted((o for o in planes() if o.Name not in before), key=lambda o: o.Placement.Base.z)[0].Name


def test_11_delete_the_rows_first_plane():
    from incad.core import delete
    first = doc().getObject(ST["row"])
    rest = work.series(doc(), first)
    names = [o.Name for o in rest]
    zs = [round(o.Placement.Base.z, 6) for o in rest]
    delete.delete(first)
    doc().recompute()
    harness.pump(800)
    for n, z in zip(names, zs):
        o = doc().getObject(n)
        assert o is not None, "%s went with the first plane" % n
        assert "Invalid" not in o.State, "%s: %s" % (n, o.getStatusString())
        assert abs(o.Placement.Base.z - z) < 1e-6, (n, o.Placement.Base.z, z)
    second = doc().getObject(names[0])
    s().edit_feature(second)
    harness.pump(1200)
    d = dialog()
    assert d is not None, "no dialog for the row's next plane"
    _ok(d, "the row's next plane after its first was deleted")
    assert abs(second.Placement.Base.z - zs[0]) < 1e-6, second.Placement


def test_12_corners_reclicked_on_edit_stay_corners():
    """The audit: once the plane existed, corners clicked again on its Edit became fixed points (the plane no
    longer followed the part)."""
    f = doc().getObject(ST["made"][1])  # Parallel through point
    s().edit_feature(f)
    harness.pump(1200)
    d = dialog()
    _markers(d, "point", [V(0, 10, 6)])
    assert d.values()["point"].startswith(ST["box"] + ":Vertex"), d.values()["point"]
    _ok(d, "Parallel through point, corner clicked again")


def test_13_work_points_are_marked_points():
    """An axis through two work points (the audit: work points were never offered to click)."""
    from incad.features import work as w
    a = w.POINT.create(doc(), body(), None, dict(w.POINT.defaults(doc(), body(), None), mode="vertex",
                                                 vertex="@3 4 6"))
    b = w.POINT.create(doc(), body(), None, dict(w.POINT.defaults(doc(), body(), None), mode="vertex",
                                                 vertex="@15 4 6"))
    doc().recompute()
    harness.pump(500)
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("work.axis")
    harness.pump(1000)
    d = dialog()
    m = d.field("mode")
    m.setCurrentIndex(m.findData("two_points"))
    harness.pump(600)
    _markers(d, "points", [V(3, 4, 6), V(15, 4, 6)])
    assert d.values()["points"] == "%s,%s" % (a.Name, b.Name), d.values()["points"]
    _ok(d, "axis through two work points")
    axis = sorted((o for o in body().Group if o.TypeId == "PartDesign::Line"), key=lambda o: o.Name)[-1]
    a.AttachmentSupport, a.MapMode = [], "Deactivated"
    a.Placement = App.Placement(V(3, 4, 2), App.Rotation())
    doc().recompute()
    p, n = axis.Placement.Base, axis.Placement.Rotation.multVec(V(0, 0, 1))
    off = V(3, 4, 2) - p
    assert (off - n * off.dot(n)).Length < 1e-6, ("the axis did not follow its work point", axis.Placement)


def test_99_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_box, test_1_offset, test_2_parallel_through_point, test_3_midplane, test_4_angle_around_edge,
             test_5_angle_around_an_origin_axis, test_6_three_points, test_7_normal_to_edge, test_8_tangent,
             test_9_cancel_an_edit_puts_it_back, test_10_a_row_goes_with_cancel_and_with_undo,
             test_11_delete_the_rows_first_plane, test_12_corners_reclicked_on_edit_stay_corners,
             test_13_work_points_are_marked_points, test_99_cleanup])
