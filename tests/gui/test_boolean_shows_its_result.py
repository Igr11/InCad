"""A Boolean is drawn as its result, never in FreeCAD's Group mode (which draws the tool Solids): the user's lid,
whose last step was a Boolean, showed nothing when the file was opened again."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.features import combine  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def doc():
    return App.ActiveDocument


def test_0_a_boolean_made_shows_its_result():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    base = document.primary_body(doc())
    base.Tip = util.add_pad(base, util.add_rect_sketch(base, 40, 30, "BlockSk"), 10, "Block")
    tool = doc().addObject("PartDesign::Body", "Pin")
    sk = tool.newObject("Sketcher::SketchObject", "PinSk")
    sk.AttachmentSupport = [(util.xy_plane(tool), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(20, 15, 0), App.Vector(0, 0, 1), 4))
    tool.Tip = util.add_pad(tool, sk, 20, "PinPad")
    doc().recompute()
    v = dict(combine.defaults(doc(), base, None), base=base.Name, tools=tool.Name, operation="cut", clearance="0 mm")
    f = combine.create(doc(), base, None, v)
    doc().recompute()
    harness.pump(400)
    assert f.ViewObject.DisplayMode != "Group", f.ViewObject.DisplayMode
    ST["f"] = f


def test_1_one_in_group_mode_is_put_right_on_open():
    f = ST["f"]
    f.ViewObject.DisplayMode = "Group"  # as a file saved before (or a recovered one) brings it
    combine.show_results(doc())
    assert f.ViewObject.DisplayMode == "Flat Lines"


def test_2_reopened_it_shows_its_result():
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), "boolean.FCStd")
    doc().saveAs(path)
    name = ST["f"].Name
    App.closeDocument(doc().Name)
    harness.pump(500)
    d = App.openDocument(path)
    raw = d.getObject(name).ViewObject.DisplayMode  # as FreeCAD restored it, before InCad's look at the file
    harness.pump(1500)
    print("REOPENED raw mode", raw)
    assert d.getObject(name).ViewObject.DisplayMode != "Group", (raw, d.getObject(name).ViewObject.DisplayMode)


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_a_boolean_made_shows_its_result, test_1_one_in_group_mode_is_put_right_on_open,
             test_2_reopened_it_shows_its_result, test_9_cleanup])
