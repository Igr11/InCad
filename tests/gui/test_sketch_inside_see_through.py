"""A sketch on a work plane inside the part (the user: it was hidden by the part): while it is open the solid the
plane runs through is drawn see-through (an override material, nothing saved); a sketch on the part's outside face
leaves it solid; closing the sketch brings it back."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def see_through(obj):
    entry = s().sketches._dimmed.get((doc().Name, obj.Name))
    return entry is not None and entry[1].transparency[0] > 0.5


def open_sketch_on(target, sub=""):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, target.Name, sub)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1200)
    sk = s().sketches.editing()
    assert sk is not None
    s().sketches.sync()
    harness.pump(200)
    return sk


def close_sketch():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    s().sketches.sync()


def test_0_part_and_a_plane_through_it():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(doc())
    pad = util.add_pad(body, util.add_rect_sketch(body, 20, 10, "Base"), 10)
    body.Tip = pad
    plane = body.newObject("PartDesign::Plane", "Inside")
    plane.AttachmentSupport = [(util.xy_plane(body), "")]
    plane.MapMode = "FlatFace"
    plane.AttachmentOffset = App.Placement(V(0, 0, 5), App.Rotation())
    doc().recompute()
    harness.pump(500)
    ST.update(body=body, pad=pad, plane=plane)


def test_1_inside_is_see_through_and_back_after():
    open_sketch_on(ST["plane"])
    assert see_through(ST["pad"]), s().sketches._dimmed
    close_sketch()
    assert not see_through(ST["pad"])
    assert (doc().Name, ST["pad"].Name) not in s().sketches._dimmed or s().sketches.editing() is None


def test_2_on_the_outside_face_stays_solid():
    top = [i + 1 for i, f in enumerate(ST["pad"].Shape.Faces) if f.normalAt(0, 0).z > 0.99][0]
    open_sketch_on(ST["pad"], "Face%d" % top)
    assert not see_through(ST["pad"]), s().sketches._dimmed
    close_sketch()


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_part_and_a_plane_through_it, test_1_inside_is_see_through_and_back_after,
             test_2_on_the_outside_face_stays_solid, test_9_cleanup])
