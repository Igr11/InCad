"""Clicks and moves for InCad's own sketch tools (offset, slots), taken from the 3D view's Qt events ahead of FreeCAD
and of InCad's navigation: in sketch edit FreeCAD's sketch handles the mouse itself and Coin event callbacks never
saw a real click (the tools' tests had called their handlers directly). A plain left press is the tool's (consumed,
with its release); other buttons, drags with the middle / right button and modifiers other than Cmd/Ctrl/Shift
stay FreeCAD's / InCad's (zoom, orbit, pan, the marking menu)."""
from incad.qt import QtCore


class ViewClicks(QtCore.QObject):
    def __init__(self, view, on_press, on_move):
        super().__init__()
        self.view = view
        self._press, self._move = on_press, on_move  # callables(coin_x, coin_y, modifiers) / (coin_x, coin_y)
        self._viewport = None
        self._swallow_release = False

    def start(self):
        try:
            self._viewport = self.view.graphicsView().viewport()
            self._viewport.installEventFilter(self)
        except Exception:
            self._viewport = None

    def stop(self):
        if self._viewport is not None:
            try:
                self._viewport.removeEventFilter(self)
            except RuntimeError:
                pass
        self._viewport = None

    def _coin(self, event):
        from incad.ui.nav import to_coin
        p = event.position()
        return to_coin(self._viewport, p.x(), p.y())

    def eventFilter(self, obj, event):
        if obj is not self._viewport:
            return False
        try:
            t = event.type()
            if t == QtCore.QEvent.MouseMove and event.buttons() == QtCore.Qt.NoButton:
                self._move(*self._coin(event))
                return False  # FreeCAD still preselects under the pointer
            if t == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                x, y = self._coin(event)
                self._swallow_release = True
                self._press(x, y, event.modifiers())
                return True
            if t == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton \
                    and self._swallow_release:
                self._swallow_release = False
                return True
        except Exception:
            from incad.core import log
            log.logger().exception("InCad sketch tool input")
        return False
