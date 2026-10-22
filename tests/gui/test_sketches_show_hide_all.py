"""View ▸ Hide / Show ▸ Show All Sketches / Hide All Sketches (the user): every sketch of the part shows — the ones its
features use too — or hides, and stays so after the view refreshes; one undo step brings the earlier state back."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def doc():
    return App.getDocument(ST["doc"])


def shown():
    return {n: doc().getObject(n).Visibility for n in (ST["base"], ST["open"])}


def run(cmd):
    r = commands.REGISTRY.run(cmd)
    assert getattr(r, "ok", True), getattr(r, "error", "")
    shell.instance().schedule_refresh()
    harness.pump(1200)


def test_0_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    d = App.ActiveDocument
    body = document.primary_body(d)
    base = util.add_rect_sketch(body, 20, 10, "Base")
    body.Tip = util.add_pad(body, base, 10)
    sk = body.newObject("Sketcher::SketchObject", "Path")
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(V(0, 0, 0), V(5, 5, 0)))
    d.recompute()
    document.show_result(body)
    harness.pump(500)
    ST.update(doc=d.Name, base=base.Name, open=sk.Name)
    assert shown() == {base.Name: False, sk.Name: True}, shown()


def test_1_show_all():
    run("view.sketches_show_all")
    assert all(shown().values()), shown()


def test_2_hide_all_and_undo():
    run("view.sketches_hide_all")
    assert not any(shown().values()), shown()
    assert doc().UndoNames[0] == "Hide All Sketches", doc().UndoNames[:2]
    run("edit.undo")
    assert all(shown().values()), shown()


def test_9_cleanup():
    App.closeDocument(ST["doc"])


harness.run([test_0_part, test_1_show_all, test_2_hide_all_and_undo, test_9_cleanup])
