"""Floating box to type a dimension's value or formula (Inventor's edit-dimension box). Enter applies, Esc cancels.
While it is open, clicking a dimension or a parameter inserts that name at the cursor."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class ValueBox(QtWidgets.QFrame):
    applied = Signal(str, str)
    closed = Signal()

    def __init__(self, name, text, theme="light", parent=None, apply=None):
        # a panel inside the main window (as the feature dialogs), not a window of its own: macOS gives the
        # keyboard back to a separate window unreliably once the 3D view was clicked (the Dimension tool's
        # placing click), so typing, Enter and Esc went to the view
        super().__init__(parent)
        self.setObjectName("InCadValueBox")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.name = name
        self._apply_fn = apply  # apply(name, text) -> (ok, error); the box stays open and red on error
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(8, 6, 8, 6)
        row = QtWidgets.QHBoxLayout()
        col.addLayout(row)
        row.addWidget(QtWidgets.QLabel(name + " ="))
        self.edit = QtWidgets.QLineEdit(text)
        self.edit.setMinimumWidth(170)
        self.edit.selectAll()
        self._typed = False  # until the user types, taking the keyboard selects the value (typing replaces it)
        self.edit.textEdited.connect(lambda _t: setattr(self, "_typed", True))
        self.edit.returnPressed.connect(self._apply)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit)
        hint = QtWidgets.QLabel("Enter ✓  Esc ✕")
        hint.setObjectName("InCadValueHint")
        row.addWidget(hint)
        self._error = QtWidgets.QLabel("")
        self._error.setObjectName("InCadValueError")
        self._error.hide()
        col.addWidget(self._error)
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadValueBox {{ background: {panel}; border: 1px solid {accent}; border-radius: 8px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadValueError {{ color: {error}; }} QLabel#InCadValueHint {{ color: {text_dim}; font-size: 10px; }}"
            " QLineEdit {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 4px;"
            " padding: 2px 4px; }}".format(**p))

    def show_near(self, global_pos):
        self.adjustSize()
        parent = self.parentWidget()
        pos = parent.mapFromGlobal(global_pos + QtCore.QPoint(16, 16)) if parent is not None else global_pos
        if parent is not None:  # stay inside the view
            pos.setX(max(0, min(pos.x(), parent.width() - self.width())))
            pos.setY(max(0, min(pos.y(), parent.height() - self.height())))
        self.move(pos)
        self.show()
        self.take_keyboard()

    def take_keyboard(self):
        try:
            self.raise_()
            self.window().activateWindow()
            self.edit.setFocus(QtCore.Qt.OtherFocusReason)
            if not self._typed:
                self.edit.selectAll()
        except RuntimeError:
            pass

    def insert(self, name):
        self.edit.insert(name)
        self._typed = True
        self.take_keyboard()  # a click in the view or the table took the keyboard

    def _apply(self):
        text = self.edit.text().strip()
        if not text:
            self.close()
            return
        if self._apply_fn is not None:
            ok, error = self._apply_fn(self.name, text)
            if not ok:
                self.set_error(error or "This value cannot be used")
                return
            self.close()
            return
        self.close()
        self.applied.emit(self.name, text)

    def set_error(self, text):
        self._error.setText(text)
        self._error.setVisible(bool(text))
        self.edit.setStyleSheet("border: 1px solid #d0021b;" if text else "")
        self.adjustSize()
        self.edit.setFocus()

    def error_text(self):
        return self._error.text()

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self.close()
            return True
        return False

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
