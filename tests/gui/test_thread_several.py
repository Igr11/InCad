"""Thread on several faces at once (the user: as Hole does): two shafts picked in one Thread dialog get a thread
each; Apply + opens the next Thread with the same settings."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.features import hole, thread  # noqa: E402
import Part  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = shell.instance().feature_session
    return fs.dialog if fs is not None else None


def test_0_plate_with_two_shafts():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 40, 20, 5
    for x in (10, 30):
        c = body().newObject("PartDesign::AdditiveCylinder", "Shaft")
        c.Radius, c.Height = 5, 15
        c.Placement = App.Placement(V(x, 10, 5), App.Rotation())
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    tip = body().Tip
    ST["faces"] = ",".join("%s:Face%d" % (tip.Name, i + 1) for i, f in enumerate(tip.Shape.Faces)
                           if f.Surface.TypeId == "Part::GeomCylinder" and abs(f.Surface.Radius - 5) < 1e-6)
    assert len(ST["faces"].split(",")) == 2, ST["faces"]


def test_1_two_faces_two_threads_and_apply_keeps_the_settings():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.thread")
    harness.pump(1000)
    d = dialog()
    assert d is not None
    d.set_values({"chamfer": "start", "hand": "left"})
    d._emit()
    harness.pump(500)
    d.set_pick("face", ST["faces"])
    harness.pump(4000)
    assert not d.error_text(), d.error_text()
    QTest.mouseClick(d.apply_button, QtCore.Qt.LeftButton)
    harness.pump(5000)
    made = [o for o in doc().Objects if thread.claims(o) and not getattr(o, thread.HELPER, None)]
    assert len(made) == 2 and all("Invalid" not in t.State for t in made), [(t.Name, t.State) for t in made]
    assert all(thread.read(doc(), t)["hand"] == "left" for t in made)
    d2 = dialog()
    assert d2 is not None and d2 is not d, "Apply + opened the next Thread"
    v = d2.values()
    assert (v["chamfer"], v["hand"], v["face"]) == ("start", "left", ""), v
    d2.cancel_button.click()
    harness.pump(800)


def test_2_the_second_hole_clicked_on_the_first_threads_preview():
    """The user: in holes it did not work — the second hole is on screen as the first thread's preview (the dialog's
    own feature), and clicks on it were dropped. A real click there adds it."""
    import math
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Plate")
    box.Length, box.Width, box.Height = 40, 20, 8
    doc().recompute()
    top = [i + 1 for i, f in enumerate(box.Shape.Faces) if abs(f.CenterOfMass.z - 8) < 1e-6][0]
    sk = body().newObject("Sketcher::SketchObject", "Holes")
    sk.AttachmentSupport = [(box, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    for x in (10, 30):
        sk.addGeometry(Part.Circle(V(x, 10, 0), V(0, 0, 1), 3))
    doc().recompute()
    h = hole.create(doc(), body(), None, dict(hole.defaults(doc(), body(), None), sketch=sk.Name, diameter="6 mm",
                                              depth_type="through_all"))
    doc().recompute()
    first = [("%s:Face%d" % (h.Name, i + 1)) for i, f in enumerate(h.Shape.Faces)
             if f.Surface.TypeId == "Part::GeomCylinder" and abs(f.Surface.Center.x - 10) < 1e-6][0]
    commands.REGISTRY.run("feature.thread")
    harness.pump(1000)
    d = dialog()
    d.set_pick("face", first)
    harness.pump(4000)
    view = Gui.ActiveDocument.ActiveView
    view.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(800)
    vp = view.graphicsView().viewport()
    dpr = vp.devicePixelRatioF()
    hit = None
    harness.pump(800)
    for dz in [7.5 - 0.5 * k for k in range(14)]:  # every point round the second hole's wall, top down
        for ang in range(0, 360, 5):
            p = V(30 + 2.99 * math.cos(math.radians(ang)), 10 + 2.99 * math.sin(math.radians(ang)), dz)
            sx, sy = view.getPointOnViewport(p)
            info = view.getObjectInfo((int(sx), int(sy)))
            if info and info.get("Component", "").startswith("Face"):
                el = doc().getObject(info["Object"]).Shape.getElement(info["Component"])
                if el.Surface.TypeId == "Part::GeomCylinder" and abs(el.Surface.Center.x - 30) < 1e-6:
                    hit = (sx, sy, info["Object"])
                    break
        if hit:
            break
    assert hit is not None, "the second hole's wall is on screen"
    assert thread.claims(doc().getObject(hit[2])), "it shows as the first thread's preview: %s" % hit[2]
    at = QtCore.QPoint(int(hit[0] / dpr), int(vp.height() - hit[1] / dpr))
    QTest.mouseMove(vp, at)
    harness.pump(300)
    QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
    harness.pump(5000)
    faces = d.values()["face"].split(",")
    assert len(faces) == 2 and all(x.startswith(h.Name + ":") for x in faces), faces
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(3000)
    made = [o for o in doc().Objects if thread.claims(o) and not getattr(o, thread.HELPER, None)]
    assert len(made) == 2 and all("Invalid" not in t.State for t in made), [(t.Name, t.State) for t in made]


def test_9_cleanup():
    harness.pump(300)
    for name in list(App.listDocuments()):
        App.closeDocument(name)


harness.run([test_0_plate_with_two_shafts, test_1_two_faces_two_threads_and_apply_keeps_the_settings,
             test_2_the_second_hole_clicked_on_the_first_threads_preview, test_9_cleanup])
