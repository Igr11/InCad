"""Relationships rows (Inventor's browser): their own marking menu, Suppress / Unsuppress, Rename and the Delete key."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, context, prefs, safe, tree  # noqa: E402
from incad.features import constraints as C  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["asm"])


def joint_rows():
    rel = [n for n in tree.build(doc())[0].children if n.kind == "relationships"][0]
    return {n.name: n for n in rel.children}


def click_row(label):
    b = s().browser
    item = b.item_by_label(label)
    parent = item.parent()
    while parent is not None:
        parent.setExpanded(True)
        parent = parent.parent()
    harness.pump(100)
    QTest.mouseClick(b.tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, b.tree.visualItemRect(item).center())
    harness.pump(400)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_rows_")
    for name, w, h, t in (("Plate", 40, 30, 10), ("Block", 10, 10, 10)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    d = actions.new_assembly("mm")
    d.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = d.Name
    a, b = s().assembly_place(ST["Plate"]), s().assembly_place(ST["Block"])
    top = [i + 1 for i, f in enumerate(a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    bot = [i + 1 for i, f in enumerate(b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
    r = safe.run_safely("Mate", lambda: C.MATE.create(d, None, None, dict(
        C.MATE.defaults(d, None), first="%s:Face%d" % (a.Name, top), second="%s:Face%d" % (b.Name, bot))), d)
    assert r.ok, r.error
    ST["j"], ST["b"] = r.value.Name, b.Name
    s().schedule_refresh()
    harness.pump(800)


def test_1_row_menu_is_the_constraint_menu():
    s()._on_browser_marking_menu(ST["j"], QtCore.QPoint(300, 300))
    harness.pump(300)
    assert s().menu_kind == "joint", s().menu_kind
    s().marking_menu.close()
    harness.pump(200)


def test_2_suppress_from_the_row_and_back():
    j = doc().getObject(ST["j"])
    context.set_target(j.Name)
    r = commands.REGISTRY.run("constraint.suppress")
    harness.pump(500)
    assert r.ok and j.Suppressed, (r.ok, r.error)
    assert joint_rows()[j.Name].state == "suppressed"
    assert doc().UndoNames[0] == "Suppress / Unsuppress", doc().UndoNames[:2]
    context.set_target(j.Name)
    r = commands.REGISTRY.run("constraint.suppress")
    harness.pump(500)
    assert r.ok and not j.Suppressed, (r.ok, r.error)


def test_3_rename_from_the_row():
    j = doc().getObject(ST["j"])
    context.set_target(j.Name)
    actions.rename(ask=lambda current: "Block on plate")
    harness.pump(300)
    assert j.Label == "Block on plate", j.Label


def test_4_delete_key_on_a_selected_row():
    j_name = ST["j"]
    s().schedule_refresh()
    harness.pump(500)
    click_row("Block on plate")
    n0 = len(doc().UndoNames)
    r = commands.REGISTRY.run("edit.delete")
    harness.pump(600)
    assert r.ok, r.error
    assert doc().getObject(j_name) is None
    assert doc().getObject(ST["b"]) is not None, "the part stays"
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Delete", doc().UndoNames[:2]
    commands.REGISTRY.run("edit.undo")
    harness.pump(600)
    assert doc().getObject(j_name) is not None, "Undo brings the constraint back"


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_setup, test_1_row_menu_is_the_constraint_menu, test_2_suppress_from_the_row_and_back,
             test_3_rename_from_the_row, test_4_delete_key_on_a_selected_row, test_9_cleanup])
