import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import marking_layout, shell  # noqa: E402


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


harness.run([test_0_new_part_starts_near_the_origin, test_1_plane_panel_picks_a_plane,
             test_2_look_at_faces_the_sketch_while_sketching])
