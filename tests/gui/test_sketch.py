import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad import actions  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, document, params, prefs, sketch  # noqa: E402
from incad.ui import shell, theme  # noqa: E402

mw = Gui.getMainWindow()
L = QtCore.Qt.LeftButton
BASE = {}
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def sk():
    return s().sketches.editing()


def sketch_settings():
    return {g: params.snapshot(g, keys) for g, keys in theme.SKETCH_KEYS.items()}


def plane(role):
    body = document.primary_body(doc())
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def click_view():
    v = Gui.ActiveDocument.ActiveView
    vp = v.graphicsView().viewport()
    p = QtCore.QPointF(vp.width() * 0.5, vp.height() * 0.5)
    for t, bs in ((QtCore.QEvent.MouseButtonPress, L), (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
        QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(t, p, QtCore.QPointF(vp.mapToGlobal(p.toPoint())),
                                                                L, bs, QtCore.Qt.NoModifier))
        harness.pump(60)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    BASE["sketch"] = sketch_settings()
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)


def test_1_sketcher_commands_exist():
    missing = [c for _, _, c, _ in actions.SKETCHER.values() if c not in Gui.listCommands()]
    assert not missing, missing


def test_2_start_on_selected_plane_stays_in_incad():
    Gui.Selection.addSelection(doc().Name, plane("XY_Plane").Name)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    assert sk() is not None and sk().Label == "Sketch1"
    assert Gui.activeWorkbench().name() == "InCadWorkbench", Gui.activeWorkbench().name()
    assert s().active
    assert s().ribbon.tab_names()[0] == "Sketch", s().ribbon.tab_names()
    assert s().status.texts()["dof"] != ""
    ST["sk"] = sk().Name


def test_3_settings_applied_while_active():
    p = App.ParamGet(theme.SKETCH_TOOLS)
    assert p.GetInt("OnViewParameterVisibility", 1) == 0  # FreeCAD's own value field is off: InCad's box instead
    assert not App.ParamGet(theme.SKETCH_ROOT).GetBool("ShowDialogOnDistanceConstraint", True)


def test_4_dimension_names_and_value_box():
    k = sk()
    k.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)))
    k.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0)))
    harness.pump(400)
    assert s().value_box is None, "drawing must not open the value box"
    k.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
    harness.pump(600)
    assert k.Constraints[-1].Name == "d0", [c.Name for c in k.Constraints]
    box = s().value_box
    assert box is not None and box.isVisible() and box.name == "d0"
    box.edit.setText("40")
    QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
    harness.pump(600)
    assert abs(k.getDatum("d0").Value - 40) < 1e-6, k.getDatum("d0")


def test_5_click_a_dimension_inserts_its_name():
    k = sk()
    k.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10))
    harness.pump(600)
    box = s().value_box
    assert box is not None and box.name == "d1"
    index = [c.Name for c in k.Constraints].index("d0")
    Gui.Selection.setPreselection(k, "Constraint%d" % (index + 1))
    click_view()
    assert box.edit.text() == "d0", box.edit.text()
    QTest.keyClicks(box.edit, "/2")
    QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
    harness.pump(600)
    rows = {n: (f, v) for n, f, v in sketch.model_parameters(doc())}
    assert rows["d1"] == ("d0 / 2", "20 mm"), rows
    assert ("d1", "d0 / 2", "20 mm") in s().browser.parameter_rows(), s().browser.parameter_rows()


def test_6_parameter_click_and_rename():
    document.set_parameter(doc(), "Width", "100 mm")
    s().open_value_box(sk(), "d0")
    harness.pump(200)
    s().browser.parameterClicked.emit("Width")
    box = s().value_box
    assert box.edit.text() == "Width", box.edit.text()
    QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
    harness.pump(600)
    s().browser.parameterRenamed.emit("d0", "Len")
    harness.pump(600)
    rows = {n: (f, v) for n, f, v in sketch.model_parameters(doc())}
    assert rows["Len"] == ("Width", "100 mm") and rows["d1"][0] == "Len / 2", rows


def test_7_shortcuts_follow_the_mode():
    assert s().shortcut_action("sketch.line").isEnabled()
    assert not s().shortcut_action("sketch.start").isEnabled()


def test_8_right_click_in_a_sketch():
    v = Gui.ActiveDocument.ActiveView
    vp = v.graphicsView().viewport()
    p = QtCore.QPointF(vp.width() * 0.2, vp.height() * 0.8)
    R = QtCore.Qt.RightButton
    for t, bs in ((QtCore.QEvent.MouseButtonPress, R), (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
        QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(t, p, QtCore.QPointF(vp.mapToGlobal(p.toPoint())),
                                                                R, bs, QtCore.Qt.NoModifier))
        harness.pump(80)
    assert s().menu_kind == "sketch", s().menu_kind
    s().marking_menu.close()
    harness.pump(100)


def test_9_typing_never_triggers_sketch_shortcuts():
    ran = []
    original = commands.REGISTRY.run
    commands.REGISTRY.run = lambda i: (ran.append(i), original(i))[1]
    try:
        b = s().browser
        r = b.add_parameter_row()
        editor = b.params.findChild(QtWidgets.QLineEdit)
        QTest.keyClicks(editor, "Lcdrax")
        QTest.keyClick(editor, QtCore.Qt.Key_Escape)
        b.params.removeRow(r)
    finally:
        commands.REGISTRY.run = original
    assert not [i for i in ran if i.startswith("sketch.")], ran


def test_10_finish():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    assert sk() is None
    assert "Sketch" not in s().ribbon.tab_names()[:1] or s().ribbon.tab_names()[0] == "3D Model", s().ribbon.tab_names()
    assert s().shortcut_action("sketch.start").isEnabled()
    row = [r for r in s().browser.tree_rows() if r[1] == "Sketch1"]
    assert row, s().browser.tree_rows()


def test_11_pick_mode():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.start")
    harness.pump(500)
    assert s().sketches.picking
    Gui.Selection.addSelection(doc().Name, plane("XZ_Plane").Name)
    harness.pump(1000)
    assert not s().sketches.picking and sk() is not None and sk().Label == "Sketch2"
    commands.REGISTRY.run("sketch.finish")
    harness.pump(600)


def test_12_sketch_on_a_face():
    import headless.util as util
    body = document.primary_body(doc())
    base = util.add_rect_sketch(body, name="Base")
    pad = util.add_pad(body, base, 10)
    doc().recompute()
    top = [i + 1 for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    Gui.Selection.addSelection(doc().Name, pad.Name, "Face%d" % top)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    assert sk() is not None
    support = sk().AttachmentSupport[0]
    assert support[0].Name == pad.Name and support[1][0] == "Face%d" % top, support
    commands.REGISTRY.run("sketch.finish")
    harness.pump(600)


def test_12b_value_box_follows_its_sketch():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, plane("YZ_Plane").Name)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    k = sk()
    ST["fresh"] = k.Name
    # the first thing drawn: a circle with its size typed while drawing (geometry and dimension in one go)
    k.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
    k.addConstraint(Sketcher.Constraint("Diameter", 0, 10))
    harness.pump(600)
    assert s().value_box is None, "values typed while drawing must not open the value box"
    name = k.Constraints[-1].Name
    s().open_value_box(k, name)
    harness.pump(200)
    box = s().value_box
    box.edit.setText("Nope*2")
    QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
    harness.pump(400)
    assert s().value_box is box and box.isVisible() and box.edit.text() == "Nope*2", "rejected text must stay"
    assert box.error_text(), "the reason must be shown"
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    assert s().value_box is None, "the box must close with its sketch"
    assert doc().getObject(ST["fresh"]).ViewObject.EditingWorkbench == "SketcherWorkbench", \
        doc().getObject(ST["fresh"]).ViewObject.EditingWorkbench


def test_12c_leaving_incad_mid_sketch_closes_the_sketch():
    s().sketches.edit(doc().getObject(ST["fresh"]))
    harness.pump(800)
    assert sk() is not None
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert Gui.ActiveDocument.getInEdit() is None
    assert doc().getObject(ST["fresh"]).ViewObject.EditingWorkbench == "SketcherWorkbench"
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)


def test_13_leaving_incad_restores_sketch_settings():
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert sketch_settings() == BASE["sketch"], (sketch_settings(), BASE["sketch"])


harness.run([test_0_setup, test_1_sketcher_commands_exist, test_2_start_on_selected_plane_stays_in_incad,
             test_3_settings_applied_while_active, test_4_dimension_names_and_value_box,
             test_5_click_a_dimension_inserts_its_name, test_6_parameter_click_and_rename,
             test_7_shortcuts_follow_the_mode, test_8_right_click_in_a_sketch,
             test_9_typing_never_triggers_sketch_shortcuts, test_10_finish, test_11_pick_mode,
             test_12_sketch_on_a_face, test_12b_value_box_follows_its_sketch,
             test_12c_leaving_incad_mid_sketch_closes_the_sketch, test_13_leaving_incad_restores_sketch_settings])
