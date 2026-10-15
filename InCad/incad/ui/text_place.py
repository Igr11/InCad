"""Sketch ▸ Text with nothing picked: two clicks in the sketch — opposite corners of the text box (Inventor), its
outline following the pointer after the first — then the Text dialog opens on that box. Clicks come from the view's Qt events (incad.ui.view_clicks): FreeCAD's sketch
swallows clicks otherwise. Esc, another command or leaving the sketch ends it (the shell's slot-tool slot)."""
import FreeCAD as App

from incad.core import log

PROMPT = "Click the first corner of the text box (or pick a box / curve first; Esc cancels)"
PROMPT_2 = "Click the opposite corner of the text box (Esc cancels)"


_cursor_made = None


def text_cursor():
    """A cross with an orange Aa at its lower right, as FreeCAD's Line / Arc / Rectangle cursors carry their tool."""
    global _cursor_made
    if _cursor_made is None:
        _cursor_made = _draw_cursor()
    return _cursor_made


def _draw_cursor():
    from incad.qt import QtCore, QtGui
    dpr = 2  # drawn for Retina, shown at 32 × 32
    pm = QtGui.QPixmap(32 * dpr, 32 * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    for color, width in ((QtGui.QColor(0, 0, 0, 170), 3.0), (QtGui.QColor(255, 255, 255), 1.2)):  # (an outline)
        p.setPen(QtGui.QPen(color, width))
        p.drawLine(QtCore.QPointF(8, 0), QtCore.QPointF(8, 16))
        p.drawLine(QtCore.QPointF(0, 8), QtCore.QPointF(16, 8))
    f = QtGui.QFont("Helvetica", 12)
    f.setBold(True)
    path = QtGui.QPainterPath()
    path.addText(QtCore.QPointF(12.5, 29), f, "Aa")  # the user's pick of six (a capital T read as Perpendicular)
    p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 220), 2.4, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap,
                        QtCore.Qt.RoundJoin))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawPath(path)  # a dark rim first, under the letters: they read on a light part and on the dark view
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(255, 160, 60))
    p.drawPath(path)
    p.end()
    return QtGui.QCursor(pm, 8, 8)


class TextPlaceTool:
    def __init__(self, view, sketch, on_place, on_finish=None):
        self.view, self.sketch = view, sketch
        self._on_place, self._on_finish = on_place, on_finish
        self._input = None
        self._first = None
        self._preview = self._coords = None

    def start(self):
        from incad.ui.view_clicks import ViewClicks
        self._input = ViewClicks(self.view, self._press, self._moved)
        self._input.start()
        self._cursor()
        self._make_preview()
        log.report("info", PROMPT)

    def _cursor(self, on=True):
        try:
            vp = self.view.graphicsView().viewport()
        except Exception:
            return
        if on:
            vp.setCursor(text_cursor())
        else:
            vp.unsetCursor()

    def _moved(self, x, y):
        self._cursor()  # (FreeCAD's sketch puts its own arrow back as the pointer moves)
        if self._first is not None:
            pt = self.to_sketch(x, y)
            if pt is not None:
                self._draw(self._first, pt)

    def stop(self):
        if self._input is not None:
            self._cursor(False)
            self._input.stop()
            self._input = None
            if self._preview is not None:
                try:
                    self.view.getSceneGraph().removeChild(self._preview)
                except Exception:
                    pass
                self._preview = None
            if self._on_finish is not None:
                self._on_finish(self)

    def to_sketch(self, x, y):
        """Coin position (device px, bottom-left) -> point on the sketch plane, in sketch coordinates."""
        pl = self.sketch.getGlobalPlacement()
        normal = pl.Rotation.multVec(App.Vector(0, 0, 1))
        p = self.view.getPoint(int(round(x)), int(round(y)))
        d = self.view.getViewDirection()
        denom = d.dot(normal)
        if abs(denom) < 1e-9:
            return None
        hit = p + d * ((pl.Base - p).dot(normal) / denom)
        local = pl.inverse().multVec(hit)
        return App.Vector(round(local.x, 3), round(local.y, 3), 0)

    def _press(self, x, y, modifiers):
        pt = self.to_sketch(x, y)
        if pt is None:
            return
        if self._first is None:
            self._first = pt
            self._draw(pt, pt)
            log.report("info", PROMPT_2)
            return
        if abs(pt.x - self._first.x) < 1e-6 or abs(pt.y - self._first.y) < 1e-6:
            log.report("info", PROMPT_2)  # a box with no width or height: wait for the real corner
            return
        place, first = self._on_place, self._first
        self.stop()
        place(first, pt)

    # ----- the box's outline while the second corner is chosen (Coin lines on the sketch plane) -----
    def _make_preview(self):
        from pivy import coin
        sep = coin.SoSeparator()
        tr = coin.SoTransform()
        pl = self.sketch.getGlobalPlacement()
        tr.translation.setValue(*pl.Base)
        q = pl.Rotation.Q
        tr.rotation.setValue(q[0], q[1], q[2], q[3])
        color = coin.SoBaseColor()
        color.rgb.setValue(0.95, 0.62, 0.29)
        style = coin.SoDrawStyle()
        style.lineWidth = 2
        style.linePattern = 0xFF00  # dashed, as the construction box it becomes
        self._coords = coin.SoCoordinate3()
        lines = coin.SoLineSet()
        lines.numVertices.setValue(0)
        self._lines = lines
        for node in (tr, color, style, self._coords, lines):
            sep.addChild(node)
        self.view.getSceneGraph().addChild(sep)
        self._preview = sep

    def _draw(self, a, b):
        if self._coords is None:
            return
        pts = [(a.x, a.y, 0.01), (b.x, a.y, 0.01), (b.x, b.y, 0.01), (a.x, b.y, 0.01), (a.x, a.y, 0.01)]
        self._coords.point.setValues(0, 5, pts)
        self._coords.point.setNum(5)
        self._lines.numVertices.setValue(5)
