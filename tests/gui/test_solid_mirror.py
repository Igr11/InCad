"""Mirror Solid in the window (the user: mirror the part as a dependent copy until the link is broken, the way the
sketch's Mirror works): the Solid selected, Mirror Solid, the YZ plane picked, OK -> a new Solid with a Mirror Solid
row; the original grows -> the copy follows; the row's right-click menu has Break Mirror Link (an ordinary feature's
row has not); after it the copy stays as it is; Undo brings the link back."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, context, document, prefs  # noqa: E402
from incad.features import solid_mirror  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def zmax(body):
    return round(body.Shape.BoundBox.ZMax, 6)


def labels(kind):
    view = s()._mdi().viewport()
    menu = s()._show_marking_menu(kind, view.mapToGlobal(view.rect().center()))
    out = menu.list_labels() if menu is not None else []
    try:
        menu.close()
    except (AttributeError, RuntimeError):
        pass
    harness.pump(100)
    return out


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(doc())
    sk = util.add_rect_sketch(body, 20, 10, "BlockSk")
    body.Tip = util.add_pad(body, sk, 10, "Block")
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["body"], ST["pad"] = body.Name, body.Tip.Name


def test_1_select_mirror_solid_pick_the_plane():
    body = doc().getObject(ST["body"])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, body.Name)
    before = {b.Name for b in document.bodies(doc())}
    r = commands.REGISTRY.run("feature.mirror_solid")
    harness.pump(1000)
    assert r.ok and dialog() is not None, r.error
    assert dialog().values()["solid"] == body.Name, dialog().values()
    assert dialog().active_pick() == "plane", dialog().active_pick()  # waits for the mirror plane
    yz = [o for o in body.Origin.OriginFeatures if o.Role == "YZ_Plane"][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, yz.Name)
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    assert dialog() is None
    new = [b for b in document.bodies(doc()) if b.Name not in before]
    assert len(new) == 1, new
    copy = new[0]
    assert solid_mirror.claims(copy.Tip), copy.Tip
    bb = copy.Shape.BoundBox
    assert (round(bb.XMin, 6), round(bb.XMax, 6)) == (-20, 0), bb
    assert copy.Visibility and copy.Tip.Visibility
    from incad.core import nodes, tree
    rows = [n.name for _d, n in nodes.flatten(tree.build(doc()))]
    assert copy.Tip.Name in rows, rows  # its row in the part's history
    ST["copy"], ST["f"] = copy.Name, copy.Tip.Name


def test_2_the_copy_follows():
    pad = doc().getObject(ST["pad"])
    pad.Length = 14
    doc().recompute()
    harness.pump(300)
    assert zmax(doc().getObject(ST["copy"])) == 14


def test_3_break_mirror_link_only_on_a_mirror_row():
    context.set_target(ST["pad"])
    assert "Break Mirror Link" not in labels("browser")
    context.set_target(ST["f"])
    assert "Break Mirror Link" in labels("browser")
    context.set_target(ST["copy"])
    assert "Break Mirror Link" in labels("solid")  # its Solid's row too
    context.set_target(ST["f"])
    r = commands.REGISTRY.run("browser.break_mirror")
    harness.pump(500)
    assert r.ok, r.error
    pad = doc().getObject(ST["pad"])
    pad.Length = 18
    doc().recompute()
    harness.pump(300)
    assert zmax(doc().getObject(ST["copy"])) == 14  # stays as it was
    context.set_target(ST["f"])
    assert "Break Mirror Link" not in labels("browser")


def test_4_undo_links_it_again():
    commands.REGISTRY.run("edit.undo")
    harness.pump(500)
    f = doc().getObject(ST["f"])
    assert solid_mirror.claims(f), getattr(f, solid_mirror.MARK, None)
    doc().recompute()
    assert zmax(doc().getObject(ST["copy"])) == 18


def test_5_join_into_itself():
    """The user: a half mirrored into itself (Boolean-like Join). Result ▸ Join: no new Solid, the part made whole."""
    body = doc().getObject(ST["body"])
    before = len(document.bodies(doc()))
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, body.Name)
    r = commands.REGISTRY.run("feature.mirror_solid")
    harness.pump(1000)
    assert r.ok and dialog() is not None, r.error
    dialog().field("result").button("join").click()
    harness.pump(600)
    assert dialog().values()["side"] == "whole"  # the user: a choice of side for a part crossing the plane
    dialog().field("side").button("back").click()
    harness.pump(400)
    dialog().field("side").button("whole").click()
    harness.pump(600)
    face = [i + 1 for i, fc in enumerate(body.Tip.Shape.Faces)
            if fc.Surface.TypeId == "Part::GeomPlane" and abs(fc.CenterOfMass.x - 20) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, body.Name, "%s.Face%d" % (body.Tip.Name, face))
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    assert dialog() is None
    assert len(document.bodies(doc())) == before
    bb = body.Shape.BoundBox
    assert (round(bb.XMin, 6), round(bb.XMax, 6)) == (0, 40), bb
    assert len(body.Shape.Solids) == 1
    assert body.Tip.Visibility


def test_6_boolean_with_the_mirrored_copy():
    """The user's screen: Boolean, base Solid1, tool its mirrored Solid2 -> 'Solid2 already depends on Solid1'. Now
    the copy follows Solid1 up to the step before the Boolean, and the Boolean is made."""
    body, copy = doc().getObject(ST["body"]), doc().getObject(ST["copy"])
    assert solid_mirror.claims(copy.Tip)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, body.Name)
    Gui.Selection.addSelection(doc().Name, copy.Name)
    r = commands.REGISTRY.run("feature.combine")
    harness.pump(1500)
    assert r.ok and dialog() is not None, r.error
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    assert dialog() is None
    assert "Invalid" not in body.Tip.State, body.Tip.getStatusString()
    assert copy.Tip.Source.getParentGeoFeatureGroup() is body  # a step of Solid1 now, not Solid1 itself


def test_9_cleanup():
    context.set_target(None)
    App.closeDocument(doc().Name)
    harness.pump(300)


harness.run([test_0_setup, test_1_select_mirror_solid_pick_the_plane, test_2_the_copy_follows,
             test_3_break_mirror_link_only_on_a_mirror_row, test_4_undo_links_it_again, test_5_join_into_itself,
             test_6_boolean_with_the_mirrored_copy, test_9_cleanup])
