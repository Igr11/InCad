"""Make Assembly: one dialog with the names of the assembly and of each piece (filled in), each piece's volume;
hovering a row highlights that piece on the view (the shell connects `hovered`)."""
from incad.qt import QtCore, QtWidgets, Signal


class _Row(QtWidgets.QWidget):
    entered = Signal()
    left = Signal()

    def enterEvent(self, event):
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.left.emit()
        super().leaveEvent(event)


class MakeAssemblyDialog(QtWidgets.QDialog):
    hovered = Signal(int)

    def __init__(self, asm_name, rows, check, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Make Assembly")
        self._check = check
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Each piece becomes a part file (with its history) in the part's folder;\n"
                                       "the assembly links them where they are. This part stays as it is."))
        form = QtWidgets.QFormLayout()
        self._asm = QtWidgets.QLineEdit(asm_name)
        form.addRow("Assembly", self._asm)
        self._fields = []
        for i, (name, volume) in enumerate(rows):
            row = _Row(self)
            h = QtWidgets.QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            field = QtWidgets.QLineEdit(name)
            h.addWidget(field, 1)
            h.addWidget(QtWidgets.QLabel(volume))
            row.entered.connect(lambda i=i: self.hover_row(i))
            row.left.connect(lambda: self.hover_row(-1))
            form.addRow("Piece %d%s" % (i + 1, " (grounded)" if i == 0 else ""), row)
            self._fields.append(field)
        lay.addLayout(form)
        self._error = QtWidgets.QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet("color: #c0392b;")
        lay.addWidget(self._error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        for f in [self._asm] + self._fields:
            f.textChanged.connect(self._validate)
        self._validate()

    def name_field(self, i):
        return self._fields[i]

    def names(self):
        return self._asm.text().strip(), [f.text().strip() for f in self._fields]

    def error_text(self):
        return self._error.text()

    def hover_row(self, i):
        self.hovered.emit(i)

    def _validate(self):
        reason = self._check(*self.names())
        self._error.setText(reason)
        self.ok_button.setEnabled(not reason)
