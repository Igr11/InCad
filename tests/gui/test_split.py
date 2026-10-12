"""Split in a real window: pick the sketch, Split shows two pieces; Cut keeps the piece clicked."""
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
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def doc():
    return App.ActiveDocument


def dialog():
    fs = shell.instance().feature_session
    return fs.dialog if fs is not None else None


def test_0_box_and_a_knife():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    part = document.primary_body(doc())
    box = part.newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 20, 10, 10
    part.Tip = box
    sk = part.newObject("Sketcher::SketchObject", "Knife")
    sk.AttachmentSupport = [([o for o in part.Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(App.Vector(5, -5, 0), App.Vector(5, 15, 0)))
    doc().recompute()
    harness.pump(400)
    ST.update(part=part.Name, sk=sk.Name)


def test_1_split_then_cut_by_a_click():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, ST["sk"])
    commands.REGISTRY.run("feature.split")
    harness.pump(1500)
    assert dialog() is not None and dialog().values()["sketch"].startswith(ST["sk"]), dialog() and dialog().values()
    fs = shell.instance().feature_session
    from incad.features import split
    assert len(fs.feature.Shape.Solids) == 1 and len(split.piece_bodies(fs.feature)) == 1, \
        "Keep all: the other piece is a Solid of its own (it can be hidden)"
    ST["preview_vo"] = (fs.feature.ViewObject.DisplayMode, type(getattr(fs.feature.ViewObject, "Proxy", None)).__name__)
    dialog().field("mode").button("cut").click()
    harness.pump(800)
    assert dialog().active_pick() == "keep", dialog().active_pick()
    big = max(fs.feature.Shape.Solids, key=lambda s: s.Volume)
    face = next(i + 1 for i, f in enumerate(fs.feature.Shape.Faces) if big.isInside(f.CenterOfMass, 1e-6, True)
                and f.CenterOfMass.x > 12)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, fs.feature.Name, "Face%d" % face)
    harness.pump(1200)
    assert dialog().values()["keep"], (dialog().values(), dialog().error_text())
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    tip = doc().getObject(ST["part"]).Tip
    assert abs(tip.Shape.Volume - 1500) < 1e-6, (tip.Shape.Volume, tip.Name, getattr(tip, "Mode", None),
                                                  getattr(tip, "Keep", None), getattr(tip, "ShowAll", None), tip.State)
    assert doc().UndoNames[0] == "Split", doc().UndoNames
    # the user's report: the part disappeared — a Python feature made from code had no display mode
    assert tip.ViewObject.DisplayMode in tip.ViewObject.listDisplayModes(), (
        tip.ViewObject.DisplayMode, type(getattr(tip.ViewObject, "Proxy", None)).__name__, ST.get("preview_vo"), tip.Name)


harness.run([test_0_box_and_a_knife, test_1_split_then_cut_by_a_click])
