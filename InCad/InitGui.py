import FreeCADGui as Gui


class InCadWorkbench(Gui.Workbench):
    """Inventor/Alibre-style modeling. The whole UI is built by incad.ui.shell when the workbench activates."""

    MenuText = "InCad"
    ToolTip = "Inventor-style part and assembly modeling"

    def __init__(self):
        import os
        import incad
        self.__class__.Icon = os.path.join(os.path.dirname(incad.__file__), "resources", "icons", "light", "incad.svg")

    def Initialize(self):
        from incad import actions
        actions.register_all()

    def Activated(self):
        from incad import actions
        from incad.ui import shell
        actions.register_all()
        try:
            from incad.core import quality
            quality.set_defaults()  # ⚙ ▸ Display Quality for every shape made from now on
        except Exception:
            pass
        shell.activate()

    def Deactivated(self):
        from incad.ui import shell
        shell.deactivate()

    def GetClassName(self):
        return "Gui::PythonWorkbench"


def _incad_startup():
    """Remember the last non-InCad workbench (for ⇄ FreeCAD) and repair FreeCAD's UI after a crash."""
    try:
        from incad.core import prefs
        from incad.qt import QtCore
        from incad.ui import shell

        def remember(name):
            if name != "InCadWorkbench":
                prefs.set_last_workbench(name)

        Gui.getMainWindow().workbenchActivated.connect(remember)
        QtCore.QTimer.singleShot(1500, shell.recover_after_crash)
        # tear InCad down while Python still runs: Qt deleting InCad's objects after Python is gone crashed FreeCAD
        QtCore.QCoreApplication.instance().aboutToQuit.connect(shell.shutdown)
        from incad.core import perf
        perf.watch_ui()  # slow calls and stalls go to the log (a slow Windows PC)
        QtCore.QCoreApplication.instance().aboutToQuit.connect(perf.stop)
        from incad import host
        from incad.core import log
        QtCore.QTimer.singleShot(3000, lambda: log.logger().info("Started: %s", host.describe()))
    except Exception as e:
        import FreeCAD
        FreeCAD.Console.PrintWarning("InCad startup hooks failed: %s\n" % e)


Gui.addWorkbench(InCadWorkbench())
_incad_startup()
