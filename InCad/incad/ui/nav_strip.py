"""Navigation strip floating at the right edge of the 3D view, below the ViewCube (Inventor's navigation bar)."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes

STRIP = ("view.zoom_all", "view.home", "view.look_at", "nav.orbit", "nav.pan", "view.style_shaded",
         "view.style_wireframe")


class NavStrip(QtWidgets.QFrame):
    def __init__(self, registry, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadNavStrip")
        self._registry = registry
        self._buttons = {}
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(4, 4, 4, 4)
        col.setSpacing(2)
        for cmd_id in STRIP:
            if not registry.has(cmd_id):
                continue
            cmd = registry.get(cmd_id)
            b = QtWidgets.QToolButton(self)
            b.setIconSize(QtCore.QSize(20, 20))
            b.setToolTip(cmd.label + ("\n" + cmd.tooltip if cmd.tooltip else ""))
            b.setAutoRaise(True)
            b.setCheckable(cmd.checkable)
            b.clicked.connect(lambda _=False, i=cmd_id: self._run(i))
            col.addWidget(b)
            self._buttons[cmd_id] = b
        self.set_theme(theme)

    def button(self, cmd_id):
        return self._buttons.get(cmd_id)

    def _run(self, cmd_id):
        self._registry.run(cmd_id)
        self.refresh_checks()

    def refresh_checks(self):
        for cmd_id, b in self._buttons.items():
            cmd = self._registry.get(cmd_id)
            if cmd.checkable:
                b.setChecked(bool(cmd.is_checked and cmd.is_checked()))

    def set_theme(self, theme):
        p = themes.PALETTES[theme]
        for cmd_id, b in self._buttons.items():
            b.setIcon(themes.icon(self._registry.get(cmd_id).icon, theme))
        self.setStyleSheet(
            "QFrame#InCadNavStrip {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}"
            " QToolButton {{ border: none; border-radius: 5px; padding: 3px; }}"
            " QToolButton:hover, QToolButton:checked {{ background: {accent_soft}; }}".format(**p))

    def place(self, area_rect):
        self.adjustSize()
        self.move(area_rect.right() + 1 - self.width() - 14, area_rect.top() + 150)
        self.raise_()
