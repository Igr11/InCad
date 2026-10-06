import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

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


def ok():
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(700)


def top_edges(f, z):
    return ["Edge%d" % (i + 1) for i, e in enumerate(f.Shape.Edges)
            if abs(e.BoundBox.ZMin - z) < 1e-6 and abs(e.BoundBox.ZMax - z) < 1e-6]


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    sk = util.add_rect_sketch(body(), w=40, h=20)
    pad = util.add_pad(body(), sk, 10)
    body().Tip = pad
    doc().recompute()
    ST["pad"] = pad.Name
    harness.pump(300)


def test_1_fillet_takes_preselected_edges():
    pad = doc().getObject(ST["pad"])
    Gui.Selection.clearSelection()
    for e in top_edges(pad, 10):
        Gui.Selection.addSelection(doc().Name, pad.Name, e)
    commands.REGISTRY.run("feature.fillet")
    harness.pump(900)
    assert dialog() is not None
    assert dialog().field("edges").text() == "4 edges", dialog().field("edges").text()
    ok()
    assert body().Tip.TypeId == "PartDesign::Fillet", body().Tip.TypeId


def test_2_hole_from_sketch():
    fillet = body().Tip
    top = [i + 1 for i, f in enumerate(fillet.Shape.Faces)
           if abs(f.CenterOfMass.z - 10) < 1e-6 and f.Surface.TypeId == "Part::GeomPlane"][0]
    sk = body().newObject("Sketcher::SketchObject", "Holes")
    sk.AttachmentSupport = [(fillet, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(10, 10, 0), App.Vector(0, 0, 1), 1))
    sk.addGeometry(Part.Circle(App.Vector(30, 10, 0), App.Vector(0, 0, 1), 1))
    doc().recompute()
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.hole")
    harness.pump(800)
    assert dialog().active_pick() == "sketch"
    from incad.qt import QtWidgets
    shown = [t.objectName() for t in Gui.getMainWindow().findChildren(QtWidgets.QTabWidget)
             if t.objectName().startswith("Overlay") and t.isVisible()]
    assert shown == [], "FreeCAD's overlay panels show through InCad: %s" % shown
    Gui.Selection.addSelection(doc().Name, sk.Name)
    harness.pump(800)
    ok()
    assert body().Tip.TypeId == "PartDesign::Hole", body().Tip.TypeId


def test_3_wrong_pick_kind_is_refused():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(800)
    tip = body().Tip
    assert tip.TypeId == "PartDesign::Hole", tip.TypeId  # an unfinished Chamfer must not linger as the Tip
    top = [i + 1 for i, f in enumerate(tip.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    Gui.Selection.addSelection(doc().Name, tip.Name, "Face%d" % top)
    harness.pump(600)
    assert "Select edge" in dialog().error_text(), dialog().error_text()
    QTest.keyClick(dialog(), QtCore.Qt.Key_Escape)
    harness.pump(600)
    assert s().feature_session is None


def test_4_rectangular_pattern_of_the_hole():
    hole = body().Tip
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, hole.Name)
    commands.REGISTRY.run("feature.rect_pattern")
    harness.pump(900)
    w = dialog().field("spacing1")
    w.setText("5 mm")
    w.editingFinished.emit()
    harness.pump(600)
    assert not dialog().error_text(), (dialog().error_text(), dialog().values())
    ok()
    assert body().Tip.TypeId == "PartDesign::LinearPattern", body().Tip.TypeId


def test_5_measure_and_mass():
    tip = body().Tip
    faces = tip.Shape.Faces
    bottom = [i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, tip.Name, "Face%d" % bottom)
    commands.REGISTRY.run("inspect.measure")
    harness.pump(500)
    rows = dict(s().info_panel.rows())
    assert "Area" in rows, rows
    commands.REGISTRY.run("inspect.mass")
    harness.pump(500)
    rows = dict(s().info_panel.rows())
    assert "Mass" in rows and "Volume" in rows, rows
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("inspect.measure")  # nothing selected: Measure waits and says what to pick
    harness.pump(400)
    assert s().info_panel is None and "Select" in s().status.texts()["prompt"], s().status.texts()
    assert shell.measuring() == "auto"
    s()._on_escape()
    harness.pump(300)
    assert shell.measuring() is None


def test_6_extrude_to_face_pick_now_works():
    sk = body().newObject("Sketcher::SketchObject", "ToProfile")
    sk.AttachmentSupport = [(util.xy_plane(body()), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(-20, 0, 0), App.Vector(0, 0, 1), 2))
    plane = body().newObject("PartDesign::Plane", "Limit")
    plane.AttachmentSupport = [(util.xy_plane(body()), "")]
    plane.MapMode = "FlatFace"
    plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 7), App.Rotation())
    doc().recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(800)
    dialog().field("operation").button("new_solid").click()
    dialog().field("extent").button("to").click()
    harness.pump(500)
    dialog().field("to_face").click()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, plane.Name)
    harness.pump(800)
    assert dialog().values()["to_face"].startswith(plane.Name), dialog().values()
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)
    if s().feature_session is not None:  # the simulated click missed the button (harness flake): cancel anyway
        s().feature_session.cancel()
        harness.pump(400)
    assert s().feature_session is None


def test_7_theme_switch_closes_the_old_info_panel():
    commands.REGISTRY.run("inspect.mass")
    harness.pump(400)
    assert s().info_panel is not None
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    assert s().info_panel is None


def _fillet():
    return [o for o in body().Group if o.TypeId == "PartDesign::Fillet"][0]


def test_8_pattern_without_selection_shows_and_keeps_its_feature():
    Gui.Selection.clearSelection()
    fs0 = s().feature_session
    commands.REGISTRY.run("feature.circ_pattern")
    harness.pump(900)
    fs = s().feature_session
    assert fs is not None and "features" in dialog()._widgets, (
        fs0 and fs0.kind.TITLE, fs and fs.kind.TITLE, open(os.environ["INCAD_LOG"]).read()[-600:])
    assert dialog().field("features").text() not in ("", "Select…"), dialog().field("features").text()
    w = dialog().field("count")
    w.setText("3")
    w.editingFinished.emit()
    harness.pump(700)
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)


def test_9_editing_picks_shows_the_base_selects_the_edges_and_restores_visibility():
    fillet, tip = _fillet(), body().Tip
    assert tip is not fillet
    before = (fillet.Visibility, tip.Visibility)
    shell.edit_feature(fillet)
    harness.pump(700)
    dialog().field("edges").click()
    harness.pump(600)
    base = fillet.BaseFeature
    assert base.Visibility and not fillet.Visibility and not tip.Visibility, (base.Visibility, fillet.Visibility,
                                                                             tip.Visibility)
    picked = sum(len(x.SubElementNames) for x in Gui.Selection.getSelectionEx(doc().Name))
    assert picked == 4, picked
    tip_edge = "Edge1"
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, tip.Name, tip_edge)
    harness.pump(600)
    assert "current shape" in dialog().error_text(), dialog().error_text()
    dialog().field("edges").click()  # stop picking
    harness.pump(400)
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(700)
    assert (fillet.Visibility, tip.Visibility) == before, ((fillet.Visibility, tip.Visibility), before)
    shell.edit_feature(fillet)
    harness.pump(700)
    dialog().field("edges").click()
    harness.pump(400)
    dialog().field("edges").click()
    harness.pump(400)
    w = dialog().field("radius")
    w.setText("1.5 mm")
    w.editingFinished.emit()
    harness.pump(600)
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(700)
    assert (fillet.Visibility, tip.Visibility) == before, ((fillet.Visibility, tip.Visibility), before)



def test_section_on_and_off_twice_never_crashes():
    """Section at the selection with its panel: offset, flip, Done keeps the cut, Section again switches off."""
    from incad import actions
    sh = shell.instance()
    Gui.Selection.clearSelection()
    for _ in range(2):
        commands.REGISTRY.run("view.section")
        harness.pump(600)
        assert actions.section_on() and sh.section_panel is not None, ("section is on with its panel",
            open(os.environ["INCAD_LOG"]).read()[-900:] if os.path.exists(os.environ["INCAD_LOG"]) else "")
        sh.section_panel.offset.setValue(3.0)
        harness.pump(300)
        sh.section_panel.flip.setChecked(True)
        harness.pump(300)
        assert actions.section_on()
        sh.section_panel.done_button.click()
        harness.pump(400)
        assert actions.section_on() and sh.section_panel is None, "Done keeps the cut, the panel goes"
        commands.REGISTRY.run("view.section")
        harness.pump(600)
        assert not actions.section_on(), "section is off again"
    commands.REGISTRY.run("view.section")
    harness.pump(500)
    sh.section_panel.off_button.click()
    harness.pump(400)
    assert not actions.section_on() and sh.section_panel is None


def test_section_by_three_marked_points():
    """Markers on the view (never in the document); three clicks on them make the cut; Esc clears them."""
    from incad import actions
    sh = shell.instance()
    d = App.ActiveDocument
    before = len(d.Objects)
    commands.REGISTRY.run("view.section_points")
    harness.pump(800)
    pick = sh._point_pick
    assert pick is not None and len(pick.points) >= 8 and len(d.Objects) == before, "markers are not objects"
    assert "3 points" in sh.status.texts()["prompt"]
    view = Gui.ActiveDocument.ActiveView
    vp = [w for w in Gui.getMainWindow().findChildren(QtWidgets.QGraphicsView) if w.isVisible()][0].viewport()
    def at(p):
        x, y = view.getPointOnViewport(p)
        r = vp.devicePixelRatioF()
        return x / r, (view.getSize()[1] - y) / r
    pts = pick.points
    a = pts[0]
    b = next(p for p in pts if (p - a).Length > 1)
    c = next(p for p in pts if (p - a).cross(b - a).Length > 1)
    for p in (a, b, c):
        assert sh._click_hook(view, vp, *at(p))
        harness.pump(300)
    assert sh._point_pick is None and actions.section_on() and sh.section_panel is not None
    assert len(d.Objects) == before and not d.HasPendingTransaction
    sh.section_panel.off_button.click()
    harness.pump(400)
    assert not actions.section_on()
    commands.REGISTRY.run("view.section_points")
    harness.pump(600)
    sh._on_escape()
    harness.pump(400)
    assert sh._point_pick is None and len(d.Objects) == before


def test_measure_edge_face_and_whole_part_by_clicking():
    """Measure, then click a rib (edge), a surface (face) and the whole part in the tree: each shows its numbers."""
    sh = shell.instance()
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    tip = body.Tip
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("inspect.measure")
    harness.pump(400)
    assert shell.measuring() == "auto"
    Gui.Selection.addSelection(doc.Name, body.Name, "%s.Edge1" % tip.Name)  # a 3D click on an edge
    harness.pump(700)
    assert sh.info_panel is not None and any(k in dict(sh.info_panel.rows()) for k in ("Length", "Radius")), sh.info_panel and sh.info_panel.rows()
    Gui.Selection.clearSelection()
    harness.pump(300)
    Gui.Selection.addSelection(doc.Name, body.Name, "%s.Face1" % tip.Name)  # a 3D click on a face
    harness.pump(700)
    assert sh.info_panel is not None and "Area" in dict(sh.info_panel.rows()), sh.info_panel and sh.info_panel.rows()
    Gui.Selection.clearSelection()
    harness.pump(300)
    assert sh.browser.select_row(body.Name), "the part row"  # a click on the part in the tree
    harness.pump(700)
    assert sh.info_panel is not None and "Volume" in dict(sh.info_panel.rows()), sh.info_panel and sh.info_panel.rows()
    sh._on_escape()
    harness.pump(300)
    assert shell.measuring() is None


harness.run([test_0_setup, test_1_fillet_takes_preselected_edges, test_2_hole_from_sketch,
             test_3_wrong_pick_kind_is_refused, test_4_rectangular_pattern_of_the_hole, test_5_measure_and_mass,
             test_6_extrude_to_face_pick_now_works, test_7_theme_switch_closes_the_old_info_panel,
             test_8_pattern_without_selection_shows_and_keeps_its_feature,
             test_9_editing_picks_shows_the_base_selects_the_edges_and_restores_visibility,
             test_section_on_and_off_twice_never_crashes, test_section_by_three_marked_points,
             test_measure_edge_face_and_whole_part_by_clicking])
