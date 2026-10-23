"""A picture imported for reference (the user: JPG for reference) and scaled by a known length (the user: "I measured
something, photographed it and said this length is so much; all the rest scales with it"): Import puts it on the XY
plane with a row of its own; Edit on it opens Scale / Transparency; two clicks on the picture and the real length scale it,
the first point staying where it is; OK keeps it."""
import os
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad import actions  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.ui.line3d_tool import viewport_of  # noqa: E402
from incad.core import commands, image_reference, prefs, tree  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui import dof_handles as dh  # noqa: E402

ST = {}


def s():
    return shell.instance()


def png(path, w, h):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\x00" + bytes((40 + (x * 200) // w) for x in range(w)) for _ in range(h))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def test_0_import_a_picture():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    path = os.path.join(tempfile.mkdtemp(), "photo.png")
    png(path, 400, 200)
    actions.insert_picture_at(path)
    harness.pump(1000)
    pics = [o for o in App.ActiveDocument.Objects if image_reference.is_picture(o)]
    assert len(pics) == 1, [o.TypeId for o in App.ActiveDocument.Objects]
    rows = {n.label: n.kind for n in tree.build(App.ActiveDocument)[0].children}
    assert rows.get("photo (image)") == "picture", rows
    ST["pic"] = pics[0].Name


def test_1_scale_by_a_known_length():
    doc = App.ActiveDocument
    pic = doc.getObject(ST["pic"])
    Gui.ActiveDocument.ActiveView.viewTop()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    s()._on_feature_activated(pic.Name)  # a double-click on its row
    harness.pump(1000)
    fs = s().feature_session
    assert fs is not None and fs.kind.TITLE == "Scale / Transparency", fs and fs.kind.TITLE
    d = fs.dialog
    ring = s()._overlay
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    first = pic.Placement.multVec(App.Vector(-25, 0, 0))  # u 0.25, v 0.5 on the 100 x 50 picture
    for p in (first, pic.Placement.multVec(App.Vector(25, 0, 0))):
        x, y = dh.screen(view, vp, p)
        ring.hover(view, vp, x, y)
        assert ring.press(view, vp, x, y), "the click missed the picture"
        ring.release()
        harness.pump(300)
    assert "2 points" in d.field("points").count.text(), d.field("points").count.text()
    assert "length" in d.error_text().lower(), d.error_text()  # the tip: type the real length
    d.set_values({"length": "120 mm"})
    d._emit()
    harness.pump(1200)
    assert abs(pic.XSize.Value - 240) < 0.5, pic.XSize
    assert (pic.Placement.multVec(App.Vector(-60, 0, 0)) - first).Length < 0.5, "the first point moved"
    if os.environ.get("INNCAD_SHOT"):
        d.grab().save(os.environ["INNCAD_SHOT"])
        Gui.SendMsgToActiveView("ViewFit")
        harness.pump(300)
        view.saveImage(os.environ["INNCAD_SHOT"].replace(".png", "_view.png"), 900, 600, "Current")
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    assert s().feature_session is None
    assert abs(pic.XSize.Value - 240) < 0.5 and abs(pic.YSize.Value - 120) < 0.5, (pic.XSize, pic.YSize)


def test_1b_a_line_made_horizontal_turns_the_image():
    """Two points on a slanting line, Line ▸ Horizontal: the image turns about the first point until that line lies
    along X (the user); the magnifying glass shows beside the pointer over the image."""
    doc = App.ActiveDocument
    pic = doc.getObject(ST["pic"])
    s()._on_feature_activated(pic.Name)
    harness.pump(1000)
    fs = s().feature_session
    d = fs.dialog
    ring = s()._overlay
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    from incad.features import picture_scale as k
    uv = [(0.3, 0.3), (0.7, 0.8)]  # slanting
    for u, v in uv:
        x, y = dh.screen(view, vp, pic.Placement.multVec(k.local(pic, u, v)))
        ring.hover(view, vp, x, y)
        assert ring._glass is not None and ring._glass.isVisible(), "no magnifying glass"
        assert ring.press(view, vp, x, y)
        ring.release()
        harness.pump(300)
    img = ring._glass._image
    c = img.pixelColor(img.width() // 2 - 30, img.height() // 2)  # inside the glass, beside the cross
    assert c.red() > 60, c.name()  # the grey image under the pointer, not black
    if os.environ.get("INNCAD_SHOT"):
        ring._glass.grab().save(os.environ["INNCAD_SHOT"].replace(".png", "_glass.png"))
    clicked = [(float(a), float(b)) for a, b, _ in (i.split() for i in d.values()["points"].split(";"))]
    first = pic.Placement.multVec(k.local(pic, *clicked[0]))  # where the first click landed, before the turn
    d.field("align").button("horizontal").click()
    harness.pump(1200)
    pts = [(float(a), float(b)) for a, b, _ in (i.split() for i in d.values()["points"].split(";"))]
    a, b = (pic.Placement.multVec(k.local(pic, u, v)) for u, v in pts)
    assert abs(a.y - b.y) < 0.05 * (b - a).Length and abs(a.z - b.z) < 1e-6, (a, b)  # along X now
    assert (a - first).Length < 1e-6, (a, first)  # the first point stayed
    if os.environ.get("INNCAD_SHOT"):
        d.grab().save(os.environ["INNCAD_SHOT"].replace(".png", "_level.png"))
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    assert s().feature_session is None
    assert ring._glass is None or not ring._glass.isVisible()


def test_2_picture_tab():
    """The Picture tab (the user: a tab of its own with several buttons): on XZ, a quarter turn, see-through, show /
    hide, and Scale / Transparency opening the dialog on the picture (its slider sets the transparency)."""
    doc = App.ActiveDocument
    pic = doc.getObject(ST["pic"])
    rb = s().ribbon
    tabs = [rb._tabs.tabText(i) for i in range(rb._tabs.count())]
    assert "Image" in tabs, tabs
    for cid in ("picture.insert", "picture.scale", "picture.show_hide"):
        assert commands.REGISTRY.get(cid) is not None, cid
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("picture.on_xz")
    harness.pump(400)
    assert r.ok, r.error
    n = pic.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    assert abs(abs(n.y) - 1) < 1e-9, n  # standing on XZ: its normal along Y
    up = pic.Placement.Rotation.multVec(App.Vector(0, 1, 0))
    assert abs(up.z - 1) < 1e-9, up  # its top up
    assert commands.REGISTRY.run("picture.turn").ok
    harness.pump(300)
    right = pic.Placement.Rotation.multVec(App.Vector(1, 0, 0))
    assert abs(right.z - 1) < 1e-9, right
    assert hasattr(pic.ViewObject, "Transparency"), pic.ViewObject.PropertiesList
    assert commands.REGISTRY.run("picture.show_hide").ok and not pic.Visibility
    assert commands.REGISTRY.run("picture.show_hide").ok and pic.Visibility
    assert commands.REGISTRY.run("picture.scale").ok
    harness.pump(800)
    fs = s().feature_session
    assert fs is not None and fs.kind.TITLE == "Scale / Transparency" and fs.feature is pic, fs and fs.kind.TITLE
    fs._recompute_count = 0
    real = fs._recompute

    def counted():
        fs._recompute_count += 1
        return real()
    fs._recompute = counted
    for v in range(5, 65, 5):  # the slider dragged: set at once, no preview (the user: it jerked)
        fs.dialog.field("transparency").slider.setValue(v)
        harness.pump(30)
    harness.pump(900)
    assert pic.ViewObject.Transparency == 60, pic.ViewObject.Transparency
    assert fs._recompute_count == 0, fs._recompute_count
    fs._recompute = real
    if os.environ.get("INNCAD_SHOT"):
        fs.dialog.grab().save(os.environ["INNCAD_SHOT"].replace(".png", "_dialog.png"))
    fs.dialog.field("transparency").slider.setValue(0)
    harness.pump(900)
    assert pic.ViewObject.Transparency == 0
    fs.cancel()
    harness.pump(400)
    if os.environ.get("INNCAD_SHOT"):
        rb._tabs.setCurrentIndex(tabs.index("Image"))
        harness.pump(300)
        rb.grab().save(os.environ["INNCAD_SHOT"].replace(".png", "_tab.png"))
    ST["tabs"] = tabs


def test_9_cleanup():
    if s().feature_session is not None:
        s().feature_session.cancel()
    harness.pump(300)
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_import_a_picture, test_1_scale_by_a_known_length, test_1b_a_line_made_horizontal_turns_the_image,
             test_2_picture_tab, test_9_cleanup])
