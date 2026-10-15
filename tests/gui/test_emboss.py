"""3D Model ▸ Emboss (user request): a Text on the origin plane through a drum's axis, Emboss, a click on the drum's
round side: the letters stand wrapped round it, raised along the radius; Engrave cuts them in."""
import math
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
from incad.features import emboss, sketch_text  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}
OUT = os.environ.get("INCAD_SHOTS")


def s():
    return shell.instance()


def fs():
    return s().feature_session


def test_0_drum_and_text():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = App.newDocument("EmbossDrum")
    ST["doc"] = d.Name
    harness.pump(400)
    body = document.make_part(d)
    drum = body.newObject("PartDesign::AdditiveCylinder", "Drum")
    drum.Radius, drum.Height = 12, 30
    body.Tip = drum
    yz = [f for f in body.Origin.OriginFeatures if f.Role == "YZ_Plane"][0]
    sk = body.newObject("Sketcher::SketchObject", "Label")
    sk.AttachmentSupport = [(yz, "")]
    sk.MapMode = "FlatFace"
    d.recompute()
    ST["drum"], ST["sk"] = drum.Name, sk.Name
    s().sketches.edit(sk)
    harness.pump(1200)
    sketch_text._pending_box = (App.Vector(-16, 9, 0), App.Vector(16, 21, 0))
    s().start_feature(sketch_text.TEXT)
    harness.pump(1500)
    fs().dialog.set_values({"text": "InCad", "bold": True, "size": "7 mm"})
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    s().sketches.finish()
    harness.pump(1000)
    t = [o for o in d.Objects if sketch_text.is_text(o)][0]
    assert "Invalid" not in t.State, t.getStatusString()
    ST["text"] = t.Name


def test_1_emboss_wraps_the_text_round_the_drum():
    d = App.getDocument(ST["doc"])
    drum = d.getObject(ST["drum"])
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("feature.emboss")
    harness.pump(1500)
    assert r.ok, r.error
    from incad.features import common
    body = document.primary_body(d)
    assert fs() is not None and fs().kind is emboss and fs().profile.Name == ST["text"], (
        fs() and fs().profile, s()._profile_pick, [(o.Name, o.TypeId, [c.Name for c in common.consumers(o)])
                                                   for o in body.Group], open(os.environ["INCAD_LOG"]).read()[-500:])
    assert fs().dialog.active_pick() == "face", fs().dialog.active_pick()
    side = next(i + 1 for i, f in enumerate(drum.Shape.Faces) if f.Surface.TypeId == "Part::GeomCylinder")
    Gui.Selection.addSelection(d.Name, drum.Name, "Face%d" % side)
    harness.pump(2000)
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, (f and f.getStatusString(), fs().dialog.error_text())
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    tip = document.primary_body(d).Tip
    assert emboss.claims(tip) and "Invalid" not in tip.State, tip.getStatusString()
    rmax = max(math.hypot(v.Point.x, v.Point.y) for v in tip.Shape.Vertexes)
    assert abs(rmax - 13.0) < 1e-4, rmax
    assert not d.getObject(ST["text"]).ViewObject.Visibility, "the used text is hidden"
    ST["emboss"] = tip.Name
    if OUT:
        v = Gui.ActiveDocument.ActiveView
        v.viewRight()
        v.fitAll()
        harness.pump(500)
        v.saveImage(os.path.join(OUT, "emboss_raised.png"), 1100, 800, "Current")


def test_2_engrave_from_the_dialog():
    d = App.getDocument(ST["doc"])
    f = d.getObject(ST["emboss"])
    raised = f.Shape.Volume
    s().edit_feature(f)
    harness.pump(1500)
    fs().dialog.set_values({"operation": "engrave", "depth": "0.6 mm"})
    harness.pump(2000)
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    assert "Invalid" not in f.State and f.Shape.Volume < d.getObject(ST["drum"]).Shape.Volume - 3, (
        f.Shape.Volume, raised)
    if OUT:
        v = Gui.ActiveDocument.ActiveView
        v.viewRight()
        v.fitAll()
        harness.pump(500)
        v.saveImage(os.path.join(OUT, "emboss_engraved.png"), 1100, 800, "Current")


def test_3_cleanup():
    App.closeDocument(ST["doc"])
    harness.pump(400)


harness.run([test_0_drum_and_text, test_1_emboss_wraps_the_text_round_the_drum, test_2_engrave_from_the_dialog,
             test_3_cleanup])
