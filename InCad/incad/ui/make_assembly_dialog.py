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

    def __init__(self, asm_name, rows, check, parent=None, existing=None):
        """check(asm, names, replace) -> why not ('' when fine); existing(asm, names) -> names whose files exist
        (an earlier Make Assembly made them): then "Replace existing files" is offered."""
        super().__init__(parent)
        self.setWindowTitle("Make Assembly")
        self._check = check
        self._existing = existing
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
        self.replace_box = QtWidgets.QCheckBox("Replace existing files")
        self.replace_box.setToolTip("Overwrite the files an earlier Make Assembly made (this part is never replaced)")
        self.replace_box.toggled.connect(self._validate)
        lay.addWidget(self.replace_box)
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

    def replace(self):
        return self.replace_box.isChecked() and not self.replace_box.isHidden()

    def _validate(self):
        there = self._existing(*self.names()) if self._existing is not None else []
        self.replace_box.setHidden(not there)
        if there:
            self.replace_box.setText("Replace existing files (%s)" % ", ".join(there))
        reason = self._check(*self.names(), replace=self.replace()) if self._existing is not None \
            else self._check(*self.names())
        self._error.setText(reason)
        self.ok_button.setEnabled(not reason)
