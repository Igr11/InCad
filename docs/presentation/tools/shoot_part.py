import os, sys
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness
import FreeCAD as App, FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from incad.core import commands, document, prefs, context
from incad.ui import shell
OUT = "/private/tmp/claude-501/-Volumes-Docs-Claude-projects-InCad/4b6f50bc-7c3f-4b62-9bcd-93f50bf60345/scratchpad/shots"
def mark(t):
    open(os.path.join(OUT, "progress.txt"), "a").write(t + "
")
mark("loaded")

def mw():
    return Gui.getMainWindow()

def save(name, extra=None):
    harness.pump(600)
    img = mw().grab()
    if extra is not None:  # a popup (marking menu) painted at its place over the window
        p = QtGui.QPainter(img)
        pos = mw().mapFromGlobal(extra.mapToGlobal(QtCore.QPoint(0, 0)))
        p.drawPixmap(pos, extra.grab())
        p.end()
    img.save(os.path.join(OUT, name + ".png"))

def fit():
    Gui.ActiveDocument.ActiveView.viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)

def test_0_open():
    mark('prefs.set_theme')
    prefs.set_theme("dark")
    prefs.set_remember_new_choice(True)
    mw().showNormal()
    mw().resize(1680, 1000)
    mw().move(40, 40)
    mark('Gui.activateWorkbench')
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1500)
    mark('App.openDocument')
    App.openDocument(os.path.join(OUT, "part.FCStd"))
    harness.pump(3000)
    shell.instance().schedule_refresh()
    harness.pump(800)
    mark('fit')
    fit()
    save("1_overview")

def test_1_highlight():
    b = shell.instance().browser
    assert b.select_row("Extrude003")
    harness.pump(800)
    save("2_highlight")
    Gui.Selection.clearSelection()
    b.tree.clearSelection()

def test_2_dialog():
    context.set_target("Extrude004")
    r = commands.REGISTRY.run("browser.edit")
    harness.pump(2000)
    save("3_dialog")
    fs = shell.instance().feature_session
    if fs is not None:
        fs.cancel()
        harness.pump(1000)

def test_3_menu():
    vp = Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    centre = vp.mapToGlobal(QtCore.QPoint(vp.width() // 2, vp.height() // 2))
    menu = shell.instance()._show_marking_menu("part", centre)
    harness.pump(600)
    save("4_menu", shell.instance().marking_menu)
    if shell.instance().marking_menu is not None:
        shell.instance().marking_menu.close()
    harness.pump(400)

def test_4_sketch():
    sk = App.ActiveDocument.getObject("Sketch007")
    shell.instance().sketches.edit(sk)
    harness.pump(2500)
    save("5_sketch")
    commands.REGISTRY.run("sketch.finish")
    harness.pump(1000)

harness.run([test_0_open, test_1_highlight, test_2_dialog, test_3_menu, test_4_sketch])
