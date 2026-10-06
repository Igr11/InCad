import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}
PLATE = 40 * 30 * 10


def s():
    return shell.instance()


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def asm():
    return App.getDocument(ST["asm"])


def plate_doc():
    return assembly.components(asm())[0].LinkedObject.Document


def plate_volume():
    return document.primary_body(plate_doc()).Shape.Volume


def select_both():
    doc = asm()
    a, b = assembly.components(doc)
    root = assembly.assembly_of(doc)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, root.Name, "%s.Face1" % a.Name)
    Gui.Selection.addSelection(doc.Name, root.Name, "%s.Face1" % b.Name)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_cut_")
    paths = []
    for name, w, h, t in (("Plate", 40, 30, 10), ("Block", 10, 10, 10)):
        d, p = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
        paths.append(p)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = doc.Name
    for p in paths:
        s().assembly_place(p)
    b = assembly.components(doc)[1]
    b.Placement = App.Placement(App.Vector(15, 10, 5), App.Rotation())
    doc.recompute()
    harness.pump(800)


def test_1_cancel_leaves_the_part_file_unchanged():
    undo = list(plate_doc().UndoNames)
    select_both()
    commands.REGISTRY.run("assembly.combine")
    harness.pump(1500)
    a, b = assembly.components(asm())
    assert dialog().values()["base"].startswith(a.Name) and dialog().values()["tools"].startswith(b.Name), \
        dialog().values()
    assert not dialog().error_text(), dialog().error_text()
    assert plate_volume() < PLATE - 1  # previewed
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    assert abs(plate_volume() - PLATE) < 1e-6, plate_volume()
    assert [o for o in plate_doc().Objects if o.TypeId == "App::Link"] == []
    assert list(plate_doc().UndoNames) == undo, (plate_doc().UndoNames, undo)


def test_2_ok_writes_the_pocket_and_it_follows_the_tool():
    select_both()
    commands.REGISTRY.run("assembly.combine")
    harness.pump(1500)
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert abs(plate_volume() - (PLATE - 10.4 * 10.4 * 5.2)) < 0.1, plate_volume()
    # one step in each document; FreeCAD marks a step shared by several documents with "-> "
    assert plate_doc().UndoNames[0].endswith("Combine") and asm().UndoNames[0].endswith("Combine"), \
        (plate_doc().UndoNames, asm().UndoNames)
    body = document.primary_body(plate_doc())
    assert not body.Shape.isInside(App.Vector(20, 15, 9), 1e-6, True)
    b = assembly.components(asm())[1]
    b.Placement = App.Placement(App.Vector(2, 2, 5), App.Rotation())
    asm().recompute()
    s().schedule_refresh()
    harness.pump(1200)
    assert body.Shape.isInside(App.Vector(20, 15, 9), 1e-6, True)
    assert not body.Shape.isInside(App.Vector(7, 7, 9), 1e-6, True)


def test_3_base_change_then_cancel_leaves_both_parts_unchanged():
    a, b = assembly.components(asm())
    block_doc = b.LinkedObject.Document
    plate_before, block_before = plate_volume(), document.primary_body(block_doc).Shape.Volume
    records = len([o for o in asm().Objects if hasattr(o, "InCadAsmCut")])
    select_both()
    commands.REGISTRY.run("assembly.combine")
    harness.pump(1500)
    dialog().set_pick("base", b.Name)
    dialog().set_pick("tools", a.Name)
    harness.pump(1500)
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert abs(plate_volume() - plate_before) < 1e-6, (plate_volume(), plate_before)
    assert abs(document.primary_body(block_doc).Shape.Volume - block_before) < 1e-6
    assert len([o for o in asm().Objects if hasattr(o, "InCadAsmCut")]) == records


def test_4_opening_a_component_keeps_its_unsaved_cut():
    volume = plate_volume()
    a = assembly.components(asm())[0]
    s().open_component(a)
    harness.pump(1500)
    assert abs(plate_volume() - volume) < 1e-6, (plate_volume(), volume)
    assert App.ActiveDocument is plate_doc()


def test_5_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_setup, test_1_cancel_leaves_the_part_file_unchanged,
             test_2_ok_writes_the_pocket_and_it_follows_the_tool,
             test_3_base_change_then_cancel_leaves_both_parts_unchanged,
             test_4_opening_a_component_keeps_its_unsaved_cut, test_5_cleanup])
