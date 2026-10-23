"""A component whose file was made outside InnCad (the user's R180 reducer: parts written by a script), double-clicked
in the assembly: its tab opens as an InnCad part — the part ribbon, its Solid in the browser — and a Solid hidden
there comes back with Undo and with Hide / Show on its row (it opened as "Not an InnCad part", Hide took the part
away and nothing could bring it back); Hide on the component in the assembly hides it there, not in its file."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, context, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def foreign_part(folder):
    """A Body made the way a script makes it: no InnCad marks in the file."""
    doc = util.new_doc("Cover")
    body = doc.addObject("PartDesign::Body", "Cover")
    body.Tip = util.add_pad(body, util.add_rect_sketch(body, 40, 30, "S"), 5)
    doc.recompute()
    assert not document.is_incad_part(doc)
    path = os.path.join(folder, "Cover.FCStd")
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    return path


def run(cmd):
    r = commands.REGISTRY.run(cmd)
    harness.pump(800)
    assert getattr(r, "ok", True), (cmd, getattr(r, "error", ""))


def test_0_assembly_with_a_foreign_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = tempfile.mkdtemp(prefix="incad_foreign_")
    path = foreign_part(d)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(d, "Asm.FCStd"))
    link = s().assembly_place(path)
    harness.pump(1000)
    ST.update(asm=doc.Name, link=link.Name, part=link.LinkedObject.Document.Name)


def test_1_hide_in_the_assembly_stays_in_the_assembly():
    Gui.Selection.clearSelection()
    context.set_target(ST["link"])
    run("view.toggle_visibility")
    asm = App.getDocument(ST["asm"])
    link = asm.getObject(ST["link"])
    assert not link.Visibility and link.LinkedObject.Visibility, "hidden in its file instead of the assembly"
    assert App.ActiveDocument.Name == ST["asm"], "Hide opened another tab"
    context.set_target(ST["link"])
    run("view.toggle_visibility")
    assert link.Visibility, "Hide / Show did not bring it back"


def test_2_double_click_opens_it_as_an_incad_part():
    s()._on_feature_activated(ST["link"])  # a double-click on its row (or on it in the view): Edit
    harness.pump(2500)
    part = App.ActiveDocument
    assert part.Name == ST["part"], part.Name
    assert document.is_incad_part(part), "still 'Not an InnCad part': no tools in its tab"
    assert document.primary_body(part) is not None
    labels = [n.label for n in __import__("incad.core.tree", fromlist=["build"]).build(part)[0].children]
    assert "Pad" in labels, ("its history in the browser", labels)


def test_3_a_hidden_solid_comes_back_with_undo():
    part = App.ActiveDocument
    body = document.primary_body(part)
    Gui.Selection.clearSelection()
    context.set_target(body.Name)
    run("view.toggle_visibility")
    assert not document.is_shown(body), "the Solid did not hide"
    run("edit.undo")
    assert document.is_shown(body), "Undo did not bring the hidden Solid back"


def test_9_cleanup():
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_assembly_with_a_foreign_part, test_1_hide_in_the_assembly_stays_in_the_assembly,
             test_2_double_click_opens_it_as_an_incad_part, test_3_a_hidden_solid_comes_back_with_undo,
             test_9_cleanup])
