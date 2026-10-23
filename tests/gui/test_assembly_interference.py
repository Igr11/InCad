"""Interference in an assembly (the user: "where parts go into each other must show in a bright colour"): two blocks
5 mm into each other show their shared 1000 mm³ in red over the parts and listed; moved to just touch, nothing; back,
it is there again; Interference off removes the red and the list."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, document, interference, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def save_block(folder, name):
    doc = util.new_doc(name)
    body = document.make_part(doc)
    body.Tip = util.add_pad(body, util.add_rect_sketch(body, 20, 20, "S"), 10)
    doc.recompute()
    path = os.path.join(folder, name + ".FCStd")
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    return path


def asm():
    return App.getDocument(ST["asm"])


def move_b(x):
    b = asm().getObject(ST["b"])
    b.Placement = App.Placement(V(x, 0, 0), App.Rotation())
    asm().recompute()
    s().schedule_refresh()
    harness.pump(1500)


def shown():
    d = s()._interference
    return d is not None and d[0].root is not None


def panel_title():
    p = s().info_panel
    return p.findChild(__import__("incad.qt", fromlist=["QtWidgets"]).QtWidgets.QLabel, "InCadDialogTitle").text() \
        if p is not None else None


def test_0_two_blocks():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = tempfile.mkdtemp(prefix="incad_interference_")
    pa, pb = save_block(d, "BlockA"), save_block(d, "BlockB")
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(d, "Asm.FCStd"))
    a = s().assembly_place(pa)
    b = s().assembly_place(pb)
    harness.pump(600)
    ST.update(asm=doc.Name, a=a.Name, b=b.Name)
    a.Placement = App.Placement()
    move_b(15)  # 5 mm into A: 5 x 20 x 10 shared
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)


def test_1_on_shows_the_overlap():
    r = commands.REGISTRY.run("assembly.interference")
    harness.pump(1500)
    assert getattr(r, "ok", True), getattr(r, "error", "")
    assert s().interference_shown()
    found = interference.overlaps(asm())
    assert len(found) == 1 and abs(found[0][3] - 1000) < 1e-3, [(a.Label, b.Label, v) for a, b, _, v in found]
    assert shown(), "the overlap is not drawn"
    assert panel_title() == "Interference: 1", panel_title()
    if os.environ.get("INNCAD_SHOT"):
        Gui.ActiveDocument.ActiveView.saveImage(os.environ["INNCAD_SHOT"], 1200, 900, "Current")


def test_2_touching_is_no_interference():
    move_b(20)
    assert interference.overlaps(asm()) == []
    assert not shown(), "red left on touching parts"
    assert panel_title() == "Interference: 0", panel_title()


def test_3_back_into_it():
    move_b(12)  # 8 mm in: 1600 mm³
    found = interference.overlaps(asm())
    assert len(found) == 1 and abs(found[0][3] - 1600) < 1e-3, found and found[0][3]
    assert shown() and panel_title() == "Interference: 1"


def test_4_off_removes_it():
    commands.REGISTRY.run("assembly.interference")
    harness.pump(800)
    assert not s().interference_shown()
    assert not shown()
    assert s().info_panel is None or not getattr(s().info_panel, "_incad_interference", False)


def test_9_cleanup():
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_two_blocks, test_1_on_shows_the_overlap, test_2_touching_is_no_interference, test_3_back_into_it,
             test_4_off_removes_it, test_9_cleanup])
