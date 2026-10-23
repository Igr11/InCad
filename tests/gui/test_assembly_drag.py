"""Assembly: DOF on the rows, dragging a part along its own freedoms (FreeCAD's native drag), DOF glyphs."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, prefs, safe, tree  # noqa: E402
from incad.features import constraints as C  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["asm"])


def obj(key):
    return doc().getObject(ST[key])


def rows():
    return {n.name: n.detail for n in tree.build(doc())[0].children if n.kind == "component"}


def fz(link, z):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if abs(f.CenterOfMass.z - z) < 1e-6][0])


def constrain(kind, first, second):
    r = safe.run_safely(kind.TITLE, lambda: kind.create(doc(), None, None, dict(kind.defaults(doc(), None),
                                                                               first=first, second=second)), doc())
    assert r.ok, r.error
    s().schedule_refresh()
    harness.pump(1200)
    return r.value


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_drag_")
    for name, w, h, t in (("Plate", 60, 40, 10), ("Mid", 20, 20, 10), ("Top", 8, 8, 6)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    d = actions.new_assembly("mm")
    d.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = d.Name
    for key, name in (("p", "Plate"), ("m", "Mid"), ("t", "Top")):
        ST[key] = s().assembly_place(ST[name]).Name
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1500)


def test_1_rows_show_dof():
    assert rows() == {ST["p"]: "grounded", ST["m"]: "DOF 6", ST["t"]: "DOF 6"}, rows()
    constrain(C.MATE, fz(obj("m"), 10), fz(obj("t"), 0))  # Top on the free Mid
    assert rows()[ST["t"]] == "DOF 3", rows()


def test_2_undo_of_a_constraint_recounts():
    commands.REGISTRY.run("edit.undo")
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 6", rows()
    commands.REGISTRY.run("edit.redo")
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 3", rows()


def test_3_count_does_not_mark_the_file_modified():
    App.setActiveDocument(ST["asm"])
    gdoc = Gui.getDocument(ST["asm"])
    Gui.ActiveDocument = gdoc
    Gui.runCommand("Std_Save")  # as from the window (App's save leaves the Gui flag set)
    harness.pump(500)
    assert not gdoc.Modified, "saved"
    from incad.core import dof
    dof._CACHE.clear()
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 3", rows()  # it did recount
    assert not gdoc.Modified, "a count is no change to save"


def view():
    return Gui.getDocument(ST["asm"]).ActiveView


def viewport():
    return view().graphicsView().viewport()


def screen_of(point):
    vp = viewport()
    x, y = view().getPointOnViewport(point)
    dpr = vp.devicePixelRatioF()
    return QtCore.QPointF(x / dpr, vp.height() - y / dpr)


def send(kind, pos, button, buttons):
    vp = viewport()
    glob = QtCore.QPointF(vp.mapToGlobal(pos.toPoint()))
    QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, pos, glob, button, buttons, QtCore.Qt.NoModifier))


def drag(start, dx, dy, steps=12):
    L = QtCore.Qt.LeftButton
    send(QtCore.QEvent.MouseMove, start, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
    harness.pump(300)
    send(QtCore.QEvent.MouseButtonPress, start, L, L)
    harness.pump(100)
    for i in range(1, steps + 1):
        send(QtCore.QEvent.MouseMove, QtCore.QPointF(start.x() + dx * i / steps, start.y() + dy * i / steps),
             QtCore.Qt.NoButton, L)
        harness.pump(60)
    send(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(start.x() + dx, start.y() + dy), L, QtCore.Qt.NoButton)
    harness.pump(800)


def top_of(key):
    bb = obj(key).Shape.BoundBox
    return screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))


def same(a, b):
    return a.isSame(b, 1e-7)


def test_4_drag_moves_only_along_its_own_dof():
    m, t = obj("m"), obj("t")
    bm, bt = App.Placement(m.Placement), App.Placement(t.Placement)
    n0 = len(doc().UndoNames)
    drag(top_of("t"), 70, -60)
    assert not same(t.Placement, bt), "Top moved"
    assert same(m.Placement, bm), "the free Mid it is Mated to stays put"
    assert abs(t.Shape.BoundBox.ZMin - m.Shape.BoundBox.ZMax) < 1e-6, "still on Mid's face"
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Move part", doc().UndoNames[:3]
    assert not [j for j in assembly.joints(doc()) if getattr(j, "ObjectToGround", None) is m], "no ground left"
    assert Gui.getDocument(ST["asm"]).getInEdit() is None and not safe.drag_edit()
    assert "Moved Top" in s().status.texts()["message"], s().status.texts()
    mate = [j for j in assembly.joints(doc()) if not hasattr(j, "ObjectToGround")][0]
    assert mate.ViewObject.Proxy.switch_JCS1.pick.style.getValue() == coin.SoPickStyle.SHAPE_ON_TOP, \
        "its markers are pickable again"
    ST["moved_from"] = bt


def test_5_undo_and_redo_of_a_drag():
    t = obj("t")
    moved_to = App.Placement(t.Placement)
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    assert same(t.Placement, ST["moved_from"]), t.Placement
    commands.REGISTRY.run("edit.redo")
    harness.pump(800)
    assert same(t.Placement, moved_to)
    assert len([j for j in assembly.joints(doc()) if hasattr(j, "ObjectToGround")]) == 1, "only Plate's ground"


def test_5b_a_lost_release_does_not_block_the_next_drag():
    m, t = obj("m"), obj("t")
    bm, bt = App.Placement(m.Placement), App.Placement(t.Placement)
    n0 = len(doc().UndoNames)
    pos = top_of("t")
    assert s().asm_drag.begin(view(), viewport(), pos.x(), pos.y()), "a drag began"  # its drag_end never comes
    assert s().asm_drag.active() and safe.drag_edit()
    drag(top_of("t"), -50, 40)  # the next drag finishes the stale one first
    assert not s().asm_drag.active()
    assert not same(t.Placement, bt), "the new drag moved Top"
    assert same(m.Placement, bm), "Mid stays put"
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Move part", doc().UndoNames[:3]
    assert len([j for j in assembly.joints(doc()) if hasattr(j, "ObjectToGround")]) == 1, "only Plate's ground"
    assert Gui.getDocument(ST["asm"]).getInEdit() is None and not safe.drag_edit()


def test_6_grounded_part_stays_and_says_so():
    p = obj("p")
    bp = App.Placement(p.Placement)
    bb = p.Shape.BoundBox
    drag(screen_of(App.Vector(bb.XMin + 3, bb.YMin + 3, bb.ZMax)), -50, 20)
    assert same(p.Placement, bp)
    assert "Plate is grounded" in s().status.texts()["message"], s().status.texts()


def test_7_a_click_selects_without_edit():
    Gui.Selection.clearSelection()
    pos = top_of("t")
    L = QtCore.Qt.LeftButton
    send(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
    harness.pump(300)
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    harness.pump(60)
    send(QtCore.QEvent.MouseButtonRelease, pos, L, QtCore.Qt.NoButton)
    harness.pump(600)
    assert Gui.Selection.getSelectionEx("", 0), "the click selected"
    assert Gui.getDocument(ST["asm"]).getInEdit() is None
    Gui.Selection.clearSelection()


def test_8_fully_constrained_part_is_not_dragged():
    p, m = obj("p"), obj("m")
    def fx(link, x):
        return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                          if abs(f.CenterOfMass.x - x) < 1e-6][0])
    def fy(link, y):
        return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                          if abs(f.CenterOfMass.y - y) < 1e-6][0])
    constrain(C.MATE, fz(p, 10), fz(m, 0))
    constrain(C.FLUSH, fx(p, 0), fx(m, 0))
    constrain(C.FLUSH, fy(p, 0), fy(m, 0))
    assert rows()[ST["m"]] == "DOF 0", rows()
    bm = App.Placement(m.Placement)
    n0 = len(doc().UndoNames)
    bb = m.Shape.BoundBox
    drag(screen_of(App.Vector(bb.XMax - 2, bb.YMax - 2, bb.ZMax)), 60, 40)
    assert same(m.Placement, bm)
    assert len(doc().UndoNames) == n0, "no empty step"
    assert "Mid is fully constrained" in s().status.texts()["message"], s().status.texts()


def test_8b_no_drag_while_a_constraint_dialog_is_open():
    t = obj("t")
    bt = App.Placement(t.Placement)
    commands.REGISTRY.run("constrain.flush")
    harness.pump(800)
    assert s().feature_session is not None
    drag(top_of("t"), 60, 30)
    assert same(t.Placement, bt), "the part does not move while the dialog is open"
    s()._close_feature_session(cancel=True)
    harness.pump(800)


def temp_grounds():
    return len([j for j in assembly.joints(doc()) if hasattr(j, "ObjectToGround")])


def test_8d_a_command_ends_a_drag_first():
    import re
    import zipfile
    t = obj("t")
    bt = App.Placement(t.Placement)
    pos = top_of("t")
    assert s().asm_drag.begin(view(), viewport(), pos.x(), pos.y()), "a drag began"
    assert temp_grounds() > 1, "the other free parts are held while it drags"
    r = commands.REGISTRY.run("file.save")
    harness.pump(500)
    assert r.ok, r.error
    assert not s().asm_drag.active() and not safe.drag_edit(), "the command ended the drag first"
    assert temp_grounds() == 1, "only Plate's ground"
    assert same(t.Placement, bt)
    assert Gui.getDocument(ST["asm"]).getInEdit() is None
    with zipfile.ZipFile(doc().FileName) as z:
        xml = z.read("Document.xml").decode("utf-8")
    saved = re.findall(r'<Object type="[^"]*" name="(GroundedJoint\d*)"', xml)
    assert len(saved) == 1, ("the saved file has only the real ground", saved)


def test_8e_a_failed_edit_is_no_drag():
    t = obj("t")
    bt = App.Placement(t.Placement)
    n0 = len(doc().UndoNames)
    real = Gui.getDocument

    class Refusing:
        def __init__(self, g):
            self._g = g

        def setEdit(self, *a):
            return False  # FreeCAD said no

        def __getattr__(self, name):
            return getattr(self._g, name)

    pos = top_of("t")
    Gui.getDocument = lambda name: Refusing(real(name))
    try:
        began = s().asm_drag.begin(view(), viewport(), pos.x(), pos.y())
    finally:
        Gui.getDocument = real
    harness.pump(300)
    assert not began and not s().asm_drag.active() and not safe.drag_edit()
    assert "Can't drag Top" in s().status.texts()["message"], s().status.texts()
    assert temp_grounds() == 1 and same(t.Placement, bt) and len(doc().UndoNames) == n0


def test_9e_dof_view_with_an_empty_part():
    from headless import util
    from incad.core import document, dof
    d = util.new_doc("Empty")
    document.make_part(d)
    d.recompute()
    path = os.path.join(ST["dir"], "Empty.FCStd")
    d.saveAs(path)
    App.closeDocument(d.Name)
    App.setActiveDocument(ST["asm"])
    Gui.ActiveDocument = Gui.getDocument(ST["asm"])
    ST["e"] = s().assembly_place(path).Name
    s().schedule_refresh()
    harness.pump(1500)
    assert (dof.last(doc()) or {}).get(ST["e"]) is not None, "the empty part is counted"
    s().status.clear_message()
    commands.REGISTRY.run("view.dof")
    harness.pump(800)
    s().dof_display_changed()  # no exception
    s().schedule_refresh()
    harness.pump(800)
    assert "could not update" not in s().status.texts()["message"], s().status.texts()
    assert glyph_parts() == 1 and ST["t"] in s()._dof_glyphs.parts, "Top's glyph is drawn"
    commands.REGISTRY.run("view.dof")
    harness.pump(500)
    assert glyph_parts() == 0


def test_8f_no_drag_while_a_sketch_is_open_in_another_tab():
    t = obj("t")
    bt = App.Placement(t.Placement)
    s().open_component(obj("p"))
    harness.pump(1000)
    plate = App.ActiveDocument
    assert plate.Name != ST["asm"]
    s().sketches.edit(plate.getObject("S"))  # InCad's route, never a raw setEdit on a sketch
    harness.pump(800)
    assert Gui.getDocument(plate.Name).getInEdit() is not None
    s()._back_to(doc())  # the assembly's tab
    harness.pump(800)
    assert App.ActiveDocument.Name == ST["asm"]
    assert Gui.getDocument(plate.Name).getInEdit() is not None, "the sketch stays open in its own tab"
    n0 = len(doc().UndoNames)
    pos = top_of("t")
    drag = s().asm_drag
    drag._component_at = lambda *a: (doc(), obj("t"))  # Top under the pointer (this checks the edit, not the pick)
    try:
        began = drag.begin(view(), viewport(), pos.x(), pos.y())
    finally:
        del drag._component_at
    harness.pump(300)
    in_edit = Gui.getDocument(plate.Name).getInEdit() is not None
    if began:
        s().asm_drag.finish(moved_ok=False)
    assert not began and in_edit and not s().asm_drag.active(), \
        ("no drag while another tab edits a sketch, the sketch still open", began, in_edit)
    assert same(t.Placement, bt) and len(doc().UndoNames) == n0 and temp_grounds() == 1
    s()._back_to(plate)
    harness.pump(500)
    s().sketches.finish()
    harness.pump(800)
    s()._back_to(doc())
    harness.pump(500)


def test_8c_closing_the_document_ends_a_drag():
    from incad.core import dof
    t = obj("t")
    bt = App.Placement(t.Placement)
    n0 = len(doc().UndoNames)
    pos = top_of("t")
    assert s().asm_drag.begin(view(), viewport(), pos.x(), pos.y()), "a drag began"
    shell._finish_open_tools()  # what ⌘W does before its Save dialog
    assert not s().asm_drag.active() and not safe.drag_edit()
    assert same(t.Placement, bt) and len(doc().UndoNames) == n0, "nothing moved, no step"
    assert len([j for j in assembly.joints(doc()) if hasattr(j, "ObjectToGround")]) == 1, "only Plate's ground"
    assert Gui.getDocument(ST["asm"]).getInEdit() is None
    commands.REGISTRY.run("view.dof")  # on for this document, with a tip
    harness.pump(500)
    s()._on_dof_hover(ST["t"])
    assert s()._dof_glyphs is not None and ST["asm"] in s()._dof_on
    pos = top_of("t")
    assert s().asm_drag.begin(view(), viewport(), pos.x(), pos.y()), "a drag began"
    App.closeDocument(ST["asm"])  # mid-drag: its release never comes
    assert s().asm_drag.link_name is None, "the close itself ended the drag"
    harness.pump(800)
    assert not s().asm_drag.active() and not safe.drag_edit() and not safe.edit_open()
    assert ST["asm"] not in s()._dof_on, "DOF view state of the closed file is gone"
    assert s()._dof_hover is None and ST["asm"] not in dof._CACHE
    assert s()._dof_glyphs is None or s()._dof_glyphs.doc_name != ST["asm"], "no glyphs of the closed file"


def glyph_parts():
    g = s()._dof_glyphs
    return 0 if g is None else g.count


def test_9a_view_button_draws_only_available_freedoms():
    from incad.core import dof
    s()._dof_linger = None  # the part dragged just before keeps its gizmo a while (the user): not this test's
    s().dof_display_changed()
    harness.pump(200)
    assert glyph_parts() == 0
    commands.REGISTRY.run("view.dof")
    harness.pump(800)
    free = [n for n, f in (dof.last(doc()) or {}).items() if f.n]
    assert glyph_parts() == len(free) and ST["t"] in free and ST["m"] not in free, (glyph_parts(), free)  # Mid is DOF 0
    lines, heads = s()._dof_glyphs.parts[ST["t"]]
    assert (lines, heads) == (3, 5), (lines, heads)  # Top on Mid: two slides (double arrows) and one turn
    first = s()._dof_glyphs.node.getChild(0)
    assert first.isOfType(coin.SoPickStyle.getClassTypeId()), "a pick style first under the glyphs"
    assert first.style.getValue() == coin.SoPickStyle.UNPICKABLE, "glyphs are never picked (the part under them is)"
    commands.REGISTRY.run("view.dof")
    harness.pump(500)
    assert glyph_parts() == 0


def test_9b_hover_tip_on_a_free_part_only():
    s()._on_dof_hover(ST["t"])
    harness.pump(300)
    assert glyph_parts() == 1 and s()._dof_glyphs.highlighted == [ST["t"]]
    s()._on_dof_hover(ST["m"])  # DOF 0: no tip
    harness.pump(300)
    assert glyph_parts() == 0
    s()._on_dof_hover(None)
    harness.pump(300)
    assert glyph_parts() == 0


def test_9c_hover_from_real_preselection():
    pos = top_of("t")
    send(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
    harness.pump(600)
    assert glyph_parts() == 1, glyph_parts()
    send(QtCore.QEvent.MouseMove, QtCore.QPointF(5, 5), QtCore.Qt.NoButton, QtCore.Qt.NoButton)  # empty corner
    harness.pump(600)
    assert glyph_parts() == 0, glyph_parts()


def glyph_rgb():
    g = s()._dof_glyphs
    for i in range(g.node.getNumChildren()):
        sep = g.node.getChild(i)
        if not sep.isOfType(coin.SoGroup.getClassTypeId()):
            continue
        for j in range(sep.getNumChildren()):
            c = sep.getChild(j)
            if c.getTypeId().getName().getString() == "BaseColor":
                return tuple(round(v, 3) for v in c.rgb[0].getValue())
    return None


def test_9d_glyphs_follow_the_theme():
    from incad.ui import theme as themes
    from incad.ui.dof_glyphs import _rgb
    commands.REGISTRY.run("view.dof")
    harness.pump(500)
    start = themes.current()
    want = lambda name: tuple(round(v, 3) for v in _rgb(themes.PALETTES[name]["marker_end"]))
    assert glyph_rgb() == want(start), (glyph_rgb(), start)
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(800)
    other = themes.current()
    assert other != start and glyph_rgb() == want(other), (glyph_rgb(), other)
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(800)
    assert themes.current() == start and glyph_rgb() == want(start)
    commands.REGISTRY.run("view.dof")
    harness.pump(500)
    assert glyph_parts() == 0


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


TESTS = [test_0_setup, test_1_rows_show_dof, test_2_undo_of_a_constraint_recounts,
         test_3_count_does_not_mark_the_file_modified, test_4_drag_moves_only_along_its_own_dof,
         test_5_undo_and_redo_of_a_drag, test_5b_a_lost_release_does_not_block_the_next_drag,
         test_6_grounded_part_stays_and_says_so, test_7_a_click_selects_without_edit,
         test_8_fully_constrained_part_is_not_dragged, test_8b_no_drag_while_a_constraint_dialog_is_open,
         test_8d_a_command_ends_a_drag_first, test_8e_a_failed_edit_is_no_drag,
         test_9a_view_button_draws_only_available_freedoms, test_9b_hover_tip_on_a_free_part_only,
         test_9c_hover_from_real_preselection, test_9d_glyphs_follow_the_theme,
         test_9e_dof_view_with_an_empty_part,  # adds a part without a solid
         test_8f_no_drag_while_a_sketch_is_open_in_another_tab,  # opens Plate in its own tab
         test_8c_closing_the_document_ends_a_drag]  # 8c closes the document
harness.run(TESTS + [test_9_cleanup])
