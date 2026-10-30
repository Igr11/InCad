"""A sketch tool's step recomputes the open sketch only (the user's jar: a thread and letters wrapped on a curved face
after the sketch, 45 s on every Offset click); the part after it follows when the sketch is finished."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs, safe  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def doc():
    return App.ActiveDocument


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(doc())
    base = util.add_pad(body, util.add_rect_sketch(body, 20, 10, "Base"), 10, "BasePad")
    top = util.add_rect_sketch(body, 6, 4, "Top")
    top.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
    boss = util.add_pad(body, top, 5, "TopPad")
    body.Tip = boss
    doc().recompute()
    harness.pump(400)
    ST.update(base=base, top=top, boss=boss)


def test_1_a_step_in_the_open_sketch_recomputes_it_alone():
    shell.instance().sketches.edit(ST["top"])
    harness.pump(800)
    r = safe.run_safely("Line", lambda: ST["top"].addGeometry(Part.LineSegment(V(1, 1, 0), V(3, 2, 0)), True), doc())
    assert r.ok, r.error
    assert "Touched" not in ST["top"].State, "the open sketch was not recomputed"
    assert "Touched" in ST["boss"].State, "the part after the sketch was recomputed on a sketch step"
    safe.recompute(doc())
    assert "Touched" in ST["boss"].State
    from incad.core import sketch  # Construction on a line: the user's jar, its chamfer broke and the switch undone
    r = safe.run_safely("Construction", lambda: sketch.toggle_construction(ST["top"], [0]), doc())
    assert r.ok and ST["top"].getConstruction(0), r.error
    assert "Touched" in ST["boss"].State
    r = safe.run_safely("Construction", lambda: sketch.toggle_construction(ST["top"], [0]), doc())
    assert r.ok and not ST["top"].getConstruction(0), r.error


def test_2_finish_brings_the_part_up_to_date():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    assert shell.instance().sketches.editing() is None
    assert "Touched" not in ST["boss"].State and "Invalid" not in ST["boss"].State


def test_3_without_an_open_sketch_everything():
    ST["base"].Length = 12
    r = safe.run_safely("Length", lambda: setattr(ST["base"], "Length", 11), doc())
    assert r.ok, r.error
    assert "Touched" not in ST["boss"].State


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_part, test_1_a_step_in_the_open_sketch_recomputes_it_alone, test_2_finish_brings_the_part_up_to_date,
             test_3_without_an_open_sketch_everything, test_9_cleanup])
