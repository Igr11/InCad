"""Inventor-style marking menu: up to 8 commands in a ring around the cursor plus a short list below it.
Right-click opens it for hover-and-click; a right-drag (flick) picks the slot in the drag direction on release."""
import math

from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes
from incad.ui.marking_layout import DIRECTIONS

RADIUS = 92
DEAD_ZONE = 18


def direction_for(dx, dy, dead_zone=DEAD_ZONE):
    """Screen vector (dy positive downward) -> 'N'…'NW', or None inside the dead zone."""
    if math.hypot(dx, dy) < dead_zone:
        return None
    angle = math.degrees(math.atan2(dx, -dy)) % 360
    return DIRECTIONS[int((angle + 22.5) // 45) % 8]


class MarkingMenu(QtWidgets.QWidget):
    triggered = Signal(str)

    def __init__(self, registry, slots, items, theme="light", parent=None):
        super().__init__(parent, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setObjectName("InCadMarkingMenu")
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self._registry, self._theme = registry, theme
        self._buttons, self._slot_ids, self._list = {}, {}, []
        self._flick, self._flick_to, self._hot = False, None, None
        width = 2 * RADIUS + 220
        self._center = QtCore.QPoint(width // 2, RADIUS + 40)
        self.resize(width, self._center.y() + RADIUS + 50 + 30 * len(items))
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QToolButton {{ background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 8px;"
            " padding: 4px 10px; }} QToolButton:hover, QToolButton[hot=\"true\"] {{ background: {accent};"
            " color: {selection_text}; }}".format(**p))
        for direction, cmd in slots:
            b = self._make_button(cmd)
            a = math.radians(DIRECTIONS.index(direction) * 45)
            x = self._center.x() + RADIUS * math.sin(a)
            y = self._center.y() - RADIUS * math.cos(a)
            b.move(int(x - b.width() / 2), int(y - b.height() / 2))
            self._buttons[direction] = b
            self._slot_ids[direction] = cmd.id
        y = self._center.y() + RADIUS + 34
        for cmd in items:
            b = self._make_button(cmd)
            b.setMinimumWidth(170)
            b.adjustSize()
            b.move(self._center.x() - b.width() // 2, y)
            y += b.height() + 2
            self._list.append(b)

    def _make_button(self, cmd):
        b = QtWidgets.QToolButton(self)
        b.setIcon(themes.icon(cmd.icon, self._theme))
        b.setIconSize(QtCore.QSize(20, 20))
        b.setText(cmd.label)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        b.clicked.connect(lambda _=False, i=cmd.id: self.choose(i))
        b.adjustSize()
        return b

    # ----- public -----
    def show_at(self, global_pos):
        self.move(global_pos - self._center)
        self.show()
        self.raise_()

    def center_global(self):
        return self.mapToGlobal(self._center)

    def button(self, direction):
        return self._buttons.get(direction)

    def list_labels(self):
        return [b.text() for b in self._list]

    def hot_direction(self):
        return self._hot

    def choose(self, cmd_id):
        self.close()
        self.triggered.emit(cmd_id)
        self._registry.run(cmd_id)

    def start_flick(self):
        self._flick = True

    def flick_move(self, global_pos):
        d = global_pos - self.center_global()
        self._set_hot(direction_for(d.x(), d.y()))
        self._flick_to = self.mapFromGlobal(global_pos)
        self.update()

    def flick_end(self, global_pos):
        d = global_pos - self.center_global()
        cmd_id = self._slot_ids.get(direction_for(d.x(), d.y()))
        if cmd_id:
            self.choose(cmd_id)
        else:
            self.close()

    # ----- internals -----
    def _set_hot(self, direction):
        self._hot = direction if direction in self._buttons else None
        for d, b in self._buttons.items():
            b.setProperty("hot", d == self._hot)
            b.style().unpolish(b)
            b.style().polish(b)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pal = themes.PALETTES[self._theme]
        pen = QtGui.QPen(QtGui.QColor(pal["accent"]))
        pen.setWidth(2)
        painter.setPen(pen)
        fill = QtGui.QColor(pal["accent"])
        fill.setAlpha(40)
        painter.setBrush(fill)
        painter.drawEllipse(self._center, DEAD_ZONE, DEAD_ZONE)
        if self._flick_to is not None:
            painter.drawLine(self._center, self._flick_to)
        painter.end()

    def mouseMoveEvent(self, event):
        if self._flick:
            self.flick_move(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._flick and event.button() == QtCore.Qt.RightButton:
            self.flick_end(event.globalPosition().toPoint())
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        self.close()  # a click on the empty area around the ring

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
