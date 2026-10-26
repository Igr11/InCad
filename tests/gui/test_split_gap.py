"""Split ▸ Gap in the window (the user: the gap between the split parts, from one part or from both; arrows in 0.05 mm
steps): the Gap field's arrows step 0.05 mm, Gap from is offered for Keep all (not for Keep picked), OK leaves the
pieces apart by the gap, taken from the side chosen; the gap is a parameter in the Parameters list."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, model, prefs  # noqa: E402
from incad.features import split  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def test_0_box_and_knife():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    b = body().newObject("PartDesign::AdditiveBox", "Box")
    b.Length, b.Width, b.Height = 20, 10, 10
    doc().recompute()
    sk = body().newObject("Sketcher::SketchObject", "Knife")
    sk.AttachmentSupport = [([o for o in body().Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(V(5, -5, 0), V(5, 15, 0)))
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["sketch"] = sk.Name


def test_1_gap_field_steps_by_005():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, ST["sketch"])
    commands.REGISTRY.run("feature.split")
    harness.pump(1500)
    d = dialog()
    assert d is not None, "no Split dialog"
    assert d.field("gap").isVisible() and d.field("gap_from").isVisible(), "no Gap / Gap from"
    up, down = d.step_buttons("gap")
    for _ in range(8):
        QTest.mouseClick(up, QtCore.Qt.LeftButton)
        harness.pump(150)
    harness.pump(1200)
    assert abs(App.Units.Quantity(d.values()["gap"]).Value - 0.4) < 1e-9, d.values()["gap"]
    QTest.mouseClick(down, QtCore.Qt.LeftButton)
    harness.pump(600)
    assert abs(App.Units.Quantity(d.values()["gap"]).Value - 0.35) < 1e-9, d.values()["gap"]
    QTest.mouseClick(up, QtCore.Qt.LeftButton)
    harness.pump(600)


def test_2_gap_from_this_solid():
    d = dialog()
    QTest.mouseClick(d.field("gap_from").button("this"), QtCore.Qt.LeftButton)
    harness.pump(1500)
    mode = d.field("mode")
    QTest.mouseClick(mode.button("cut"), QtCore.Qt.LeftButton)  # Keep picked: no choice of side
    harness.pump(600)
    assert not d.field("gap_from").isVisible(), "Gap from shown for Keep picked"
    QTest.mouseClick(mode.button("split"), QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert d.field("gap_from").isVisible()
    fs = s().feature_session
    for _ in range(100):
        if not fs._previewing and not fs._timer.isActive():
            break
        harness.pump(100)
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    for _ in range(100):
        if s().feature_session is None:
            break
        harness.pump(100)
    assert s().feature_session is None, d.error_text()
    f = [o for o in body().Group if split.claims(o)][-1]
    assert abs(f.Shape.Volume - 1460) < 1e-6, f.Shape.Volume  # 15 mm piece less the whole 0.4 mm gap
    others = split.piece_bodies(f)
    assert len(others) == 1 and abs(others[0].Shape.Volume - 500) < 1e-6, [o.Shape.Volume for o in others]
    gap_name = split.param_names(f)["gap"]
    assert gap_name in [r[0] for r in s().browser.parameter_rows()], s().browser.parameter_rows()
    ST["split"] = f.Name


def test_3_edit_reads_it_back():
    f = doc().getObject(ST["split"])
    s().edit_feature(f)
    harness.pump(1500)
    d = dialog()
    assert d.values()["gap_from"] == "this", d.values()
    assert abs(App.Units.Quantity(d.values()["gap"]).Value - 0.4) < 1e-9, d.values()["gap"]
    QTest.mouseClick(d.cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)


def test_9_cleanup():
    App.closeDocument(doc().Name)
    harness.pump(300)


harness.run([test_0_box_and_knife, test_1_gap_field_steps_by_005, test_2_gap_from_this_solid,
             test_3_edit_reads_it_back, test_9_cleanup])
