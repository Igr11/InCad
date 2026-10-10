"""A click on a sketch row in the model tree shows that sketch in the 3D view (with its points) while it is
selected — a consumed sketch too; the next row, Esc or a cleared selection hides it again. Nothing is saved."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def _count():
    entry = shell.instance().sketch_markers.get(App.ActiveDocument.Name)
    return entry[1].count if entry else 0


def _sk():
    return App.ActiveDocument.getObject("Sketch")


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    from incad.core import document
    body = document.primary_body(App.ActiveDocument)
    sk = util.add_rect_sketch(body)
    pad = util.add_pad(body, sk, 10)
    body.Tip = pad
    App.ActiveDocument.recompute()
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(600)
    assert not sk.Visibility, "a consumed sketch is hidden"
    assert _count() == 0


def test_1_click_shows_the_consumed_sketch_and_the_next_row_hides_it():
    sh = shell.instance()
    assert sh.browser.select_row("Sketch")
    harness.pump(500)
    assert _sk().Visibility, "shown while selected"
    assert _count() == 4, _count()
    assert [o.Name for o in Gui.Selection.getSelection()] == ["Sketch"]
    assert sh.browser.select_row("Pad")
    harness.pump(500)
    assert not _sk().Visibility, "the next row hides it again"
    assert _count() == 0, _count()
    assert document_shown_prop_absent()


def document_shown_prop_absent():
    from incad.core import document
    return document.SHOWN_PROP not in _sk().PropertiesList  # a peek is never saved as a choice


def test_2_esc_hides_it():
    sh = shell.instance()
    sh.browser.select_row("Sketch")
    harness.pump(500)
    assert _sk().Visibility
    sh._on_escape()
    harness.pump(500)
    assert not _sk().Visibility
    assert _count() == 0


def test_3_a_cleared_3d_selection_hides_it():
    sh = shell.instance()
    sh.browser.select_row("Sketch")
    harness.pump(500)
    assert _sk().Visibility
    Gui.Selection.clearSelection()
    harness.pump(500)
    assert not _sk().Visibility
    assert _count() == 0


def test_4_an_unused_shown_sketch_stays_shown_after_the_peek():
    from incad.core import document
    import Part
    sh = shell.instance()
    body = document.primary_body(App.ActiveDocument)
    path = body.newObject("Sketcher::SketchObject", "Path")
    path.AttachmentSupport = [(util.xy_plane(body), "")]
    path.MapMode = "FlatFace"
    path.addGeometry(Part.LineSegment(App.Vector(0, 30, 0), App.Vector(30, 30, 0)))
    App.ActiveDocument.recompute()
    sh.schedule_refresh()
    harness.pump(600)
    assert path.Visibility and _count() == 2, (path.Visibility, _count())
    sh.browser.select_row("Path")
    harness.pump(500)
    assert path.Visibility and _count() == 2
    sh.browser.select_row("Pad")
    harness.pump(500)
    assert path.Visibility, "an open contour keeps its own rule"
    assert _count() == 2


def test_5_a_sweeps_path_and_profile_show_when_their_rows_are_clicked():
    from incad.core import document
    import Part
    sh = shell.instance()
    body = document.primary_body(App.ActiveDocument)
    prof = body.newObject("Sketcher::SketchObject", "Prof")
    prof.AttachmentSupport = [(next(o for o in body.Origin.OriginFeatures if o.Role == "YZ_Plane"), "")]
    prof.MapMode = "FlatFace"
    prof.AttachmentOffset = App.Placement(App.Vector(0, 0, 0), App.Rotation())
    prof.addGeometry(Part.Circle(App.Vector(30, 0, 0), App.Vector(0, 0, 1), 2))  # on YZ at y=30 (x in sketch = y)
    App.ActiveDocument.recompute()
    path = App.ActiveDocument.getObject("Path")
    commands.REGISTRY.run("feature.sweep")
    harness.pump(600)
    fs = sh.feature_session
    fs.dialog.set_pick("profile", "Prof")
    fs.dialog.set_pick("path", "Path")
    harness.pump(900)
    fs.ok()
    harness.pump(900)
    sweep = [o for o in App.ActiveDocument.Objects if o.TypeId == "PartDesign::AdditivePipe"][0]
    assert "Invalid" not in sweep.State, sweep.State
    assert not path.Visibility and not prof.Visibility, "both consumed and hidden"
    assert sh.browser.select_row("Path")
    harness.pump(500)
    assert path.Visibility, "the path shows while its row is selected"
    assert sh.browser.select_row("Prof")
    harness.pump(500)
    assert prof.Visibility and not path.Visibility, "the profile shows, the path goes back"
    assert sh.browser.select_row("Pad")
    harness.pump(500)
    assert not prof.Visibility


harness.run([test_0_part, test_1_click_shows_the_consumed_sketch_and_the_next_row_hides_it, test_2_esc_hides_it,
             test_3_a_cleared_3d_selection_hides_it, test_4_an_unused_shown_sketch_stays_shown_after_the_peek,
             test_5_a_sweeps_path_and_profile_show_when_their_rows_are_clicked])
