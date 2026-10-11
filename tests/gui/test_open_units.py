"""Parameters keep their units when a part is opened again: FreeCAD does not save a quantity's unit, so '90°' showed
'90' and '12 mm' showed '12' in the Parameters list (and in the dialogs) until something recomputed them."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, model, prefs  # noqa: E402

ST = {}


def test_0_save_a_part_with_parameters():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    document.set_parameter(doc, "width", "40 mm")
    ST["angle"] = model.new_feature_parameter(doc, "90 °", "angle")
    ST["half"] = model.new_feature_parameter(doc, "width / 2", "length")
    path = os.path.join(os.environ["FREECAD_USER_TEMP"], "units.FCStd")
    doc.saveAs(path)
    harness.pump(300)
    App.closeDocument(doc.Name)
    harness.pump(800)
    ST["path"] = path


def test_1_the_reopened_part_shows_the_units():
    App.openDocument(ST["path"])
    harness.pump(2500)
    doc = App.ActiveDocument
    users = {n: v for n, _, v in document.list_parameters(doc)}
    values = {n: v for n, _, v in model.feature_parameters(doc)}
    assert users["width"] == "40 mm", users
    assert values[ST["angle"]] == "90°" and values[ST["half"]] == "20 mm", values
    assert model.parameter_text(doc, ST["angle"]) == "90°"
    assert not doc.UndoNames, doc.UndoNames  # opening it made no undo step


harness.run([test_0_save_a_part_with_parameters, test_1_the_reopened_part_shows_the_units])
