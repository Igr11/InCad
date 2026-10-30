"""A sketch in the middle of a part (the user: "Why can't I see the part when I'm editing a sketch?"): FreeCAD hides
everything built on it, the finished part with it; the part as it is before the sketch is shown while the sketch is
open, and hidden again when it closes (the finished part back)."""
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


def test_0_part_of_two_pads():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(doc())
    base = util.add_pad(body, util.add_rect_sketch(body, 20, 10, "Base"), 10, "BasePad")
    top = util.add_rect_sketch(body, 6, 4, "Top")
    top.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
    boss = util.add_pad(body, top, 5, "TopPad")
    body.Tip = boss
    doc().recompute()
    harness.pump(500)
    for o in (base, top):
        o.ViewObject.Visibility = False
    boss.ViewObject.Visibility = True
    harness.pump(300)
    ST.update(body=body, base=base, top=top, boss=boss)


def test_1_the_part_before_is_shown_while_sketching():
    s().sketches.edit(ST["top"])
    harness.pump(800)
    assert s().sketches.editing() is ST["top"]
    assert not ST["boss"].Visibility  # FreeCAD's own hiding of what uses the sketch
    assert ST["base"].Visibility, "the part before the sketch is not shown"


def test_2_closing_brings_the_finished_part_back():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    s().sketches.sync()
    assert s().sketches.editing() is None
    assert ST["boss"].Visibility
    assert not ST["base"].Visibility
    assert "Touched" not in ST["boss"].State


def test_3_first_sketch_shows_nothing_before():
    s().sketches.edit(doc().getObject("Base"))
    harness.pump(800)
    assert not ST["base"].Visibility and not ST["boss"].Visibility
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    assert ST["boss"].Visibility and not ST["base"].Visibility


def test_4_a_solid_cut_by_this_one_stays_shown():
    """The user's lid, cut by the jar: FreeCAD hid it with the jar on every new sketch of the jar."""
    import Part
    lid = doc().addObject("PartDesign::Body", "Lid")
    sk = lid.newObject("Sketcher::SketchObject", "LidSk")
    sk.AttachmentSupport = [(util.xy_plane(lid), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 15))
    blank = util.add_pad(lid, sk, 30, "LidBlank")
    cut = lid.newObject("PartDesign::Boolean", "LidCut")
    cut.Type = "Cut"
    cut.Group = [ST["body"]]
    lid.Tip = cut
    doc().recompute()
    cut.ViewObject.Visibility = True
    blank.ViewObject.Visibility = False
    ST["body"].ViewObject.Visibility = True
    harness.pump(400)
    assert "Invalid" not in cut.State, cut.getStatusString()
    top = [i + 1 for i, f in enumerate(ST["boss"].Shape.Faces) if f.normalAt(0, 0).z > 0.99 and f.CenterOfMass.z > 14][0]
    new = shell.instance().sketches.start_on(ST["boss"], "Face%d" % top)
    harness.pump(1000)
    assert shell.instance().sketches.editing() is new
    assert cut.Visibility, "the lid cut by this Solid was hidden with it"
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    assert cut.Visibility


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_part_of_two_pads, test_1_the_part_before_is_shown_while_sketching,
             test_2_closing_brings_the_finished_part_back, test_3_first_sketch_shows_nothing_before,
             test_4_a_solid_cut_by_this_one_stays_shown, test_9_cleanup])
