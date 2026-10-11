"""Constraints window in a real FreeCAD window: ribbon, filter by pick, highlight, delete (window, right-click,
Delete key with the window open), closes with the sketch."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.core import sketch_constraints as sc  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_sketch_constraints import rect  # noqa: E402

ST = {}


def sk():
    return Gui.ActiveDocument.getInEdit().Object


def panel():
    return shell.instance().constraints_panel


def test_0_sketch_with_a_rectangle():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    shell.instance().plane_panel.button("XY_Plane").click()
    harness.pump(1200)
    rect(sk())
    App.ActiveDocument.recompute()
    harness.pump(500)


def test_1_ribbon_opens_the_window_with_every_constraint():
    b = shell.instance().ribbon.button("sketch.constraints_window")
    assert b is not None and b.isVisible()
    b.click()
    harness.pump(500)
    assert panel() is not None and panel().isVisible()
    assert panel().title_text() == "Constraints — %s" % sk().Label, panel().title_text()
    assert len(panel().row_texts()) == len(sk().Constraints) == 10


def test_2_picking_a_line_filters_and_a_row_highlights():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge1")
    harness.pump(500)
    assert panel().header_text().startswith("Picked: Line 1"), panel().header_text()
    assert [t for t, _, _ in panel().row_texts()] == ["Coincident", "Coincident", "Horizontal", "Horizontal Distance"]
    panel().select_index(4)
    harness.pump(300)
    subs = Gui.Selection.getSelectionEx(App.ActiveDocument.Name)[0].SubElementNames
    assert "Constraint5" in subs and "Edge1" in subs, subs


def test_3_delete_from_the_window_is_one_undo_step():
    doc = App.ActiveDocument
    before = len(doc.UndoNames)
    panel().set_checked(4, True)
    panel().delete_button.click()
    harness.pump(600)
    assert len(sk().Constraints) == 9
    assert doc.UndoNames[0] == "Delete Constraints" and len(doc.UndoNames) == before + 1, doc.UndoNames
    assert ("Horizontal", "Line 1", "") not in panel().row_texts()


def test_4_a_refused_delete_says_why_and_keeps_everything():
    sk().setExpression("Constraints.d2", "%s.Constraints.d1 / 2" % sk().Name)
    App.ActiveDocument.recompute()
    harness.pump(300)
    Gui.Selection.clearSelection()
    harness.pump(400)
    d1 = next(r.index for r in sc.rows(sk()) if r.name == "d1")
    panel().select_index(d1)
    panel().delete_button.click()
    harness.pump(400)
    assert "d1 is used by d2" in panel().message_text(), panel().message_text()
    assert any(r.name == "d1" for r in sc.rows(sk()))


def test_5_right_click_on_a_line_lists_its_constraints():
    s = shell.instance()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge2")
    harness.pump(300)
    menu = s.open_sketch_menu_for_test()
    labels = menu.list_labels()
    assert "Delete Vertical" in labels, labels
    assert any(lb.startswith("Delete all constraints (") for lb in labels), labels
    assert "Constraints…" in labels, labels
    n = len(sk().Constraints)
    menu.extra_button("Delete Vertical").click()
    harness.pump(600)
    assert len(sk().Constraints) == n - 1
    Gui.Selection.clearSelection()
    harness.pump(300)
    empty = s.open_sketch_menu_for_test()
    labels = empty.list_labels()
    assert "Constraints…" not in labels and not [lb for lb in labels if lb.startswith("Delete all constraints")], labels
    assert "Delete Pattern" in labels  # the menu's own list is still there
    empty.close()


def test_6_delete_key_with_the_window_open_refreshes_the_list():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Constraint1")
    commands.REGISTRY.run("edit.delete")
    harness.pump(600)
    Gui.Selection.clearSelection()
    harness.pump(400)
    assert len(panel().row_texts()) == len(sk().Constraints), (panel().row_texts(), len(sk().Constraints))


def test_7_finish_sketch_closes_the_window():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    assert shell.instance().constraints_panel is None


harness.run([test_0_sketch_with_a_rectangle, test_1_ribbon_opens_the_window_with_every_constraint,
             test_2_picking_a_line_filters_and_a_row_highlights, test_3_delete_from_the_window_is_one_undo_step,
             test_4_a_refused_delete_says_why_and_keeps_everything, test_5_right_click_on_a_line_lists_its_constraints,
             test_6_delete_key_with_the_window_open_refreshes_the_list, test_7_finish_sketch_closes_the_window])
