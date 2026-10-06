"""Section view controls (Inventor's slice): offset along the plane's normal, flip, done / off."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class SectionPanel(QtWidgets.QFrame):
    changed = Signal(float, bool)  # offset (mm), flipped
    done = Signal()
    off = Signal()

    def __init__(self, theme="light", parent=None, reach=50.0):
        super().__init__(parent)
        self.setObjectName("InCadSectionPanel")
        col = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Section")
        title.setObjectName("InCadDialogTitle")
        col.addWidget(title)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Offset"))
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider.setRange(-int(reach * 10), int(reach * 10))  # tenths of a mm
        self.slider.setValue(0)
        self.slider.setMinimumWidth(180)
        row.addWidget(self.slider, 1)
        self.offset = QtWidgets.QDoubleSpinBox(self)
        self.offset.setRange(-10000.0, 10000.0)
        self.offset.setDecimals(2)
        self.offset.setSuffix(" mm")
        self.offset.setSingleStep(1.0)
        row.addWidget(self.offset)
        col.addLayout(row)
        row2 = QtWidgets.QHBoxLayout()
        self.flip = QtWidgets.QCheckBox("Flip", self)
        row2.addWidget(self.flip)
        row2.addStretch(1)
        self.off_button = QtWidgets.QPushButton("Off", self)
        self.done_button = QtWidgets.QPushButton("Done", self)
        self.done_button.setDefault(True)
        row2.addWidget(self.off_button)
        row2.addWidget(self.done_button)
        col.addLayout(row2)
        self._syncing = False
        self.slider.valueChanged.connect(self._from_slider)
        self.offset.valueChanged.connect(self._from_spin)
        self.flip.toggled.connect(lambda _on: self._emit())
        self.done_button.clicked.connect(self.done.emit)
        self.off_button.clicked.connect(self.off.emit)
        self.set_theme(theme)

    def set_theme(self, theme):
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadSectionPanel {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; font-size: 14px; }}"
            " QCheckBox {{ color: {text}; }} QDoubleSpinBox {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " border-radius: 4px; padding: 2px 4px; }} QPushButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " border-radius: 6px; padding: 4px 14px; }} QPushButton:default {{ background: {accent}; color: {selection_text}; }}".format(**p))

    def _from_slider(self, tenths):
        if self._syncing:
            return
        self._syncing = True
        self.offset.setValue(tenths / 10.0)
        self._syncing = False
        self._emit()

    def _from_spin(self, value):
        if self._syncing:
            return
        self._syncing = True
        self.slider.setValue(int(round(max(min(value, self.slider.maximum() / 10.0), self.slider.minimum() / 10.0) * 10)))
        self._syncing = False
        self._emit()

    def _emit(self):
        self.changed.emit(float(self.offset.value()), bool(self.flip.isChecked()))

    def values(self):
        return float(self.offset.value()), bool(self.flip.isChecked())
