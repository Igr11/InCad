"""Unused open sketches stay visible in the part view with their key points marked (spline poles, segment ends,
circle centres); the markers follow the user's Hide / Show, sketch edit mode, deletion, and the real part."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def _body():
    from incad.core import document
    return document.primary_body(App.ActiveDocument)


def _markers():
    entry = shell.instance().sketch_markers.get(App.ActiveDocument.Name)
    return entry[1] if entry else None


def _count():
    m = _markers()
    return m.count if m is not None else 0


def _spline(poles):
    c = Part.BSplineCurve()
    c.buildFromPoles(poles)
    return c


def _sketch_on(body, role, name):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(next(o for o in body.Origin.OriginFeatures if o.Role == role), "")]
    sk.MapMode = "FlatFace"
    return sk


def test_0_part_with_a_path():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    from incad.core import document
    body = _body()
    sk = _sketch_on(body, "XY_Plane", "Path")
    sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0)))
    sk.addGeometry(_spline([App.Vector(30, 0, 0), App.Vector(40, 10, 0), App.Vector(50, 0, 0)]))
    App.ActiveDocument.recompute()
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(600)
    assert sk.Visibility, "an open contour stays visible"
    assert _count() == 4, _count()  # (0,0), (30,0) shared, (40,10), (50,0)


def test_1_hidden_path_has_no_markers():
    from incad.core import document
    sk = App.ActiveDocument.getObject("Path")
    document.set_visibility([sk], False)
    shell.instance().schedule_refresh()
    harness.pump(500)
    assert _count() == 0, _count()
    document.set_visibility([sk], True)
    shell.instance().schedule_refresh()
    harness.pump(500)
    assert _count() == 4, _count()


def test_2_sketch_edit_mode_hides_the_markers():
    sh = shell.instance()
    sh.sketches.edit(App.ActiveDocument.getObject("Path"))  # InCad's route (a raw setEdit switches workbenches)
    sh.schedule_refresh()
    harness.pump(800)
    assert sh.sketches.editing() is not None, "the sketch is being edited"
    assert _count() == 0, _count()
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    assert sh.sketches.editing() is None
    assert _count() == 4, _count()


def test_3_deleted_sketch_drops_its_markers():
    App.ActiveDocument.removeObject("Path")
    App.ActiveDocument.recompute()
    shell.instance().schedule_refresh()
    harness.pump(500)
    assert _count() == 0, _count()


def test_4_real_part_sketch7_is_shown_with_its_ends():
    path = os.environ.get("INCAD_REAL_PART",
                          os.path.join(os.environ["INCAD_REPO"], "tests", "gui", "data", "p2_test_reordered.FCStd"))
    App.openDocument(path)
    harness.pump(1500)
    shell.instance().schedule_refresh()
    harness.pump(800)
    sk = App.ActiveDocument.getObject("Sketch006")
    assert sk.Visibility, "Sketch7 (two open chains) is shown"
    assert _count() >= 4, _count()
    others = [o.Name for o in App.ActiveDocument.Objects if o.TypeId == "Sketcher::SketchObject" and o.Visibility
              and o is not sk]
    assert others == [], others


harness.run([test_0_part_with_a_path, test_1_hidden_path_has_no_markers, test_2_sketch_edit_mode_hides_the_markers,
             test_3_deleted_sketch_drops_its_markers, test_4_real_part_sketch7_is_shown_with_its_ends])
