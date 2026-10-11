"""The sketch's Constraints window: the list (type, what it ties, value), a filter header, Select all / Delete
selected / close. Rows come in as plain tuples (index, type, text, value, locked); no FreeCAD here."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class ConstraintsPanel(QtWidgets.QFrame):
    delete_requested = Signal(list)
    highlight = Signal(int)  # -1: nothing
    show_all = Signal()
    closed = Signal()

    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadConstraintsPanel")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        col = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel("")
        self.title.setObjectName("InCadDialogTitle")
        top.addWidget(self.title, 1)
        self.close_button = QtWidgets.QToolButton(self)
        self.close_button.setText("✕")
        self.close_button.clicked.connect(self.closed.emit)
        top.addWidget(self.close_button)
        col.addLayout(top)
        self.header = QtWidgets.QLabel("")
        col.addWidget(self.header)
        self.table = QtWidgets.QTreeWidget(self)
        self.table.setColumnCount(3)
        self.table.setHeaderHidden(True)
        self.table.setRootIsDecorated(False)
        self.table.setMinimumSize(360, 240)
        self.table.currentItemChanged.connect(self._current_changed)
        col.addWidget(self.table, 1)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        col.addWidget(self.message)
        row = QtWidgets.QHBoxLayout()
        self.select_all_button = QtWidgets.QPushButton("Select all", self)
        self.delete_button = QtWidgets.QPushButton("Delete selected", self)
        self.select_all_button.clicked.connect(self._select_all)
        self.delete_button.clicked.connect(self._delete)
        row.addWidget(self.select_all_button)
        row.addStretch(1)
        row.addWidget(self.delete_button)
        col.addLayout(row)
        self._theme = theme
        self.set_theme(theme)

    def set_theme(self, theme):
        self._theme = theme
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadConstraintsPanel {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; font-size: 14px; }}"
            " QTreeWidget {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; }}"
            " QPushButton, QToolButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " border-radius: 6px; padding: 4px 12px; }}".format(**p))

    # ----- content -----
    def set_rows(self, title, header, rows):
        keep = self.selected()
        self.title.setText(title)
        self.header.setText(header)
        self.table.blockSignals(True)
        self.table.clear()
        current = None
        for index, kind, text, value, locked in rows:
            item = QtWidgets.QTreeWidgetItem([("🔒 " if locked else "") + kind, text, value])
            item.setData(0, QtCore.Qt.UserRole, index)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.Unchecked)
            self.table.addTopLevelItem(item)
            if index == keep:
                current = item
        for c in range(3):
            self.table.resizeColumnToContents(c)
        self.table.setCurrentItem(current)
        self.table.blockSignals(False)
        if keep is not None and current is None:
            self.highlight.emit(-1)

    def set_message(self, text, ok=False):
        p = themes.PALETTES[self._theme]
        self.message.setStyleSheet("color: %s;" % (p["text"] if ok else p["error"]))
        self.message.setText(text)

    # ----- reading -----
    def _items(self):
        return [self.table.topLevelItem(i) for i in range(self.table.topLevelItemCount())]

    def _item(self, index):
        return next((it for it in self._items() if it.data(0, QtCore.Qt.UserRole) == index), None)

    def selected(self):
        it = self.table.currentItem()
        return it.data(0, QtCore.Qt.UserRole) if it is not None else None

    def checked(self):
        return [it.data(0, QtCore.Qt.UserRole) for it in self._items() if it.checkState(0) == QtCore.Qt.Checked]

    def select_index(self, index):
        self.table.setCurrentItem(self._item(index) if index is not None else None)

    def set_checked(self, index, on):
        it = self._item(index)
        if it is not None:
            it.setCheckState(0, QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)

    def title_text(self):
        return self.title.text()

    def header_text(self):
        return self.header.text()

    def message_text(self):
        return self.message.text()

    def row_texts(self):
        return [(it.text(0).replace("🔒 ", ""), it.text(1), it.text(2)) for it in self._items()]

    # ----- actions -----
    def _current_changed(self, item, _previous):
        self.highlight.emit(item.data(0, QtCore.Qt.UserRole) if item is not None else -1)

    def _select_all(self):
        for it in self._items():
            it.setCheckState(0, QtCore.Qt.Checked)

    def _delete(self):
        ids = self.checked() or ([self.selected()] if self.selected() is not None else [])
        if not ids:
            self.set_message("Check rows or select one first")
            return
        self.set_message("")
        self.delete_requested.emit(ids)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.show_all.emit()
            return
        super().keyPressEvent(event)
