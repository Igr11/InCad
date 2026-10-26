"""Suppress on a Fillet / Chamfer row (the user: suppress should make the fillet disappear from the Solid): the row's
Suppress takes the round off what the view shows, Unsuppress puts it back; the same for a Chamfer, and for a Fillet
in the middle of the history (a Pocket after it)."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, context, document, prefs  # noqa: E402
from incad.features import dressup  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def shown_volume():
    """The volume of what the view draws for the part: its shown features' shapes."""
    shown = [o for o in body().Group if o.Visibility and hasattr(o, "Shape") and not o.Shape.isNull()
             and o.Shape.Solids]
    assert len(shown) == 1, [o.Name for o in shown]
    return round(shown[0].Shape.Volume, 3)


def run_on(name, cmd):
    context.set_target(name)
    r = commands.REGISTRY.run(cmd)
    harness.pump(1200)
    assert r.ok, r.error


def test_0_box():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    b = body().newObject("PartDesign::AdditiveBox", "Box")
    b.Length, b.Width, b.Height = 20, 10, 10
    doc().recompute()
    ST["box"] = b.Name


def _top_edge(feature):
    return "%s:Edge%d" % (feature.Name, [i + 1 for i, e in enumerate(feature.Shape.Edges)
                                         if abs(e.CenterOfMass.z - 10) < 1e-6 and abs(e.CenterOfMass.y) < 1e-6][0])


def test_1_suppress_a_fillet():
    box = doc().getObject(ST["box"])
    k = dressup.FILLET
    f = k.create(doc(), body(), None, dict(k.defaults(doc(), body(), None), edges=_top_edge(box)))
    doc().recompute()
    s().schedule_refresh()
    harness.pump(800)
    with_round = shown_volume()
    assert with_round < 2000, with_round
    run_on(f.Name, "browser.suppress")
    assert f.Suppressed
    assert shown_volume() == 2000.0, ("the round is still drawn", shown_volume())
    run_on(f.Name, "browser.suppress")
    assert not f.Suppressed and shown_volume() == with_round
    ST["fillet"] = f.Name


def test_2_suppress_a_chamfer():
    f0 = doc().getObject(ST["fillet"])
    k = dressup.CHAMFER
    edge = "%s:Edge%d" % (f0.Name, [i + 1 for i, e in enumerate(f0.Shape.Edges)
                                    if abs(e.CenterOfMass.z - 10) < 1e-6 and abs(e.CenterOfMass.y - 10) < 1e-6][0])
    c = k.create(doc(), body(), None, dict(k.defaults(doc(), body(), None), edges=edge))
    doc().recompute()
    s().schedule_refresh()
    harness.pump(800)
    both = shown_volume()
    run_on(c.Name, "browser.suppress")
    assert shown_volume() > both, ("the chamfer is still drawn", shown_volume(), both)
    run_on(c.Name, "browser.suppress")
    assert shown_volume() == both
    ST["chamfer"] = c.Name


def test_3_a_fillet_in_the_middle():
    """The Fillet first, the Chamfer after it: suppressing the Fillet takes its round off the end result."""
    before = shown_volume()
    run_on(ST["fillet"], "browser.suppress")
    after = shown_volume()
    assert after > before, ("the round of a fillet in the middle stays", after, before)
    assert "Invalid" not in doc().getObject(ST["chamfer"]).State, doc().getObject(ST["chamfer"]).getStatusString()
    run_on(ST["fillet"], "browser.suppress")
    assert shown_volume() == before


def test_9_cleanup():
    App.closeDocument(doc().Name)
    harness.pump(300)


harness.run([test_0_box, test_1_suppress_a_fillet, test_2_suppress_a_chamfer, test_3_a_fillet_in_the_middle,
             test_9_cleanup])
