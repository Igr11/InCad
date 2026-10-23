"""Appearance (incad.core.appearance): a compact window for the picked Solids or faces — a colour from the palette
or any colour (More…), a finish, Hide Edges — shown on the part as it is chosen; OK keeps it as one undo step,
Cancel (Esc) puts the part back as it was."""
from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes


def _hex(color):
    return QtGui.QColor.fromRgbF(*color[:3]).name()


class AppearanceDialog(QtWidgets.QDialog):
    changed = Signal()  # a choice changed: the owner previews it

    def __init__(self, title, color, finish, edges, edges_mixed=False, theme="light", parent=None, texture="None"):
        super().__init__(parent)
        self.setObjectName("InCadAppearance")
        self.setWindowTitle("Appearance")
        self.color, self.finish = tuple(color[:3]), finish
        self.reset_asked = False
        self.color_chosen = self.finish_chosen = False  # untouched: each target keeps its own
        p = themes.PALETTES[theme]
        col = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QLabel(title)
        head.setObjectName("InCadDialogTitle")
        col.addWidget(head)

        grid = QtWidgets.QGridLayout()
        grid.setSpacing(4)
        from incad.core import appearance
        self.swatches = []
        for i, c in enumerate(appearance.PALETTE):
            b = QtWidgets.QToolButton()
            b.setObjectName("InCadSwatch")
            b.setFixedSize(26, 26)
            b.setToolTip(_hex(c))
            b.setStyleSheet("QToolButton {{ background: {0}; border: 1px solid {1}; border-radius: 4px; }}"
                            " QToolButton:hover {{ border: 2px solid {2}; }}".format(_hex(c), p["border"],
                                                                                     p["accent"]))
            b.clicked.connect(lambda _=False, c=c: self.set_color(c))
            grid.addWidget(b, i // 8, i % 8)
            self.swatches.append((c, b))
        col.addLayout(grid)
        row = QtWidgets.QHBoxLayout()
        self.current = QtWidgets.QLabel()
        self.current.setFixedSize(44, 22)
        row.addWidget(QtWidgets.QLabel("Colour"))
        row.addWidget(self.current)
        more = QtWidgets.QPushButton("More…")
        more.setObjectName("InCadColorMore")
        more.clicked.connect(self._more)
        row.addWidget(more)
        row.addStretch(1)
        col.addLayout(row)

        finishes = QtWidgets.QHBoxLayout()
        finishes.setSpacing(2)
        self.finish_buttons = {}
        group = QtWidgets.QButtonGroup(self)
        for name in appearance.FINISHES:
            b = QtWidgets.QToolButton()
            b.setText(name)
            b.setCheckable(True)
            b.setChecked(name == finish)
            b.setObjectName("InCadFinish")
            b.clicked.connect(lambda _=False, n=name: self.set_finish(n))
            group.addButton(b)
            finishes.addWidget(b)
            self.finish_buttons[name] = b
        col.addLayout(finishes)

        from incad.core import textures
        tex_row = QtWidgets.QHBoxLayout()
        tex_row.setSpacing(2)
        tex_row.addWidget(QtWidgets.QLabel("Texture  "))
        self.texture, self.texture_chosen = texture, False
        self.texture_buttons = {}
        group = QtWidgets.QButtonGroup(self)
        for name in textures.NAMES:
            b = QtWidgets.QToolButton()
            b.setText(name)
            b.setCheckable(True)
            b.setChecked(name == texture)
            b.setObjectName("InCadFinish")
            b.setToolTip("No texture" if name == "None" else "%s over the colour (the whole Solid)" % name)
            b.clicked.connect(lambda _=False, n=name: self.set_texture(n))
            group.addButton(b)
            tex_row.addWidget(b)
            self.texture_buttons[name] = b
        tex_row.addStretch(1)
        col.addLayout(tex_row)

        self.edges = QtWidgets.QCheckBox("Hide Edges")
        self.edges.setToolTip("Draw the Solid without its edge lines (the whole Solid)")
        self.edges.setTristate(edges_mixed)
        self.edges.setCheckState(QtCore.Qt.PartiallyChecked if edges_mixed else
                                 QtCore.Qt.Unchecked if edges else QtCore.Qt.Checked)
        self.edges.stateChanged.connect(lambda *_: (self.edges.setTristate(False), self.changed.emit()))
        col.addWidget(self.edges)

        buttons = QtWidgets.QHBoxLayout()
        self.reset_button = QtWidgets.QPushButton("Reset")
        self.reset_button.setToolTip("Back to the material's colour (picked faces: back to the Solid's)")
        self.reset_button.clicked.connect(self._reset)
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button = QtWidgets.QPushButton("OK")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.ok_button)
        col.addLayout(buttons)
        self._show_color()
        self.setStyleSheet(
            "QDialog#InCadAppearance {{ background: {panel}; }} QLabel, QCheckBox {{ color: {text}; }}"
            " QLabel#InCadDialogTitle {{ font-weight: 600; font-size: 13px; }}"
            " QToolButton#InCadFinish {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " padding: 3px 7px; }} QToolButton#InCadFinish:checked {{ background: {accent}; color: {selection_text}; }}"
            " QPushButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 6px;"
            " padding: 3px 14px; }} QPushButton:default {{ background: {accent}; color: {selection_text}; }}"
            .format(**p))
        self._border = p["border"]

    def hide_edges(self):
        """True / False, or None while left mixed (each Solid keeps its own)."""
        s = self.edges.checkState()
        return None if s == QtCore.Qt.PartiallyChecked else s == QtCore.Qt.Checked

    def set_color(self, color):
        self.color = tuple(color[:3])
        self.color_chosen, self.reset_asked = True, False
        self._show_color()
        self.changed.emit()

    def set_finish(self, name):
        self.finish = name
        self.finish_chosen, self.reset_asked = True, False
        for n, b in self.finish_buttons.items():
            b.setChecked(n == name)
        self.changed.emit()

    def set_texture(self, name):
        self.texture = name
        self.texture_chosen, self.reset_asked = True, False
        for n, b in self.texture_buttons.items():
            b.setChecked(n == name)
        self.changed.emit()

    def _show_color(self):
        self.current.setStyleSheet("background: %s; border: 1px solid %s; border-radius: 4px;"
                                   % (_hex(self.color), getattr(self, "_border", "#888")))

    def _more(self):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor.fromRgbF(*self.color), self, "Colour")
        if c.isValid():
            self.set_color((c.redF(), c.greenF(), c.blueF()))

    def _reset(self):
        self.reset_asked = True
        self.color_chosen = self.finish_chosen = self.texture_chosen = False
        for n, b in self.texture_buttons.items():
            b.setChecked(n == "None")
        self.edges.blockSignals(True)  # the edges come back too
        self.edges.setTristate(False)
        self.edges.setCheckState(QtCore.Qt.Unchecked)
        self.edges.blockSignals(False)
        self.changed.emit()
