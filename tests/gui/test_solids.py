"""A box drawn away from the part is its own Solid: a sketch on its face lands in that Solid, and the feature
made from it (a Cut) works on the box, not on the part."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def _body():
    from incad.core import document
    return document.primary_body(App.ActiveDocument)


def test_0_part_with_a_box_aside():
    from incad.core import document
    from incad.features import extrude
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = _body()
    pad = util.add_pad(body, util.add_rect_sketch(body), 10)
    body.Tip = pad
    far = util.add_rect_sketch(body, name="Far")
    far.AttachmentOffset = App.Placement(App.Vector(50, 50, 0), App.Rotation())
    App.ActiveDocument.recompute()
    box = extrude.create(App.ActiveDocument, body, far, extrude.defaults(App.ActiveDocument, body, far))
    App.ActiveDocument.recompute()
    assert box.getParentGeoFeatureGroup() is not body
    for b in document.bodies(App.ActiveDocument):
        document.show_result(b)
    shell.instance().schedule_refresh()
    harness.pump(600)
    rows = shell.instance().browser.tree_rows()
    assert sum(1 for _, label, kind, _ in rows if kind == "end_of_part") == 1, rows


def test_1_a_sketch_on_the_box_and_a_cut_through_it():
    from incad.core import document
    sh = shell.instance()
    box = App.ActiveDocument.getObject("Extrude")
    other = box.getParentGeoFeatureGroup()
    top = [i + 1 for i, f in enumerate(box.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    sk = sh.sketches.start_on(box, "Face%d" % top)  # as a double-click on the face / New Sketch there
    harness.pump(1200)
    assert sk is not None and sk.getParentGeoFeatureGroup() is other, "the sketch belongs to the box's Solid"
    assert sh.sketches.editing() is sk
    centre = sk.Placement.inverse().multVec(App.Vector(60, 55, 10))  # the middle of the box's top, in sketch coords
    sk.addGeometry(Part.Circle(App.Vector(centre.x, centre.y, 0), App.Vector(0, 0, 1), 2))
    App.ActiveDocument.recompute()
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    assert sh.sketches.editing() is None
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(1200)
    fs = sh.feature_session
    assert fs is not None and fs.body is other, (fs and fs.body.Label)
    fs.dialog.field("operation").button("cut").click()
    fs.dialog.field("extent").button("through_all").click()
    harness.pump(1200)
    assert fs.dialog.error_text() == "", fs.dialog.error_text()
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(900)
    assert sh.feature_session is None
    pocket = other.Tip
    where = [(o.Label, o.TypeId, o.getParentGeoFeatureGroup().Label if o.getParentGeoFeatureGroup() else None)
             for o in App.ActiveDocument.Objects if o.isDerivedFrom("PartDesign::Feature")]
    assert pocket.TypeId == "PartDesign::Pocket" and pocket.getParentGeoFeatureGroup() is other, (pocket.Label, where)
    import math
    assert abs(pocket.Shape.Volume - (2000 - math.pi * 4 * 10)) < 2.0, pocket.Shape.Volume
    assert abs(_body().Tip.Shape.Volume - 2000) < 1e-6, "the part is untouched"
    assert len(document.bodies(App.ActiveDocument)) == 2, "no third Solid"


harness.run([test_0_part_with_a_box_aside, test_1_a_sketch_on_the_box_and_a_cut_through_it])
