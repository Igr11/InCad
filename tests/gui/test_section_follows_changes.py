"""An open section follows the part (the user: a chamfer added while the section was on showed as a hole in the cut,
as if it were a surface): the cut is meshed again from the changed part."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def cut_reach():
    caps = s()._section_display[3]
    import Part
    faces = caps[0].faces(s()._section_last)
    return Part.makeCompound(faces).BoundBox.XMax


def test_0_box_and_a_section():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 20, 10, 6
    box.Placement = App.Placement(V(-10, -5, -3), App.Rotation())  # the XZ plane runs through it
    doc().recompute()
    harness.pump(500)
    xz = [o for o in body().Origin.OriginFeatures if o.Role == "XZ_Plane"][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, xz.Name, "")
    commands.REGISTRY.run("view.section")
    harness.pump(1500)
    assert shell.section_on()
    ST["box"], ST["reach"] = box, cut_reach()


def test_1_the_part_grows_and_the_cut_follows():
    ST["box"].Length = 30
    doc().recompute()
    s().schedule_refresh()
    harness.pump(1500)
    assert abs(cut_reach() - (ST["reach"] + 10)) < 0.1, "the cut still shows the old part: %s" % cut_reach()


def test_9_cleanup():
    if shell.section_on():
        shell.stop_section()
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_box_and_a_section, test_1_the_part_grows_and_the_cut_follows, test_9_cleanup])
