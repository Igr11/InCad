"""A slot made symmetric about an axis with FreeCAD's Symmetric tool (its two arc centres and the axis): the slot's
Horizontal repeats what the new tie holds, the sketch stopped solving (the user). The Horizontal goes, the sketch
solves, the slot sits centred on the axis."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs, slots  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def vertex(sk, geo, pos):
    for n in range(1, 200):
        if tuple(sk.getGeoVertexIndex(n - 1)) == (geo, pos):
            return "Vertex%d" % n
    raise AssertionError("no vertex for %s" % ((geo, pos),))


def test_0_slot_in_a_sketch():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    Gui.Selection.addSelection(doc.Name, xy.Name)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    sk = s().sketches.editing()
    assert sk is not None
    ST["ids"] = slots.add(sk, V(-12, 3, 0), V(14, 3, 0), 4)
    doc.recompute()
    harness.pump(500)
    assert "Horizontal" in [c.Type for c in sk.Constraints]
    ST["sk"] = sk.Name


def test_1_symmetric_about_the_vertical_axis():
    doc = App.ActiveDocument
    sk = doc.getObject(ST["sk"])
    a1, a2 = ST["ids"][:2]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, sk.Name, vertex(sk, a1, 3))
    Gui.Selection.addSelection(doc.Name, sk.Name, vertex(sk, a2, 3))
    Gui.Selection.addSelection(doc.Name, sk.Name, "V_Axis")
    harness.pump(300)
    commands.REGISTRY.run("sketch.symmetric")
    harness.pump(1500)
    types = [c.Type for c in sk.Constraints]
    assert "Symmetric" in types, types
    assert "Horizontal" not in types, types
    assert sk.solve() == 0, (list(sk.RedundantConstraints), list(sk.ConflictingConstraints))
    c1, c2 = sk.getPoint(a1, 3), sk.getPoint(a2, 3)
    assert abs(c1.x + c2.x) < 1e-6 and abs(c1.y - c2.y) < 1e-6, (c1, c2)


def test_9_cleanup():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.stop")
    harness.pump(300)
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_slot_in_a_sketch, test_1_symmetric_about_the_vertical_axis, test_9_cleanup])
