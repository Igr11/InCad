"""FreeCAD's pick radius (Preferences ▸ Display ▸ 3D View ▸ Pick radius) counts device pixels: its default 5 is 2.5
points round a sketch point on a Retina screen, so a point between lines (a rectangle's centre point on its diagonals)
caught the pointer one time in five (the user). On such a screen InCad sets FreeCAD's default times the pixel ratio,
once; a radius the user chose stays. Points still win over the lines under them (they are drawn above)."""
import FreeCAD as App

from incad.core import prefs

VIEW = "User parameter:BaseApp/Preferences/View"
DEFAULT = 5.0  # FreeCAD's own


def widen():
    if prefs.pick_radius_widened():
        return
    from incad.qt import QtWidgets
    app = QtWidgets.QApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    ratio = screen.devicePixelRatio() if screen is not None else 1.0
    if ratio <= 1:
        return  # an ordinary screen: FreeCAD's radius is right (a Retina screen met later still gets it)
    p = App.ParamGet(VIEW)
    if abs(p.GetFloat("PickRadius", DEFAULT) - DEFAULT) < 1e-6:
        p.SetFloat("PickRadius", DEFAULT * ratio)
    prefs.set_pick_radius_widened(True)
