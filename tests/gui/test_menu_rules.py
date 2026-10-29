"""Right-click menus show only what applies to what is under the pointer (the user: too many buttons; incad.ui.menu_rules):
empty space of a one-Solid part has no Make Assembly, Hide, Show or Show All; the hidden origin offers Show All Origin
only; a flat face has no Thread, a round one has; a visible Solid offers Hide, not Show; the style in use is not
offered again; a hidden Solid brings Show All; a feature's tree row has no New Sketch, a work plane's has."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, context, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def labels(kind):
    view = s()._mdi().viewport()
    menu = s()._show_marking_menu(kind, view.mapToGlobal(view.rect().center()))
    out = menu.list_labels() if menu is not None else []  # at once: a popup closes when another app takes focus
    try:
        menu.close()
    except (AttributeError, RuntimeError):
        pass
    harness.pump(100)
    return out


def face(feature, surface):
    return "Face%d" % [i + 1 for i, f in enumerate(feature.Shape.Faces) if f.Surface.TypeId == surface][0]


def test_0_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    b = body().newObject("PartDesign::AdditiveCylinder", "Cyl")
    b.Radius, b.Height = 5, 10
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["cyl"] = b.Name


def test_1_empty_space_of_a_one_solid_part():
    Gui.Selection.clearSelection()
    context.set_target(None)
    got = labels("part")
    for gone in ("Make Assembly", "Hide", "Show", "Show All", "Zoom All", "Home View", "Appearance…", "Appearance"):
        assert gone not in got, (gone, got)
    assert "Show All Origin" in got and "Hide All Origin" not in got, got  # a new part's origin is hidden


def test_2_flat_and_round_faces():
    cyl = doc().getObject(ST["cyl"])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, cyl.Name, face(cyl, "Part::GeomPlane"))
    got = labels("face")
    assert "Thread" not in got, got
    assert "Hide" in got and "Show" not in got, got  # the Solid is shown
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, cyl.Name, "Edge1")
    got = labels("edge")
    assert "Wireframe" in got and "Shaded" not in got, got  # the style in use is not offered again
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, cyl.Name, face(cyl, "Part::GeomCylinder"))
    assert "Thread" in labels("face")


def test_3_a_hidden_solid_brings_show_all():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, body().Name)
    commands.REGISTRY.run("view.hide")
    harness.pump(500)
    Gui.Selection.clearSelection()
    context.set_target(None)
    assert "Show All" in labels("part")
    commands.REGISTRY.run("view.show_all_parts")
    harness.pump(500)
    assert "Show All" not in labels("part")


def test_4_new_sketch_only_on_a_plane_row():
    context.set_target(ST["cyl"])
    assert "New Sketch" not in labels("browser") and "Start 2D Sketch" not in labels("browser")
    from incad.features import work
    k = work.PLANE
    wp = k.create(doc(), body(), None, dict(k.defaults(doc(), body(), None), base=[
        o for o in body().Origin.OriginFeatures if o.Role == "XY_Plane"][0].Name, offset="20 mm"))
    doc().recompute()
    context.set_target(wp.Name)
    got = labels("browser")
    assert any("Sketch" in lb for lb in got), got


def test_5_a_hidden_sketch_selected_offers_show():
    """The user: the menu of a hidden sketch offered only Hide. Its row selected shows it for a moment (a peek):
    hidden all the same, so the menu offers Show."""
    import Part
    sk = body().newObject("Sketcher::SketchObject", "Loose")
    sk.AttachmentSupport = [([o for o in body().Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0)))
    doc().recompute()
    document.set_visibility([sk], False)
    harness.pump(300)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    s()._peek(sk)
    harness.pump(300)
    assert sk.Visibility, "shown while its row is selected"
    context.set_target(sk.Name)
    got = labels("browser")
    assert "Show" in got and "Hide" not in got, got
    commands.REGISTRY.run("view.show")
    harness.pump(400)
    Gui.Selection.clearSelection()
    harness.pump(400)
    assert sk.Visibility and document.sketch_shown(sk), "shown for good"
    context.set_target(None)


def test_9_cleanup():
    context.set_target(None)
    App.closeDocument(doc().Name)
    harness.pump(300)


harness.run([test_0_part, test_1_empty_space_of_a_one_solid_part, test_2_flat_and_round_faces,
             test_3_a_hidden_solid_brings_show_all, test_4_new_sketch_only_on_a_plane_row,
             test_5_a_hidden_sketch_selected_offers_show, test_9_cleanup])
