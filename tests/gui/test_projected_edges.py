"""Inventor: projected edges (Project Geometry = FreeCAD's external geometry) are NORMAL geometry by default — a
loop of them is a profile to extrude, with no extra step — and Construction switches them both ways. Files made
before follow the rule on open: their projected edges become normal and the old Construction button's tied normal
copies go."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Sketcher  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs, sketch  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {"dir": tempfile.mkdtemp(prefix="incad_proj_gui_")}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def closed(sk):
    return any(w.isClosed() for w in sk.Shape.Wires)


def block():
    """A 20 x 10 x 10 block and a sketch on its top face (not projected yet)."""
    pad = util.add_pad(body(), util.add_rect_sketch(body(), 20, 10, name="Base"), 10)
    body().Tip = pad
    doc().recompute()
    top = [i + 1 for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    sk = sketch.make_sketch(body(), pad, "Face%d" % top)
    return pad, sk


def project_top_edges(pad, sk):
    """What FreeCAD's Project Geometry tool runs for each picked edge: its own undo step, then a recompute."""
    d = sk.Document
    for i, e in enumerate(pad.Shape.Edges):
        if all(abs(v.Z - 10) < 1e-6 for v in e.Vertexes):
            d.openTransaction("Add external geometry")
            sk.addExternal(pad.Name, "Edge%d" % (i + 1))
            d.commitTransaction()
            d.recompute()
            harness.pump(100)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    ST["pad"], ST["sk"] = block()
    ST["v0"] = body().Shape.Volume
    harness.pump(300)


def test_1_edges_projected_while_sketching_are_normal_right_away():
    sk = ST["sk"]
    s().sketches.edit(sk)
    harness.pump(1000)
    assert s().sketches.editing() is sk
    project_top_edges(ST["pad"], sk)
    harness.pump(1000)
    ids = sketch.projected(sk)
    assert len(ids) == 4, ids
    assert all(sketch.is_defining(sk, g) for g in ids), [sketch.is_defining(sk, g) for g in ids]
    assert sk.GeometryCount == 0, sk.GeometryCount  # no copies: the projected edges themselves
    assert closed(sk)
    assert doc().UndoNames[0] == "Add external geometry", doc().UndoNames[:3]  # adopting made no step of its own
    assert doc().UndoNames[:4].count("Add external geometry") == 4, doc().UndoNames[:5]


def press_construction(sk, sub):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name, sub)
    harness.pump(200)
    commands.REGISTRY.run("sketch.construction")
    harness.pump(800)


def test_2_construction_switches_a_projected_edge_both_ways_one_undo_step_each():
    from incad.features import common
    sk = ST["sk"]
    assert s().sketches.editing() is sk
    for want_defining in (False, True):
        undo = doc().UndoCount
        press_construction(sk, "ExternalEdge1")
        assert sketch.is_defining(sk, -3) is want_defining, (want_defining, sketch.is_defining(sk, -3))
        assert closed(sk) is want_defining and common.closed_profile(sk) is want_defining  # the profile changes
        assert doc().UndoCount == undo + 1 and doc().UndoNames[0] == "Construction", doc().UndoNames[:3]
        assert not s().construction_mode  # a pick switches geometry, never the drawing mode
    harness.pump(500)
    assert sketch.is_defining(sk, -3)


def test_3_the_construction_choice_is_kept_when_more_is_projected():
    sk = ST["sk"]
    press_construction(sk, "ExternalEdge2")
    assert not sketch.is_defining(sk, -4)
    vertical = next(i + 1 for i, e in enumerate(ST["pad"].Shape.Edges)
                    if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1)
    doc().openTransaction("Add external geometry")
    sk.addExternal(ST["pad"].Name, "Edge%d" % vertical)  # projects to a point; the shell adopts after the change
    doc().commitTransaction()
    doc().recompute()
    harness.pump(800)
    assert len(sk.ExternalGeo) == 7
    assert not sketch.is_defining(sk, -4), "adopting new projections leaves the user's construction edge"
    assert [sketch.is_defining(sk, g) for g in (-3, -5, -6)] == [True] * 3
    doc().undo()  # the point goes again
    harness.pump(800)
    assert len(sk.ExternalGeo) == 6 and not sketch.is_defining(sk, -4)
    press_construction(sk, "ExternalEdge2")
    assert all(sketch.is_defining(sk, g) for g in sketch.projected(sk))


def test_4_finish_and_extrude_the_loop_of_projected_edges():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    assert s().sketches.editing() is None
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, ST["sk"].Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(1000)
    assert dialog() is not None and dialog().isVisible()
    f = s().feature_session.feature
    assert f is not None and f.Profile[0] is ST["sk"], (f, f.Profile if f else None)
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert s().feature_session is None
    ST["extrude"] = body().Tip
    assert "Invalid" not in ST["extrude"].State, ST["extrude"].getStatusString()
    assert body().Shape.Volume > ST["v0"] + 1, (body().Shape.Volume, ST["v0"])


def test_4b_construction_that_would_break_the_extrude_is_refused_like_any_profile_edge():
    """InCad's Construction runs as a safe step: a change that breaks a feature is rolled back (the same for a
    drawn line of a used profile)."""
    sk = ST["sk"]
    s().sketches.edit(sk)
    harness.pump(1000)
    undo, volume = doc().UndoCount, body().Shape.Volume
    press_construction(sk, "ExternalEdge1")
    assert sketch.is_defining(sk, -3)
    assert doc().UndoCount == undo
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    assert "Invalid" not in ST["extrude"].State and abs(body().Shape.Volume - volume) < 1e-6


def _old_style_file(path):
    """A part as the old InCad left it: projected edges construction, a normal copy tied on each (the old
    Construction button), extruded. Built with the shell's adopting switched off, as an older InCad would."""
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    adopt, s()._adopt_projections = s()._adopt_projections, lambda *a, **k: None
    try:
        pad, sk = block()
        for i, e in enumerate(pad.Shape.Edges):
            if all(abs(v.Z - 10) < 1e-6 for v in e.Vertexes):
                sk.addExternal(pad.Name, "Edge%d" % (i + 1))
        doc().recompute()
        for g in sketch.projected(sk):
            new = sk.addGeometry(sk.ExternalGeo[-g - 1].copy(), False)
            sk.setConstruction(new, False)
            sk.addConstraint(Sketcher.Constraint("Coincident", new, 1, g, 1))
            sk.addConstraint(Sketcher.Constraint("Coincident", new, 2, g, 2))
        ext = util.add_pad(body(), sk, 5, name="OnTop")
        body().Tip = ext
        doc().recompute()
        harness.pump(500)
        assert sk.GeometryCount == 4 and not any(sketch.is_defining(sk, g) for g in sketch.projected(sk))
        assert "Invalid" not in ext.State, ext.getStatusString()
        volume = body().Shape.Volume
        names = (sk.Name, ext.Name)
        doc().saveAs(path)
    finally:
        s()._adopt_projections = adopt
    App.closeDocument(doc().Name)
    harness.pump(800)
    return names, volume


def test_5_an_old_file_is_migrated_on_open():
    path = os.path.join(ST["dir"], "OldStyle.FCStd")
    (sk_name, ext_name), volume = _old_style_file(path)
    App.openDocument(path)
    harness.pump(3000)
    d = App.ActiveDocument
    assert d is not None and d.FileName == path
    sk, ext = d.getObject(sk_name), d.getObject(ext_name)
    assert sk.GeometryCount == 0, "the tied copies are gone (%d left)" % sk.GeometryCount
    assert all(sketch.is_defining(sk, g) for g in sketch.projected(sk))
    assert "Invalid" not in ext.State, ext.getStatusString()
    assert abs(document.primary_body(d).Shape.Volume - volume) < 1e-6
    assert d.UndoCount == 0, d.UndoNames  # the migration is no undo step
    d.save()
    App.closeDocument(d.Name)
    harness.pump(800)
    ST["migrated"] = path


def test_6_a_file_with_nothing_to_adopt_is_not_marked_modified_on_open():
    App.openDocument(ST["migrated"])
    harness.pump(3000)
    d = App.ActiveDocument
    assert d is not None and d.FileName == ST["migrated"]
    assert not Gui.getDocument(d.Name).Modified, "opening changed the file"
    App.closeDocument(d.Name)
    harness.pump(500)


harness.run([test_0_setup, test_1_edges_projected_while_sketching_are_normal_right_away,
             test_2_construction_switches_a_projected_edge_both_ways_one_undo_step_each,
             test_3_the_construction_choice_is_kept_when_more_is_projected,
             test_4_finish_and_extrude_the_loop_of_projected_edges,
             test_4b_construction_that_would_break_the_extrude_is_refused_like_any_profile_edge,
             test_5_an_old_file_is_migrated_on_open,
             test_6_a_file_with_nothing_to_adopt_is_not_marked_modified_on_open])
