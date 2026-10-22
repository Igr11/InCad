"""End of Part dropped in the browser before a sketch, a Text or a work plane stays there (the user: it jumped back
to the end — FreeCAD's Tip is only ever a solid feature): what is below it is greyed and hidden, a drop at the end
brings it all back."""
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


def b():
    return shell.instance().browser


def order():
    return [("%s*" % r[1]) if r[3] == "rolled_back" else r[1] for r in b().tree_rows()
            if r[0] == 1 and r[2] in ("feature", "sketch", "end_of_part")]


def drop(label, above):
    b().drop_end_of_part_on(b().item_by_label(label), above)
    harness.pump(1500)


def test_0_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    body.Tip = util.add_pad(body, util.add_rect_sketch(body, 20, 10, "Base"), 10)
    plane = body.newObject("PartDesign::Plane", "WorkPlane")
    plane.AttachmentSupport = [(util.xy_plane(body), "")]
    plane.MapMode = "FlatFace"
    sk = body.newObject("Sketcher::SketchObject", "Sketch3")
    sk.AttachmentSupport = [(plane, "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(V(0, 0, 0), V(5, 5, 0)))
    doc.recompute()
    shell.instance().schedule_refresh()
    harness.pump(1000)
    ST.update(doc=doc.Name, sk=sk.Name)
    assert order()[-1] == "End of Part", order()


def test_1_before_the_sketch_stays():
    drop("Sketch3", True)
    assert order()[-2:] == ["End of Part", "Sketch3*"], order()
    assert not App.getDocument(ST["doc"]).getObject(ST["sk"]).Visibility


def test_2_before_the_work_plane():
    drop("WorkPlane", True)
    assert order()[-3:] == ["End of Part", "WorkPlane*", "Sketch3*"], order()


def test_3_at_the_end_all_back():
    drop("Sketch3", False)
    assert order()[-1] == "End of Part" and "Sketch3*" not in order(), order()
    assert App.getDocument(ST["doc"]).getObject(ST["sk"]).Visibility


def test_9_cleanup():
    App.closeDocument(ST["doc"])


harness.run([test_0_part, test_1_before_the_sketch_stays, test_2_before_the_work_plane, test_3_at_the_end_all_back,
             test_9_cleanup])
