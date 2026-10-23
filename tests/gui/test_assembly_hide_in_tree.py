"""Hide and Show of a part in an assembly stay in the assembly (the user's R180 reducer: a right-click on a part ▸ Hide
opened the part's file in a new tab and hid it there — "it vanished, and now I have to look for it"). The right-click
picks the part as the assembly's component, so Hide hides it in the assembly, no tab opens and its file is left
alone; its row stays in the assembly's tree and Show on it brings it back — also a part an older build hid inside its
own file."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, context, document, prefs, tree  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui import dof_handles as dh  # noqa: E402
from incad.ui.line3d_tool import viewport_of  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def foreign(folder, name, w, x):
    doc = util.new_doc(name)
    body = doc.addObject("PartDesign::Body", name)  # written by a script: not an InCad part
    body.Tip = util.add_pad(body, util.add_rect_sketch(body, w, 20, "S" + name), 6, "Pad" + name)
    doc.recompute()
    path = os.path.join(folder, name + ".FCStd")
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    return path


def asm():
    return App.getDocument(ST["asm"])


def views():
    return [n for n in App.listDocuments() if Gui.getDocument(n) is not None and Gui.getDocument(n).ActiveView]


def run(cmd):
    r = commands.REGISTRY.run(cmd)
    harness.pump(900)
    assert getattr(r, "ok", True), (cmd, getattr(r, "error", ""))


def test_0_assembly_of_scripted_parts():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = tempfile.mkdtemp(prefix="incad_hide_tree_")
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(d, "Asm.FCStd"))
    cover = s().assembly_place(foreign(d, "Cover", 40, 0))
    base = s().assembly_place(foreign(d, "Base", 30, 0))
    base.Placement = App.Placement(App.Vector(60, 0, 0), App.Rotation())
    doc.recompute()
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1200)
    ST.update(asm=doc.Name, cover=cover.Name, base=base.Name)


def test_1_right_click_hide_stays_in_the_assembly():
    link = asm().getObject(ST["cover"])
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    bb = link.Shape.BoundBox
    x, y = dh.screen(view, vp, App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))
    local = QtCore.QPoint(int(x), int(y))
    menu = s()._open_marking_menu(view, vp, local, vp.mapToGlobal(local), False)
    harness.pump(400)
    sel = [(x.Object.Document.Name, x.Object.Name) for x in Gui.Selection.getSelectionEx("", 0)]
    assert sel and all(d == ST["asm"] for d, _ in sel), ("picked in the part's file", sel)
    assert App.ActiveDocument.Name == ST["asm"], App.ActiveDocument.Name
    try:
        if menu is not None:
            menu.close()
    except RuntimeError:
        pass  # it closed by itself
    harness.pump(200)
    run("view.hide")  # the menu's Hide
    assert not link.Visibility, "the part did not hide in the assembly"
    assert link.LinkedObject.Visibility and document.is_shown(link.LinkedObject), "hidden in its own file"
    assert App.ActiveDocument.Name == ST["asm"] and views() == [ST["asm"]], ("a tab opened", views())


def test_2_its_row_stays_and_show_brings_it_back():
    rows = [n.name for n in tree.build(asm())[0].children]
    assert ST["cover"] in rows, rows
    Gui.Selection.clearSelection()
    context.set_target(ST["cover"])  # its row's menu ▸ Show
    run("view.show")
    assert asm().getObject(ST["cover"]).Visibility


def test_3_show_brings_back_a_part_hidden_inside_its_file():
    link = asm().getObject(ST["base"])
    document.set_visibility([link.LinkedObject], False)  # what the old build did from the assembly
    harness.pump(400)
    assert not document.is_shown(link.LinkedObject)
    context.set_target(link.Name)
    run("view.show")
    assert link.Visibility and document.is_shown(link.LinkedObject), "still hidden in its file"


def test_9_cleanup():
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_assembly_of_scripted_parts, test_1_right_click_hide_stays_in_the_assembly,
             test_2_its_row_stays_and_show_brings_it_back, test_3_show_brings_back_a_part_hidden_inside_its_file,
             test_9_cleanup])
