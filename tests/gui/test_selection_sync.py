"""The model tree and the 3D view share one selection: a tree click selects the object in the model (and shows a
hidden plane, axis or sketch while it is selected), a 3D pick highlights the tree row, the tree keeps its
selection and its expanded Origin across refreshes, and Hide / Show acts on whatever is selected."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def _sel():
    return [(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx()]


def _item(label):
    return shell.instance().browser.item_by_label(label)


def _click_row(label):
    b = shell.instance().browser
    item = _item(label)
    parent = item.parent()
    while parent is not None:
        parent.setExpanded(True)
        parent = parent.parent()
    harness.pump(100)
    QTest.mouseClick(b.tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, b.tree.visualItemRect(item).center())
    harness.pump(400)


def _origin(role):
    from incad.core import document
    return [o for o in document.origin_items(document.primary_body(App.ActiveDocument)) if o.Role == role][0]


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    from incad.core import document
    body = document.primary_body(App.ActiveDocument)
    sk = util.add_rect_sketch(body)
    pad = util.add_pad(body, sk, 10)
    body.Tip = pad
    App.ActiveDocument.recompute()
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(600)


def test_1_tree_click_selects_in_the_model_and_shows_a_hidden_axis_while_selected():
    from incad.core import document
    z = _origin("Z_Axis")
    assert not document.is_shown(z)
    _click_row("Z Axis")
    assert _sel() == [("Z_Axis", ())], _sel()
    assert document.is_shown(z), "shown while its row is selected"
    assert not document.is_shown(_origin("X_Axis")), "only the selected one"
    _click_row("Pad")
    assert _sel() == [("Pad", ())], _sel()
    assert not document.is_shown(z), "hidden again when the selection moves on"
    assert document.SHOWN_PROP not in z.PropertiesList


def test_2_a_3d_pick_highlights_the_tree_row():
    b = shell.instance().browser
    Gui.Selection.clearSelection()
    harness.pump(300)
    assert b.selected_names() == [], b.selected_names()
    Gui.Selection.addSelection(App.ActiveDocument.Name, "Pad", "Face1")
    harness.pump(400)
    assert b.selected_names() == ["Pad"], b.selected_names()
    Gui.Selection.clearSelection()
    harness.pump(300)
    assert b.selected_names() == []


def test_3_a_3d_pick_of_a_shown_plane_expands_origin_and_highlights_its_row():
    from incad.core import document
    b = shell.instance().browser
    xy = _origin("XY_Plane")
    document.set_visibility([xy], True)
    shell.instance().schedule_refresh()
    harness.pump(500)
    _item("Origin").setExpanded(False)  # the user closed it
    harness.pump(200)
    Gui.Selection.addSelection(App.ActiveDocument.Name, xy.Name)
    harness.pump(400)
    assert b.selected_names() == [xy.Name], b.selected_names()
    assert _item("Origin").isExpanded()
    Gui.Selection.clearSelection()
    harness.pump(300)
    document.set_visibility([xy], False)
    shell.instance().schedule_refresh()
    harness.pump(400)


def test_4_refresh_keeps_the_selection_and_the_expanded_origin():
    b = shell.instance().browser
    _click_row("Y Axis")
    assert b.selected_names() == ["Y_Axis"]
    App.ActiveDocument.recompute()
    shell.instance().schedule_refresh()
    harness.pump(600)
    assert b.selected_names() == ["Y_Axis"], b.selected_names()
    assert _item("Origin").isExpanded()
    assert _sel() == [("Y_Axis", ())]


def test_5_hide_show_on_the_selected_axis_after_a_refresh_sticks():
    from incad.core import document
    y = _origin("Y_Axis")
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert r.ok, r.error
    harness.pump(500)
    assert document.is_shown(y)
    _click_row("Pad")
    assert document.is_shown(y), "a Hide / Show choice outlives the row's selection"
    _click_row("Y Axis")
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert r.ok, r.error
    harness.pump(500)
    assert not document.is_shown(y)
    _click_row("Pad")
    assert not document.is_shown(y)


def test_6_hide_show_with_a_face_selected_says_what_was_selected():
    Gui.Selection.clearSelection()
    shell.instance().browser.tree.clearSelection()
    from incad.core import context
    context.set_target(None)
    Gui.Selection.addSelection(App.ActiveDocument.Name, "Pad", "Face1")
    harness.pump(300)
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert not r.ok and "Pad" in r.error, (r.ok, r.error)
    Gui.Selection.clearSelection()
    harness.pump(200)


harness.run([test_0_part, test_1_tree_click_selects_in_the_model_and_shows_a_hidden_axis_while_selected,
             test_2_a_3d_pick_highlights_the_tree_row, test_3_a_3d_pick_of_a_shown_plane_expands_origin_and_highlights_its_row,
             test_4_refresh_keeps_the_selection_and_the_expanded_origin,
             test_5_hide_show_on_the_selected_axis_after_a_refresh_sticks,
             test_6_hide_show_with_a_face_selected_says_what_was_selected])
