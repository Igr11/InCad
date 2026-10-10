"""InCad mouse navigation on FreeCAD's 3D views (rules in incad.core.gestures): LMB+RMB drag orbits around the
point under the cursor, right-click opens the marking menu (or finishes the running Sketcher tool: FreeCAD's spline
and polyline tools end on a right click), right-drag flicks it, left clicks still select.
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
        self.click_hook = None      # callable(view, viewport, x, y) -> True takes the left click
        self.dblclick_hook = None   # same for left double-clicks
        self._swallow_release = False

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
                self._attached[viewport] = [view, machine, QtCore.Qt.NoModifier]  # + modifiers at the last press
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
        view, machine = entry[0], entry[1]
        try:
            if kind == "press":
                entry[2] = event.modifiers()
            pos = event.position()
            if event.button() == QtCore.Qt.LeftButton:
                if kind == "press" and machine.state == "idle" and self.click_hook is not None \
                        and self.click_hook(view, obj, pos.x(), pos.y()):
                    self._swallow_release = True
                    return True
                if kind == "release" and self._swallow_release:
                    self._swallow_release = False
                    return True
                if kind == "dblclick" and self.dblclick_hook is not None \
                        and self.dblclick_hook(view, obj, pos.x(), pos.y()):
                    return True
            actions = machine.feed(kind, _button(event.button()), _held(event.buttons()), pos.x(), pos.y())
            for action in actions:
                self._do(obj, view, action, entry[2])
            return gestures.PASS not in actions
        except Exception:
            log.logger().exception("InCad navigation")
            machine.reset()
            return False

    def _do(self, viewport, view, action, press_modifiers):
        name = action[0]
        if name == "replay_press":
            self._replay(viewport, action[1], action[2], press_modifiers)
        elif name == "orbit_start":
            self._pivot = self._pivot_at(view, viewport, action[1], action[2])
        elif name == "orbit":
            cam = view.getCameraNode()
            camera.orbit(cam, self._pivot if self._pivot is not None else camera.focal_point(cam), action[1], action[2])
        elif name == "orbit_end":
            self._pivot = None
        elif name == "pan":
            camera.pan_pixels(view.getCameraNode(), action[1], action[2], viewport.height())
        elif name == "menu" and self.tool_cursor(viewport):
            self._replay(viewport, action[1], action[2], press_modifiers, QtCore.Qt.RightButton, release=True)
        elif name in ("menu", "flick_start"):
            local = QtCore.QPointF(action[1], action[2])
            self._open_menu(view, viewport, local, viewport.mapToGlobal(local.toPoint()), name == "flick_start")

    @staticmethod
    def tool_cursor(viewport):
        """True while a Sketcher tool runs in this view: it shows its own bitmap cursor, and FreeCAD tells Python
        nothing else. A plain right click then belongs to the tool (it finishes a spline or a polyline, ends an
        empty tool), not to the marking menu; a right drag still flicks the menu."""
        try:
            return viewport.cursor().shape() == QtCore.Qt.BitmapCursor
        except RuntimeError:
            return False

    def _replay(self, viewport, x, y, modifiers, button=QtCore.Qt.LeftButton, release=False):
        """Hand FreeCAD a press InCad held back (and its release, for a right click a Sketcher tool finishes on)."""
        local = QtCore.QPointF(x, y)
        glob = QtCore.QPointF(viewport.mapToGlobal(local.toPoint()))
        events = [QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, local, glob, button, button, modifiers)]
        if release:
            events.append(QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, local, glob, button,
                                            QtCore.Qt.NoButton, modifiers))
        self._replaying = True
        try:
            for ev in events:
                QtWidgets.QApplication.sendEvent(viewport, ev)
        finally:
            self._replaying = False

    @staticmethod
    def _pivot_at(view, viewport, x, y):
        info = view.getObjectInfo(to_coin(viewport, x, y))
        if info:
            return (info["x"], info["y"], info["z"])
        return None
