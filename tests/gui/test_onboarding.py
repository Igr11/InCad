import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import marking_layout, shell, sketch_session  # noqa: E402


def s():
    return shell.instance()


def view_size():
    cam = Gui.ActiveDocument.ActiveView.getCameraNode()
    if isinstance(cam, coin.SoOrthographicCamera):
        return cam.height.getValue()
    return 2 * cam.focalDistance.getValue()


def test_0_new_part_starts_near_the_origin():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    assert 20 < view_size() < 1000, view_size()  # the origin in view: not a few mm, not kilometres


def test_1_plane_panel_picks_a_plane():
    commands.REGISTRY.run("sketch.start")
    harness.pump(800)
    panel = s().plane_panel
    assert panel is not None and panel.isVisible()
    assert 20 < view_size() < 1000, view_size()
    panel.button("XZ_Plane").click()
    harness.pump(1200)
    sk = s().sketch_session().editing() if callable(getattr(s(), "sketch_session", None)) else s().sketches.editing()
    assert sk is not None
    assert sk.AttachmentSupport[0][0].Role == "XZ_Plane", sk.AttachmentSupport
    assert not s().plane_panel.isVisible()


def test_2_look_at_faces_the_sketch_while_sketching():
    view = Gui.ActiveDocument.ActiveView
    view.viewIsometric()
    harness.pump(300)
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("view.look_at")
    harness.pump(1500)
    d = view.getViewDirection()
    assert abs(abs(d.y) - 1) < 1e-3, d  # looking along the XZ plane's normal
    assert "view.look_at" in marking_layout.LAYOUT["sketch"].values() or \
        "view.look_at" in marking_layout.LAYOUT["sketch"]["list"]


def test_3_double_click_a_plane_in_the_browser_starts_a_sketch():
    from incad.core import context
    from incad.ui import marking_layout
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    body = document.primary_body(App.ActiveDocument)
    yz = [o for o in body.Origin.OriginFeatures if o.Role == "YZ_Plane"][0]
    s().browser.featureActivated.emit(yz.Name)
    harness.pump(1200)
    sk = s().sketches.editing()
    assert sk is not None and sk.AttachmentSupport[0][0] is yz, sk and sk.AttachmentSupport
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    browser = marking_layout.LAYOUT["browser"]
    assert "sketch.start" in list(browser.values()) + browser["list"]
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    context.set_target(xy.Name)
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.start")
    harness.pump(1200)
    sk = s().sketches.editing()
    assert sk is not None and sk.AttachmentSupport[0][0] is xy, sk and sk.AttachmentSupport
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)


def plane_on_screen(role):
    """(fraction of the view height the plane covers, all its corners inside the view) while picking."""
    view = Gui.ActiveDocument.ActiveView
    body = document.primary_body(App.ActiveDocument)
    plane = [o for o in body.Origin.OriginFeatures if o.Role == role][0]
    bb = sketch_session.screen_box(view, [plane.ViewObject])
    w, h = view.getSize()
    pts = [view.getPointOnViewport(App.Vector(x, y, z))
           for x in (bb.XMin, bb.XMax) for y in (bb.YMin, bb.YMax) for z in (bb.ZMin, bb.ZMax)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    inside = all(0 <= x <= w for x in xs) and all(0 <= y <= h for y in ys)
    return max(max(xs) - min(xs), max(ys) - min(ys)) / float(h), inside


def test_4_origin_planes_fill_the_view_while_picking():
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    commands.REGISTRY.run("sketch.start")
    harness.pump(800)
    w, h = Gui.ActiveDocument.ActiveView.getSize()
    cx, cy = Gui.ActiveDocument.ActiveView.getPointOnViewport(App.Vector(0, 0, 0))
    assert abs(cx - w / 2.0) < 3 and abs(cy - h / 2.0) < 3, (cx, cy, w, h)  # the origin in the middle
    size, inside = plane_on_screen("XY_Plane")
    assert inside and size > 0.25, (size, inside)  # big enough to see and click, not a speck
    s().sketches.cancel_pick()
    harness.pump(300)
    assert App.ParamGet(sketch_session._VIEW).GetFloat("DatumScale", -1.0) == -1.0  # user's setting back
    doc = App.ActiveDocument
    box = document.primary_body(doc).newObject("PartDesign::AdditiveBox", "Box")
    box.Length = box.Width = box.Height = 80
    doc.recompute()
    view = Gui.ActiveDocument.ActiveView
    cam = view.getCameraNode()
    cam.position.setValue(cam.position.getValue() + coin.SbVec3f(3000, 0, 0))  # looking somewhere else
    harness.pump(300)
    commands.REGISTRY.run("sketch.start")
    harness.pump(800)
    w, h = view.getSize()
    cx, cy = view.getPointOnViewport(App.Vector(0, 0, 0))
    assert abs(cx - w / 2.0) < 3 and abs(cy - h / 2.0) < 3, (cx, cy, w, h)  # the origin in the middle
    for role in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
        size, inside = plane_on_screen(role)
        assert inside and size > 0.1, (role, size, inside)
        plane = [o for o in document.primary_body(doc).Origin.OriginFeatures if o.Role == role][0]
        reach = sketch_session.screen_box(view, [plane.ViewObject])
        assert max(reach.XMax, reach.YMax, reach.ZMax) > 80, (role, reach)  # sticks out of the solid
    s().sketches.cancel_pick()
    harness.pump(300)


harness.run([test_0_new_part_starts_near_the_origin, test_1_plane_panel_picks_a_plane,
             test_2_look_at_faces_the_sketch_while_sketching,
             test_3_double_click_a_plane_in_the_browser_starts_a_sketch,
             test_4_origin_planes_fill_the_view_while_picking])
