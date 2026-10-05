"""InCad mouse navigation on FreeCAD's 3D views (rules in incad.core.gestures): LMB+RMB drag orbits around the
point under the cursor, right-click opens the marking menu, right-drag flicks it, left clicks still select.
Middle-drag pan and wheel zoom stay FreeCAD's own (the shell sets the CAD style with zoom-at-cursor)."""
from incad.core import camera, gestures, log
from incad.qt import QtCore, QtGui, QtWidgets

QT_BUTTONS = ((QtCore.Qt.LeftButton, gestures.LEFT), (QtCore.Qt.RightButton, gestures.RIGHT),
              (QtCore.Qt.MiddleButton, gestures.MIDDLE))
KINDS = {QtCore.QEvent.MouseButtonPress: "press", QtCore.QEvent.MouseButtonRelease: "release",
         QtCore.QEvent.MouseMove: "move", QtCore.QEvent.MouseButtonDblClick: "dblclick"}


def to_coin(viewport, x, y):
    """Qt viewport position (logical px, top-left origin) -> Coin position (device px, bottom-left origin)."""
    dpr = viewport.devicePixelRatioF()
    return (int(round(x * dpr)), int(round((viewport.height() - y) * dpr)))


def _button(qt_button):
    for q, g in QT_BUTTONS:
        if qt_button == q:
            return g
    return 0


def _held(qt_buttons):
    held = 0
    for q, g in QT_BUTTONS:
        if qt_buttons & q:
            held |= g
    return held


class Navigator(QtCore.QObject):
    def __init__(self, open_menu, on_mode_changed=None, parent=None):
        super().__init__(parent)
        self._open_menu = open_menu
        self._on_mode_changed = on_mode_changed
        self._attached = {}  # viewport -> [view, Gestures]
        self._replaying = False
        self._pivot = None
        self.mode = None

    def attached(self):
        return list(self._attached)

    def attach_all(self):
        import FreeCAD as App
        import FreeCADGui as Gui
        for name in App.listDocuments():
            gdoc = Gui.getDocument(name)
            if gdoc is None:
                continue
            for view in gdoc.mdiViewsOfType("Gui::View3DInventor"):
                try:
                    viewport = view.graphicsView().viewport()
                except Exception:
                    continue
                if viewport in self._attached:
                    continue
                machine = gestures.Gestures()
                machine.mode = self.mode
                self._attached[viewport] = [view, machine]
                viewport.installEventFilter(self)
                viewport.destroyed.connect(lambda _=None, v=viewport: self._attached.pop(v, None))

    def detach_all(self):
        for viewport in list(self._attached):
            try:
                viewport.removeEventFilter(self)
            except RuntimeError:
                pass
        self._attached.clear()

    def set_mode(self, mode):
        self.mode = mode
        for entry in self._attached.values():
            entry[1].mode = mode
            entry[1].reset()
        if self._on_mode_changed is not None:
            self._on_mode_changed(mode)

    def eventFilter(self, obj, event):
        if self._replaying:
            return False
        entry = self._attached.get(obj)
        kind = KINDS.get(event.type())
        if entry is None or kind is None:
            return False
        view, machine = entry
        try:
            pos = event.position()
            actions = machine.feed(kind, _button(event.button()), _held(event.buttons()), pos.x(), pos.y())
            for action in actions:
                self._do(obj, view, action, event)
            return gestures.PASS not in actions
        except Exception:
            log.logger().exception("InCad navigation")
            machine.reset()
            return False

    def _do(self, viewport, view, action, event):
        name = action[0]
        if name == "replay_press":
            self._replay(viewport, action[1], action[2], event)
        elif name == "orbit_start":
            self._pivot = self._pivot_at(view, viewport, action[1], action[2])
        elif name == "orbit":
            cam = view.getCameraNode()
            camera.orbit(cam, self._pivot if self._pivot is not None else camera.focal_point(cam), action[1], action[2])
        elif name == "orbit_end":
            self._pivot = None
        elif name == "pan":
            camera.pan_pixels(view.getCameraNode(), action[1], action[2], viewport.height())
        elif name in ("menu", "flick_start"):
            local = QtCore.QPointF(action[1], action[2])
            self._open_menu(view, viewport, local, viewport.mapToGlobal(local.toPoint()), name == "flick_start")

    def _replay(self, viewport, x, y, event):
        local = QtCore.QPointF(x, y)
        press = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, local,
                                  QtCore.QPointF(viewport.mapToGlobal(local.toPoint())),
                                  QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, event.modifiers())
        self._replaying = True
        try:
            QtWidgets.QApplication.sendEvent(viewport, press)
        finally:
            self._replaying = False

    @staticmethod
    def _pivot_at(view, viewport, x, y):
        info = view.getObjectInfo(to_coin(viewport, x, y))
        if info:
            return (info["x"], info["y"], info["z"])
        return None
