"""Loft's sections as a numbered list (2026-10-10, the user found the one 'Select…' button vague): sketches
clicked in order fill the rows, ✕ removes one (the 3D selection follows), a section added again goes last,
▲▼ fix the order, OK builds the loft through all three."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def fs():
    return shell.instance().feature_session


def click(name):
    Gui.Selection.addSelection(App.ActiveDocument.Name, name)
    harness.pump(700)


def test_0_three_circles_and_the_loft_dialog():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(App.ActiveDocument)
    for name, z, r in (("Low", 0, 6), ("Mid", 10, 4), ("High", 20, 6)):
        sk = body.newObject("Sketcher::SketchObject", name)
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        sk.AttachmentOffset = App.Placement(App.Vector(0, 0, z), App.Rotation())
        sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), r))
    App.ActiveDocument.recompute()
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.loft")
    harness.pump(800)
    assert fs() is not None and fs().kind.TITLE == "Loft"
    d = fs().dialog
    assert d.list_rows("sections") == [] and "2 or more" in d.pick_text("sections"), d.pick_text("sections")
    assert d.active_pick() == "sections", d.active_pick()


def test_1_clicked_in_order_fill_the_rows():
    for name in ("Low", "Mid", "High"):
        click(name)
    d = fs().dialog
    assert d.list_rows("sections") == ["1.  Low", "2.  Mid", "3.  High"], d.list_rows("sections")
    assert d.error_text() == "", d.error_text()


def test_2_remove_then_add_again_goes_last_and_order_is_fixed_with_the_arrows():
    d = fs().dialog
    d.row_button("sections", 1, "remove").click()
    harness.pump(800)
    assert d.list_rows("sections") == ["1.  Low", "2.  High"]
    assert sorted(s.ObjectName for s in Gui.Selection.getSelectionEx(App.ActiveDocument.Name)) == ["High", "Low"]
    click("Mid")
    assert d.list_rows("sections") == ["1.  Low", "2.  High", "3.  Mid"], d.list_rows("sections")
    d.row_button("sections", 2, "up").click()
    harness.pump(900)
    assert d.list_rows("sections") == ["1.  Low", "2.  Mid", "3.  High"]
    assert d.error_text() == "", d.error_text()


def test_3_ok_builds_the_loft_through_the_three():
    fs().ok()
    harness.pump(900)
    assert fs() is None
    loft = document.primary_body(App.ActiveDocument).Tip
    assert loft.TypeId == "PartDesign::AdditiveLoft" and "Invalid" not in loft.State, loft.getStatusString()
    assert [s.Name for s in [loft.Profile[0]] + [x[0] if isinstance(x, (tuple, list)) else x for x in loft.Sections]] \
        == ["Low", "Mid", "High"]
    assert loft.Shape.Volume > 0


harness.run([test_0_three_circles_and_the_loft_dialog, test_1_clicked_in_order_fill_the_rows,
             test_2_remove_then_add_again_goes_last_and_order_is_fixed_with_the_arrows,
             test_3_ok_builds_the_loft_through_the_three])
