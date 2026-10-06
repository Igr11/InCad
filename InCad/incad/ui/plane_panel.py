"""Small panel shown while a sketch plane is being picked: the origin planes as buttons (and Cancel)."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes

PLANES = (("XY_Plane", "XY · Top"), ("XZ_Plane", "XZ · Front"), ("YZ_Plane", "YZ · Right"))


class PlanePanel(QtWidgets.QFrame):
    picked = Signal(str)
    cancelled = Signal()

    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadPlanePanel")
        col = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("New sketch on")
        title.setObjectName("InCadDialogTitle")
        col.addWidget(title)
        hint = QtWidgets.QLabel("a plane below, or click a plane or a flat face")
        col.addWidget(hint)
        row = QtWidgets.QHBoxLayout()
        self._buttons = {}
        for role, label in PLANES:
            b = QtWidgets.QPushButton(label, self)
            b.clicked.connect(lambda _=False, r=role: self.picked.emit(r))
            row.addWidget(b)
            self._buttons[role] = b
        col.addLayout(row)
        cancel = QtWidgets.QPushButton("Cancel", self)
        cancel.clicked.connect(self.cancelled.emit)
        col.addWidget(cancel, 0, QtCore.Qt.AlignRight)
        self.set_theme(theme)

    def button(self, role):
        return self._buttons[role]

    def set_theme(self, theme):
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadPlanePanel {{ background: {panel}; border: 1px solid {border}; border-radius: 9px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; }}"
            " QPushButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 6px;"
            " padding: 4px 12px; }} QPushButton:hover {{ border-color: {accent}; }}".format(**p))
