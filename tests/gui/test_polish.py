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
from incad import actions  # noqa: E402
from incad.core import commands, context, document, materials, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)


def test_1_coil_from_a_selected_sketch():
    sk = body().newObject("Sketcher::SketchObject", "Wire")
    sk.AttachmentSupport = [([o for o in body().Origin.OriginFeatures if o.Role == "XZ_Plane"][0], "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(15, 0, 0), App.Vector(0, 0, 1), 1))
    doc().recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.coil")
    harness.pump(1500)
    assert dialog().values()["profile"] == sk.Name, dialog().values()
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert body().Tip.TypeId == "PartDesign::AdditiveHelix", body().Tip.TypeId


def test_2_material_and_mass():
    actions.choose_material(lambda: "PETG")
    harness.pump(300)
    assert materials.material(doc()) == "PETG"
    commands.REGISTRY.run("inspect.mass")
    harness.pump(500)
    rows = dict(s().info_panel.rows())
    assert "Mass" in rows, rows


def test_3_section_toggles_without_error():
    commands.REGISTRY.run("view.section")
    harness.pump(400)
    assert "failed" not in s().status.texts()["message"].lower(), s().status.texts()
    commands.REGISTRY.run("view.section")
    harness.pump(400)


def test_4_delete_from_the_browser_is_one_undo_step():
    name = body().Tip.Name
    undo = len(doc().UndoNames)
    context.set_target(name)
    commands.REGISTRY.run("browser.delete")
    harness.pump(600)
    assert doc().getObject(name) is None
    assert doc().UndoNames[0] == "Delete" and len(doc().UndoNames) == undo + 1, doc().UndoNames
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    assert body().Tip.TypeId == "PartDesign::AdditiveHelix", body().Tip


harness.run([test_0_setup, test_1_coil_from_a_selected_sketch, test_2_material_and_mass,
             test_3_section_toggles_without_error, test_4_delete_from_the_browser_is_one_undo_step])
