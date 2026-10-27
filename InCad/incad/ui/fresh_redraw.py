"""A sketch's view redraws as the mouse moves (the user: drawing lagged behind the mouse). FreeCAD postpones its
redraws until the stream of mouse moves pauses: drawing a rectangle, half the moves waited over 55 ms for the
picture and one in ten over 280 ms (measured in the user's ProstoCAD; 15 / 116 ms without InCad's own mouse handling).
While a sketch is open, a move redraws the view at once, at most every REDRAW_S: what FreeCAD did with the move
before is on screen when the next one comes (3.5 ms typical, 17 ms the slowest). Independent of InCad's navigation,
which the user can turn off."""
import time

from incad.qt import QtCore

REDRAW_S = 0.016  # at most ~60 redraws a second
_filter = None


class _Fresh(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.viewports = set()
        self.last = 0.0

    def eventFilter(self, obj, event):
        try:
            if event.type() == QtCore.QEvent.MouseMove and obj in self.viewports:
                now = time.perf_counter()
                if now - self.last >= REDRAW_S and _sketch_open():
                    self.last = now
                    obj.repaint()
        except RuntimeError:  # the view is going
            pass
        return False


def _sketch_open():
    import FreeCADGui as Gui
    from incad.core import sketch
    gdoc = Gui.ActiveDocument
    vp = gdoc.getInEdit() if gdoc is not None else None
    return vp is not None and sketch.is_sketch(getattr(vp, "Object", None))


def attach_all():
    """Every open 3D view (again after new views appear: each is attached once)."""
    global _filter
    import FreeCAD as App
    import FreeCADGui as Gui
    if _filter is None:
        _filter = _Fresh()
    for name in App.listDocuments():
        gdoc = Gui.getDocument(name)
        if gdoc is None:
            continue
        for view in gdoc.mdiViewsOfType("Gui::View3DInventor"):
            try:
                viewport = view.graphicsView().viewport()
            except Exception:
                continue
            if viewport in _filter.viewports:
                continue
            _filter.viewports.add(viewport)
            viewport.installEventFilter(_filter)
            viewport.destroyed.connect(lambda _=None, v=viewport: _filter.viewports.discard(v))


def detach_all():
    if _filter is None:
        return
    for viewport in list(_filter.viewports):
        try:
            viewport.removeEventFilter(_filter)
        except RuntimeError:
            pass
    _filter.viewports.clear()
