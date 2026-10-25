"""Tools ▸ Material ▸ Appearance in the real window (the user: "rendering, or at least colour"; "Hide Edges"): with
nothing picked every Solid gets the colour and finish — drawn so, seen in the view —, Cancel puts the part back, a
picked face gets its own colour and keeps it when a longer Extrude moves it, Hide Edges draws the Solid without its
lines, Reset goes back to the material's colour, and each OK is one undo step."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import appearance, commands, document, prefs  # noqa: E402
from incad.qt import QtGui  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}
RED, GREEN, BLUE = (0.85, 0.15, 0.13), (0.25, 0.65, 0.25), (0.15, 0.45, 0.85)


def body():
    return document.primary_body(App.ActiveDocument)


def drawn():
    """What the view really draws for the Solid ('NormalRoot' = with edges, 'FlatRoot' = without): a draw style
    over the whole view wins over the Solid's DisplayMode."""
    from pivy import coin
    sa = coin.SoSearchAction()
    sa.setName(coin.SbName("ModeSwitch"))
    sa.apply(body().Tip.ViewObject.RootNode)
    switch = sa.getPath().getTail()
    return switch.getChild(switch.whichChild.getValue()).getName().getString()


def colors():
    return [tuple(round(c, 2) for c in m.DiffuseColor[:3]) for m in body().ViewObject.ShapeAppearance]


def near(a, b, tol=0.03):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def top_face():
    faces = body().Shape.Faces
    return max(range(len(faces)), key=lambda i: faces[i].CenterOfMass.z)


def centre_pixel():
    """The view's middle as drawn (the part fills it): what the user sees there."""
    view = Gui.ActiveDocument.ActiveView
    path = os.path.join(tempfile.gettempdir(), "incad_appearance_%d.png" % os.getpid())
    view.saveImage(path, 200, 200, "Current")
    c = QtGui.QImage(path).pixelColor(100, 100)
    os.remove(path)
    return c.redF(), c.greenF(), c.blueF()


def pick(color=None, finish=None, hide=None, reset=False, ok=True, during=None, texture=None):
    def choose(dlg):
        if reset:
            dlg.reset_button.click()
        if color is not None:
            dlg.set_color(color)
        if finish is not None:
            dlg.set_finish(finish)
        if hide is not None:
            dlg.edges.setChecked(hide)
        if texture is not None:
            dlg.set_texture(texture)
        harness.pump(300)
        if during is not None:
            during()
        return ok
    r = actions.appearance(choose)
    harness.pump(500)
    return r


def test_0_plate():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    pad = util.add_pad(body(), util.add_rect_sketch(body(), 40, 20, "Plate"), 6)
    body().Tip = pad
    App.ActiveDocument.recompute()
    Gui.ActiveDocument.ActiveView.viewTop()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["pad"] = pad.Name
    assert commands.REGISTRY.has("tools.appearance")


def test_1_nothing_picked_colours_every_solid():
    Gui.Selection.clearSelection()
    n = len(App.ActiveDocument.UndoNames)
    pick(RED, "Metal")
    rec = appearance.record(body())
    assert rec["color"] == [round(c, 4) for c in RED] and rec["finish"] == "Metal", rec
    assert len(colors()) == 1 and near(colors()[0], tuple(c * 0.75 for c in RED)), colors()
    r, g, b = centre_pixel()
    assert r > g + 0.15 and r > b + 0.15, ("the part is drawn red", (r, g, b))
    assert len(App.ActiveDocument.UndoNames) == n + 1 and App.ActiveDocument.UndoNames[0] == "Appearance", \
        App.ActiveDocument.UndoNames


def test_2_cancel_puts_it_back():
    seen = []
    pick(BLUE, "Glossy", ok=False, during=lambda: seen.append(colors()))
    assert seen and near(seen[0][0], BLUE), ("shown while choosing", seen)
    assert near(colors()[0], tuple(c * 0.75 for c in RED)), ("back as it was", colors())
    assert appearance.record(body())["color"] == [round(c, 4) for c in RED]


def test_3_a_picked_face_gets_its_own():
    Gui.Selection.clearSelection()
    i = top_face()
    Gui.Selection.addSelection(App.ActiveDocument.Name, body().Name, "%s.Face%d" % (ST["pad"], i + 1))
    harness.pump(300)
    pick(GREEN, "Glossy")
    cs = colors()
    assert len(cs) == len(body().Shape.Faces), cs
    assert near(cs[i], GREEN) and all(near(c, tuple(x * 0.75 for x in RED)) for k, c in enumerate(cs) if k != i), cs
    r, g, b = centre_pixel()  # seen from the top: the green face
    assert g > r + 0.15, ("the top face is drawn green", (r, g, b))
    Gui.Selection.clearSelection()


def test_4_the_face_keeps_it_when_it_moves():
    pad = App.ActiveDocument.getObject(ST["pad"])
    pad.Length = 10
    App.ActiveDocument.recompute()
    harness.pump(800)
    i = top_face()
    assert abs(body().Shape.Faces[i].CenterOfMass.z - 10) < 1e-6
    assert near(colors()[i], GREEN), colors()


def test_5_hide_edges():
    commands.REGISTRY.run("view.style_shaded")  # the user's report: after the Shaded button the edges stayed
    harness.pump(400)
    assert body().ViewObject.DisplayMode == "Flat Lines"
    assert drawn() == "NormalRoot", drawn()
    pick(hide=True)
    assert body().ViewObject.DisplayMode == "Shaded", body().ViewObject.DisplayMode
    assert drawn() == "FlatRoot", ("edges still drawn", drawn())
    assert appearance.record(body())["edges"] is False
    assert near(colors()[top_face()], GREEN), ("the colours stay", colors())
    App.ActiveDocument.undo()
    harness.pump(600)
    assert body().ViewObject.DisplayMode == "Flat Lines"
    App.ActiveDocument.redo()
    harness.pump(600)
    assert body().ViewObject.DisplayMode == "Shaded"


def test_5b_a_texture_over_the_colours():
    from incad.core import textures
    pick(texture="Wood")
    assert appearance.record(body())["texture"] == "Wood"
    assert textures.name_on(body()) == "Wood"
    assert near(colors()[top_face()], GREEN), ("the colours stay under it", colors())
    App.ActiveDocument.undo()
    harness.pump(800)
    assert textures.name_on(body()) == "None", "undone: the texture goes"
    App.ActiveDocument.redo()
    harness.pump(800)
    assert textures.name_on(body()) == "Wood"


def test_6_reset_and_undo():
    pick(reset=True)
    assert appearance.record(body()) is None
    assert len(colors()) == 1 and near(colors()[0], appearance.material_color(App.ActiveDocument)), colors()
    assert body().ViewObject.DisplayMode == "Flat Lines"
    from incad.core import textures
    assert textures.name_on(body()) == "None"
    App.ActiveDocument.undo()
    harness.pump(800)
    assert appearance.record(body())["color"] == [round(c, 4) for c in RED]
    assert near(colors()[top_face()], GREEN), colors()
    assert textures.name_on(body()) == "Wood"


def test_7_saved_and_opened_again():
    path = os.path.join(tempfile.mkdtemp(prefix="incad_appearance_"), "Plate.FCStd")
    App.ActiveDocument.saveAs(path)
    name = App.ActiveDocument.Name
    App.closeDocument(name)
    harness.pump(500)
    App.openDocument(path)
    harness.pump(1500)
    assert appearance.record(body())["color"] == [round(c, 4) for c in RED]
    assert near(colors()[top_face()], GREEN), colors()
    assert body().ViewObject.DisplayMode == "Shaded"
    from incad.core import textures
    assert textures.name_on(body()) == "Wood", "the texture is put back on a file opened again"


def test_8_an_assembly_shows_the_part_as_coloured():
    from incad.ui import shell
    path = App.ActiveDocument.FileName
    App.ActiveDocument.save()
    d = actions.new_assembly("mm")
    harness.pump(800)
    shell.instance().assembly_place(path)
    harness.pump(1500)
    Gui.ActiveDocument.ActiveView.viewTop()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(800)
    r, g, b = centre_pixel()
    assert g > r + 0.1 and g > b, ("the component's top face is green there too", (r, g, b))


def test_9_cleanup():
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_plate, test_1_nothing_picked_colours_every_solid, test_2_cancel_puts_it_back,
             test_3_a_picked_face_gets_its_own, test_4_the_face_keeps_it_when_it_moves, test_5_hide_edges,
             test_5b_a_texture_over_the_colours, test_6_reset_and_undo, test_7_saved_and_opened_again,
             test_8_an_assembly_shows_the_part_as_coloured, test_9_cleanup])
