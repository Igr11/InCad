"""The Parameters window (the ribbon's Parameters button; the user: it did nothing but put the keyboard on the small
panel). A window of its own, resizable, that stays open while the part is worked on: every parameter in one table —
Name, Value (a number or a formula), Result, Used by — dimensions and feature values first (accent; type a new name
to rename one), then the user's own. + adds a parameter, − removes the selected one, Delete Unused removes every
value nothing uses, Find narrows the list. Rows come in as plain tuples (kind, name, value, result, used by); the
shell applies the edits by the same rules as the panel under the browser. No FreeCAD here."""
from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes

NAME_ROLE = QtCore.Qt.UserRole        # the saved name (a rename compares with it)
KIND_ROLE = QtCore.Qt.UserRole + 1    # 'dimension', 'feature', 'user', or None for a row being added
COLUMNS = ("Name", "Value", "Result", "Used by")
_KIND_TIPS = {"dimension": "A sketch dimension — type a new name to rename it",
              "feature": "A feature value — type a new name to rename it",
              "user": "Your own parameter"}


class ParametersWindow(QtWidgets.QDialog):
    parameterSet = Signal(str, str)        # name, value or formula
    parameterRenamed = Signal(str, str)    # old, new
    parameterRemoved = Signal(str)
    parameterClicked = Signal(str)         # a name clicked: into the open value box or dialog field
    deleteUnusedRequested = Signal()
    closed = Signal()

    def __init__(self, theme="light", parent=None):
        super().__init__(parent, QtCore.Qt.Tool)  # above the main window, not modal
        self.setObjectName("InCadParametersWindow")
        self.setWindowTitle("Parameters")
        self._loading = False
        self._enabled = True
        self._rows = None
        self.finished.connect(lambda _=0: self.closed.emit())  # Close, Esc and the window's own close button
        col = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel("Parameters")
        self.title.setObjectName("InCadDialogTitle")
        top.addWidget(self.title, 1)
        self.find = QtWidgets.QLineEdit()
        self.find.setPlaceholderText("Find a name")
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(self._filter)
        top.addWidget(self.find)
        col.addLayout(top)
        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("InCadParamsTable")
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        head = self.table.horizontalHeader()
        for c in range(3):
            head.setSectionResizeMode(c, QtWidgets.QHeaderView.Interactive)
        head.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked
                                   | QtWidgets.QAbstractItemView.EditKeyPressed
                                   | QtWidgets.QAbstractItemView.AnyKeyPressed)
        self.table.itemChanged.connect(self._changed)
        self.table.cellClicked.connect(self._clicked)
        col.addWidget(self.table, 1)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        col.addWidget(self.message)
        row = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("+ Add")
        self.add_button.clicked.connect(self.add_row)
        self.remove_button = QtWidgets.QPushButton("− Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.unused_button = QtWidgets.QPushButton("Delete Unused")
        self.unused_button.setToolTip("Remove every parameter nothing uses (values left behind by deleted features)")
        self.unused_button.clicked.connect(self.deleteUnusedRequested.emit)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        for b in (self.add_button, self.remove_button, self.unused_button):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(close)
        col.addLayout(row)
        self.resize(640, 460)
        self._theme = theme
        self.set_theme(theme)

    def set_theme(self, theme):
        self._theme = theme
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QDialog#InCadParametersWindow {{ background: {panel}; color: {text}; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; font-size: 14px; }}"
            " QTableWidget {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " gridline-color: {border}; }}"
            " QTableWidget::item:selected {{ background: {accent}; color: {selection_text}; }}"
            " QHeaderView::section {{ background: {panel}; color: {text_dim}; border: none; padding: 2px 6px; }}"
            " QLineEdit {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 6px;"
            " padding: 3px 6px; }}"
            " QPushButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " border-radius: 6px; padding: 4px 12px; }}"
            " QPushButton:disabled {{ color: {text_dim}; }}".format(**p))
        if self._rows is not None:
            rows, self._rows = self._rows, None
            self.set_rows(rows, self._enabled)  # names in the new accent

    # ----- content -----
    def set_rows(self, rows, enabled=True):
        """rows: [(kind, name, value, result, used_by list)]. The same rows again leave the table alone (an edit in
        progress survives a refresh); a row being added stays below the others."""
        rows = [(k, n, v, r, tuple(u)) for k, n, v, r, u in rows]
        self._set_enabled(enabled)
        if rows == self._rows:
            return
        editing = self.table.state() == QtWidgets.QAbstractItemView.EditingState
        if editing and self._rows is not None:
            return  # the user is typing: the next refresh after the edit fills it in
        p = themes.PALETTES[self._theme]
        accent, dim = QtGui.QBrush(QtGui.QColor(p["accent"])), QtGui.QBrush(QtGui.QColor(p["text_dim"]))
        pending = self._pending_rows()
        selected = self.selected()
        self._rows = rows
        self._loading = True
        try:
            self.table.setRowCount(0)
            for kind, name, value, result, used in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                name_item = QtWidgets.QTableWidgetItem(name)
                name_item.setData(NAME_ROLE, name)
                name_item.setData(KIND_ROLE, kind)
                name_item.setToolTip(_KIND_TIPS[kind])
                if kind == "user":  # a user parameter keeps its name (the panel's rule)
                    name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
                else:
                    name_item.setForeground(accent)
                self.table.setItem(r, 0, name_item)
                self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(value))
                self.table.setItem(r, 2, self._readonly(result))
                users = self._readonly(", ".join(used) if used else "— not used")
                if not used:
                    users.setForeground(dim)
                users.setToolTip("\n".join(used) if used else "Nothing uses it: Delete Unused removes it")
                self.table.setItem(r, 3, users)
            for name, value in pending:
                self._append_new(name, value)
        finally:
            self._loading = False
        for c in range(3):
            self.table.resizeColumnToContents(c)
        self.select(selected)
        self._filter(self.find.text())

    def _set_enabled(self, enabled):
        """Parameters are edited only in an InCad part or assembly (never added to a plain FreeCAD file)."""
        self._enabled = enabled
        for b in (self.add_button, self.remove_button, self.unused_button):
            b.setEnabled(enabled)
        self.add_button.setToolTip("Add a parameter" if enabled else "Open or create an InCad part to add parameters")

    def set_message(self, text, ok=False):
        p = themes.PALETTES[self._theme]
        self.message.setStyleSheet("color: %s;" % (p["text"] if ok else p["error"]))
        self.message.setText(text)

    @staticmethod
    def _readonly(text):
        item = QtWidgets.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item

    def _pending_rows(self):
        out = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None and item.data(KIND_ROLE) is None:
                value = self.table.item(r, 1)
                out.append((item.text(), value.text() if value is not None else ""))
        return out

    def _append_new(self, name="", value=""):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(value))
        self.table.setItem(r, 2, self._readonly(""))
        self.table.setItem(r, 3, self._readonly(""))
        return r

    # ----- reading -----
    def row_texts(self):
        def text(r, c):
            item = self.table.item(r, c)
            return item.text() if item else ""
        return [tuple(text(r, c) for c in range(len(COLUMNS))) for r in range(self.table.rowCount())]

    def visible_names(self):
        return [self.table.item(r, 0).text() for r in range(self.table.rowCount()) if not self.table.isRowHidden(r)]

    def selected(self):
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        return (item.data(NAME_ROLE) or item.text()) if item is not None else None

    def select(self, name):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if name and item is not None and (item.data(NAME_ROLE) or item.text()) == name:
                self.table.setCurrentCell(r, 0)
                return

    # ----- actions -----
    def add_row(self):
        if not self._enabled:
            return -1
        self._loading = True
        try:
            self.find.clear()
            r = self._append_new()
        finally:
            self._loading = False
        self.table.setCurrentCell(r, 0)
        self.table.setFocus()
        self.table.editItem(self.table.item(r, 0))  # the name first; Tab goes on to Value
        return r

    def remove_selected(self):
        if not self._enabled:
            return
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        if item is None:
            self.set_message("Select a parameter first")
            return
        if item.data(KIND_ROLE) is None:  # a row not saved yet
            self.table.removeRow(r)
            return
        self.set_message("")
        self.parameterRemoved.emit(item.data(NAME_ROLE))  # the shell refuses a value still in use

    def _changed(self, item):
        if self._loading or not self._enabled:
            return
        r = item.row()
        name_item, value_item = self.table.item(r, 0), self.table.item(r, 1)
        if name_item is None:
            return
        kind = name_item.data(KIND_ROLE)
        if item.column() == 0 and kind in ("dimension", "feature"):
            old, new = name_item.data(NAME_ROLE), name_item.text().strip()
            if new and new != old:
                self.set_message("")
                self.parameterRenamed.emit(old, new)
            return
        name = name_item.data(NAME_ROLE) or name_item.text().strip()
        value = value_item.text().strip() if value_item is not None else ""
        if name and value and item.column() in (0, 1):
            self.set_message("")
            self.parameterSet.emit(name, value)

    def _clicked(self, row, column):
        item = self.table.item(row, 0)
        if column == 0 and item is not None and item.data(KIND_ROLE) is not None:
            self.parameterClicked.emit(item.data(NAME_ROLE))

    def _filter(self, text):
        text = (text or "").strip().lower()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            new = item is None or item.data(KIND_ROLE) is None
            self.table.setRowHidden(r, bool(text) and not new and text not in item.text().lower())

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            return  # Enter ends a cell's edit; it never closes the window
        super().keyPressEvent(event)
