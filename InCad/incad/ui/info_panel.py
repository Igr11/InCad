"""Small floating panel with label/value rows (Inspect results)."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes


class InfoPanel(QtWidgets.QFrame):
    def __init__(self, title, rows, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadInfoPanel")
        self._rows = list(rows)
        col = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel(title)
        t.setObjectName("InCadDialogTitle")
        head.addWidget(t, 1)
        self.close_button = QtWidgets.QToolButton()
        self.close_button.setText("✕")
        self.close_button.clicked.connect(self.close)
        head.addWidget(self.close_button)
        col.addLayout(head)
        grid = QtWidgets.QGridLayout()
        for r, (label, value) in enumerate(self._rows):
            grid.addWidget(QtWidgets.QLabel(label), r, 0)
            v = QtWidgets.QLabel(value)
            v.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            grid.addWidget(v, r, 1)
        col.addLayout(grid)
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadInfoPanel {{ background: {panel}; border: 1px solid {border}; border-radius: 9px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; }}"
            " QToolButton {{ background: transparent; border: none; color: {text_dim}; }}".format(**p))

    def rows(self):
        return list(self._rows)
