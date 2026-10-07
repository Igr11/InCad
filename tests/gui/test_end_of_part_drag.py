"""End of Part dragged in the Model Browser with mouse events: the drop position decides (upper half of a feature
row = before it, lower half or its sketch = after it), Inventor's way; the Update button recomputes."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def s():
    return shell.instance()


def body():
    return document.primary_body(App.ActiveDocument)


def row(label):
    """A row by its text; 'Pad2/sketch' = the first child row of Pad2 (its sketch)."""
    label, _, child = label.partition("/")
    it = QtWidgets.QTreeWidgetItemIterator(s().browser.tree)
    while it.value():
        if it.value().text(0) == label:
            item = it.value()
            if child:
                assert item.childCount(), "no child rows under %r" % label
                return item.child(0)
            return item
        it += 1
    raise AssertionError("no row %r" % label)


def drag(src_label, dst_label, part="center"):
    tree = s().browser.tree
    vp = tree.viewport()
    src = tree.visualItemRect(row(src_label)).center()
    rect = tree.visualItemRect(row(dst_label))
    dy = {"center": 0, "upper": -rect.height() // 3, "lower": rect.height() // 3}[part]
    dst = rect.center() + QtCore.QPoint(0, dy)
    QTest.mousePress(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, src)
    harness.pump(120)
    QTest.mouseMove(vp, dst)
    harness.pump(120)
    QTest.mouseRelease(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, dst)
    harness.pump(1200)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    b = body()
    pad = util.add_pad(b, util.add_rect_sketch(b, name="SketchA"), 10)
    pad2 = util.add_pad(b, util.add_rect_sketch(b, w=5, h=5, name="SketchB"), 20, name="Pad2")
    b.Tip = pad2
    App.ActiveDocument.recompute()
    harness.pump(1000)
    assert body().Tip.Name == "Pad2"
    assert row("End of Part") is not None and row("Pad") is not None


def test_1_dragged_up_one_row_onto_the_last_feature_moves_before_it():
    drag("End of Part", "Pad2", "upper")
    assert body().Tip.Name == "Pad", body().Tip.Name


def test_2_dragged_down_onto_the_lower_half_moves_after_it():
    drag("End of Part", "Pad2", "lower")
    assert body().Tip.Name == "Pad2", body().Tip.Name


def test_3_dragged_onto_a_feature_two_rows_up_goes_after_it():
    drag("End of Part", "Pad", "center")
    assert body().Tip.Name == "Pad", body().Tip.Name


def test_3b_dragged_up_one_row_onto_the_centre_of_the_feature_above_moves_before_it():
    """The user's case: End of Part right under the last feature, dragged onto that row (lower half): before it."""
    drag("End of Part", "Pad2", "lower")
    assert body().Tip.Name == "Pad2"
    drag("End of Part", "Pad2", "center")
    assert body().Tip.Name == "Pad", body().Tip.Name
    drag("End of Part", "Pad2", "lower")
    assert body().Tip.Name == "Pad2"
    drag("End of Part", "Pad2/sketch", "center")  # its sketch, when the marker is right under the feature
    assert body().Tip.Name == "Pad", body().Tip.Name


def test_3c_the_shown_feature_follows_end_of_part():
    pad, pad2 = App.ActiveDocument.getObject("Pad"), App.ActiveDocument.getObject("Pad2")
    assert pad.Visibility and not pad2.Visibility, (pad.Visibility, pad2.Visibility)
    drag("End of Part", "Pad2", "lower")
    assert pad2.Visibility and not pad.Visibility, (pad.Visibility, pad2.Visibility)


def test_4_dragged_onto_the_first_feature_upper_half_rolls_everything_back():
    drag("End of Part", "Pad", "upper")
    assert body().Tip is None, body().Tip
    drag("End of Part", "Pad2", "lower")
    assert body().Tip.Name == "Pad2", body().Tip.Name


harness.run([test_0_setup, test_1_dragged_up_one_row_onto_the_last_feature_moves_before_it,
             test_2_dragged_down_onto_the_lower_half_moves_after_it,
             test_3_dragged_onto_a_feature_two_rows_up_goes_after_it,
             test_3b_dragged_up_one_row_onto_the_centre_of_the_feature_above_moves_before_it,
             test_3c_the_shown_feature_follows_end_of_part,
             test_4_dragged_onto_the_first_feature_upper_half_rolls_everything_back])
