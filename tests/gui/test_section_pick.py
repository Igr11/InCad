"""Section at the picked plane (the user): an origin plane from the browser or a flat face, then Section — with
either face of the split button (Section, Section by 3 Points: both show "Section"). An origin plane put the
section at -5e99 and nothing was cut; Section by 3 Points passed over the selection for its markers."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def plane(role):
    return [o for o in body().Origin.OriginFeatures if o.Role == role][0]


def normal():
    return s()._section_base.Rotation.multVec(V(0, 0, 1))


def section_with(cmd, *picks):
    if shell.section_on():
        shell.stop_section()
    Gui.Selection.clearSelection()
    for obj, sub in picks:
        Gui.Selection.addSelection(doc().Name, obj.Name, sub)
    harness.pump(200)
    r = commands.REGISTRY.run(cmd)
    harness.pump(1200)
    assert getattr(r, "ok", True), getattr(r, "error", "")
    assert shell.section_on(), "sectioned"
    assert s()._point_pick is None, "no point markers"
    assert s()._section_base.Base.Length < 1e6, s()._section_base


def test_0_box():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 20, 10, 6
    box.AttachmentSupport = [(plane("XY_Plane"), "")]
    box.MapMode = "FlatFace"
    box.AttachmentOffset = App.Placement(V(-10, -5, -3), App.Rotation())  # round the origin: every plane cuts it
    doc().recompute()
    harness.pump(500)
    bb = body().Shape.BoundBox
    assert (bb.XMin, bb.YMin, bb.ZMin) == (-10, -5, -3), bb


def test_1_xy_plane_with_section():
    section_with("view.section", (plane("XY_Plane"), ""))
    assert abs(normal().z) > 0.999, normal()


def test_2_xz_plane_with_section_by_3_points():
    section_with("view.section_points", (plane("XZ_Plane"), ""))
    assert abs(normal().y) > 0.999, normal()


def test_3_a_face_moves_a_running_section():
    section_with("view.section", (plane("XY_Plane"), ""))
    faces = body().Tip.Shape.Faces
    side = [i + 1 for i, f in enumerate(faces) if abs(f.normalAt(0, 0).x) > 0.999][0]
    Gui.Selection.addSelection(doc().Name, body().Tip.Name, "Face%d" % side)
    harness.pump(200)
    commands.REGISTRY.run("view.section")
    harness.pump(1200)
    assert shell.section_on() and abs(normal().x) > 0.999, normal()


def test_4_nothing_selected_section_by_3_points_shows_markers():
    if shell.section_on():
        shell.stop_section()
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("view.section_points")
    harness.pump(800)
    assert s()._point_pick is not None, "markers to click"
    s().cancel_point_pick()


def test_9_cleanup():
    if shell.section_on():
        shell.stop_section()
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_box, test_1_xy_plane_with_section, test_2_xz_plane_with_section_by_3_points,
             test_3_a_face_moves_a_running_section, test_4_nothing_selected_section_by_3_points_shows_markers,
             test_9_cleanup])
