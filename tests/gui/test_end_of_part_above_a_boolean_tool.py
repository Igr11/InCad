"""End of Part moved above the Solid a Boolean of another Solid cuts with (the user: the jar's lid, cut by its grip
ribs): the Boolean below End of Part loses its tool, and that is no failure — the move stays, and moves back."""
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


def doc():
    return App.ActiveDocument


def body_with_circle(name, r, z, length, label):
    b = doc().addObject("PartDesign::Body", name)
    sk = b.newObject("Sketcher::SketchObject", name + "Sk")
    sk.AttachmentSupport = [(util.xy_plane(b), "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), r))
    pad = util.add_pad(b, sk, length, name + "Pad")
    b.Tip = pad
    b.Label = label
    return b, pad


def test_0_jar_lid_and_ribs():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    jar = document.primary_body(doc())
    jar.Tip = util.add_pad(jar, util.add_rect_sketch(jar, 20, 10, "JarSk"), 10, "Jar")
    lid, blank = body_with_circle("LidB", 12, 10, 6, "Lid")
    ribs, _ = body_with_circle("RibsB", 3, 9, 8, "Ribs")
    from incad.features import combine
    doc().recompute()
    v = dict(combine.defaults(doc(), lid, None), base=lid.Name, tools=ribs.Name, operation="cut", clearance="0 mm",
             keep_tool=False)  # as the user's: the ribs used up, shown inside the Boolean's row
    cut = combine.create(doc(), lid, None, v)
    doc().recompute()
    shell.instance().schedule_refresh()
    harness.pump(500)
    assert "Invalid" not in cut.State, cut.getStatusString()
    ST.update(jar=jar, lid=lid, ribs=ribs, cut=cut, first=jar.Tip)


def test_1_move_end_of_part_above_the_ribs():
    shell.instance()._on_end_of_part_moved(ST["first"].Name)
    harness.pump(800)
    assert ST["ribs"].Tip is None, "the move was undone: ribs tip %s" % ST["ribs"].Tip
    assert ST["lid"].Tip is not ST["cut"]


def test_2_and_back_to_the_end():
    shell.instance()._on_end_of_part_moved(ST["cut"].Name)
    harness.pump(800)
    assert ST["lid"].Tip is ST["cut"] and "Invalid" not in ST["cut"].State, ST["cut"].State


def test_3_dropped_below_the_tools_last_row_goes_after_the_boolean():
    """The ribs Solid is shown inside the lid's Boolean row; its last row is the tree's last: a drop there means the
    end, not 'after the ribs' (which is before the Boolean)."""
    from incad.ui.browser import NAME_ROLE
    sh = shell.instance()
    sh._on_end_of_part_moved(ST["first"].Name)
    sh.schedule_refresh()
    harness.pump(800)
    tree = sh.browser.tree
    rows = []

    def walk(item):
        rows.append(item)
        for i in range(item.childCount()):
            walk(item.child(i))
    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i))
    rib_rows = [r for r in rows if r.data(0, NAME_ROLE) == "RibsBPad" and r.parent() is not None
                and r.parent().parent() is not None and r.parent().parent().data(0, NAME_ROLE) == ST["cut"].Name]
    assert rib_rows, [r.data(0, NAME_ROLE) for r in rows]
    sh.browser.drop_end_of_part_on(rib_rows[-1], False)
    harness.pump(800)
    assert ST["lid"].Tip is ST["cut"], "End of Part landed before the Boolean: lid tip %s" % ST["lid"].Tip.Name


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_jar_lid_and_ribs, test_1_move_end_of_part_above_the_ribs, test_2_and_back_to_the_end,
             test_3_dropped_below_the_tools_last_row_goes_after_the_boolean, test_9_cleanup])
