"""Hide, Show and Show All said outright (the user: "Undo is no way back: a Hide button and a Show button, in the
context menu too"), and files made outside InCad opened with every tool (the user: "parts not made in InCad must be
edited the same way"): a script's part and a STEP-like file of moved groups become InCad parts when they come to the
front; in a part and in an assembly Hide hides the picked one, Show brings it back, Show All brings back everything."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, context, document, prefs  # noqa: E402
from incad.ui import marking_layout, ribbon_layout, shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def run(cmd):
    r = commands.REGISTRY.run(cmd)
    harness.pump(900)
    assert getattr(r, "ok", True), (cmd, getattr(r, "error", ""))


def front(doc):
    App.setActiveDocument(doc.Name)
    Gui.ActiveDocument = Gui.getDocument(doc.Name)
    s().schedule_refresh()
    harness.pump(1200)


def test_0_files():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = tempfile.mkdtemp(prefix="incad_hide_show_")
    doc = util.new_doc("Scripted")  # two Bodies, the way a script writes them: no InCad marks
    for name, x in (("Big", 0), ("Small", 60)):
        b = doc.addObject("PartDesign::Body", name)
        b.Placement = App.Placement(App.Vector(x, 0, 0), App.Rotation())
        b.Tip = util.add_pad(b, util.add_rect_sketch(b, 40 if name == "Big" else 10, 20, "S" + name), 8, "Pad" + name)
    doc.recompute()
    ST["scripted"] = os.path.join(d, "Scripted.FCStd")
    doc.saveAs(ST["scripted"])
    App.closeDocument(doc.Name)
    doc = util.new_doc("StepLike")  # a STEP opened as it is: shapes in a moved group
    grp = doc.addObject("App::Part", "Product")
    grp.Placement = App.Placement(App.Vector(100, 0, 0), App.Rotation())
    blk = doc.addObject("Part::Feature", "Block")
    blk.Shape = Part.makeBox(10, 10, 10)
    grp.addObject(blk)
    doc.recompute()
    ST["step"] = os.path.join(d, "StepLike.FCStd")
    doc.saveAs(ST["step"])
    App.closeDocument(doc.Name)
    ST["dir"] = d


def test_1_a_scripted_part_opens_with_every_tool():
    doc = App.openDocument(ST["scripted"])
    front(doc)
    assert document.is_incad_part(doc), "still not an InCad part"
    assert document.primary_body(doc).Name == "Big", document.primary_body(doc).Name  # the largest is the main one
    assert s().ribbon._mode == "part", s().ribbon._mode
    ST["part"] = doc.Name


def test_2_hide_show_and_show_all_in_a_part():
    doc = App.getDocument(ST["part"])
    small = doc.getObject("Small")
    Gui.Selection.clearSelection()
    context.set_target(small.Name)
    run("view.hide")
    assert not document.is_shown(small)
    context.set_target(small.Name)  # its row in the browser, though it is hidden
    run("view.show")
    assert document.is_shown(small), "Show did not bring it back"
    for name in ("Big", "Small"):
        context.set_target(name)
        run("view.hide")
    assert not any(document.is_shown(b) for b in document.bodies(doc))
    context.set_target(None)
    Gui.Selection.clearSelection()
    run("view.show_all_parts")  # nothing to pick: everything comes back
    assert all(document.is_shown(b) for b in document.bodies(doc)), [b.Name for b in document.bodies(doc)
                                                                       if not document.is_shown(b)]


def test_3_a_step_like_file_becomes_a_part_in_place():
    doc = App.openDocument(ST["step"])
    front(doc)
    assert document.is_incad_part(doc)
    body = document.primary_body(doc)
    bb = body.Shape.BoundBox
    assert abs(bb.XMin - 100) < 1e-6 and abs(bb.XLength - 10) < 1e-6, ("where it was shown", bb)
    assert not doc.getObject("Block").Visibility, "the original shape still drawn on top"


def test_4_hide_show_all_in_an_assembly():
    p = os.path.join(ST["dir"], "Blk.FCStd")
    d = util.new_doc("Blk")
    b = document.make_part(d)
    b.Tip = util.add_pad(b, util.add_rect_sketch(b, 20, 20, "S"), 10)
    d.recompute()
    d.saveAs(p)
    App.closeDocument(d.Name)
    asm = actions.new_assembly("mm")
    asm.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    link = s().assembly_place(p)
    harness.pump(800)
    Gui.Selection.clearSelection()
    context.set_target(link.Name)
    run("view.hide")
    assert not link.Visibility and link.LinkedObject.Visibility, "hidden in its file, not in the assembly"
    context.set_target(None)
    run("view.show_all_parts")
    assert link.Visibility


def test_5_buttons_and_menus():
    tabs = {mode: repr(ribbon_layout.LAYOUT[mode]) for mode in ("part", "assembly")}
    for mode, text in tabs.items():
        for cmd in ("view.hide", "view.show", "view.show_all_parts"):
            assert cmd in text, (mode, cmd)
    for ctx in ("solid", "asm_face", "face", "browser"):
        for cmd in ("view.hide", "view.show"):
            assert cmd in marking_layout.LAYOUT[ctx]["list"], (ctx, cmd)


def test_9_cleanup():
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_files, test_1_a_scripted_part_opens_with_every_tool, test_2_hide_show_and_show_all_in_a_part,
             test_3_a_step_like_file_becomes_a_part_in_place, test_4_hide_show_all_in_an_assembly,
             test_5_buttons_and_menus, test_9_cleanup])
