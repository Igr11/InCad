"""Delete in the Model Browser (the user, Windows: a Chamfer's delete hung, then did nothing): deleting a feature
that others are built on asks to delete those too — Yes deletes them all in one step, No leaves the part as it was."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, context, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ASKED = []


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def test_0_box_fillet_chamfer_on_it():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 20, 10, 10
    doc().recompute()
    v = [i + 1 for i, e in enumerate(box.Shape.Edges) if e.BoundBox.ZLength > 9][0]
    f = body().newObject("PartDesign::Fillet", "Fillet")
    f.Base = (box, ["Edge%d" % v])
    f.Radius = 3
    doc().recompute()
    arc = [i + 1 for i, e in enumerate(f.Shape.Edges)
           if e.Curve.TypeId == "Part::GeomCircle" and e.BoundBox.ZMax > 9.9][0]
    c = body().newObject("PartDesign::Chamfer", "Chamfer")
    c.Base = (f, ["Edge%d" % arc])
    c.Size = 0.5
    doc().recompute()
    harness.pump(500)


def delete_fillet(answer):
    shell.CONFIRM = lambda title, text: (ASKED.append(text), answer)[1]
    try:
        context.set_target("Fillet")
        commands.REGISTRY.run("browser.delete")
        harness.pump(1500)
    finally:
        shell.CONFIRM = None


def test_1_no_leaves_the_part_as_it_was():
    delete_fillet(False)
    assert ASKED and "Chamfer" in ASKED[-1] and "Fillet" in ASKED[-1], ASKED
    assert doc().getObject("Fillet") is not None and doc().getObject("Chamfer") is not None
    assert "Invalid" not in doc().getObject("Chamfer").State


def test_2_yes_deletes_both_in_one_step():
    delete_fillet(True)
    assert doc().getObject("Fillet") is None and doc().getObject("Chamfer") is None
    assert body().Tip.Name == "Box", body().Tip.Name
    doc().undo()
    doc().recompute()
    harness.pump(800)
    assert doc().getObject("Fillet") is not None and doc().getObject("Chamfer") is not None, "one undo step back"


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_box_fillet_chamfer_on_it, test_1_no_leaves_the_part_as_it_was, test_2_yes_deletes_both_in_one_step,
             test_9_cleanup])
