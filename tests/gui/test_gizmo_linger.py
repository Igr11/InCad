"""The gizmo of a part just dragged stays a while (the user: the assembly gizmos went out the moment the button was
released, very hard to grab): a press that moves drags the part without selecting it; its gizmo stays about 3 s,
longer while the pointer is on a handle, then goes."""
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


def test_1_a_dragged_part_keeps_its_gizmo():
    import time
    doc = App.getDocument(ST["asm"])
    b = doc.getObject(ST["b"])
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    Gui.Selection.clearSelection()
    harness.pump(300)
    x, y = dh.screen(view, vp, b.Shape.BoundBox.Center)
    p = QtCore.QPoint(int(x), int(y))
    QTest.mousePress(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
    for k in range(1, 8):
        QTest.mouseMove(vp, QtCore.QPoint(int(x) + 4 * k, int(y)))
        harness.pump(40)
    QTest.mouseRelease(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(int(x) + 28, int(y)))
    harness.pump(300)
    handles = s().dof_handles
    assert handles.drawn is not None and handles.drawn[1] == ST["b"], handles.drawn and handles.drawn[:2]
    start = time.monotonic()
    QTest.mouseMove(vp, QtCore.QPoint(5, 5))  # the pointer away (over a handle the gizmo stays on, as it should)
    harness.pump(1200)
    assert handles.drawn is not None and handles.drawn[1] == ST["b"], "gone after 1.2 s"
    harness.pump(int((s().LINGER + 1.6 - (time.monotonic() - start)) * 1000))
    from incad.ui.dof_handles import selected_component
    assert handles.drawn is None or handles.drawn[1] != ST["b"], ("still there after %.1f s" % (time.monotonic() - start),
                                                                  selected_component(doc), handles.lit,
                                                                  s()._dof_linger, time.monotonic())


def test_9_cleanup():
    for d in list(App.listDocuments().values()):
        App.closeDocument(d.Name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_assembly_with_a_plate_and_a_shaft, test_1_a_dragged_part_keeps_its_gizmo, test_9_cleanup])
