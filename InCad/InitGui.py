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
        pass

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(InCadWorkbench())
