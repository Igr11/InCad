"""Inventor-style Save dialog for closing or quitting: every changed file with a Save tick, then Save / Don't Save /
Cancel. Themed like the rest of InCad (FreeCAD's plain per-document question looked out of place)."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes


class SaveDialog(QtWidgets.QDialog):
    def __init__(self, files, theme="light", parent=None, action="closing"):
        """files: [(name, path or '')] — a file without a path is saved with Save As."""
        super().__init__(parent)
        self.setObjectName("InCadSaveDialog")
        self.setWindowTitle("Save")
        self.setModal(True)
        self._choice = ("cancel", [])
        col = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Save changes before %s?" % action)
        title.setObjectName("InCadDialogTitle")
        col.addWidget(title)
        self.table = QtWidgets.QTableWidget(len(files), 2, self)
        self.table.setHorizontalHeaderLabels(["Save", "File"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._names = []
        for r, (name, path) in enumerate(files):
            tick = QtWidgets.QTableWidgetItem()
            tick.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            tick.setCheckState(QtCore.Qt.Checked)
            self.table.setItem(r, 0, tick)
            item = QtWidgets.QTableWidgetItem(name + ("" if path else "  (new — Save As)"))
            item.setToolTip(path or "Not saved yet")
            self.table.setItem(r, 1, item)
            self._names.append(name)
        self.table.resizeColumnToContents(0)
        self.table.setMinimumWidth(420)
        self.table.setMaximumHeight(36 + 30 * max(1, len(files)))
        col.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        self.dont_save_button = QtWidgets.QPushButton("Don't Save")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.save_button = QtWidgets.QPushButton("Save")
        self.save_button.setDefault(True)
        row.addWidget(self.dont_save_button)
        row.addStretch(1)
        row.addWidget(self.cancel_button)
        row.addWidget(self.save_button)
        col.addLayout(row)
        self.save_button.clicked.connect(self._save)
        self.dont_save_button.clicked.connect(lambda: self._done(("discard", [])))
        self.cancel_button.clicked.connect(lambda: self._done(("cancel", [])))
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QDialog#InCadSaveDialog {{ background: {panel}; }} QLabel {{ color: {text}; }}"
            " QLabel#InCadDialogTitle {{ font-weight: 600; font-size: 14px; }}"
            " QTableWidget {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " gridline-color: {border}; }} QHeaderView::section {{ background: {panel}; color: {text_dim};"
            " border: none; padding: 3px; }}"
            " QPushButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 6px;"
            " padding: 4px 16px; }} QPushButton:default {{ background: {accent}; color: {selection_text}; }}"
            .format(**p))

    def rows(self):
        return [(n, self.table.item(r, 0).checkState() == QtCore.Qt.Checked) for r, n in enumerate(self._names)]

    def set_checked(self, name, on):
        r = self._names.index(name)
        self.table.item(r, 0).setCheckState(QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)

    def _save(self):
        self._done(("save", [n for n, on in self.rows() if on]))

    def _done(self, choice):
        self._choice = choice
        (self.reject if choice[0] == "cancel" else self.accept)()

    def result_choice(self):
        return self._choice
