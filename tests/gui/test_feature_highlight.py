"""Inventor's browser link both ways (2026-10-10): a feature row lights the faces it made on the shown solid,
and a face clicked on the solid lights the row of the feature that made it. While a dialog waits for a feature
pick, a row click still hands the feature itself to the dialog."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, feature_faces, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def sel():
    return [(s.ObjectName, tuple(s.SubElementNames)) for s in Gui.Selection.getSelectionEx(App.ActiveDocument.Name)]


def test_0_part_with_a_pocket():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(App.ActiveDocument)
    pad = util.add_pad(body, util.add_rect_sketch(body), 10)
    body.Tip = pad
    hole = body.newObject("Sketcher::SketchObject", "HoleSk")
    hole.AttachmentSupport = [(util.xy_plane(body), "")]
    hole.MapMode = "FlatFace"
    hole.AttachmentOffset = App.Placement(App.Vector(0, 0, 10), App.Rotation())
    hole.addGeometry(Part.Circle(App.Vector(5, 5, 0), App.Vector(0, 0, 1), 2))
    pocket = body.newObject("PartDesign::Pocket", "Pocket")
    pocket.Profile = hole
    pocket.Length = 4
    body.Tip = pocket
    App.ActiveDocument.recompute()
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(800)
    ST.update(pad=pad.Name, pocket=pocket.Name)


def test_1_a_feature_row_lights_its_faces_on_the_solid():
    b = shell.instance().browser
    assert b.select_row(ST["pad"])
    harness.pump(500)
    got = sel()
    assert len(got) == 1 and got[0][0] == ST["pocket"], got  # the shown solid is the Pocket (the Tip)
    pad_faces = set(got[0][1])
    assert pad_faces and all(n.startswith("Face") for n in pad_faces), got
    assert pad_faces == set(feature_faces.on_tip(App.ActiveDocument.getObject(ST["pad"])))
    assert b.select_row(ST["pocket"])
    harness.pump(500)
    got = sel()
    assert set(got[0][1]) == set(feature_faces.on_tip(App.ActiveDocument.getObject(ST["pocket"]))), got
    assert not pad_faces & set(got[0][1])


def test_2_a_face_clicked_on_the_solid_lights_its_feature_row():
    b = shell.instance().browser
    pocket = App.ActiveDocument.getObject(ST["pocket"])
    Gui.Selection.clearSelection()
    harness.pump(200)
    Gui.Selection.addSelection(App.ActiveDocument.Name, ST["pocket"], feature_faces.on_tip(pocket)[0])
    harness.pump(500)
    assert b.selected_names() == [ST["pocket"]], b.selected_names()
    Gui.Selection.clearSelection()
    pad = App.ActiveDocument.getObject(ST["pad"])
    Gui.Selection.addSelection(App.ActiveDocument.Name, ST["pocket"], feature_faces.on_tip(pad)[0])
    harness.pump(500)
    assert b.selected_names() == [ST["pad"]], b.selected_names()
    Gui.Selection.clearSelection()
    harness.pump(300)


def test_3_show_in_window_and_show_in_browser():
    """The menu items Inventor has: Show in Window from a row, Show in Browser from a pick in the view."""
    from incad.core import context
    b = shell.instance().browser
    pocket = App.ActiveDocument.getObject(ST["pocket"])
    pad = App.ActiveDocument.getObject(ST["pad"])
    context.set_target(ST["pocket"])
    r = commands.REGISTRY.run("browser.show_in_window")
    assert r.ok, r.error
    harness.pump(500)
    assert set(sel()[0][1]) == set(feature_faces.on_tip(pocket)), sel()
    Gui.Selection.clearSelection()
    harness.pump(200)
    b.tree.clearSelection()
    shell.instance()._syncing = True  # a pick the tree has not followed yet
    Gui.Selection.addSelection(App.ActiveDocument.Name, ST["pocket"], feature_faces.on_tip(pad)[0])
    shell.instance()._syncing = False
    harness.pump(300)
    r = commands.REGISTRY.run("view.show_in_browser")
    assert r.ok, r.error
    harness.pump(400)
    assert b.selected_names() == [ST["pad"]], b.selected_names()
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("view.show_in_browser")
    assert not r.ok and "Select something" in r.error, r.error


harness.run([test_0_part_with_a_pocket, test_1_a_feature_row_lights_its_faces_on_the_solid,
             test_2_a_face_clicked_on_the_solid_lights_its_feature_row, test_3_show_in_window_and_show_in_browser])
