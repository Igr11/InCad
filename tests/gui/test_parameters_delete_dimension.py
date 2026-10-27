"""A sketch dimension deleted from the Parameters panel (the user: Parameters did not allow deleting dimensions):
its row's − removes the dimension from its sketch, as Delete in the sketch would; one a formula uses is refused and
stays, with the reason in the status line."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from incad.core import commands, document, prefs, sketch  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def names():
    return [n for n, _sk, _i in sketch.dimensions(App.ActiveDocument)]


def test_0_sketch_with_named_dimensions():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    k = body.newObject("Sketcher::SketchObject", "Sk")
    k.AttachmentSupport = [([o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
    k.MapMode = "FlatFace"
    a = k.addGeometry(Part.LineSegment(V(0, 0, 0), V(30, 0, 0)))
    b = k.addGeometry(Part.LineSegment(V(0, 10, 0), V(20, 10, 0)))
    k.addConstraint(Sketcher.Constraint("Distance", a, 30))
    k.addConstraint(Sketcher.Constraint("Distance", b, 20))
    k.renameConstraint(0, "d1")
    k.renameConstraint(1, "d2")
    k.setExpression("Constraints.d2", "Constraints.d1 * 2 / 3")  # d1 is used by a formula
    doc.recompute()
    harness.pump(500)
    ST["sk"] = k.Name
    assert {"d1", "d2"} <= set(names()), names()


def test_1_a_dimension_a_formula_uses_is_refused():
    s().browser.parameterRemoved.emit("d1")  # the panel's −, as the row sends it
    harness.pump(600)
    assert "d1" in names(), "d1 is used by d2's formula: it must stay"


def test_2_a_free_dimension_goes():
    count = len(App.ActiveDocument.getObject(ST["sk"]).Constraints)
    s().browser.parameterRemoved.emit("d2")
    harness.pump(600)
    assert "d2" not in names(), names()
    assert len(App.ActiveDocument.getObject(ST["sk"]).Constraints) == count - 1
    s().browser.parameterRemoved.emit("d1")  # free now that d2 is gone
    harness.pump(600)
    assert "d1" not in names(), names()


def test_9_cleanup():
    App.closeDocument(App.ActiveDocument.Name)
    harness.pump(300)


harness.run([test_0_sketch_with_named_dimensions, test_1_a_dimension_a_formula_uses_is_refused,
             test_2_a_free_dimension_goes, test_9_cleanup])
