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



DRAG = {"edit": False}


def install_drag_on_press():
    """Option A: the assembly is in edit only while a drag that started on a free component runs."""
    nav = s().navigator
    orig_replay, orig_filter = nav._replay, nav.eventFilter

    def replay(viewport_, x, y, modifiers, button=QtCore.Qt.LeftButton, release=False):
        doc = asm_doc()
        if button == QtCore.Qt.LeftButton and not release and assembly.is_assembly(App.ActiveDocument):
            info = view().getObjectInfo(nav_to_coin(viewport_, x, y))
            name = info and info.get("SubName", "").split(".")[0]
            link = doc.getObject(name) if name else None
            if link is not None and link in assembly.components(doc) and not assembly.is_grounded(link):
                Gui.getDocument(doc.Name).setEdit(assembly.assembly_of(doc).Name)
                DRAG["edit"] = True
                DRAG.setdefault("log", []).append("edit for " + name)
        return orig_replay(viewport_, x, y, modifiers, button, release)

    def efilter(obj, event):
        res = orig_filter(obj, event)
        if DRAG["edit"] and event.type() == QtCore.QEvent.MouseButtonRelease:
            DRAG["edit"] = False
            QtCore.QTimer.singleShot(0, lambda: Gui.getDocument(ST["asm"]).resetEdit())
        return res

    nav._replay = replay
    nav.eventFilter = efilter
    # eventFilter is looked up on the C++ side via the Python override: reinstall to be sure
    for vp_ in nav.attached():
        vp_.removeEventFilter(nav)
        vp_.installEventFilter(nav)


from incad.ui.nav import to_coin as nav_to_coin  # noqa: E402


def test_1_click_selects_no_edit():
    install_drag_on_press()
    doc = asm_doc()
    b = doc.getObject(ST["b"])
    bb = b.Shape.BoundBox
    pos, _ = screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))
    before = pl(b)
    send(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
    harness.pump(300)
    L = QtCore.Qt.LeftButton
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    harness.pump(80)
    send(QtCore.QEvent.MouseButtonRelease, pos, L, QtCore.Qt.NoButton)
    harness.pump(600)
    note("click.selection", [(o.ObjectName, o.SubElementNames) for o in Gui.Selection.getSelectionEx("", 0)])
    note("click.moved", pl(b) != before)
    note("click.in_edit", Gui.getDocument(doc.Name).getInEdit() is not None)
    note("click.log", list(DRAG.get("log", [])))
    Gui.Selection.clearSelection()
    harness.pump(300)


def test_2_drag_free_on_press():
    doc = asm_doc()
    a, b = doc.getObject(ST["a"]), doc.getObject(ST["b"])
    bb = b.Shape.BoundBox
    pos, _ = screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))
    before, before_a = pl(b), pl(a)
    undo = len(doc.UndoNames)
    drag(pos, 80, -30)
    note("pressdrag.moved", pl(b) != before)
    note("pressdrag.after", pl(b))
    note("pressdrag.plate_moved", pl(a) != before_a)
    note("pressdrag.in_edit_after", Gui.getDocument(doc.Name).getInEdit() is not None)
    note("pressdrag.undo", list(doc.UndoNames)[:2])
    note("pressdrag.undo_steps", len(doc.UndoNames) - undo)
    note("pressdrag.log", list(DRAG.get("log", [])))
    note("pressdrag.selection", [(o.ObjectName, o.SubElementNames) for o in Gui.Selection.getSelectionEx("", 0)])
    ST["moved_from"] = before
    Gui.Selection.clearSelection()


def test_3_undo_restores():
    doc = asm_doc()
    b = doc.getObject(ST["b"])
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    note("undo.back", pl(b) == ST["moved_from"])
    note("undo.placement", pl(b))


def test_4_grounded_stays_and_no_edit():
    doc = asm_doc()
    a = doc.getObject(ST["a"])
    bb = a.Shape.BoundBox
    pos, _ = screen_of(App.Vector(bb.XMin + 3, bb.Center.y, bb.ZMax))
    before = pl(a)
    n = len(DRAG.get("log", []))
    drag(pos, -50, 20)
    note("ground.moved", pl(a) != before)
    note("ground.edit_entered", len(DRAG.get("log", [])) != n)
    Gui.Selection.clearSelection()


def test_5_mate_works_after_drag():
    doc = asm_doc()
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
    note("mate.zmin", round(b.Shape.BoundBox.ZMin, 5))
    Gui.Selection.clearSelection()


def test_6_drag_mated_rotation_kept():
    doc = asm_doc()
    b = doc.getObject(ST["b"])
    bb = b.Shape.BoundBox
    pos, _ = screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))
    before = pl(b)
    drag(pos, 60, 40)
    note("mated.before", before)
    note("mated.after", pl(b))
    note("mated.zmin", round(b.Shape.BoundBox.ZMin, 5))


def test_7_orbit_still_works():
    doc = asm_doc()
    cam = view().getCameraNode()
    q0 = cam.orientation.getValue().getValue()
    vp_ = viewport()
    pos = QtCore.QPointF(vp_.width() * 0.2, vp_.height() * 0.2)
    L, R = QtCore.Qt.LeftButton, QtCore.Qt.RightButton
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    send(QtCore.QEvent.MouseButtonPress, pos, R, L | R)
    for i in range(1, 8):
        send(QtCore.QEvent.MouseMove, QtCore.QPointF(pos.x() + 8 * i, pos.y()), QtCore.Qt.NoButton, L | R)
        harness.pump(30)
    send(QtCore.QEvent.MouseButtonRelease, pos, R, L)
    send(QtCore.QEvent.MouseButtonRelease, pos, L, QtCore.Qt.NoButton)
    harness.pump(300)
    note("orbit.changed", cam.orientation.getValue().getValue() != q0)


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_setup, test_1_click_selects_no_edit, test_2_drag_free_on_press, test_3_undo_restores,
             test_4_grounded_stays_and_no_edit, test_5_mate_works_after_drag, test_6_drag_mated_rotation_kept,
             test_7_orbit_still_works, test_9_cleanup])
