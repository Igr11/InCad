"""Opening the user's part crashed FreeCAD twice on 2026-10-10: while a file is restored FreeCAD pumps the Qt
event loop for its progress bar, so InCad's deferred handlers (the sketch-change follow-ups, the panel refresh)
ran a recompute on the half-restored document and the Sketcher died in rebuildExternalGeometry (a projected
edge whose feature had no shape yet). The part here is the smallest one with the ingredients: a sketch with
external geometry that also owns an area profile. INCAD_REAL_PART names a real file to open as well."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs, regions  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def _open(path):
    App.openDocument(path)  # what the Start page runs; FreeCAD pumps events during the restore
    harness.pump(4000)
    doc = App.ActiveDocument
    assert doc is not None and doc.FileName == path, getattr(doc, "FileName", None)
    assert not getattr(doc, "Restoring", False)
    bad = [o.Name for o in doc.Objects if "Invalid" in o.State]
    assert not bad, "objects failed after the load: %s" % bad
    assert shell.instance().active
    return doc


def test_0_save_a_part_with_a_projected_edge_and_an_area_profile():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    # a heavy shape saved before the sketches: loading it takes long enough for FreeCAD's progress bar to show
    # and pump events, as the user's 5 MB part does; a small file loads in one go and never pumps
    heavy = doc.addObject("Part::Feature", "Ballast")
    heavy.Shape = Part.makeCompound([Part.makeBox(1, 1, 1, App.Vector(i, j, 0)) for i in range(60) for j in range(60)])
    heavy.Visibility = False
    pad = util.add_pad(body, util.add_rect_sketch(body), 10)
    body.Tip = pad
    doc.recompute()
    top = [i for i, f in enumerate(pad.Shape.Faces, 1) if abs(f.normalAt(0, 0).z - 1) < 1e-6][0]
    sk = body.newObject("Sketcher::SketchObject", "OnTop")
    sk.AttachmentSupport = [(pad, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    doc.recompute()
    sk.addExternal(pad.Name, "Edge1")  # a projected edge: rebuilt from the Pad's shape on every recompute
    pts = [App.Vector(2, 2, 0), App.Vector(18, 2, 0), App.Vector(18, 8, 0), App.Vector(2, 8, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    sk.addGeometry(Part.LineSegment(App.Vector(10, 0, 0), App.Vector(10, 10, 0)))  # two areas
    doc.recompute()
    prof = regions.make_profile(doc, body, sk, regions.region_at(sk, App.Vector(5, 5, 0)))
    cut = body.newObject("PartDesign::Pocket", "Cut")
    cut.Profile = prof
    cut.Length = 3
    body.Tip = cut
    doc.recompute()
    assert cut.Shape.Volume < pad.Shape.Volume
    path = os.path.join(os.environ["FREECAD_USER_TEMP"], "restore_me.FCStd")
    doc.saveAs(path)
    harness.pump(300)
    App.closeDocument(doc.Name)
    harness.pump(800)
    ST["path"] = path


def test_1_the_part_opens_whole():
    doc = _open(ST["path"])
    assert document.primary_body(doc).Tip.Name == "Cut"
    App.closeDocument(doc.Name)
    harness.pump(500)


def test_2_a_real_part_opens_whole():
    path = os.environ.get("INCAD_REAL_PART")
    if path:
        _open(path)


def test_3_nothing_ran_on_the_half_restored_document():
    log = open(os.environ["INCAD_LOG"]).read() if os.path.exists(os.environ["INCAD_LOG"]) else ""
    assert "could not update its panels" not in log and "Could not" not in log, log[-2000:]


harness.run([test_0_save_a_part_with_a_projected_edge_and_an_area_profile, test_1_the_part_opens_whole,
             test_2_a_real_part_opens_whole, test_3_nothing_ran_on_the_half_restored_document])
