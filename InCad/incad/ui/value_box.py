"""Floating box to type a dimension's value or formula (Inventor's edit-dimension box). Enter applies, Esc cancels.
While it is open, clicking a dimension or a parameter inserts that name at the cursor."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class ValueBox(QtWidgets.QFrame):
    applied = Signal(str, str)
    closed = Signal()

    def __init__(self, name, text, theme="light", parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setObjectName("InCadValueBox")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.name = name
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.addWidget(QtWidgets.QLabel(name + " ="))
        self.edit = QtWidgets.QLineEdit(text)
        self.edit.setMinimumWidth(170)
        self.edit.selectAll()
        self.edit.returnPressed.connect(self._apply)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit)
        hint = QtWidgets.QLabel("Enter ✓  Esc ✕")
        hint.setObjectName("InCadValueHint")
        row.addWidget(hint)
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadValueBox {{ background: {panel}; border: 1px solid {accent}; border-radius: 8px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadValueHint {{ color: {text_dim}; font-size: 10px; }}"
            " QLineEdit {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 4px;"
            " padding: 2px 4px; }}".format(**p))

    def show_near(self, global_pos):
        self.adjustSize()
        self.move(global_pos + QtCore.QPoint(16, 16))
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def insert(self, name):
        self.edit.insert(name)
        self.edit.setFocus()

    def _apply(self):
        text = self.edit.text().strip()
        self.close()
        if text:
            self.applied.emit(self.name, text)

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self.close()
            return True
        return False

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
