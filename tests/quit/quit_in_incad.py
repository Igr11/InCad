"""Start InCad with a part and a sketch open, then quit with InCad's ⌘Q command (no unsaved changes)."""
import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore
from incad.core import commands, prefs
from incad.ui import shell


def step2():
    shell.instance().plane_panel.button("XY_Plane").click()
    QtCore.QTimer.singleShot(1500, step3)


def step3():
    for d in App.listDocuments().values():
        d.clearUndos()
        for o in d.Objects:
            o.purgeTouched()
    gd = Gui.ActiveDocument
    if gd is not None:
        gd.Modified = False
    import os
    import Part
    commands.REGISTRY.run("sketch.finish")
    from incad.core import document
    body = document.primary_body(App.ActiveDocument)
    sk = [o for o in body.Group if o.TypeId == "Sketcher::SketchObject"][0]
    sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
    App.ActiveDocument.recompute()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")      # a feature dialog left open
    commands.REGISTRY.run("inspect.mass")        # and an info panel
    shell.SAVE_ASK = lambda files: ("discard", [])  # InCad's Save dialog answered "Don't Save"
    if os.environ.get("INCAD_QUIT") == "key":    # a real ⌘Q
        def press():
            from PySide6.QtTest import QTest
            mw = Gui.getMainWindow()
            mw.raise_()
            mw.activateWindow()
            from PySide6 import QtWidgets
            QtCore.QTimer.singleShot(300, lambda: QTest.keyClick(QtWidgets.QApplication.focusWidget() or mw,
                                                                QtCore.Qt.Key_Q, QtCore.Qt.ControlModifier))
        QtCore.QTimer.singleShot(800, press)
    elif os.environ.get("INCAD_QUIT") == "menu":   # InCad's File > Quit
        from PySide6 import QtWidgets
        menu = Gui.getMainWindow().menuBar().findChild(QtWidgets.QMenu, shell.MENU_PREFIX + "File")
        act = [a for a in menu.actions() if a.text() == commands.REGISTRY.get("file.quit").label][0]
        QtCore.QTimer.singleShot(800, act.trigger)
    elif os.environ.get("INCAD_QUIT") == "appmenu":  # the app menu's Quit item (the QuitRole action)
        from PySide6.QtGui import QAction
        acts = [a for a in Gui.getMainWindow().findChildren(QAction) if a.menuRole() == QAction.QuitRole]
        open(os.environ["INCAD_QUIT_LOG"], "w").write(repr([(a.text(), a.isEnabled(), a.isVisible()) for a in acts]))
        QtCore.QTimer.singleShot(800, acts[0].trigger)
    elif os.environ.get("INCAD_QUIT") == "outside":  # quit is driven from outside (a real menu click)
        log = open(os.environ["INCAD_QUIT_READY"] + ".events", "w", buffering=1)

        class Spy(QtCore.QObject):
            def eventFilter(self, obj, ev):
                if ev.type() in (QtCore.QEvent.Close, QtCore.QEvent.Quit):
                    log.write("%s %s %s accepted=%s\n" % (ev.type(), type(obj).__name__, obj.objectName(),
                                                         ev.isAccepted()))
                return False
        global _spy
        _spy = Spy()
        QtCore.QCoreApplication.instance().installEventFilter(_spy)
        QtCore.QCoreApplication.instance().aboutToQuit.connect(lambda: log.write("aboutToQuit\n"))
        open(os.environ["INCAD_QUIT_READY"], "w").write("ready")
    elif os.environ.get("INCAD_QUIT") == "app":    # like Quit from the Dock / app menu
        QtCore.QTimer.singleShot(800, lambda: QtCore.QCoreApplication.instance().quit())
    else:
        QtCore.QTimer.singleShot(800, lambda: Gui.getMainWindow().close())


def answer_freecad_prompts():
    """Answer FreeCAD's own message boxes during the quit like a user: Discard, else Yes/OK."""
    from PySide6 import QtWidgets
    box = QtWidgets.QApplication.activeModalWidget()
    if isinstance(box, QtWidgets.QMessageBox):
        roles = {box.buttonRole(b): b for b in box.buttons()}
        for role in (QtWidgets.QMessageBox.DestructiveRole, QtWidgets.QMessageBox.YesRole,
                     QtWidgets.QMessageBox.AcceptRole):
            if role in roles:
                roles[role].click()
                break
    QtCore.QTimer.singleShot(300, answer_freecad_prompts)


def quit_now():
    import os
    from PySide6 import QtWidgets
    shell.SAVE_ASK = lambda files: ("discard", [])
    for d in App.listDocuments().values():
        d.clearUndos()
        g = Gui.getDocument(d.Name)
        if g is not None:
            g.Modified = False
    answer_freecad_prompts()
    if os.environ.get("INCAD_QUIT") == "menu":
        menu = Gui.getMainWindow().menuBar().findChild(QtWidgets.QMenu, shell.MENU_PREFIX + "File")
        acts = [a for a in menu.actions() if a.text() == "Quit"] if menu is not None else []
        if acts:
            QtCore.QTimer.singleShot(500, acts[0].trigger)
            return
    QtCore.QTimer.singleShot(500, lambda: Gui.getMainWindow().close())


def waiting_step():
    """InCad chosen while a FreeCAD task (Pad) is open: it waits, then FreeCAD is quit."""
    import Part
    Gui.activateWorkbench("PartDesignWorkbench")
    doc = App.newDocument("PD")
    body = doc.addObject("PartDesign::Body", "Body")
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    sk.AttachmentSupport = [([o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
    doc.recompute()
    Gui.Selection.addSelection(doc.Name, sk.Name)
    Gui.runCommand("PartDesign_Pad")
    QtCore.QTimer.singleShot(1500, lambda: (Gui.activateWorkbench("InCadWorkbench"),
                                            QtCore.QTimer.singleShot(1500, quit_now)))


def step1():
    import os
    if os.environ.get("INCAD_QUIT_SETUP") == "waiting":
        QtCore.QTimer.singleShot(1500, waiting_step)
        return
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    QtCore.QTimer.singleShot(1500, lambda: (commands.REGISTRY.run("file.new"),
                                            QtCore.QTimer.singleShot(1000, lambda: (commands.REGISTRY.run("sketch.start"),
                                                                                    QtCore.QTimer.singleShot(800, step2)))))


QtCore.QTimer.singleShot(1000, step1)
