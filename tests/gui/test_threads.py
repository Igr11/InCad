import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402
from headless.test_thread import shaft, cyl_face  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def ok():
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    ST["pad"] = shaft(doc(), body(), radius=4.0, length=16).Name
    harness.pump(300)


def test_1_thread_on_a_selected_shaft_face():
    pad = doc().getObject(ST["pad"])
    obj_sub = cyl_face(pad, 4).split(":")
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, obj_sub[0], obj_sub[1])
    names = list(doc().UndoNames)
    commands.REGISTRY.run("feature.thread")
    harness.pump(1500)
    assert dialog() is not None
    assert dialog().values()["size"] == "", dialog().values()
    assert not dialog().error_text(), dialog().error_text()
    ok()
    tip = body().Tip
    assert tip.TypeId == "PartDesign::SubtractiveHelix", tip.TypeId
    assert abs(tip.Pitch.Value - 1.25) < 1e-6, tip.Pitch  # M8 suggested from the Ø8 face
    assert doc().UndoNames[0] == "Thread" and len(doc().UndoNames) == len(names) + 1, (doc().UndoNames, names)
    ST["thread"] = tip.Name


def test_2_edit_the_thread_size():
    t = doc().getObject(ST["thread"])
    shell.edit_feature(t)
    harness.pump(900)
    assert dialog().values()["size"] == "M8", dialog().values()
    combo = dialog().field("standard")
    combo.setCurrentIndex(combo.findData("iso_fine"))
    harness.pump(300)
    size = dialog().field("size")
    size.setCurrentIndex(size.findData("M8x1"))
    harness.pump(1500)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    assert abs(doc().getObject(ST["thread"]).Pitch.Value - 1.0) < 1e-6


def test_2b_print_friendly_takes_0_3_mm_clearance():
    """The user: print-friendly threads get 0.3 mm print clearance, set when the standard is chosen; back to ISO puts
    0.2 mm back; a typed clearance stays."""
    t = doc().getObject(ST["thread"])
    shell.edit_feature(t)
    harness.pump(900)
    assert dialog().values()["clearance"] == "0.2 mm", dialog().values()
    combo = dialog().field("standard")
    combo.setCurrentIndex(combo.findData("print"))
    harness.pump(600)
    assert dialog().values()["clearance"] == "0.3 mm", dialog().values()
    combo.setCurrentIndex(combo.findData("iso"))
    harness.pump(600)
    assert dialog().values()["clearance"] == "0.2 mm", dialog().values()
    w = dialog().field("clearance")
    w.setText("0.25 mm")
    w.editingFinished.emit()
    harness.pump(600)
    combo.setCurrentIndex(combo.findData("print"))
    harness.pump(600)
    assert dialog().values()["clearance"] == "0.25 mm", dialog().values()
    s().feature_session.cancel()
    harness.pump(900)
    assert s().feature_session is None


def test_3_threaded_hole():
    tip = body().Tip
    sk = util.add_rect_sketch(body(), w=30, h=20, name="Plate")
    plate = util.add_pad(body(), sk, 6, name="Plate")
    body().Tip = plate
    doc().recompute()
    top = [i + 1 for i, f in enumerate(plate.Shape.Faces) if abs(f.CenterOfMass.z - 6) < 1e-6
           and f.Surface.TypeId == "Part::GeomPlane" and f.Area > 400][0]
    hs = body().newObject("Sketcher::SketchObject", "HoleAt")
    hs.AttachmentSupport = [(plate, "Face%d" % top)]
    hs.MapMode = "FlatFace"
    hs.addGeometry(Part.Circle(App.Vector(20, 10, 0), App.Vector(0, 0, 1), 1))
    doc().recompute()
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.hole")
    harness.pump(800)
    Gui.Selection.addSelection(doc().Name, hs.Name)
    harness.pump(800)
    ht = dialog().field("hole_type")
    ht.setCurrentIndex(ht.findData("tapped")) if hasattr(ht, "findData") else ht.button("tapped").click()
    harness.pump(400)
    assert dialog().values()["thread_size"] == "", dialog().values()  # Auto: from the diameter
    size = dialog().field("thread_size")
    assert size.findData("M6x1.0") >= 0
    size.setCurrentIndex(size.findData("M6x1.0"))
    harness.pump(3000)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    h = body().Tip
    assert h.TypeId == "PartDesign::Hole" and h.Threaded and h.ModelThread, (h.TypeId, h.Threaded)
    assert h.ThreadSize.startswith("M6"), h.ThreadSize



def _thread_and_pad():
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    threads = [o for o in body.Group if o.TypeId == "PartDesign::SubtractiveHelix"]
    pads = [o for o in body.Group if o.TypeId == "PartDesign::Pad"]
    return doc, body, threads[-1], pads[0]


def test_edit_changes_the_start_face_and_offset():
    """Editing kept the previous start: Start face and Offset must be changeable in the dialog."""
    from PySide6.QtTest import QTest
    doc, body, th, pad = _thread_and_pad()
    cut_before = pad.Shape.cut(body.Shape).BoundBox
    shell.edit_feature(th)
    harness.pump(800)
    dlg = shell.instance().feature_session.dialog
    assert dlg.field("start_face").isEnabled() and dlg.field("offset").isEnabled(), "start can be edited"
    ends = [i + 1 for i, f in enumerate(pad.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"]
    far = min(ends, key=lambda i: abs(pad.Shape.Faces[i - 1].CenterOfMass.z - cut_before.ZMin)
              if cut_before.ZMin > pad.Shape.BoundBox.ZMin + 1 else -abs(pad.Shape.Faces[i - 1].CenterOfMass.z))
    dlg.set_active_pick("start_face")
    harness.pump(300)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, body.Name, "%s.Face%d" % (pad.Name, far))  # a 3D click on the end face
    harness.pump(600)
    assert dlg.values().get("start_face") == "%s:Face%d" % (pad.Name, far), (dlg.values().get("start_face"), dlg.error_text())
    dlg.field("offset").setText("3 mm")
    dlg.field("offset").editingFinished.emit()
    harness.pump(800)
    QTest.mouseClick(dlg.ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    cut_after = pad.Shape.cut(body.Shape).BoundBox
    assert abs(cut_after.ZMin - cut_before.ZMin) > 1 or abs(cut_after.ZMax - cut_before.ZMax) > 1, (cut_before, cut_after)
    from incad.features import thread as th_kind
    assert th_kind.read(doc, th)["offset"] == "3 mm"


def test_delete_from_a_3d_face_selection_removes_only_the_thread():
    """Delete after clicking the thread in 3D deleted the whole part: the click names the Body."""
    doc, body, th, pad = _thread_and_pad()
    v_before = body.Shape.Volume
    face = [i + 1 for i, f in enumerate(th.Shape.Faces) if f.Surface.TypeId == "Part::GeomCylinder"][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, body.Name, "%s.Face%d" % (th.Name, face))  # what a 3D click gives
    th_name = th.Name
    commands.REGISTRY.run("edit.delete")
    harness.pump(800)
    assert doc.getObject(th_name) is None, "the thread is gone"
    assert doc.getObject(body.Name) is not None and doc.getObject(pad.Name) is not None, "the part stays"
    assert body.Shape.isValid() and body.Shape.Volume > v_before, (v_before, body.Shape.Volume)


def test_4_threads_button_turns_every_thread_off_and_on():
    """User request: threads off while designing (faster redraws), on at the end — from the ribbon."""
    from incad.core import suppress, tree
    t = doc().getObject(ST["thread"])
    with_threads = body().Shape.Volume
    button = s().ribbon.button("feature.threads_toggle")
    assert button is not None and button.isVisible()
    QTest.mouseClick(button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    assert t.Suppressed and suppress.threads_off(doc())
    assert button.isChecked()
    assert body().Shape.Volume > with_threads + 1.0, (body().Shape.Volume, with_threads)  # threads gone from the part
    states = {n.name: n.state for n in tree.build(doc())[0].children}
    assert states.get(t.Name) == "suppressed", states
    assert doc().UndoNames[0] == "Threads Off / On", doc().UndoNames
    QTest.mouseClick(button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    assert not t.Suppressed and not button.isChecked()
    assert abs(body().Shape.Volume - with_threads) < 1e-3


def test_5_a_vanished_dialog_never_blocks_the_next_command():
    """User: during Chamfer on a thread the dialog disappeared, and every command after said 'Finish the Thread
    dialog first'. A change reported after the close is ignored, and a dead session is let go."""
    pad = doc().getObject(ST["pad"])
    obj_sub = cyl_face(pad, 4).split(":")
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, obj_sub[0], obj_sub[1])
    tip = body().Tip.Name  # the part before the dialog
    commands.REGISTRY.run("feature.thread")
    harness.pump(1500)
    fs = s().feature_session
    assert fs is not None and dialog() is not None
    dialog().set_values({"chamfer": "start"})
    harness.pump(1200)
    dialog().set_values({"chamfer": "both"})
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    # the dead state from the user's log: the dialog gone, the session never handed back
    fs.dialog.close()
    fs.dialog = None
    fs._changed({"chamfer": "none"})  # a late change: no crash
    r = commands.REGISTRY.run("feature.thread")
    harness.pump(1500)
    assert r.ok, r.error
    assert s().feature_session is not None and s().feature_session is not fs and dialog() is not None
    assert body().Tip.Name == tip, ("the lost dialog's half-made thread was rolled back", tip, body().Tip.Name)
    s().feature_session.cancel()
    harness.pump(900)
    assert s().feature_session is None and body().Tip.Name == tip


def test_6_grow_onto_a_new_shaft():
    """The user: a grown round thread rises out of the surface and runs back into it (canister caps); its dialog
    offers the chamfer too. Grow onto in the dialog makes a grown thread, a feature of its own."""
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    pad = shaft(doc(), body(), radius=10.0, length=16, name="Neck")
    harness.pump(300)
    obj_sub = cyl_face(pad, 10).split(":")
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, obj_sub[0], obj_sub[1])
    commands.REGISTRY.run("feature.thread")
    harness.pump(1500)
    dialog().field("build").button("grow").click()
    harness.pump(1500)
    combo = dialog().field("standard")
    combo.setCurrentIndex(combo.findData("custom"))
    harness.pump(600)
    dialog().set_values({"custom_profile": "semicircle", "custom_pitch": "2 mm", "custom_depth": "0.8 mm"})
    dialog()._emit()
    harness.pump(2500)
    assert not dialog().error_text(), dialog().error_text()
    f = s().feature_session.feature
    assert f.TypeId == "PartDesign::FeaturePython", f.TypeId
    assert "Invalid" not in f.State and f.Shape.isValid(), f.getStatusString()
    assert dialog().field("chamfer").isVisible(), "the chamfer is offered for grown threads too"
    ok()
    assert s().feature_session is None
    tip = body().Tip
    assert tip.TypeId == "PartDesign::FeaturePython" and len(body().Shape.Solids) == 1, tip.TypeId
    assert body().Shape.optimalBoundingBox().XMax > 10.5, "the bead stands on the neck"
    shell.edit_feature(tip)
    harness.pump(1200)
    assert dialog().values()["build"] == "grow" and dialog().values()["custom_profile"] == "semicircle"
    s().feature_session.cancel()
    harness.pump(800)

harness.run([test_0_setup, test_1_thread_on_a_selected_shaft_face, test_2_edit_the_thread_size,
             test_2b_print_friendly_takes_0_3_mm_clearance,
             test_3_threaded_hole, test_4_threads_button_turns_every_thread_off_and_on,
             test_edit_changes_the_start_face_and_offset,
             test_delete_from_a_3d_face_selection_removes_only_the_thread,
             test_5_a_vanished_dialog_never_blocks_the_next_command, test_6_grow_onto_a_new_shaft])
