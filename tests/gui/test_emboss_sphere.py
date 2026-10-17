"""3D Model ▸ Emboss on a sphere (user request): a Text on the XY plane through a ball's centre, Emboss, a click on the
ball: the letters are projected onto the top half along the sketch's normal, raised along the radius; 'Evenly round'
is greyed out; Engrave cuts them in."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.features import emboss, sketch_text  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}
OUT = os.environ.get("INCAD_SHOTS")


def s():
    return shell.instance()


def fs():
    return s().feature_session


def shot(name):
    if OUT:
        v = Gui.ActiveDocument.ActiveView
        v.viewIsometric()
        v.fitAll()
        harness.pump(500)
        v.saveImage(os.path.join(OUT, name), 1100, 800, "Current")


def test_0_ball_and_text():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = App.newDocument("EmbossBall")
    ST["doc"] = d.Name
    harness.pump(400)
    body = document.make_part(d)
    ball = body.newObject("PartDesign::AdditiveSphere", "Ball")
    ball.Radius = 15
    body.Tip = ball
    xy = [f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0]
    sk = body.newObject("Sketcher::SketchObject", "Label")
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    d.recompute()
    ST["ball"] = ball.Name
    s().sketches.edit(sk)
    harness.pump(1200)
    sketch_text._pending_box = (App.Vector(-10, -3, 0), App.Vector(10, 5, 0))
    s().start_feature(sketch_text.TEXT)
    harness.pump(1500)
    fs().dialog.set_values({"text": "InCad", "bold": True, "size": "5 mm"})
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    s().sketches.finish()
    harness.pump(1000)
    t = [o for o in d.Objects if sketch_text.is_text(o)][0]
    assert "Invalid" not in t.State, t.getStatusString()
    ST["text"] = t.Name


def test_1_emboss_projects_the_text_onto_the_ball():
    d = App.getDocument(ST["doc"])
    ball = d.getObject(ST["ball"])
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("feature.emboss")
    harness.pump(1500)
    assert r.ok, r.error
    assert fs() is not None and fs().kind is emboss and fs().profile.Name == ST["text"], fs() and fs().profile
    fs().dialog.set_values({"around": "even"})
    harness.pump(300)
    side = next(i + 1 for i, f in enumerate(ball.Shape.Faces) if f.Surface.TypeId == "Part::GeomSphere")
    Gui.Selection.addSelection(d.Name, ball.Name, "Face%d" % side)
    harness.pump(2000)
    assert fs().dialog.values().get("around") == "drawn", fs().dialog.values()  # Evenly round gave way
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, (f and f.getStatusString(), fs().dialog.error_text())
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    tip = document.primary_body(d).Tip
    assert emboss.claims(tip) and "Invalid" not in tip.State, tip.getStatusString()
    assert tip.Shape.Volume > ball.Shape.Volume + 1, (tip.Shape.Volume, ball.Shape.Volume)
    rmax = max(v.Point.Length for v in tip.Shape.Vertexes)
    assert abs(rmax - 16.0) < 1e-4, rmax
    assert min(v.Point.z for v in tip.Shape.Vertexes if v.Point.Length > 15.5) > 0, "letters on the top half only"
    ST["emboss"] = tip.Name
    shot("emboss_sphere_raised.png")


def test_2_engrave_from_the_dialog():
    d = App.getDocument(ST["doc"])
    f = d.getObject(ST["emboss"])
    s().edit_feature(f)
    harness.pump(1500)
    fs().dialog.set_values({"operation": "engrave", "depth": "0.6 mm"})
    harness.pump(2000)
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    ball = d.getObject(ST["ball"]).Shape.Volume
    assert "Invalid" not in f.State and f.Shape.Volume < ball - 1, (f.Shape.Volume, ball)
    assert abs(max(v.Point.Length for v in f.Shape.Vertexes) - 15.0) < 1e-4
    assert any(abs(v.Point.Length - 14.4) < 1e-4 for v in f.Shape.Vertexes), "cut 0.6 deep along the radius"
    shot("emboss_sphere_engraved.png")


def test_3_a_star_sketched_in_another_solid():
    """The user's star.FCStd: a star sketch left in a second Solid (its own pad deleted), facing the ball from the
    side; Emboss with a pick on the ball: the emboss goes on the ball's Solid, the sketch comes along."""
    import Part
    d = App.getDocument(ST["doc"])
    ball_body = document.primary_body(d)
    other = d.addObject("PartDesign::Body", "Body2")
    sk = other.newObject("Sketcher::SketchObject", "Star")
    sk.MapMode = "Deactivated"
    sk.Placement = App.Placement(App.Vector(0, -20, 0), App.Rotation(App.Vector(1, 0, 0), 90))  # faces -Y
    pts = [App.Vector((5 if i % 2 == 0 else 2) * math.sin(i * math.pi / 5),
                      (5 if i % 2 == 0 else 2) * math.cos(i * math.pi / 5), 0) for i in range(10)]
    for i in range(10):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 10]))
    d.recompute()
    before = ball_body.Tip.Shape.Volume
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(d.Name, sk.Name)
    r = commands.REGISTRY.run("feature.emboss")
    harness.pump(1500)
    assert r.ok, r.error
    assert fs() is not None and fs().kind is emboss and fs().profile is sk, fs() and fs().profile
    ball = d.getObject(ST["emboss"])
    side = max((f.Area, i + 1) for i, f in enumerate(ball.Shape.Faces) if f.Surface.TypeId == "Part::GeomSphere")[1]
    Gui.Selection.addSelection(d.Name, ball.Name, "Face%d" % side)
    harness.pump(2000)
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, (f and f.getStatusString(), fs().dialog.error_text())
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    tip = ball_body.Tip
    assert emboss.claims(tip) and tip.Profile is sk and "Invalid" not in tip.State, (tip.Name, tip.getStatusString())
    assert sk in ball_body.Group and d.getObject("Body2") is None, [b.Name for b in document.bodies(d)]
    assert tip.Shape.Volume > before + 1, (tip.Shape.Volume, before)
    assert min(v.Point.y for v in tip.Shape.Vertexes) < -15.5, "the star stands on the -Y side"
    shot("emboss_sphere_star.png")


def test_4_cleanup():
    App.closeDocument(ST["doc"])
    harness.pump(400)


harness.run([test_0_ball_and_text, test_1_emboss_projects_the_text_onto_the_ball, test_2_engrave_from_the_dialog,
             test_3_a_star_sketched_in_another_solid, test_4_cleanup])
