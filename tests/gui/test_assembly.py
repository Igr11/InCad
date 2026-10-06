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
from incad.core import assembly, commands, prefs, tree  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}


def s():
    return shell.instance()


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def asm_doc():
    return App.getDocument(ST["asm"])


def face(link, z):
    return [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - z) < 1e-6][0]


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_asm_")
    for name, w, h, t in (("Plate", 40, 30, 10), ("Block", 10, 10, 10)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = doc.Name
    harness.pump(800)
    assert s().ribbon.mode() == "assembly" if hasattr(s().ribbon, "mode") else True


def test_1_place_two_parts_first_grounded():
    a = s().assembly_place(ST["Plate"])
    b = s().assembly_place(ST["Block"])
    harness.pump(800)
    assert App.ActiveDocument is asm_doc(), App.ActiveDocument
    assert assembly.is_grounded(a) and not assembly.is_grounded(b)
    labels = [n.label for n in tree.build(asm_doc())[0].children]
    assert labels[:2] == ["Plate", "Block"], labels
    assert "Could not" not in s().status.texts()["message"], s().status.texts()  # closed part files are no error
    ST["a"], ST["b"] = a.Name, b.Name


def test_2_mate_from_3d_picks_is_one_undo_step_and_undo_restores():
    doc = asm_doc()
    a, b = doc.getObject(ST["a"]), doc.getObject(ST["b"])
    before = App.Placement(b.Placement)
    undo = len(doc.UndoNames)
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("constrain.mate")
    harness.pump(800)
    asm = assembly.assembly_of(doc)
    Gui.Selection.addSelection(doc.Name, asm.Name, "%s.Face%d" % (a.Name, face(a, 10)))
    harness.pump(600)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, asm.Name, "%s.Face%d" % (b.Name, face(b, 0)))
    harness.pump(1200)
    v = dialog().values()
    assert v["first"] == "%s:Face%d" % (a.Name, face(a, 10)) and v["second"].startswith(b.Name), v
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    assert abs(b.Shape.BoundBox.ZMin - 10) < 1e-4, b.Shape.BoundBox
    assert doc.UndoNames[0] == "Mate" and len(doc.UndoNames) == undo + 1, doc.UndoNames
    commands.REGISTRY.run("edit.undo")
    harness.pump(1000)
    assert b.Placement.isSame(before, 1e-6), (b.Placement, before)


def test_3_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_setup, test_1_place_two_parts_first_grounded,
             test_2_mate_from_3d_picks_is_one_undo_step_and_undo_restores, test_3_cleanup])
