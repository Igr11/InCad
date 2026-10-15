"""The user on a new file: Start 2D Sketch with nothing selected showed no planes ("the clicks on the empty window,
because the planes are not visible after the first click") — only a second Start 2D Sketch showed them. The planes
must be drawn, big and clickable, the first time, on every new file."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell, sketch_session  # noqa: E402
from incad.ui.nav import to_coin  # noqa: E402

ST = {"docs": []}


def s():
    return shell.instance()


def drawn_planes():
    """{plane role: (screen box width, height in logical px, what a pick at its middle hits)}."""
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    view = Gui.getDocument(doc.Name).ActiveView
    vp = view.graphicsView().viewport()
    out = {}
    for f in body.Origin.OriginFeatures:
        if f.TypeId != "App::Plane":
            continue
        box = sketch_session.screen_box(view, [f.ViewObject])
        if not box.isValid():
            out[f.Role] = (0, 0, None)
            continue
        corners = [view.getPointOnViewport(App.Vector(x, y, z)) for x in (box.XMin, box.XMax)
                   for y in (box.YMin, box.YMax) for z in (box.ZMin, box.ZMax)]
        r = vp.devicePixelRatioF()
        xs, ys = [c[0] / r for c in corners], [c[1] / r for c in corners]
        mid = box.Center + (App.Vector(box.XMax, box.YMax, box.ZMax) - box.Center) * 0.5  # inside the plane, off its axes
        mx, my = view.getPointOnViewport(mid)
        info = view.getObjectInfo((int(mx), int(my)))
        out[f.Role] = (round(max(xs) - min(xs)), round(max(ys) - min(ys)), info and info.get("Object"),
                       QtCore.QPointF(mx / r, vp.height() - my / r))
    return out


L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton


def start_on_new_file(click=False):
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    ST["docs"].append(App.ActiveDocument.Name)
    Gui.Selection.clearSelection()
    harness.pump(200)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1200)
    assert s().sketches.picking, "InCad asks for a plane"
    planes = drawn_planes()
    xy = planes.get("XY_Plane")
    assert xy and xy[0] > 150 and xy[1] > 80, ("the XY plane is drawn big enough to click", planes)
    body = document.primary_body(App.ActiveDocument)
    xy_name = [f.Name for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0]
    assert xy[2] == xy_name, ("a click on it hits the plane", planes, xy_name)
    if click:
        view = Gui.ActiveDocument.ActiveView
        vp = view.graphicsView().viewport()
        at = xy[3]
        for kind, button, buttons, ms in ((QtCore.QEvent.MouseMove, N, N, 300), (QtCore.QEvent.MouseButtonPress, L, L, 60),
                                          (QtCore.QEvent.MouseButtonRelease, L, N, 1500)):
            QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, at, QtCore.QPointF(vp.mapToGlobal(at.toPoint())),
                                                                    button, buttons, QtCore.Qt.NoModifier))
            harness.pump(ms)
        editing = s().sketches.editing()
        assert editing is not None, ("one click on the plane starts the sketch", s().sketches.picking,
                                     [(x.ObjectName, list(x.SubElementNames)) for x in Gui.Selection.getSelectionEx()],
                                     open(os.environ["INCAD_LOG"]).read()[-600:])
        s().sketches.finish()
        harness.pump(800)
        return
    s().sketches.cancel_pick()
    harness.pump(400)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)


def test_1_first_new_file_shows_the_planes_at_once():
    start_on_new_file()


def test_2_another_new_file_too():
    start_on_new_file()


def test_2b_one_click_on_the_plane_starts_the_sketch():
    start_on_new_file(click=True)


def test_2c_start_2d_sketch_after_closing_a_file_starts_a_sketch():
    """The user: after closing a file and making a new one, the Start 2D Sketch button opened another new file."""
    from PySide6.QtTest import QTest
    for name in list(ST["docs"]):
        if name in App.listDocuments():
            App.setActiveDocument(name)
            Gui.getDocument(name).ActiveView  # its tab in front
            App.closeDocument(name)
            harness.pump(800)
    ST["docs"] = [n for n in ST["docs"] if n in App.listDocuments()]
    commands.REGISTRY.run("file.new")
    harness.pump(1200)
    ST["docs"].append(App.ActiveDocument.Name)
    before = sorted(App.listDocuments())
    Gui.Selection.clearSelection()
    button = s().ribbon.button("sketch.start")
    tabs = s().ribbon.tab_names()
    assert button is not None and button.isVisible(), ("Start 2D Sketch is on the ribbon", tabs)
    at = button.rect().center()
    hit = QtWidgets.QApplication.widgetAt(button.mapToGlobal(at))
    QTest.mouseClick(button, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
    harness.pump(1500)
    after = sorted(App.listDocuments())
    assert after == before, ("no new file", before, after, tabs, hit and hit.objectName())
    assert s().sketches.picking, ("InCad asks for a plane", tabs, App.ActiveDocument.Name)
    s().sketches.cancel_pick()
    harness.pump(400)


def _tab_of(name):
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    for sub in mdi.subWindowList():
        if sub.widget() is not None and name in sub.windowTitle():
            return mdi, sub
    return mdi, None


def test_2d_after_switching_to_a_freecad_tab_and_back_the_button_still_starts_a_sketch():
    """The user's session: a plain FreeCAD document in another tab (its own workbench, SaveWBbyTab) — InCad leaves
    and comes back with the tab switches; afterwards the ribbon button must still be Start 2D Sketch."""
    from PySide6.QtTest import QTest
    App.ParamGet("User parameter:BaseApp/Preferences/View").SetBool("SaveWBbyTab", True)
    plain = App.newDocument("Unnamed")
    ST["docs"].append(plain.Name)
    harness.pump(600)
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(1200)
    part = App.ActiveDocument.Name
    ST["docs"].append(part)
    mdi, plain_tab = _tab_of("Unnamed")
    _, part_tab = _tab_of(part)
    for _ in range(2):
        mdi.setActiveSubWindow(plain_tab)
        harness.pump(1200)
        mdi.setActiveSubWindow(part_tab)
        harness.pump(1200)
    assert Gui.activeWorkbench().name() == "InCadWorkbench", Gui.activeWorkbench().name()
    ribbons = [w for w in Gui.getMainWindow().findChildren(QtWidgets.QWidget, "InCadRibbon")]
    button = s().ribbon.button("sketch.start")
    at = button.rect().center()
    hit = QtWidgets.QApplication.widgetAt(button.mapToGlobal(at))
    owner = hit
    while owner is not None and owner.objectName() != "InCadRibbon":
        owner = owner.parentWidget()
    before = sorted(App.listDocuments())
    QTest.mouseClick(button, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
    harness.pump(1500)
    after = sorted(App.listDocuments())
    info = (len(ribbons), [r.isVisible() for r in ribbons], hit and (type(hit).__name__, hit.objectName(),
            getattr(hit, "text", lambda: "")()), owner is s().ribbon, s().ribbon.tab_names())
    assert after == before, ("no new file", before, after, info)
    assert len([r for r in ribbons if r.isVisible()]) == 1 and owner is s().ribbon, ("one ribbon, the live one", info)
    assert s().sketches.picking, ("InCad asks for a plane", info)
    s().sketches.cancel_pick()
    harness.pump(400)


def test_2f_another_tab_in_front_ends_the_plane_pick():
    """The user's screenshot: the plane panel of a part's pick stayed over another document's tab."""
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    first = App.ActiveDocument.Name
    ST["docs"].append(first)
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    second = App.ActiveDocument.Name
    ST["docs"].append(second)
    mdi, first_tab = _tab_of(first)
    mdi.setActiveSubWindow(first_tab)
    harness.pump(1000)
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    assert s().sketches.picking and s().plane_panel.isVisible()
    origin = document.primary_body(App.getDocument(first)).Origin
    _, second_tab = _tab_of(second)
    mdi.setActiveSubWindow(second_tab)
    harness.pump(1200)
    assert App.ActiveDocument.Name == second, App.ActiveDocument.Name
    assert not s().sketches.picking, "the pick ends"
    assert not s().plane_panel.isVisible(), "its panel goes"
    assert not document.is_shown(origin.OriginFeatures[0]) or not origin.Visibility, "the first part's planes back"


def test_3_cleanup():
    for name in ST["docs"]:
        if name in App.listDocuments():
            App.closeDocument(name)
        harness.pump(300)


harness.run([test_0_setup, test_1_first_new_file_shows_the_planes_at_once, test_2_another_new_file_too,
             test_2b_one_click_on_the_plane_starts_the_sketch,
             test_2c_start_2d_sketch_after_closing_a_file_starts_a_sketch,
             test_2d_after_switching_to_a_freecad_tab_and_back_the_button_still_starts_a_sketch,
             test_2f_another_tab_in_front_ends_the_plane_pick, test_3_cleanup])
