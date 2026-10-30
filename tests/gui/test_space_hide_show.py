"""Space hides / shows what is picked (the user: Space did nothing), as in FreeCAD, but through InCad's own Hide /
Show: from the model tree (whose typing search used to take every key) and from the 3D view."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def space(widget):
    widget.setFocus()
    harness.pump(100)
    QTest.keyClick(widget, QtCore.Qt.Key_Space)
    harness.pump(400)


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(App.ActiveDocument)
    pad = util.add_pad(body, util.add_rect_sketch(body), 10)
    body.Tip = pad
    App.ActiveDocument.recompute()
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(600)
    assert document.is_shown(body)
    ST["body"] = body


def test_1_space_on_the_tree():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, ST["body"].Name)
    harness.pump(300)
    tree = shell.instance().browser.tree
    space(tree)
    assert not document.is_shown(ST["body"]), "Space on the tree did not hide the Solid"
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, ST["body"].Name)
    harness.pump(300)
    space(tree)
    assert document.is_shown(ST["body"]), "Space on the tree did not show the Solid again"


def test_2_space_in_the_3d_view():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, ST["body"].Name)
    harness.pump(300)
    space(Gui.ActiveDocument.ActiveView.graphicsView())
    assert not document.is_shown(ST["body"]), "Space in the 3D view did not hide the Solid"
    commands.REGISTRY.run("view.show_all_parts")
    harness.pump(400)


def test_9_cleanup():
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_part, test_1_space_on_the_tree, test_2_space_in_the_3d_view, test_9_cleanup])
