"""End of Part dropped in the Model Browser: the drop position decides for an applied feature (upper half of its
row = before it, lower half or its sketch = after it), and a drop on a ROLLED-BACK feature (below the marker)
applies it whichever half was hit. The shown feature follows the tip and profile sketches hide after a move.

These drive `drop_end_of_part_on` directly: the rule is what matters, and a synthetic QTest mouse drag of the
marker is timing-flaky in the offscreen harness (the real press/move/release -> drop_target -> drop_end_of_part_on
path is covered by tests/real). Each test builds its own part so the sequence can't cascade."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.features import revolve  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

DONE = [False]


def s():
    return shell.instance()


def body():
    return document.primary_body(App.ActiveDocument)


def fresh_two_pads():
    """A part with Pad then Pad2, Pad2 the tip; a closed document from the previous test is replaced."""
    if not DONE[0]:
        prefs.set_remember_new_choice(True)
        prefs.set_default_units("mm")
        Gui.activateWorkbench("InCadWorkbench")
        harness.pump(1000)
        DONE[0] = True
    for d in list(App.listDocuments()):
        App.closeDocument(d)
    harness.pump(200)
    commands.REGISTRY.run("file.new")
    harness.pump(700)
    b = body()
    util.add_pad(b, util.add_rect_sketch(b, name="SketchA"), 10)
    pad2 = util.add_pad(b, util.add_rect_sketch(b, w=5, h=5, name="Pad2Sketch"), 20, name="Pad2")
    b.Tip = pad2
    App.ActiveDocument.recompute()
    s().refresh()
    harness.pump(600)
    return b


def row(label):
    it = QtWidgets.QTreeWidgetItemIterator(s().browser.tree)
    while it.value():
        if it.value().text(0) == label or it.value().text(0).startswith(label + " "):
            return it.value()
        it += 1
    raise AssertionError("no tree row %r" % label)


def drop(label, above):
    s().refresh()  # the tree must reflect the current tip before we read rows (rolled-back is decided by position)
    harness.pump(120)
    s().browser.drop_end_of_part_on(row(label), above=above)
    harness.pump(700)


def test_1_upper_half_of_the_last_feature_moves_before_it():
    fresh_two_pads()
    drop("Pad2", above=True)   # Pad2 is applied (the tip): upper half -> before it
    assert body().Tip.Name == "Pad", body().Tip.Name


def test_2_drop_on_a_rolled_back_feature_applies_it():
    fresh_two_pads()
    drop("Pad2", above=True)   # Pad2 applied -> before it (roll it back)
    assert body().Tip.Name == "Pad", body().Tip.Name
    drop("Pad2", above=True)   # Pad2 now rolled back -> applied, even on the upper half
    assert body().Tip.Name == "Pad2", body().Tip.Name


def test_2b_rolled_back_feature_applies_on_lower_half_and_via_its_sketch():
    fresh_two_pads()
    drop("Pad2", above=True)    # roll Pad2 back
    assert body().Tip.Name == "Pad"
    drop("Pad2", above=False)   # lower half of a rolled-back feature -> apply
    assert body().Tip.Name == "Pad2", body().Tip.Name
    drop("Pad2", above=True)    # roll back again
    assert body().Tip.Name == "Pad"
    drop("Pad2Sketch", above=False)  # its sketch (rolled back) -> apply the feature
    assert body().Tip.Name == "Pad2", body().Tip.Name


def test_3_lower_half_of_an_applied_feature_two_rows_up_goes_after_it():
    fresh_two_pads()
    drop("Pad", above=False)   # Pad applied, lower half -> after it (rolls Pad2 back)
    assert body().Tip.Name == "Pad", body().Tip.Name


def test_4_upper_half_of_the_first_feature_rolls_everything_back():
    fresh_two_pads()
    drop("Pad", above=True)    # Pad is the first feature: before it = nothing applied
    assert body().Tip is None, body().Tip


def test_5_the_shown_feature_and_sketches_follow_the_tip():
    fresh_two_pads()
    pad, pad2 = App.ActiveDocument.getObject("Pad"), App.ActiveDocument.getObject("Pad2")
    drop("Pad", above=False)   # tip -> Pad
    assert pad.Visibility and not pad2.Visibility, (pad.Visibility, pad2.Visibility)
    assert not App.ActiveDocument.getObject("SketchA").Visibility  # profile sketch hidden
    drop("Pad2", above=False)  # tip -> Pad2
    assert pad2.Visibility and not pad.Visibility, (pad.Visibility, pad2.Visibility)


def test_6_rolled_back_revolve_is_applied_and_its_sketch_hidden():
    """The user's exact case: a revolve was applied, End of Part was moved up above it, and a drop back onto the
    revolve must apply it (it used to read as 'before it' and do nothing); its profile sketch hides after."""
    b = fresh_two_pads()
    xz = [o for o in b.Origin.OriginFeatures if o.Role == "XZ_Plane"][0]
    sk = b.newObject("Sketcher::SketchObject", "RevProf")
    sk.AttachmentSupport = [(xz, "")]
    sk.MapMode = "FlatFace"
    App.ActiveDocument.recompute()
    for i in range(4):
        a, c = [(12, 2), (16, 2), (16, 8), (12, 8)][i], [(12, 2), (16, 2), (16, 8), (12, 8)][(i + 1) % 4]
        sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(c[0], c[1], 0)))
    App.ActiveDocument.recompute()
    vals = revolve.defaults(App.ActiveDocument, b, sk)
    vals.update(axis_mode="V_Axis")
    rev = revolve.create(App.ActiveDocument, b, sk, vals)
    document.set_end_of_part(b, App.ActiveDocument.getObject("Pad"))  # roll the revolve (and Pad2) back
    s().refresh()
    harness.pump(700)
    assert body().Tip.Name == "Pad"
    drop("Revolve", above=True)   # upper half of a rolled-back feature still applies it
    assert body().Tip.Name == rev.Name, body().Tip.Name
    assert rev.Visibility and not sk.Visibility, (rev.Visibility, sk.Visibility)


harness.run([test_1_upper_half_of_the_last_feature_moves_before_it,
             test_2_drop_on_a_rolled_back_feature_applies_it,
             test_2b_rolled_back_feature_applies_on_lower_half_and_via_its_sketch,
             test_3_lower_half_of_an_applied_feature_two_rows_up_goes_after_it,
             test_4_upper_half_of_the_first_feature_rolls_everything_back,
             test_5_the_shown_feature_and_sketches_follow_the_tip,
             test_6_rolled_back_revolve_is_applied_and_its_sketch_hidden])
