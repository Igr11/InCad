"""Hide / Show in an assembly and Open (the user: "Hide, Show, axes, sketches and the like in the assembly too — the
white axis lines show"; "open the part to edit in a window of its own, as in Inventor"): Hide All Axes takes the
parts' axes off (remembered, back with Show All Axes), Show / Hide All Origin and Sketches act on the assembly's
origin and its parts', and Open makes the component's part the active tab, alone (no assembly context)."""
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
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def run(cmd):
    r = commands.REGISTRY.run(cmd)
    harness.pump(700)
    assert getattr(r, "ok", True), (cmd, getattr(r, "error", ""))


def save_part(folder):
    doc = util.new_doc("Shaft")
    body = document.make_part(doc)
    sk = body.newObject("Sketcher::SketchObject", "C")
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5))
    body.Tip = util.add_pad(body, sk, 30, "Shaft")
    util.add_rect_sketch(body, 6, 6, "Extra")  # a sketch nothing uses: shown
    doc.recompute()
    path = os.path.join(folder, "Shaft.FCStd")
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    return path


def part_doc():
    return App.getDocument(ST["link_doc"])


def test_0_assembly():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    prefs.set_assembly_axes(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = tempfile.mkdtemp(prefix="incad_asm_vis_")
    path = save_part(d)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(d, "Asm.FCStd"))
    link = s().assembly_place(path)
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1200)
    ST.update(asm=doc.Name, link=link.Name, link_doc=link.LinkedObject.Document.Name)
    assert s().ribbon is not None


def test_1_hide_and_show_all_axes():
    assert s()._axis_lines is not None and s()._axis_lines.root is not None, "no axes to begin with"
    run("view.axes_hide_all")
    assert prefs.assembly_axes() is False
    assert s()._axis_lines is None, "the axes are still drawn"
    run("view.axes_show_all")
    assert s()._axis_lines is not None and s()._axis_lines.root is not None, "the axes did not come back"


def test_1b_hidden_axes_show_while_a_constraint_waits():
    run("view.axes_hide_all")
    assert s()._axis_lines is None
    Gui.Selection.clearSelection()
    run("constrain.mate")
    harness.pump(800)
    assert s().feature_session is not None, "no Mate dialog"
    assert s()._axis_lines is not None and s()._axis_lines.root is not None, "no axes to pick in the dialog"
    s().feature_session.cancel()
    harness.pump(800)
    assert s()._axis_lines is None, "the axes stayed after the dialog"
    run("view.axes_show_all")


def test_2_origin_in_the_assembly():
    asm = App.getDocument(ST["asm"])
    origins = [f for d in (asm, part_doc()) for o in d.Objects if o.TypeId == "App::Origin" for f in o.OriginFeatures]
    run("view.origin_show_all")
    assert all(document.is_shown(f) for f in origins), [(f.Document.Name, f.Name) for f in origins
                                                        if not document.is_shown(f)]
    run("view.origin_hide_all")
    assert not any(document.is_shown(f) for f in origins)


def test_3_sketches_of_the_parts():
    extra = part_doc().getObject("Extra")
    run("view.sketches_hide_all")
    assert not extra.Visibility, "the part's sketch still shows"
    run("view.sketches_show_all")
    assert extra.Visibility


def test_4_open_the_part_alone():
    App.setActiveDocument(ST["asm"])
    Gui.ActiveDocument = Gui.getDocument(ST["asm"])
    harness.pump(400)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(ST["asm"], ST["link"])
    run("assembly.open")
    harness.pump(800)
    assert App.ActiveDocument.Name == ST["link_doc"], App.ActiveDocument.Name
    assert s()._active_context() is None, "Open is the part alone, not Edit's assembly context"
    assert ST["link_doc"] not in s()._contexts


def test_9_cleanup():
    prefs.set_assembly_axes(True)
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_assembly, test_1_hide_and_show_all_axes,
             test_1b_hidden_axes_show_while_a_constraint_waits, test_2_origin_in_the_assembly,
             test_3_sketches_of_the_parts, test_4_open_the_part_alone, test_9_cleanup])
