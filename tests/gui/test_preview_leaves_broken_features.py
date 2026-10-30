"""A new feature's preview computes it alone (the user's jar: a Work Plane preview took 8 s, each one recomputing a
broken Emboss after the End of Part); the rest is computed once, on OK. A new sketch too (8 s to start one)."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


RUNS = []


class _Failing:
    """A feature that fails on every run (as the user's Emboss off its face): each full recompute retries it."""

    def __init__(self, obj):
        obj.Proxy = self

    def execute(self, obj):
        RUNS.append(1)
        raise ValueError("off the face")


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = shell.instance().feature_session
    return fs.dialog if fs is not None else None


def test_0_box_and_a_broken_feature_after_the_end():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    b = body().newObject("PartDesign::AdditiveBox", "Box")
    b.Length, b.Width, b.Height = 20, 10, 6
    sk = body().newObject("Sketcher::SketchObject", "Open")
    sk.AttachmentSupport = [(b, "Face6")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(V(1, 1, 0), V(5, 1, 0)))  # an open line: the pad fails
    pad = body().newObject("PartDesign::Pad", "Broken")
    pad.Profile = sk
    pad.Length = 3
    doc().recompute()
    body().Tip = b
    doc().recompute()
    harness.pump(500)
    failing = doc().addObject("Part::FeaturePython", "Failing")
    _Failing(failing)
    doc().recompute()
    assert "Invalid" in failing.State and "Touched" in failing.State, failing.State
    ST.update(box=b.Name, pad=pad.Name)


def test_1_work_plane_preview_leaves_it():
    del RUNS[:]
    if True:
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc().Name, body().Name, "%s.Face6" % ST["box"])
        commands.REGISTRY.run("work.plane")
        harness.pump(1500)
        assert dialog() is not None, "no Work Plane dialog"
        planes = [o for o in body().Group if o.TypeId == "PartDesign::Plane"]
        assert planes, "no plane previewed"
        assert not RUNS, "the preview recomputed the failing feature %d times" % len(RUNS)
        QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
        harness.pump(1500)
        assert dialog() is None
        assert [o for o in body().Group if o.TypeId == "PartDesign::Plane"]


def test_2_a_new_sketch_leaves_it():
    del RUNS[:]
    sk = shell.instance().sketches.start_on(doc().getObject(ST["box"]), "Face6")
    harness.pump(1200)
    assert sk is not None and shell.instance().sketches.editing() is sk
    assert not RUNS, "the new sketch recomputed the failing feature %d times" % len(RUNS)
    Gui.ActiveDocument.resetEdit()
    harness.pump(800)


def test_3_a_slow_step_below_end_of_part_is_left_alone():
    """The user's jar: End of Part moved up, a Chamfer dialog recomputed the letters and the lid below it, 16 s on
    every value."""
    from incad.core import safe
    b = doc().getObject(ST["box"])
    pad = doc().getObject(ST["pad"])
    del RUNS[:]
    body().Tip = b
    pad.touch()
    assert safe.beyond_end(pad)
    from incad.ui import feature_session as fsm
    fsm._recompute_sound(doc())
    assert "Touched" in pad.State, "a step below End of Part was recomputed"


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_box_and_a_broken_feature_after_the_end, test_1_work_plane_preview_leaves_it,
             test_2_a_new_sketch_leaves_it,
             test_3_a_slow_step_below_end_of_part_is_left_alone, test_9_cleanup])
