"""SPIKE (not a repo test): FreeCAD's native assembly drag under InCad's navigation filter."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}
NOTES = {}
OUT = os.environ.get("SPIKE_OUT", "/tmp/spike_notes.json")


def note(k, v):
    NOTES[k] = v
    with open(OUT, "w") as f:
        json.dump(NOTES, f, indent=1, default=str)


def s():
    return shell.instance()


def asm_doc():
    return App.getDocument(ST["asm"])


def view():
    return Gui.getDocument(ST["asm"]).ActiveView


def viewport():
    return view().graphicsView().viewport()


def screen_of(point):
    """Qt logical viewport position of a 3D point."""
    vp = viewport()
    x, y = view().getPointOnViewport(point)
    dpr = vp.devicePixelRatioF()
    return QtCore.QPointF(x / dpr, vp.height() - y / dpr), (x, y)


def send(kind, pos, button, buttons):
    vp = viewport()
    glob = QtCore.QPointF(vp.mapToGlobal(pos.toPoint()))
    ev = QtGui.QMouseEvent(kind, pos, glob, button, buttons, QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)


def drag(start, dx, dy, steps=12):
    L = QtCore.Qt.LeftButton
    send(QtCore.QEvent.MouseMove, start, QtCore.Qt.NoButton, QtCore.Qt.NoButton)  # preselect
    harness.pump(300)
    send(QtCore.QEvent.MouseButtonPress, start, L, L)
    harness.pump(100)
    for i in range(1, steps + 1):
        send(QtCore.QEvent.MouseMove, QtCore.QPointF(start.x() + dx * i / steps, start.y() + dy * i / steps),
             QtCore.Qt.NoButton, L)
        harness.pump(60)
    end = QtCore.QPointF(start.x() + dx, start.y() + dy)
    send(QtCore.QEvent.MouseButtonRelease, end, L, QtCore.Qt.NoButton)
    harness.pump(500)


def pl(o):
    return [round(v, 4) for v in o.Placement.Base] + [round(v, 4) for v in o.Placement.Rotation.Q]


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_spike_")
    for name, w, h, t in (("Plate", 40, 30, 10), ("Block", 10, 10, 10)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = doc.Name
    a = s().assembly_place(ST["Plate"])
    b = s().assembly_place(ST["Block"])
    ST["a"], ST["b"] = a.Name, b.Name
    harness.pump(800)
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    asm = assembly.assembly_of(doc)
    vo = asm.ViewObject
    note("vp_attrs", [n for n in dir(vo) if not n.startswith("_")])
    note("vp_props", vo.PropertiesList)
    note("vp_type", vo.TypeId)
    note("workbench_before", Gui.activeWorkbench().name())


def test_1_set_edit():
    doc = asm_doc()
    asm = assembly.assembly_of(doc)
    gdoc = Gui.getDocument(doc.Name)
    ok = gdoc.setEdit(asm.Name)
    harness.pump(1500)
    edit = gdoc.getInEdit()
    note("setEdit_ret", ok)
    note("in_edit", getattr(getattr(edit, "Object", None), "Name", None))
    note("workbench_after_edit", Gui.activeWorkbench().name())
    note("control_dialog", str(Gui.Control.activeDialog()))
    wn = getattr(s(), "_wait_notice", None)
    note("wait_notice_visible", bool(wn is not None and wn.isVisible()))
    vo = asm.ViewObject
    for attr in ("EnableMovement", "MoveOnlyPreselected", "MoveInCommand", "DraggerVisibility"):
        try:
            note("vp." + attr, getattr(vo, attr))
        except Exception as e:
            note("vp." + attr, "ERR %s" % e)
    note("active_assembly", str(view().getActiveObject("part")))
    assert edit is not None


def test_2_drag_free_block():
    doc = asm_doc()
    a, b = doc.getObject(ST["a"]), doc.getObject(ST["b"])
    c = b.Shape.BoundBox.Center
    pos, coinpos = screen_of(c)
    info = view().getObjectInfo(coinpos)
    note("drag_free.hit", info and (info.get("Object"), info.get("Component"), info.get("SubName")))
    before_a, before_b = pl(a), pl(b)
    undo = list(doc.UndoNames)
    drag(pos, 80, -40)
    note("drag_free.block_before", before_b)
    note("drag_free.block_after", pl(b))
    note("drag_free.plate_moved", pl(a) != before_a)
    note("drag_free.undo_added", list(doc.UndoNames)[:3] if list(doc.UndoNames) != undo else None)
    note("drag_free.selection", [(o.ObjectName, o.SubElementNames) for o in Gui.Selection.getSelectionEx("", 0)])
    note("drag_free.moved", pl(b) != before_b)
    Gui.Selection.clearSelection()


def test_3_drag_grounded_plate():
    doc = asm_doc()
    a, b = doc.getObject(ST["a"]), doc.getObject(ST["b"])
    c = a.Shape.BoundBox.Center
    pos, coinpos = screen_of(App.Vector(a.Shape.BoundBox.XMin + 3, c.y, a.Shape.BoundBox.ZMax))
    info = view().getObjectInfo(coinpos)
    note("drag_ground.hit", info and (info.get("Object"), info.get("Component"), info.get("SubName")))
    before_a = pl(a)
    drag(pos, -60, 30)
    note("drag_ground.plate_moved", pl(a) != before_a)
    Gui.Selection.clearSelection()


def test_4_end_edit_then_mate():
    doc = asm_doc()
    gdoc = Gui.getDocument(doc.Name)
    gdoc.resetEdit()
    harness.pump(800)
    note("after_reset.in_edit", gdoc.getInEdit() is not None)
    a, b = doc.getObject(ST["a"]), doc.getObject(ST["b"])
    commands.REGISTRY.run("constrain.mate")
    harness.pump(800)
    asm = assembly.assembly_of(doc)
    top = [i + 1 for i, f in enumerate(a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    bot = [i + 1 for i, f in enumerate(b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
    Gui.Selection.addSelection(doc.Name, asm.Name, "%s.Face%d" % (a.Name, top))
    harness.pump(600)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, asm.Name, "%s.Face%d" % (b.Name, bot))
    harness.pump(1200)
    fs = s().feature_session
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    note("mate.block_after", pl(b))
    Gui.Selection.clearSelection()


def test_5_drag_mated_block():
    doc = asm_doc()
    asm = assembly.assembly_of(doc)
    gdoc = Gui.getDocument(doc.Name)
    gdoc.setEdit(asm.Name)
    harness.pump(1200)
    a, b = doc.getObject(ST["a"]), doc.getObject(ST["b"])
    bb = b.Shape.BoundBox
    pos, coinpos = screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))
    info = view().getObjectInfo(coinpos)
    note("drag_mated.hit", info and (info.get("Object"), info.get("Component"), info.get("SubName")))
    before = pl(b)
    drag(pos, 70, 30)
    note("drag_mated.before", before)
    note("drag_mated.after", pl(b))
    note("drag_mated.zmin_after", round(b.Shape.BoundBox.ZMin, 5))
    note("drag_mated.undo", list(doc.UndoNames)[:3])
    gdoc.resetEdit()
    harness.pump(500)


def test_6_drag_without_edit():
    """Does FreeCAD 1.1 drag in an assembly that is only the *active* one (no setEdit)?"""
    doc = asm_doc()
    b = doc.getObject(ST["b"])
    asm = assembly.assembly_of(doc)
    try:
        view().setActiveObject("part", asm)
    except Exception as e:
        note("noedit.setActive", "ERR %s" % e)
    harness.pump(500)
    bb = b.Shape.BoundBox
    pos, _ = screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))
    before = pl(b)
    drag(pos, 50, 20)
    note("noedit.moved", pl(b) != before)


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_setup, test_1_set_edit, test_2_drag_free_block, test_3_drag_grounded_plate,
             test_4_end_edit_then_mate, test_5_drag_mated_block, test_6_drag_without_edit, test_9_cleanup])
