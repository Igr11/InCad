"""The user on a new file: click the XY plane, then Start 2D Sketch — InCad asked for a plane again instead of
starting the sketch on the one selected. Real clicks: the plane's row in the model tree, then the ribbon button."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import browser, shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def plane(role):
    body = document.primary_body(App.ActiveDocument)
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def row(name):
    tree = s().browser.tree
    items = [i for i in s().browser._items() if i.data(0, browser.NAME_ROLE) == name]
    assert items, ("a row for", name, [i.data(0, browser.NAME_ROLE) for i in s().browser._items()])
    item = items[0]
    parent = item.parent()
    while parent is not None:
        parent.setExpanded(True)
        parent = parent.parent()
    harness.pump(200)
    tree.scrollToItem(item)
    return tree, item


def test_0_new_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    ST["doc"] = App.ActiveDocument.Name


def test_1_plane_row_then_start_2d_sketch_starts_on_that_plane():
    xy = plane("XY_Plane")
    tree, item = row(xy.Name)
    QTest.mouseClick(tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, tree.visualItemRect(item).center())
    harness.pump(600)
    selected = [(x.ObjectName, list(x.SubElementNames)) for x in Gui.Selection.getSelectionEx(ST["doc"])]
    button = s().ribbon.button("sketch.start")
    assert button is not None and button.isEnabled(), button
    QTest.mouseClick(button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    editing = s().sketches.editing()
    assert editing is not None, ("the sketch starts at once", selected, s().sketches.picking,
                                 [(x.ObjectName, list(x.SubElementNames)) for x in Gui.Selection.getSelectionEx(ST["doc"])])
    assert editing.AttachmentSupport[0][0].Name == xy.Name, editing.AttachmentSupport


def test_2_cleanup():
    s().sketches.finish()
    harness.pump(800)
    App.closeDocument(ST["doc"])
    harness.pump(500)


harness.run([test_0_new_part, test_1_plane_row_then_start_2d_sketch_starts_on_that_plane, test_2_cleanup])
