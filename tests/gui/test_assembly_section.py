"""View ▸ Section in an assembly (the user: "a section in the assembly, the cut of every part the plane goes through"):
a plate with a hole and a shaft standing in it, cut by XZ through both: each component gets its cut face in its own
colour, hatched at its own angle; a part the plane misses gets none; the slider moves the cut; Off removes it all."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import appearance, commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}
RED, BLUE = (0.85, 0.15, 0.13), (0.15, 0.45, 0.85)


def s():
    return shell.instance()


def circle_sketch(body, r, name, at=V(0, 0, 0)):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(at, V(0, 0, 1), r))
    return sk


def save(folder, name, build, color):
    doc = util.new_doc(name)
    body = document.make_part(doc)
    build(body)
    doc.recompute()
    appearance.set_record(body, {"color": list(color)})
    appearance.apply(body, force=True)
    path = os.path.join(folder, name + ".FCStd")
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    return path


def plate(body):  # 40 x 30 x 10, a hole of 8 at its middle (20, 15)
    util.add_pad(body, util.add_rect_sketch(body, 40, 30, "S"), 10, "Pad")
    hole = body.newObject("PartDesign::Pocket", "Hole")
    hole.Profile = circle_sketch(body, 4, "H", V(20, 15, 0))
    hole.Type = "ThroughAll"
    hole.Midplane = True
    body.Tip = hole


def shaft(body):  # a rod of 8, 30 long
    body.Tip = util.add_pad(body, circle_sketch(body, 4, "C"), 30, "Shaft")


def caps():
    d = s()._section_display
    return [] if d is None else [disp._coords.point.getNum() for disp in d[0]]


def test_0_assembly():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_asm_section_")
    p = save(ST["dir"], "Plate", plate, RED)
    q = save(ST["dir"], "Shaft", shaft, BLUE)
    doc = actions.new_assembly("mm")
    doc.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    a = s().assembly_place(p)
    b = s().assembly_place(q)
    harness.pump(600)
    a.Placement = App.Placement(V(-20, -15, 0), App.Rotation())  # the hole on the Z axis
    b.Placement = App.Placement(V(0, 0, -10), App.Rotation())    # the shaft in it
    doc.recompute()
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1000)
    ST.update(asm=doc.Name, a=a.Name, b=b.Name)


def test_1_xz_cuts_both_parts():
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("view.section")
    harness.pump(1200)
    assert getattr(r, "ok", True), getattr(r, "error", "")
    assert actions.section_on(), "no section in the assembly"
    d = s()._section_display
    assert len(d[0]) == 2, ("one cut per component", len(d[0]))
    assert all(n > 0 for n in caps()), ("each part has its cut face", caps())
    colours = sorted(tuple(round(c, 2) for c in disp._material.diffuseColor[0].getValue()) for disp in d[0])
    want = sorted(tuple(round(c * 0.85, 2) for c in col) for col in (RED, BLUE))
    assert colours == want, ("each in its part's colour", colours, want)
    hatches = [disp._hatch_coords.point.getNum() for disp in d[0]]
    assert all(h > 0 for h in hatches), ("both hatched", hatches)
    if os.environ.get("INNCAD_SHOT"):
        Gui.ActiveDocument.ActiveView.saveImage(os.environ["INNCAD_SHOT"], 1200, 900, "Current")


def test_2_the_slider_past_the_plate_cuts_only_the_shaft():
    """3 mm along the normal: inside the shaft (radius 4) and the plate; 8 mm: past the shaft, still in the plate
    (half width 15): only the plate is cut."""
    s()._section_changed(3.0, False)  # 3 mm along the normal: inside the shaft (radius 4) and the plate
    harness.pump(600)
    assert all(n > 0 for n in caps()), caps()
    s()._section_changed(8.0, False)  # past the shaft (radius 4), still in the plate (half width 15)
    harness.pump(600)
    n = caps()
    assert n[0] > 0 and n[1] == 0 or n[1] > 0 and n[0] == 0, ("only the plate is cut there", n)


def test_3_off_removes_it():
    nodes = [disp.node for disp in s()._section_display[0]]
    s().stop_section(keep_cut=False)
    harness.pump(400)
    assert not actions.section_on()
    scene = Gui.ActiveDocument.ActiveView.getSceneGraph()
    assert all(scene.findChild(n) == -1 for n in nodes), "a cut face left on the view"


def test_9_cleanup():
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_assembly, test_1_xz_cuts_both_parts, test_2_the_slider_past_the_plate_cuts_only_the_shaft,
             test_3_off_removes_it, test_9_cleanup])
