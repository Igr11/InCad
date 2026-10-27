"""The sketch's right-click menu offers Delete for whatever is selected (the user: delete selected lines OR
dimensions): two dimensions selected -> Delete in the menu, and it removes just them; a line selected -> Delete;
nothing selected and nothing under the pointer -> no Delete; a right-click on a line that is not selected makes it
the selection, so Delete removes that line and nothing else."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def sk():
    return App.ActiveDocument.getObject(ST["sk"])


def menu_labels():
    view = s()._mdi().viewport()
    menu = s()._sketch_menu(view.mapToGlobal(view.rect().center()), False)
    out = menu.list_labels() if menu is not None else []
    try:
        menu.close()
    except (AttributeError, RuntimeError):
        pass
    harness.pump(100)
    return out


def dims():
    return [i for i, c in enumerate(sk().Constraints) if c.Type in ("DistanceX", "DistanceY", "Distance")]


def test_0_rectangle_with_dimensions():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    Gui.Selection.addSelection(doc.Name, xy.Name)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    k = s().sketches.editing()
    pts = [V(0, 0, 0), V(30, 0, 0), V(30, 20, 0), V(0, 20, 0)]
    ids = [k.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4])) for i in range(4)]
    for i in range(4):
        k.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[(i + 1) % 4], 1))
    k.addConstraint(Sketcher.Constraint("DistanceX", ids[0], 1, ids[0], 2, 30))
    k.addConstraint(Sketcher.Constraint("DistanceY", ids[1], 1, ids[1], 2, 20))
    k.addConstraint(Sketcher.Constraint("Distance", ids[2], 18))  # a third one, to stay
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    ST["sk"], ST["ids"] = k.Name, ids


def test_1_nothing_selected_no_delete():
    Gui.Selection.clearSelection()
    harness.pump(200)
    assert "Delete" not in menu_labels()


def test_2_two_dimensions_selected_delete_removes_them():
    before = dims()
    Gui.Selection.clearSelection()
    for i in before[:2]:
        Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Constraint%d" % (i + 1))
    harness.pump(200)
    assert "Delete" in menu_labels(), "two dimensions selected: Delete must be offered"
    commands.REGISTRY.run("edit.delete")
    harness.pump(600)
    assert len(dims()) == len(before) - 2, (before, dims())
    assert sk().GeometryCount == 4, "only the dimensions go"


def test_3_a_line_selected():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge1")
    harness.pump(200)
    assert "Delete" in menu_labels()


def test_4_right_click_on_an_unselected_line_selects_it():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge1")
    Gui.Selection.setPreselection(App.ActiveDocument.getObject(ST["sk"]), "Edge3")  # the pointer is on another line
    harness.pump(200)
    assert "Delete" in menu_labels()
    picked = [n for sel in Gui.Selection.getSelectionEx(App.ActiveDocument.Name) for n in sel.SubElementNames]
    assert picked == ["Edge3"], picked
    count = sk().GeometryCount
    commands.REGISTRY.run("edit.delete")
    harness.pump(600)
    assert sk().GeometryCount == count - 1


def test_9_cleanup():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_rectangle_with_dimensions, test_1_nothing_selected_no_delete,
             test_2_two_dimensions_selected_delete_removes_them, test_3_a_line_selected,
             test_4_right_click_on_an_unselected_line_selects_it, test_9_cleanup])
