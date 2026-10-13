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



from incad.features import constraints as C  # noqa: E402


def fz(l, z):
    return [i + 1 for i, f in enumerate(l.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - z) < 1e-6][0]


def fx(l, x):
    return [i + 1 for i, f in enumerate(l.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.x - x) < 1e-6][0]


def make(kind, f1, f2):
    doc = asm_doc()
    return kind.create(doc, None, None, dict(kind.defaults(doc, None), first=f1, second=f2))


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_spike3_")
    for name, w, h, t in (("Plate", 60, 40, 10), ("Mid", 20, 20, 10), ("Top", 8, 8, 6)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = doc.Name
    p = s().assembly_place(ST["Plate"]); m = s().assembly_place(ST["Mid"]); t = s().assembly_place(ST["Top"])
    ST["p"], ST["m"], ST["t"] = p.Name, m.Name, t.Name
    harness.pump(500)
    # Top mated on Mid's top face; Mid has NO constraints (free)
    make(C.MATE, "%s:Face%d" % (m.Name, fz(m, 10)), "%s:Face%d" % (t.Name, fz(t, 0)))
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)


def top_point():
    t = asm_doc().getObject(ST["t"])
    bb = t.Shape.BoundBox
    return screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))[0]


def native_drag(dx, dy):
    doc = asm_doc()
    gdoc = Gui.getDocument(doc.Name)
    gdoc.setEdit(assembly.assembly_of(doc).Name)
    harness.pump(800)
    drag(top_point(), dx, dy)
    gdoc.resetEdit()
    harness.pump(500)


def test_1_native_pulls_free_neighbour():
    doc = asm_doc()
    m, t = doc.getObject(ST["m"]), doc.getObject(ST["t"])
    bm, bt = pl(m), pl(t)
    native_drag(70, -60)  # screen drag up-right: has a component off Top's Mate plane
    note("native.mid_moved", pl(m) != bm)
    note("native.mid", (bm, pl(m)))
    note("native.top", (bt, pl(t)))
    note("native.top_gap", round(t.Shape.BoundBox.ZMin - m.Shape.BoundBox.ZMax, 5))
    commands.REGISTRY.run("edit.undo")
    harness.pump(600)


def held_drag(dx, dy):
    """Fix: every other free part grounded for the drag, inside InCad's own 'Move part' step."""
    doc = asm_doc()
    gdoc = Gui.getDocument(doc.Name)
    asm = assembly.assembly_of(doc)
    t = doc.getObject(ST["t"])
    others = [c for c in assembly.components(doc) if c is not t and not assembly.is_grounded(c)]
    undo0 = len(doc.UndoNames)
    doc.openTransaction("Move part")
    for c in others:
        assembly.ground(c)
    asm.ViewObject.MoveInCommand = False
    gdoc.setEdit(asm.Name)
    harness.pump(800)
    drag(top_point(), dx, dy)
    gdoc.resetEdit()
    harness.pump(300)
    for c in others:
        assembly.unground(c)
    asm.ViewObject.MoveInCommand = True
    doc.commitTransaction()
    harness.pump(500)
    return len(doc.UndoNames) - undo0


def test_2_held_drag_moves_only_top_on_its_plane():
    doc = asm_doc()
    m, t = doc.getObject(ST["m"]), doc.getObject(ST["t"])
    bm, bt = pl(m), pl(t)
    steps = held_drag(70, -60)
    note("held.mid_moved", pl(m) != bm)
    note("held.top", (bt, pl(t)))
    note("held.top_moved", pl(t) != bt)
    note("held.top_gap", round(t.Shape.BoundBox.ZMin - m.Shape.BoundBox.ZMax, 5))
    note("held.undo_steps", steps)
    note("held.undo_names", list(doc.UndoNames)[:3])
    note("held.joints_left", [j.Label for j in assembly.joints(doc)])
    ST["bt"] = bt
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    note("held.undo_back", pl(t) == bt)
    note("held.joints_after_undo", [j.Label for j in assembly.joints(doc)])
    commands.REGISTRY.run("edit.redo")
    harness.pump(800)
    note("held.redo_top", pl(t))
    note("held.joints_after_redo", [j.Label for j in assembly.joints(doc)])


def test_3_dof0_part_does_not_move():
    doc = asm_doc()
    p, m = doc.getObject(ST["p"]), doc.getObject(ST["m"])
    make(C.MATE, "%s:Face%d" % (p.Name, fz(p, 10)), "%s:Face%d" % (m.Name, fz(m, 0)))
    make(C.FLUSH, "%s:Face%d" % (p.Name, fx(p, 0)), "%s:Face%d" % (m.Name, fx(m, 0)))
    from incad.features import constraints as CC
    fy = [i + 1 for i, f in enumerate(p.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.y) < 1e-6][0]
    fym = [i + 1 for i, f in enumerate(m.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.y) < 1e-6][0]
    make(CC.FLUSH, "%s:Face%d" % (p.Name, fy), "%s:Face%d" % (m.Name, fym))
    doc.recompute()
    harness.pump(500)
    bm = pl(m)
    bb = m.Shape.BoundBox
    pos = screen_of(App.Vector(bb.XMax - 2, bb.YMax - 2, bb.ZMax))[0]
    gdoc = Gui.getDocument(doc.Name)
    gdoc.setEdit(assembly.assembly_of(doc).Name)
    harness.pump(800)
    undo0 = len(doc.UndoNames)
    drag(pos, 60, 40)
    gdoc.resetEdit()
    harness.pump(400)
    note("dof0.mid_moved", pl(m) != bm)
    note("dof0.undo_added", len(doc.UndoNames) - undo0)


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_setup, test_1_native_pulls_free_neighbour, test_2_held_drag_moves_only_top_on_its_plane,
             test_3_dof0_part_does_not_move, test_9_cleanup])
