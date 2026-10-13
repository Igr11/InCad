"""Assembly: DOF on the rows, dragging a part along its own freedoms (FreeCAD's native drag), DOF glyphs."""
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
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, prefs, safe, tree  # noqa: E402
from incad.features import constraints as C  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["asm"])


def obj(key):
    return doc().getObject(ST[key])


def rows():
    return {n.name: n.detail for n in tree.build(doc())[0].children if n.kind == "component"}


def fz(link, z):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if abs(f.CenterOfMass.z - z) < 1e-6][0])


def constrain(kind, first, second):
    r = safe.run_safely(kind.TITLE, lambda: kind.create(doc(), None, None, dict(kind.defaults(doc(), None),
                                                                               first=first, second=second)), doc())
    assert r.ok, r.error
    s().schedule_refresh()
    harness.pump(1200)
    return r.value


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_drag_")
    for name, w, h, t in (("Plate", 60, 40, 10), ("Mid", 20, 20, 10), ("Top", 8, 8, 6)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    d = actions.new_assembly("mm")
    d.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = d.Name
    for key, name in (("p", "Plate"), ("m", "Mid"), ("t", "Top")):
        ST[key] = s().assembly_place(ST[name]).Name
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1500)


def test_1_rows_show_dof():
    assert rows() == {ST["p"]: "grounded", ST["m"]: "DOF 6", ST["t"]: "DOF 6"}, rows()
    constrain(C.MATE, fz(obj("m"), 10), fz(obj("t"), 0))  # Top on the free Mid
    assert rows()[ST["t"]] == "DOF 3", rows()


def test_2_undo_of_a_constraint_recounts():
    commands.REGISTRY.run("edit.undo")
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 6", rows()
    commands.REGISTRY.run("edit.redo")
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 3", rows()


def test_3_count_does_not_mark_the_file_modified():
    App.setActiveDocument(ST["asm"])
    gdoc = Gui.getDocument(ST["asm"])
    Gui.ActiveDocument = gdoc
    Gui.runCommand("Std_Save")  # as from the window (App's save leaves the Gui flag set)
    harness.pump(500)
    assert not gdoc.Modified, "saved"
    from incad.core import dof
    dof._CACHE.clear()
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 3", rows()  # it did recount
    assert not gdoc.Modified, "a count is no change to save"


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


TESTS = [test_0_setup, test_1_rows_show_dof, test_2_undo_of_a_constraint_recounts,
         test_3_count_does_not_mark_the_file_modified]
harness.run(TESTS + [test_9_cleanup])
