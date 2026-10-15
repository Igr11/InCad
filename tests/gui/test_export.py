import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, document, prefs, suppress  # noqa: E402
from incad.features import thread  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_thread import shaft, cyl_face  # noqa: E402

ST = {"dir": tempfile.mkdtemp()}


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def menu_action(title, label):
    bar = Gui.getMainWindow().menuBar()
    menu = bar.findChild(QtWidgets.QMenu, shell.MENU_PREFIX + title)
    return next(a for a in menu.actions() if a.text() == label)


def answer_threads(button_text):
    """Read the real threads question when it shows and click one of its buttons."""
    seen = {}

    def poll():
        box = QtWidgets.QApplication.activeModalWidget()
        if isinstance(box, QtWidgets.QMessageBox):
            seen["text"] = box.text()
            seen["buttons"] = [b.text() for b in box.buttons()]
            next(b for b in box.buttons() if b.text() == button_text).click()
        else:
            QtCore.QTimer.singleShot(100, poll)
    QtCore.QTimer.singleShot(100, poll)
    return seen


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    pad = shaft(doc(), body(), radius=4.0, length=16)
    thread.create(doc(), body(), None, dict(thread.defaults(doc(), body(), None), face=cyl_face(pad, 4), size="M8"))
    doc().recompute()
    ST["threaded"] = body().Shape.Volume
    commands.REGISTRY.run("feature.threads_toggle")
    harness.pump(1500)
    assert suppress.threads_off(doc())
    ST["plain"] = body().Shape.Volume
    assert ST["plain"] > ST["threaded"] + 1.0, (ST["plain"], ST["threaded"])


def test_1_menu_export_turns_threads_on_for_a_step():
    path = os.path.join(ST["dir"], "shaft.step")
    actions.EXPORT_ASK = lambda d: (path, "step")  # stands for the native Save dialog
    undo = list(doc().UndoNames)
    Gui.getDocument(doc().Name).Modified = False
    seen = answer_threads("Turn On for Export")
    menu_action("File", "Export").trigger()
    harness.pump(1500)
    assert "Threads Off" in seen.get("text", ""), seen
    assert set(seen["buttons"]) == {"Turn On for Export", "Export Without Threads", "Cancel"}, seen
    assert os.path.isfile(path)
    assert abs(Part.read(path).Volume - ST["threaded"]) < 1e-2, (Part.read(path).Volume, ST["threaded"])
    assert suppress.threads_off(doc()), "threads go back off after the export"
    assert abs(body().Shape.Volume - ST["plain"]) < 1e-3
    assert not Gui.getDocument(doc().Name).Modified
    assert list(doc().UndoNames) == undo, (doc().UndoNames, undo)
    assert prefs.export_folder() == ST["dir"] and prefs.export_type() == "step"


def test_2_export_without_threads_to_stl():
    import Mesh
    path = os.path.join(ST["dir"], "shaft.stl")
    actions.EXPORT_ASK = lambda d: (path, "stl_fine")
    answer_threads("Export Without Threads")
    menu_action("File", "Export").trigger()
    harness.pump(1500)
    assert os.path.isfile(path)
    assert abs(Mesh.Mesh(path).Volume - ST["plain"]) < ST["plain"] * 0.01, (Mesh.Mesh(path).Volume, ST["plain"])
    assert prefs.export_type() == "stl_fine"
    actions.EXPORT_ASK = None


harness.run([test_0_setup, test_1_menu_export_turns_threads_on_for_a_step, test_2_export_without_threads_to_stl])
