"""Screenshots for the 0.2.0 presentation and manual, taken in a test FreeCAD window (tests/run_gui.sh this file).
Works on copies in SHOTS (never the originals): part.FCStd, Train_1.FCStd (two pieces), Train_3-Assembly.FCStd with its
Train_3-Solid1/2.FCStd. Nothing is saved. PNGs go to SHOTS; the caller converts them to JPG."""
import os
import sys
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import assembly, commands, context, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui import make_assembly_dialog  # noqa: E402

SHOTS = os.environ.get("INCAD_SHOTS", "/private/tmp/claude-501/-Volumes-Docs-Claude-projects-InCad/"
                       "4d5aee15-414f-472b-8875-35e2583f4c1b/scratchpad/shots")


def mark(t):
    open(os.path.join(SHOTS, "progress.txt"), "a").write(t + "\n")


mark("loaded")


def s():
    return shell.instance()


def mw():
    return Gui.getMainWindow()


def save(name, extra=(), frame=None):
    """The main window, with the 3D view rendered offscreen and pasted in (a window grab leaves it blank when the
    screen is locked), the panels over the view painted back on top, and every other visible window (dialogs) at
    its place."""
    mark("save " + name)
    harness.pump(800)
    img = mw().grab()
    p = QtGui.QPainter(img)
    try:
        view = Gui.ActiveDocument.ActiveView
        gv = view.graphicsView()
        rect = QtCore.QRect(mw().mapFromGlobal(gv.mapToGlobal(QtCore.QPoint(0, 0))), gv.size())
        dpr = img.devicePixelRatio()
        if frame is not None:
            frame()
        from pivy import coin  # noqa: F401  (getCameraNode needs it)
        cam = view.getCameraNode()  # a view never drawn (locked screen) keeps stale near / far: open them wide
        cam.nearDistance.setValue(1.0)
        cam.farDistance.setValue(cam.focalDistance.getValue() * 2 + 5000.0)
        gl = os.path.join(SHOTS, "_view.png")
        scale = float(os.environ.get("INCAD_SHOT_SCALE", dpr))
        view.saveImage(gl, int(gv.width() * scale), int(gv.height() * scale), "Current")
        p.drawImage(rect, QtGui.QImage(gl))
        for w in s()._mdi().viewport().children() + gv.viewport().children():
            if isinstance(w, QtWidgets.QWidget) and w.isVisible() and not isinstance(w, QtWidgets.QMdiSubWindow):
                p.drawPixmap(mw().mapFromGlobal(w.mapToGlobal(QtCore.QPoint(0, 0))), w.grab())
    except Exception as e:  # no 3D view (or no document): the plain grab
        mark("no view: %r" % e)
    others = list(extra) + [w for w in QtWidgets.QApplication.topLevelWidgets()
                            if w is not mw() and w.isVisible() and w.isWindow() and w.width() > 40 and w not in extra]
    for w in others:
        p.drawPixmap(mw().mapFromGlobal(w.mapToGlobal(QtCore.QPoint(0, 0))), w.grab())
    p.end()
    img.save(os.path.join(SHOTS, name + ".png"))


def fit():
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)


def frame_box(view, bb):
    """Point the camera at a box (fitAll in a tab never drawn, on a locked screen, misses the context)."""
    from pivy import coin
    centre = coin.SbVec3f(bb.Center.x, bb.Center.y, bb.Center.z)
    diag = bb.DiagonalLength
    cam = view.getCameraNode()
    d = cam.orientation.getValue().multVec(coin.SbVec3f(0, 0, -1))
    cam.position.setValue(centre - d * (diag * 2))
    cam.focalDistance.setValue(diag * 2)
    cam.height.setValue(diag * 1.1)
    cam.nearDistance.setValue(1.0)
    cam.farDistance.setValue(diag * 4 + 100)


def close_all():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    harness.pump(800)


def test_0_window():
    mark('test_0_window')
    prefs.set_theme("dark")
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    shell.UPDATE_ASK = lambda *a, **k: True
    shell.CONFIRM = lambda *a, **k: True
    if os.environ.get("INCAD_SHOTS_RESIZE"):  # the window as for the 0.2 shots; moving it hung FreeCAD now and then
        mw().showNormal()
        mw().resize(1680, 1000)
        mw().move(40, 40)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1500)


def test_1_part_dialogs():
    mark('test_1_part_dialogs')
    App.openDocument(os.path.join(SHOTS, "part.FCStd"))
    harness.pump(3000)
    s().schedule_refresh()
    harness.pump(800)
    fit()
    for name, shot in (("Thread", "13_thread_dialog"), ("Hole", "12_hole_dialog")):
        try:
            context.set_target(name)
            commands.REGISTRY.run("browser.edit")
            harness.pump(2500)
            save(shot)
        finally:
            fs = s().feature_session
            if fs is not None:
                fs.cancel()
                harness.pump(1000)
    commands.REGISTRY.run("view.parameters")
    harness.pump(1200)
    save("14_parameters")
    commands.REGISTRY.run("view.parameters")
    harness.pump(600)


def test_2_constraint_list():
    mark('test_2_constraint_list')
    doc = App.ActiveDocument
    sketches = [o for o in doc.Objects if o.TypeId == "Sketcher::SketchObject" and not o.Name.startswith("Thread")]
    sk = max(sketches, key=lambda o: o.ConstraintCount)
    s().sketches.edit(sk)
    harness.pump(2500)
    commands.REGISTRY.run("sketch.constraints_window")
    harness.pump(1500)
    save("6_constraint_list")
    s().close_constraints_window()
    commands.REGISTRY.run("sketch.finish")
    harness.pump(1200)
    close_all()


def test_3_make_assembly_dialog():
    mark('test_3_make_assembly_dialog')
    App.openDocument(os.path.join(SHOTS, "Train_1.FCStd"))
    harness.pump(2500)
    s().schedule_refresh()
    harness.pump(800)
    fit()

    def shown(dlg):
        dlg.show()
        harness.pump(1500)
        save("11_make_assembly", (dlg,))
        dlg.close()
        return QtWidgets.QDialog.Rejected
    old = make_assembly_dialog.MakeAssemblyDialog.exec
    make_assembly_dialog.MakeAssemblyDialog.exec = shown
    try:
        commands.REGISTRY.run("file.make_assembly")
    finally:
        make_assembly_dialog.MakeAssemblyDialog.exec = old
    harness.pump(800)
    close_all()


def test_4_assembly():
    mark('test_4_assembly')
    App.openDocument(os.path.join(SHOTS, "Train_3-Solid2.FCStd"))  # its tab exists before Edit (laid out, drawn)
    harness.pump(2000)
    asm = App.openDocument(os.path.join(SHOTS, "Train_3-Assembly.FCStd"))
    harness.pump(3000)
    App.setActiveDocument(asm.Name)
    Gui.ActiveDocument = Gui.getDocument(asm.Name)
    s().schedule_refresh()
    harness.pump(1500)
    fit()
    free = next(c for c in assembly.components(asm) if c.Name.endswith("Solid2"))
    commands.REGISTRY.run("view.dof")
    harness.pump(1500)
    save("9_dof")
    commands.REGISTRY.run("view.dof")
    harness.pump(800)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(asm.Name, free.Name)
    harness.pump(1500)
    save("8_gizmo")
    Gui.Selection.clearSelection()
    harness.pump(500)
    tangent = next(j for j in asm.getObject("Joints").Group if j.Label.startswith("Tangent"))
    s().edit_feature(tangent)
    harness.pump(2500)
    save("7_mate_flip")
    s()._close_feature_session(cancel=True)
    harness.pump(1200)
    s().assembly_edit(free)
    harness.pump(3000)
    v = Gui.getDocument(App.ActiveDocument.Name).ActiveView  # the part's new tab
    v.viewIsometric()
    bb = App.BoundBox()
    for o in App.ActiveDocument.Objects:
        if o.TypeId == "PartDesign::Body":
            bb.add(o.Shape.BoundBox)
    bb.enlarge(bb.DiagonalLength * 0.6)  # room for the parts around it
    save("10_context", frame=lambda: frame_box(v, bb))  # set right before the render: a pump resets it
    close_all()


def test_5_move_face():
    """15_move_face: Move Face on the sample part's top, 3 mm typed: the dialog, the preview, the arrow and its label."""
    App.openDocument(os.path.join(SHOTS, "part.FCStd"))
    harness.pump(3000)
    s().schedule_refresh()
    harness.pump(800)
    fit()
    doc = App.ActiveDocument
    tip = document.primary_body(doc).Tip
    faces = tip.Shape.Faces
    i = max((k for k, fc in enumerate(faces) if fc.Surface.__class__.__name__ == "Plane" and fc.normalAt(0, 0).z > 0.999),
            key=lambda k: faces[k].Area)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, tip.Name, "Face%d" % (i + 1))
    commands.REGISTRY.run("feature.move_face")
    harness.pump(2000)
    fs = s().feature_session
    fs.dialog.set_values({"mode": "together"})  # the sample's top has fillets: Together carries them up
    w = fs.dialog.field("distance")
    w.setText("3 mm")
    w.editingFinished.emit()
    harness.pump(2500)
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")  # after the preview: the part grew, the arrow and its label stay in view
    harness.pump(800)
    Gui.ActiveDocument.ActiveView.getCameraNode().height.setValue(Gui.ActiveDocument.ActiveView.getCameraNode().height.getValue() * 1.25)
    harness.pump(500)
    Gui.Selection.clearSelection()
    harness.pump(500)
    save("15_move_face")
    fs.cancel()
    harness.pump(1000)
    close_all()


TESTS = [test_0_window, test_1_part_dialogs, test_2_constraint_list, test_3_make_assembly_dialog, test_4_assembly,
         test_5_move_face]
ONLY = os.environ.get("INCAD_SHOTS_ONLY")  # e.g. "test_4_assembly": that one after test_0_window
harness.run([t for t in TESTS if not ONLY or t is test_0_window or t.__name__ in ONLY.split(",")])
