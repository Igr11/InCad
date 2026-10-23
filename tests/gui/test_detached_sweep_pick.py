"""A Sweep joined away from the part, its face picked in Move Face (the user: the dialog split it off into its own
Solid on every preview — its path sketch left behind, 'links go out of the allowed scope' — round and round until
FreeCAD crashed): it moves once, with its path, and the dialog stays usable; Cancel closes it."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def log_count(text):
    try:
        return open(os.environ["INCAD_LOG"]).read().count(text)
    except Exception:
        return 0


def test_0_part_and_a_sweep_away_from_it():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    d = App.ActiveDocument
    body = document.primary_body(d)
    body.Tip = util.add_pad(body, util.add_rect_sketch(body, 20, 10, "Base"), 10)
    yz = [o for o in body.Origin.OriginFeatures if o.Role == "YZ_Plane"][0]
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    prof = body.newObject("Sketcher::SketchObject", "Prof")
    prof.AttachmentSupport = [(yz, "")]
    prof.MapMode = "FlatFace"
    prof.AttachmentOffset = App.Placement(V(0, 0, 60), App.Rotation())
    prof.addGeometry(Part.Circle(V(50, 5, 0), V(0, 0, 1), 3))
    path = body.newObject("Sketcher::SketchObject", "Path")
    path.AttachmentSupport = [(xy, "")]
    path.MapMode = "FlatFace"
    path.addGeometry(Part.LineSegment(V(60, 50, 0), V(90, 50, 0)))
    d.recompute()
    sweep = body.newObject("PartDesign::AdditivePipe", "Sweep")
    sweep.Profile = prof
    sweep.Spine = (path, [])
    body.Tip = sweep
    d.recompute()
    harness.pump(600)
    assert document.is_detached_lump(sweep)
    ST.update(sweep=sweep.Name, path=path.Name)


def test_1_move_face_on_it_moves_it_once():
    d = App.ActiveDocument
    sweep = d.getObject(ST["sweep"])
    before = log_count("does not touch the part")
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1200)
    end = next(i + 1 for i, f in enumerate(sweep.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"
               and f.CenterOfMass.x > 89)
    Gui.Selection.addSelection(d.Name, sweep.Name, "Face%d" % end)
    harness.pump(8000)  # a loop would split it off again and again by now (every ~2 s)
    assert log_count("does not touch the part") - before <= 1, open(os.environ["INCAD_LOG"]).read()[-1500:]
    owner = d.getObject(ST["path"]).getParentGeoFeatureGroup()
    assert owner is sweep.getParentGeoFeatureGroup(), (owner.Label, sweep.getParentGeoFeatureGroup().Label)
    fs = s().feature_session
    assert fs is not None
    fs.cancel()
    harness.pump(1000)
    assert s().feature_session is None


def test_9_cleanup():
    if s().feature_session is not None:
        s().feature_session.cancel()
    harness.pump(300)
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_part_and_a_sweep_away_from_it, test_1_move_face_on_it_moves_it_once, test_9_cleanup])
