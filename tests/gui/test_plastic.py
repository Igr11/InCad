"""Boss, Lip / Groove and Snap Fit in the real window (the user's pick from SolidCraft's list, for printed boxes):
the ribbon's commands open their dialogs, a sketch or a rim face picked as the user picks it, OK joins the result to
the part; and Hole ▸ Insert. INCAD_SHOTS=<folder> saves pictures."""
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
from incad.features import plastic  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402
from headless.test_plastic import box, rim_face, point_sketch  # noqa: E402

ST = {}
OUT = os.environ.get("INCAD_SHOTS")
V = App.Vector


def s():
    return shell.instance()


def fs():
    return s().feature_session


def doc():
    return App.ActiveDocument


def ok():
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    if fs() is not None:
        fs().ok()
        harness.pump(1200)
    assert fs() is None, fs() and fs().dialog.error_text()


def shot(name):
    if OUT:
        v = Gui.ActiveDocument.ActiveView
        v.viewIsometric()
        v.fitAll()
        harness.pump(500)
        v.saveImage(os.path.join(OUT, name + ".png"), 1000, 760, "Current")


def start(command):
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run(command)
    harness.pump(1500)
    assert r.ok, r.error
    assert fs() is not None, "the dialog opened"


def test_0_an_open_box():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    d = doc()
    body = document.primary_body(d)
    sk = util.add_rect_sketch(body, 40, 30)
    pad = util.add_pad(body, sk, 20)
    body.Tip = pad
    d.recompute()
    top = next(i for i, f in enumerate(pad.Shape.Faces, 1)
               if abs(f.normalAt(0, 0).z - 1) < 1e-9 and abs(f.CenterOfMass.z - 20) < 1e-9)
    shell_f = body.newObject("PartDesign::Thickness", "Shell")
    shell_f.Base = (pad, ["Face%d" % top])
    shell_f.Value = 2
    shell_f.Reversed = True
    shell_f.Join = "Intersection"
    body.Tip = shell_f
    d.recompute()
    points = point_sketch(body, [(6, 6), (34, 24)], z=2)
    hooks = body.newObject("Sketcher::SketchObject", "Hooks")
    hooks.AttachmentSupport = [(util.xy_plane(body), "")]
    hooks.MapMode = "FlatFace"
    hooks.AttachmentOffset = App.Placement(V(0, 0, 20), App.Rotation())
    hooks.addGeometry(Part.LineSegment(V(15, 1.5, 0), V(25, 1.5, 0)))
    d.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST.update(body=body.Name, shell=shell_f.Name, points=points.Name, hooks=hooks.Name)
    for c in ("feature.boss", "feature.lip", "feature.snap_fit"):
        assert commands.REGISTRY.get(c) is not None, c


def test_1_boss_on_the_floor():
    start("feature.boss")
    Gui.Selection.addSelection(doc().Name, ST["points"])
    harness.pump(1500)
    fs().dialog.set_values({"height": "8 mm", "ribs": "4"})
    harness.pump(1500)
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, (f and f.getStatusString(), fs().dialog.error_text())
    ok()
    tip = document.primary_body(doc()).Tip
    assert plastic.BOSS.claims(tip) and len(tip.Shape.Solids) == 1, tip.Label
    assert not doc().getObject(ST["points"]).ViewObject.Visibility, "the used sketch is hidden"
    assert not tip.Shape.isInside(V(6, 6, 9), 1e-6, True), "the insert's hole"
    ST["boss"] = tip.Name
    shot("boss")


def test_2_lip_on_the_rim():
    start("feature.lip")
    tip = document.primary_body(doc()).Tip
    face = rim_face(tip, 20)
    Gui.Selection.addSelection(doc().Name, ST["body"], "%s.Face%d" % (tip.Name, face))
    harness.pump(1500)
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, (f and f.getStatusString(), fs().dialog.error_text())
    ok()
    lip = document.primary_body(doc()).Tip
    assert plastic.LIP.claims(lip) and abs(lip.Shape.BoundBox.ZMax - 22) < 1e-6, lip.Shape.BoundBox
    ST["lip"] = lip.Name
    shot("lip")


def test_3_snap_fit_on_the_wall():
    start("feature.snap_fit")
    Gui.Selection.addSelection(doc().Name, ST["hooks"])
    harness.pump(1500)
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, (f and f.getStatusString(), fs().dialog.error_text())
    ok()
    hook = document.primary_body(doc()).Tip
    assert plastic.SNAP_FIT.claims(hook) and abs(hook.Shape.BoundBox.ZMax - 30) < 1e-6, hook.Shape.BoundBox
    assert len(hook.Shape.Solids) == 1
    shot("snap_fit")


def test_4_double_click_opens_the_boss_again():
    f = doc().getObject(ST["boss"])
    s().edit_feature(f)
    harness.pump(1500)
    assert fs() is not None and fs().kind is plastic.BOSS
    assert fs().dialog.values()["ribs"] == "4"
    fs().cancel()
    harness.pump(800)


def test_9_cleanup():
    if fs() is not None:
        fs().cancel()
    for name in list(App.listDocuments()):
        App.closeDocument(name)


harness.run([test_0_an_open_box, test_1_boss_on_the_floor, test_2_lip_on_the_rim, test_3_snap_fit_on_the_wall,
             test_4_double_click_opens_the_boss_again, test_9_cleanup])
