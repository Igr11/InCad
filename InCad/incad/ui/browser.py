"""Model Browser: the feature tree (with a draggable End of Part marker) and the Parameters table."""
from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes

NAME_ROLE = QtCore.Qt.UserRole
KIND_ROLE = QtCore.Qt.UserRole + 1
STATE_ROLE = QtCore.Qt.UserRole + 2

KIND_ICONS = {"part": "part", "origin": "origin", "feature": "feature", "sketch": "sketch",
              "end_of_part": "end_of_part", "solids": "solids", "body": "part"}


class _Tree(QtWidgets.QTreeWidget):
    """Tree that lets the user drag the End of Part marker onto another row."""

    def __init__(self, browser):
        super().__init__(browser)
        self._browser = browser
        self._dragging = False

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        self._dragging = item is not None and item.data(0, KIND_ROLE) == "end_of_part"
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            target = self.itemAt(event.position().toPoint())
            if target is not None and target.data(0, KIND_ROLE) != "end_of_part":
                self._browser.drop_end_of_part_on(target)
        super().mouseReleaseEvent(event)


class ModelBrowser(QtWidgets.QWidget):
    featureActivated = Signal(str)
    endOfPartMoved = Signal(str)
    actionTriggered = Signal(str)
    parameterSet = Signal(str, str)
    parameterRemoved = Signal(str)

    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadBrowser")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._theme = theme
        self._nodes = []
        self._loading = False
        self._params_enabled = True
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        header = QtWidgets.QLabel("MODEL")
        header.setObjectName("InCadPanelHeader")
        col.addWidget(header)
        self.tree = _Tree(self)
        self.tree.setObjectName("InCadTree")
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        col.addWidget(self.tree, 3)
        bar = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 4, 0)
        label = QtWidgets.QLabel("PARAMETERS")
        label.setObjectName("InCadPanelHeader")
        row.addWidget(label, 1)
        self.add_button = QtWidgets.QToolButton()
        self.add_button.setText("+")
        self.add_button.setToolTip("Add parameter")
        self.add_button.clicked.connect(self.add_parameter_row)
        self.remove_button = QtWidgets.QToolButton()
        self.remove_button.setText("−")
        self.remove_button.setToolTip("Remove selected parameter")
        self.remove_button.clicked.connect(self.remove_selected_parameter)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        col.addWidget(bar)
        self.params = QtWidgets.QTableWidget(0, 3)
        self.params.setObjectName("InCadParams")
        self.params.setHorizontalHeaderLabels(["Name", "Value", "Result"])
        self.params.verticalHeader().hide()
        self.params.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)  # fit the panel
        self.params.itemChanged.connect(self._on_param_changed)
        col.addWidget(self.params, 1)

    # ----- tree -----
    def set_nodes(self, nodes):
        self._nodes = nodes
        self.tree.clear()
        for node in nodes:
            self.tree.addTopLevelItem(self._item(node))
        self.tree.expandAll()
        for item in self._items():
            if item.data(0, KIND_ROLE) == "origin":
                item.setExpanded(False)

    def _item(self, node):
        item = QtWidgets.QTreeWidgetItem([node.label])
        item.setData(0, NAME_ROLE, node.name)
        item.setData(0, KIND_ROLE, node.kind)
        item.setData(0, STATE_ROLE, node.state)
        icon = self._icon_name(node)
        if icon:
            item.setIcon(0, themes.icon(icon, self._theme))
        p = themes.PALETTES[self._theme]
        color = None
        if node.state == "error":
            color = p["error"]
        elif node.state in ("rolled_back", "suppressed"):
            color = p["rolled_back"]
        if node.kind == "end_of_part":
            color = p["eop"]
        elif node.kind == "action":
            color = p["accent"]
        if color:
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
        font = item.font(0)
        font.setStrikeOut(node.state == "suppressed")
        font.setBold(node.kind == "end_of_part")
        item.setFont(0, font)
        if node.tooltip:
            item.setToolTip(0, node.tooltip)
        for child in node.children:
            item.addChild(self._item(child))
        return item

    @staticmethod
    def _icon_name(node):
        if node.kind == "origin_item":
            return "plane" if "Plane" in node.label else "axis" if "Axis" in node.label else "point"
        return KIND_ICONS.get(node.kind)

    def _items(self):
        out = []

        def walk(item):
            out.append(item)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _depth(self, item):
        d = 0
        while item.parent() is not None:
            item = item.parent()
            d += 1
        return d

    def tree_rows(self):
        return [(self._depth(i), i.text(0), i.data(0, KIND_ROLE), i.data(0, STATE_ROLE)) for i in self._items()]

    def item_by_label(self, label):
        for item in self._items():
            if item.text(0) == label:
                return item
        return None

    def _top_feature(self, item):
        """The feature row an item belongs to: a direct child of the part row or of a solid-body row."""
        while item.parent() is not None and item.parent().data(0, KIND_ROLE) not in ("part", "body"):
            item = item.parent()
        return item

    def drop_end_of_part_on(self, item):
        """End of Part goes after the row's feature; origin/solids/part rows put it before the first feature."""
        top = self._top_feature(item)
        kind = top.data(0, KIND_ROLE)
        if kind in ("feature", "sketch"):
            self.endOfPartMoved.emit(top.data(0, NAME_ROLE))
        elif kind in ("origin", "solids", "part"):
            self.endOfPartMoved.emit("")

    def context_actions(self, item):
        kind = item.data(0, KIND_ROLE)
        if kind not in ("feature", "sketch"):
            return []
        name = item.data(0, NAME_ROLE)
        return [("Edit", lambda: self.featureActivated.emit(name)),
                ("Move End of Part Here", lambda: self.drop_end_of_part_on(item))]

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        actions = self.context_actions(item) if item is not None else []
        if not actions:
            return
        menu = QtWidgets.QMenu(self)
        for text, fn in actions:
            menu.addAction(text).triggered.connect(lambda _=False, f=fn: f())
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _on_double_click(self, item, _column=0):
        kind = item.data(0, KIND_ROLE)
        if kind in ("feature", "sketch"):
            self.featureActivated.emit(item.data(0, NAME_ROLE))
        elif kind == "action":
            self.actionTriggered.emit(item.data(0, NAME_ROLE))

    # ----- parameters -----
    def _readonly(self, text):
        item = QtWidgets.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item

    def set_parameters(self, rows):
        self._loading = True
        try:
            self.params.setRowCount(0)
            for name, formula, value in rows:
                r = self.params.rowCount()
                self.params.insertRow(r)
                self.params.setItem(r, 0, self._readonly(name))
                self.params.setItem(r, 1, QtWidgets.QTableWidgetItem(formula or value))
                self.params.setItem(r, 2, self._readonly(value))
        finally:
            self._loading = False

    def parameter_rows(self):
        def text(r, c):
            item = self.params.item(r, c)
            return item.text() if item else ""
        return [(text(r, 0), text(r, 1), text(r, 2)) for r in range(self.params.rowCount())]

    def set_parameters_enabled(self, enabled):
        """Parameters can only be edited in an InCad part (never add objects to a plain FreeCAD file)."""
        self._params_enabled = enabled
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.params.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed
                                    if enabled else QtWidgets.QAbstractItemView.NoEditTriggers)

    def add_parameter_row(self):
        if not self._params_enabled:
            return -1
        self._loading = True
        try:
            r = self.params.rowCount()
            self.params.insertRow(r)
            self.params.setItem(r, 0, QtWidgets.QTableWidgetItem(""))
            self.params.setItem(r, 1, QtWidgets.QTableWidgetItem(""))
            self.params.setItem(r, 2, self._readonly(""))
        finally:
            self._loading = False
        self.params.setCurrentCell(r, 0)
        return r

    def _on_param_changed(self, item):
        if self._loading or not self._params_enabled:
            return
        r = item.row()
        name_item, value_item = self.params.item(r, 0), self.params.item(r, 1)
        name = name_item.text().strip() if name_item else ""
        value = value_item.text().strip() if value_item else ""
        if name and value:
            self.parameterSet.emit(name, value)

    def remove_selected_parameter(self):
        if not self._params_enabled:
            return
        r = self.params.currentRow()
        if r < 0:
            return
        item = self.params.item(r, 0)
        saved = item is not None and not bool(item.flags() & QtCore.Qt.ItemIsEditable)
        if saved:
            self.parameterRemoved.emit(item.text())
        else:
            self.params.removeRow(r)

    def focus_parameters(self):
        self.params.setFocus()

    def set_theme(self, theme):
        self._theme = theme
        self.set_nodes(self._nodes)
