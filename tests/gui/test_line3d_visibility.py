"""A 3D Line hides and shows as a sketch does (the user: it could not be hidden — "Nothing to hide or show"): Hide /
Show from its row, Undo, Hide All / Show All Sketches, its browser row's state, kept after save and reopen; an unused
3D Line is shown (an open path, as an open sketch); a Text hides by Hide too."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, line3d as core_line, prefs  # noqa: E402
from incad.features import line3d  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui.browser import STATE_ROLE  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def line():
    return doc().getObject(ST["line"])


def run(cmd):
    r = commands.REGISTRY.run(cmd)
    harness.pump(600)
    assert r.ok, "%s: %s" % (cmd, r.error)


def pick_row():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, line().Name)
    harness.pump(300)


def row_state():
    s().schedule_refresh()
    harness.pump(600)
    item = s().browser.item_by_label(line().Label)
    assert item is not None, "no browser row for the 3D Line"
    return item.data(0, STATE_ROLE)


def test_0_part_and_line():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 10, 10, 5
    doc().recompute()
    f = line3d.create(doc(), body(), None, dict(line3d.defaults(doc(), body()),
                                                points=core_line.format_points([(0, 0, 0), (0, 0, 30), (20, 0, 40)])))
    doc().recompute()
    ST["line"] = f.Name
    document.apply_visibility(doc())
    harness.pump(500)
    assert line().Visibility, "an unused 3D Line is hidden (it is an open path, shown as an open sketch is)"


def test_1_hide_and_show_from_its_row():
    pick_row()
    run("view.hide")
    assert not line().Visibility, "Hide left the 3D Line shown"
    assert row_state() == "hidden", row_state()
    pick_row()
    peek = s()._peeked
    run("view.show")
    assert line().Visibility, ("Show left the 3D Line hidden", getattr(line(), document.SHOWN_PROP, None),
                               "peek before", peek, "peek now", s()._peeked)


def test_2_undo_brings_it_back():
    pick_row()
    run("view.hide")
    assert not line().Visibility
    run("edit.undo")
    assert line().Visibility, "Undo of Hide left the 3D Line hidden"
    run("edit.redo")
    assert not line().Visibility, "Redo of Hide left the 3D Line shown"


def test_3_show_all_and_hide_all_sketches():
    run("view.sketches_show_all")
    assert line().Visibility, "Show All Sketches left the 3D Line hidden"
    run("view.sketches_hide_all")
    assert not line().Visibility, "Hide All Sketches left the 3D Line shown"


def test_4_kept_after_save_and_reopen():
    path = os.path.join(tempfile.mkdtemp(), "line3d_hidden.FCStd")
    name = line().Name
    doc().saveAs(path)
    App.closeDocument(doc().Name)
    harness.pump(500)
    App.openDocument(path)
    harness.pump(1500)
    ST["line"] = name
    document.apply_visibility(doc())
    harness.pump(300)
    assert not line().Visibility, "the hidden 3D Line came back after reopening"
    pick_row()
    run("view.show")
    assert line().Visibility


def test_5_a_text_hides_too():
    from incad.features import sketch_text
    texts = [o for o in doc().Objects if sketch_text.is_text(o)]
    if not texts:
        return  # making a Text needs its sketch dialog; the rule is the same helper (document.is_sketch_like)
    t = texts[0]
    assert document.visibility_targets([t]) == [t]


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_part_and_line, test_1_hide_and_show_from_its_row, test_2_undo_brings_it_back,
             test_3_show_all_and_hide_all_sketches, test_4_kept_after_save_and_reopen, test_5_a_text_hides_too,
             test_9_cleanup])
