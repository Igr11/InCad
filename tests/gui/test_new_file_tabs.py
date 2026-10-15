"""New files and the ribbon with no part open. New (title bar) makes exactly one document — the part — and one more
tab. The user: with no part open the ribbon's first button was New too ("two times new file"): it is Start 2D Sketch,
which makes the part and asks for the plane."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def tabs():
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    return [w.windowTitle() for w in mdi.subWindowList()]


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1500)
    ST["docs"], ST["tabs"] = sorted(App.listDocuments()), tabs()


def test_1_new_makes_one_part_and_nothing_else():
    assert s().ribbon.button("file.new") is None, "New is in the title bar, not twice"
    button = next(b for b in s().title.findChildren(QtWidgets.QToolButton) if b.toolTip().startswith("New")
                  or b.text() == "New")
    QTest.mouseClick(button, QtCore.Qt.LeftButton)
    harness.pump(2500)
    docs, now = sorted(App.listDocuments()), tabs()
    made = [n for n in docs if n not in ST["docs"]]
    state = (ST, docs, now, [(n, App.getDocument(n).Label, document.is_incad_part(App.getDocument(n))) for n in docs])
    assert len(made) == 1 and document.is_incad_part(App.getDocument(made[0])), state
    assert len(now) == len(ST["tabs"]) + 1, ("one more tab", state)
    ST["made"] = made[0]


def test_1b_undo_on_a_new_part_leaves_the_part():
    """The user's log: New, then Undo seven times, then the ribbon said no part and the tab 'Unnamed' was a plain
    FreeCAD document. Undo on a new, untouched part has nothing to undo: the part stays."""
    doc = App.getDocument(ST["made"])
    before = (doc.Label, document.is_incad_part(doc), [o.Name for o in doc.Objects])
    for _ in range(7):
        QTest.keyClick(Gui.getMainWindow(), QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
        harness.pump(350)
    from incad.core import commands
    for _ in range(3):
        commands.REGISTRY.run("edit.undo")
        harness.pump(350)
    after = (doc.Label, document.is_incad_part(doc), [o.Name for o in doc.Objects])
    assert after == before, (before, after, tabs(), doc.UndoNames)
    assert s().ribbon._mode == "part", (s().ribbon._mode, tabs())


def _start_from_the_ribbon():
    before = sorted(App.listDocuments())
    button = s().ribbon.button("sketch.start")
    assert button is not None and button.isVisible(), ("Start 2D Sketch on the no-part ribbon", s().ribbon.tab_names())
    QTest.mouseClick(button, QtCore.Qt.LeftButton)
    harness.pump(2000)
    made = [n for n in sorted(App.listDocuments()) if n not in before]
    assert len(made) == 1 and document.is_incad_part(App.getDocument(made[0])), (before, made)
    assert App.ActiveDocument.Name == made[0], App.ActiveDocument.Name
    assert s().sketches.picking and s().plane_panel.isVisible(), "the plane pick is up on the new part"
    s().sketches.cancel_pick()
    harness.pump(400)


def test_1c_start_2d_sketch_with_nothing_open_makes_the_part_and_asks_the_plane():
    for n in list(App.listDocuments()):
        if n not in ST["docs"]:
            App.closeDocument(n)
            harness.pump(400)
    harness.pump(600)
    assert s().ribbon._mode == "empty", s().ribbon._mode
    _start_from_the_ribbon()


def test_1d_start_2d_sketch_with_a_plain_freecad_file_in_front_too():
    App.newDocument("Unnamed")
    harness.pump(1000)
    assert s().ribbon._mode == "empty", s().ribbon._mode
    _start_from_the_ribbon()


def test_2_cleanup():
    for n in list(App.listDocuments()):
        if n not in ST["docs"]:
            App.closeDocument(n)
            harness.pump(300)


harness.run([test_0_setup, test_1_new_makes_one_part_and_nothing_else, test_1b_undo_on_a_new_part_leaves_the_part,
             test_1c_start_2d_sketch_with_nothing_open_makes_the_part_and_asks_the_plane,
             test_1d_start_2d_sketch_with_a_plain_freecad_file_in_front_too, test_2_cleanup])
