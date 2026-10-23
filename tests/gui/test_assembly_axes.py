"""Axes in an assembly (the user: every turned body and hole has its axis, by default, grey dashed, to constrain to):
a plate with a hole and a shaft show their axes; Cylindrical picked on the two axes puts the shaft in the hole."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.ui.line3d_tool import viewport_of  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui import dof_handles as dh  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def circle_sketch(body, r, name, at=V(0, 0, 0)):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(at, V(0, 0, 1), r))
    return sk


def save(folder, name, build):
    doc = util.new_doc(name)
    body = document.make_part(doc)
    build(body)
    doc.recompute()
    path = os.path.join(folder, name + ".FCStd")
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    return path


def plate(body):
    pad = util.add_pad(body, util.add_rect_sketch(body, 40, 30, "S"), 10, "Pad")
    hole = body.newObject("PartDesign::Pocket", "Hole")
    hole.Profile = circle_sketch(body, 4, "H", V(20, 15, 0))  # the plate's middle
    hole.Type = "ThroughAll"
    hole.Midplane = True  # through the plate whichever way the sketch faces
    body.Tip = hole
    del pad


def shaft(body):
    pad = util.add_pad(body, circle_sketch(body, 4, "C"), 30, "Shaft")
    body.Tip = pad


def test_0_assembly_with_a_plate_and_a_shaft():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_axes_")
    p, q = save(ST["dir"], "Plate", plate), save(ST["dir"], "Shaft", shaft)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    a = s().assembly_place(p)
    b = s().assembly_place(q)
    harness.pump(600)
    b.Placement = App.Placement(V(60, 10, 0), App.Rotation())
    doc.recompute()
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1000)
    ST.update(asm=doc.Name, a=a.Name, b=b.Name)


def test_1_axes_are_drawn():
    lines = s()._axis_lines
    assert lines is not None and lines.root is not None, "no axes"
    names = sorted(n for n, *_ in lines.items)
    assert names == sorted([ST["a"], ST["b"]]), names  # the hole's and the shaft's
    if os.environ.get("INNCAD_SHOT"):
        Gui.ActiveDocument.ActiveView.saveImage(os.environ["INNCAD_SHOT"], 900, 600, "Current")


def test_2_cylindrical_on_the_two_axes():
    doc = App.getDocument(ST["asm"])
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("joint.cylindrical")
    harness.pump(1000)
    fs = s().feature_session
    assert r.ok and fs is not None, r.error
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    lines = s()._axis_lines
    for name in (ST["a"], ST["b"]):
        item = [i for i in lines.items if i[0] == name][0]
        mid = (item[1] + item[2]) * 0.5
        x, y = dh.screen(view, vp, mid)
        assert s().dof_handles.press(view, vp, x, y), "the axis of %s was not taken" % name
        s().dof_handles.release()
        harness.pump(800)
    v = fs.dialog.values()
    assert v["first"].startswith(ST["a"] + ":Face") and v["second"].startswith(ST["b"] + ":Face"), v
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    b = doc.getObject(ST["b"])
    axis = b.Placement.Rotation.multVec(V(0, 0, 1))
    c = b.Placement.Base
    assert abs(abs(axis.z) - 1) < 1e-6 and abs(c.x - 20) < 1e-5 and abs(c.y - 15) < 1e-5, b.Placement  # in the hole


def test_3_parallel_axis_and_face():
    """Parallel on the shaft's axis and the plate's top: the axis lies parallel to that face (the shaft lies down),
    not along its normal."""
    doc = App.getDocument(ST["asm"])
    commands.REGISTRY.run("edit.undo")  # the Cylindrical joint gone
    harness.pump(800)
    a, b = doc.getObject(ST["a"]), doc.getObject(ST["b"])
    top = [i + 1 for i, f in enumerate(a.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"
           and abs(f.CenterOfMass.z - 10) < 1e-6][0]
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("constrain.parallel")
    harness.pump(1000)
    fs = s().feature_session
    assert r.ok and fs is not None, r.error
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    asm = assembly.assembly_of(doc)
    Gui.Selection.addSelection(doc.Name, asm.Name, "%s.Face%d" % (a.Name, top))
    harness.pump(800)
    item = [i for i in s()._axis_lines.items if i[0] == ST["b"]][0]
    x, y = dh.screen(view, vp, (item[1] + item[2]) * 0.5)
    assert s().dof_handles.press(view, vp, x, y), "the shaft's axis was not taken"
    s().dof_handles.release()
    harness.pump(1000)
    v = fs.dialog.values()
    assert v["second"].startswith(ST["b"] + ":Face"), v
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    axis = b.Placement.Rotation.multVec(V(0, 0, 1))
    assert abs(axis.z) < 1e-6, axis  # lying flat, parallel to the plate's top


def test_4_mate_on_the_two_axes():
    """Mate on the two axes (the user: the axes react to Mate and Flush too): the shaft's axis goes into the hole's."""
    doc = App.getDocument(ST["asm"])
    commands.REGISTRY.run("edit.undo")  # the Parallel gone
    harness.pump(800)
    b = doc.getObject(ST["b"])
    b.Placement = App.Placement(V(60, 10, 0), App.Rotation(V(1, 0, 0), 30))
    doc.recompute()
    s().schedule_refresh()
    harness.pump(800)
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("constrain.mate")
    harness.pump(1000)
    fs = s().feature_session
    assert r.ok and fs is not None, r.error
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    for name in (ST["a"], ST["b"]):
        item = [i for i in s()._axis_lines.items if i[0] == name][0]
        x, y = dh.screen(view, vp, (item[1] + item[2]) * 0.5)
        assert s().dof_handles.press(view, vp, x, y), "the axis of %s was not taken" % name
        s().dof_handles.release()
        harness.pump(800)
    assert not fs.dialog.error_text() or "conflict" not in fs.dialog.error_text(), fs.dialog.error_text()
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    assert s().feature_session is None, fs.dialog.error_text()
    axis = b.Placement.Rotation.multVec(V(0, 0, 1))
    c = b.Placement.Base
    assert abs(abs(axis.z) - 1) < 1e-6 and abs(c.x - 20) < 1e-5 and abs(c.y - 15) < 1e-5, b.Placement


def test_9_cleanup():
    if s().feature_session is not None:
        s().feature_session.cancel()
    harness.pump(300)
    for d in list(App.listDocuments().values()):
        App.closeDocument(d.Name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_assembly_with_a_plate_and_a_shaft, test_1_axes_are_drawn, test_2_cylindrical_on_the_two_axes,
             test_3_parallel_axis_and_face, test_4_mate_on_the_two_axes, test_9_cleanup])
