"""Hole ▸ Concentric (the user): several round edges or round faces at once, a hole at each centre, no Face to pick;
Apply + opens the next Hole with the same settings (the picks start empty)."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
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


def test_0_part_with_two_bosses():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 20, 10, 6
    for x in (5, 15):
        c = body().newObject("PartDesign::AdditiveCylinder", "Boss")
        c.Radius, c.Height = 2, 3
        c.Placement = App.Placement(V(x, 5, 6), App.Rotation())
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    tip = body().Tip
    ST["tip"] = tip.Name
    ST["faces"] = ",".join("%s:Face%d" % (tip.Name, i + 1) for i, f in enumerate(tip.Shape.Faces)
                           if f.Surface.TypeId == "Part::GeomCylinder")


def test_1_two_round_faces_make_two_holes_and_apply_keeps_the_settings():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.hole")
    harness.pump(1000)
    d = dialog()
    assert d is not None
    d.set_values({"placement": "concentric", "diameter": "1 mm", "depth_type": "distance", "depth": "2 mm"})
    d._emit()
    harness.pump(800)
    d.set_pick("edge", ST["faces"])
    harness.pump(2000)
    assert not d.error_text(), d.error_text()
    QTest.mouseClick(d.apply_button, QtCore.Qt.LeftButton)
    harness.pump(2500)
    holes = [o for o in body().Group if o.TypeId == "PartDesign::Hole"]
    assert len(holes) == 1 and "Invalid" not in holes[0].State, [h.State for h in holes]
    bores = {round(f.Surface.Center.x) for f in holes[0].Shape.Faces
             if f.Surface.TypeId == "Part::GeomCylinder" and abs(f.Surface.Radius - 0.5) < 1e-6}
    assert bores == {5, 15}, bores
    d2 = dialog()
    assert d2 is not None and d2 is not d, "Apply + opened the next Hole"
    v = d2.values()
    assert (v["placement"], v["diameter"], v["depth_type"], v["depth"]) == ("concentric", "1 mm", "distance", "2 mm"), v
    assert v["edge"] == "", v["edge"]
    d2.cancel_button.click()
    harness.pump(800)


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_part_with_two_bosses, test_1_two_round_faces_make_two_holes_and_apply_keeps_the_settings,
             test_9_cleanup])
