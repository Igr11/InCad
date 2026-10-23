"""View ▸ Screenshot (the user: the part on screen saved as a picture, JPEG or BMP — for a web site and screenshots): the
3D view saved at the screen's full resolution as PNG, JPEG or BMP, and as a PNG with a transparent background."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad import actions  # noqa: E402
from incad.qt import QtGui  # noqa: E402
from incad.ui.line3d_tool import viewport_of  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def test_0_a_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(App.ActiveDocument)
    util.add_pad(body, util.add_rect_sketch(body, 30, 20, "Base"), 8)
    App.ActiveDocument.recompute()
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    ST["dir"] = tempfile.mkdtemp()


def test_1_png_jpeg_bmp_and_transparent():
    vp = viewport_of(Gui.ActiveDocument.ActiveView)
    want = (int(round(vp.width() * vp.devicePixelRatioF())), int(round(vp.height() * vp.devicePixelRatioF())))
    for name in ("part.png", "part.jpg", "part.bmp"):
        path = actions.screenshot(os.path.join(ST["dir"], name))
        img = QtGui.QImage(path)
        assert not img.isNull() and (img.width(), img.height()) == want, (name, img.size(), want)
    actions.SCREENSHOT_ASK = lambda doc, window=False: (os.path.join(ST["dir"], "clear"), True)  # through the command, no suffix
    try:
        r = commands.REGISTRY.run("view.screenshot")
    finally:
        actions.SCREENSHOT_ASK = None
    assert r.ok, r.error
    img = QtGui.QImage(os.path.join(ST["dir"], "clear.png"))
    assert img.hasAlphaChannel() and img.pixelColor(2, 2).alpha() == 0, img.pixelColor(2, 2)  # no background
    c = img.pixelColor(img.width() // 2, img.height() // 2)
    assert c.alpha() == 255, c  # the part itself is there
    if os.environ.get("INNCAD_SHOT"):
        shutil.copy(os.path.join(ST["dir"], "part.jpg"), os.environ["INNCAD_SHOT"])


def test_2_the_whole_window():
    """Screenshot (Window) (the user: with the toolbars too): the window's size, the ribbon there, and the part drawn
    where the 3D view is (a plain grab leaves it black)."""
    mw = Gui.getMainWindow()
    path = actions.screenshot(os.path.join(ST["dir"], "window.png"), window=True)
    img = QtGui.QImage(path)
    if os.environ.get("INNCAD_SHOT"):
        shutil.copy(path, os.environ["INNCAD_SHOT"].replace(".jpg", "_window.png"))
    ratio = img.width() / mw.width()
    assert abs(img.height() / ratio - mw.height()) < 2, (img.size(), mw.size())
    vp = viewport_of(Gui.ActiveDocument.ActiveView)
    mid = vp.mapTo(mw, vp.rect().center())
    c = img.pixelColor(int(mid.x() * ratio), int(mid.y() * ratio))
    assert c.lightness() > 60, c.name()  # the part in the middle of the view, not a black hole
    if os.environ.get("INNCAD_SHOT"):
        shutil.copy(path, os.environ["INNCAD_SHOT"].replace(".jpg", "_window.png"))


def test_9_cleanup():
    App.closeDocument(App.ActiveDocument.Name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_a_part, test_1_png_jpeg_bmp_and_transparent, test_2_the_whole_window, test_9_cleanup])
