"""The view provider proxy of InCad's Python features (Split, Hole ▸ Chamfer). Without one FreeCAD's
ViewProviderPython has no display mode and the feature draws nothing when it is the Tip. FreeCAD saves this module
path and class name in the file."""


class ViewProviderFeature:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        return

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def dumps(self):
        return None

    def loads(self, state):
        return None
