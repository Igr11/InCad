"""A part saved while a sketch was being edited keeps its Body hidden (FreeCAD hides it in sketch edit mode);
opened again it showed nothing until the user guessed. InCad shows the result when such a file opens."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def test_0_save_a_part_with_a_hidden_body():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    pad = util.add_pad(body, util.add_rect_sketch(body), 10)
    body.Tip = pad
    doc.recompute()
    body.Visibility = False  # what FreeCAD leaves behind when the file is saved in sketch edit mode
    path = os.path.join(os.environ["FREECAD_USER_TEMP"], "hidden_body.FCStd")
    doc.saveAs(path)
    harness.pump(300)
    App.closeDocument(doc.Name)
    harness.pump(800)
    ST["path"] = path


def test_1_the_reopened_part_shows_its_body():
    App.openDocument(ST["path"])
    harness.pump(2500)
    doc = App.ActiveDocument
    assert doc is not None and doc.FileName == ST["path"], getattr(doc, "FileName", None)
    body = document.primary_body(doc)
    assert body.Visibility, "the Body is shown again"
    assert body.Tip.Visibility, "and its result with it"


harness.run([test_0_save_a_part_with_a_hidden_body, test_1_the_reopened_part_shows_its_body])
