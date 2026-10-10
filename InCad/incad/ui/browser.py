"""Model Browser: the feature tree (with a draggable End of Part marker) and the Parameters table."""
from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes

NAME_ROLE = QtCore.Qt.UserRole
KIND_ROLE = QtCore.Qt.UserRole + 1
STATE_ROLE = QtCore.Qt.UserRole + 2
LABEL_ROLE = QtCore.Qt.UserRole + 3
PARAM_KIND_ROLE = QtCore.Qt.UserRole + 4

# double-click, Enter/F2, or simply start typing on a selected cell
EDIT_TRIGGERS = (QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed
                 | QtWidgets.QAbstractItemView.AnyKeyPressed | QtWidgets.QAbstractItemView.SelectedClicked)

KIND_ICONS = {"part": "part", "origin": "origin", "feature": "feature", "sketch": "sketch",
              "end_of_part": "end_of_part", "solids": "solids", "body": "part", "assembly": "assembly",
              "component": "part", "relationships": "mate", "joint": "mate"}


class _TypingFirst(QtCore.QObject):
    """Plain typed keys belong to the widget (table cell, tree search), never to InCad's single-key shortcuts."""

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.ShortcutOverride:
            mods = event.modifiers() & ~QtCore.Qt.ShiftModifier & ~QtCore.Qt.KeypadModifier
            if mods == QtCore.Qt.NoModifier and event.text() and event.text().isprintable():
                event.accept()
                return True
        return False


class _Tree(QtWidgets.QTreeWidget):
    """Tree that lets the user drag the End of Part marker onto another row. While dragging, a line shows where
    it will land: on the upper half of a feature row it goes before that feature, lower half (or any of the
    feature's child rows) after it (Inventor drops the marker between rows)."""

    def __init__(self, browser):
        super().__init__(browser)
        self._browser = browser
        self._dragging = False
        self._drop = None  # (item, above) under the pointer while dragging, for the drop line

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        self._dragging = item is not None and item.data(0, KIND_ROLE) == "end_of_part"
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._drop = self.drop_target(event.position().toPoint())
            self.viewport().update()
            return  # no rubber-band selection while the marker is carried
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._drop = None
            self.viewport().update()
            target, above = self.drop_target(event.position().toPoint())
            if target is not None:
                self._browser.drop_end_of_part_on(target, above)
        super().mouseReleaseEvent(event)

    def drop_target(self, pos):
        """(row under pos, pointer in its upper half) for a drop of End of Part; (None, False) off the rows."""
        item = self.itemAt(pos)
        if item is None or item.data(0, KIND_ROLE) == "end_of_part":
            return None, False
        rect = self.visualItemRect(item)
        return item, pos.y() < rect.center().y()

    def paintEvent(self, event):
        super().paintEvent(event)
        item, above = self._drop or (None, False)
        if item is None:
            return
        top = self._browser._top_feature(item)
        line_item = top if (above and item is top) else item
        rect = self.visualItemRect(line_item)
        if not rect.isValid():
            return
        y = rect.top() + 1 if (above and item is top) else rect.bottom()
        painter = QtGui.QPainter(self.viewport())
        pen = QtGui.QPen(QtGui.QColor(themes.PALETTES.get(getattr(self._browser, "_theme", "light"),
                                                         themes.PALETTES["light"])["accent"]), 2)
        painter.setPen(pen)
        painter.drawLine(rect.left(), y, self.viewport().width() - 4, y)
        painter.end()


class ModelBrowser(QtWidgets.QWidget):
    featureActivated = Signal(str)
    featureSelected = Signal(str)  # a single click on a row: selects it in the model (picks for dialogs)
    endOfPartMoved = Signal(str)
    actionTriggered = Signal(str)
    parameterSet = Signal(str, str)
    parameterRemoved = Signal(str)
    parameterRenamed = Signal(str, str)
    parameterClicked = Signal(str)
    markingMenuRequested = Signal(str, QtCore.QPoint)  # object name, global position

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
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # Shift/Cmd: Hide / Show on all
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.itemClicked.connect(self._on_click)
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
        self.params.setEditTriggers(EDIT_TRIGGERS)
        self.params.itemChanged.connect(self._on_param_changed)
        self.params.cellClicked.connect(self._on_param_clicked)
        self._typing_first = _TypingFirst(self)
        for w in (self.params, self.tree):
            w.installEventFilter(self._typing_first)
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
        item = QtWidgets.QTreeWidgetItem([node.label + ("    " + node.detail if node.detail else "")])
        item.setData(0, LABEL_ROLE, node.label)
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
        elif node.state == "hidden":
            color = p["text_dim"]
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
        return [(self._depth(i), i.data(0, LABEL_ROLE), i.data(0, KIND_ROLE), i.data(0, STATE_ROLE)) for i in self._items()]

    def selected_names(self):
        """FreeCAD names of the selected rows, tree order (Hide / Show acts on them)."""
        return [i.data(0, NAME_ROLE) for i in self._items() if i.isSelected() and i.data(0, NAME_ROLE)]

    def item_by_label(self, label):
        for item in self._items():
            if item.data(0, LABEL_ROLE) == label:
                return item
        return None

    def _top_feature(self, item):
        """The feature row an item belongs to: a direct child of the part row or of a solid-body row."""
        while item.parent() is not None and item.parent().data(0, KIND_ROLE) not in ("part", "body"):
            item = item.parent()
        return item

    def drop_end_of_part_on(self, item, above=False):
        """End of Part goes after the row's feature, or before it when dropped on the upper half of the feature's
        own row (`above`); origin/solids/part rows put it before the first feature."""
        top = self._top_feature(item)
        kind = top.data(0, KIND_ROLE)
        if kind in ("feature", "sketch"):
            if self._rolled_back(top):
                # the feature sits BELOW End of Part (rolled back): a drop on it means "bring the marker here", i.e.
                # apply up to and including it, whichever half was hit (a drag down onto it was landing on the
                # upper half and reading as 'before it', which is where the marker already was)
                self.endOfPartMoved.emit(top.data(0, NAME_ROLE))
                return
            # dropped on the feature right above the marker (any half, its sketch too): "after it" is where the
            # marker already is, so the only meaning is before it — dragging up one row must move it
            before = self._feature_before(top)
            first_of_part = top.parent() is not None and top.parent().data(0, KIND_ROLE) == "part"
            if (above and item is top) or (self._is_right_above_end_of_part(top) and (before or first_of_part)):
                self.endOfPartMoved.emit(before)  # "" = before the first feature (of the main solid only)
            else:
                self.endOfPartMoved.emit(top.data(0, NAME_ROLE))
        elif kind in ("origin", "solids", "part"):
            self.endOfPartMoved.emit("")

    @staticmethod
    def _rolled_back(top):
        """True when `top` is below the End of Part marker among its siblings (a feature not yet applied)."""
        parent = top.parent()
        if parent is None:
            return False
        marker = next((i for i in range(parent.childCount())
                       if parent.child(i).data(0, KIND_ROLE) == "end_of_part"), None)
        return marker is not None and parent.indexOfChild(top) > marker

    @staticmethod
    def _is_right_above_end_of_part(top):
        parent = top.parent()
        if parent is None:
            return False
        nxt = parent.child(parent.indexOfChild(top) + 1)
        return nxt is not None and nxt.data(0, KIND_ROLE) == "end_of_part"

    @staticmethod
    def _feature_before(top):
        """Name of the feature row above `top` among its siblings ("" when it is the first)."""
        parent = top.parent()
        if parent is None:
            return ""
        for i in range(parent.indexOfChild(top) - 1, -1, -1):
            sib = parent.child(i)
            if sib.data(0, KIND_ROLE) in ("feature", "sketch") and sib.data(0, NAME_ROLE):
                return sib.data(0, NAME_ROLE)
        return ""

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None or item.data(0, KIND_ROLE) not in ("feature", "sketch", "origin_item"):
            return
        self.tree.setCurrentItem(item)
        self.markingMenuRequested.emit(item.data(0, NAME_ROLE), self.tree.viewport().mapToGlobal(pos))

    def _on_click(self, item, _column=0):
        if item.data(0, KIND_ROLE) in ("feature", "sketch", "origin_item", "part") and item.data(0, NAME_ROLE):
            self.featureSelected.emit(item.data(0, NAME_ROLE))

    def select_row(self, name):
        """Click the row of object `name` (as a user would)."""
        for item in self._items():
            if item.data(0, NAME_ROLE) == name:
                self.tree.setCurrentItem(item)
                self._on_click(item)
                return True
        return False

    def _on_double_click(self, item, _column=0):
        kind = item.data(0, KIND_ROLE)
        if kind in ("feature", "sketch", "origin_item"):  # an origin plane: a new sketch on it
            self.featureActivated.emit(item.data(0, NAME_ROLE))
        elif kind == "action":
            self.actionTriggered.emit(item.data(0, NAME_ROLE))

    # ----- parameters -----
    def _readonly(self, text):
        item = QtWidgets.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item

    def set_parameters(self, rows, model_rows=()):
        """Model parameters (named sketch dimensions; renamable) first, then user parameters."""
        accent = QtGui.QColor(themes.PALETTES[self._theme]["accent"])
        self._loading = True
        try:
            self.params.setRowCount(0)
            for kind, entries in (("model", model_rows), ("user", rows)):
                for name, formula, value in entries:
                    r = self.params.rowCount()
                    self.params.insertRow(r)
                    name_item = QtWidgets.QTableWidgetItem(name) if kind == "model" else self._readonly(name)
                    name_item.setData(PARAM_KIND_ROLE, kind)
                    name_item.setData(NAME_ROLE, name)
                    if kind == "model":
                        name_item.setForeground(QtGui.QBrush(accent))
                        name_item.setToolTip("Model parameter (a sketch dimension) — type a new name to rename it")
                    self.params.setItem(r, 0, name_item)
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
        self.add_button.setToolTip("Add parameter" if enabled else "Open or create an InCad part to add parameters")
        self.params.setEditTriggers(EDIT_TRIGGERS if enabled else QtWidgets.QAbstractItemView.NoEditTriggers)

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
        self.params.setFocus()
        self.params.editItem(self.params.item(r, 0))  # start typing the name right away; Tab moves to Value
        return r

    def _on_param_changed(self, item):
        if self._loading or not self._params_enabled:
            return
        r = item.row()
        name_item, value_item = self.params.item(r, 0), self.params.item(r, 1)
        if name_item is not None and name_item.data(PARAM_KIND_ROLE) == "model" and item.column() == 0:
            old, new = name_item.data(NAME_ROLE), name_item.text().strip()
            if new and new != old:
                self.parameterRenamed.emit(old, new)
            return
        name = name_item.data(NAME_ROLE) or name_item.text().strip() if name_item else ""
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
        if item is not None and item.data(PARAM_KIND_ROLE) == "model":
            self.parameterRemoved.emit(item.data(NAME_ROLE) or item.text())  # the shell refuses values still in use
            return
        saved = item is not None and not bool(item.flags() & QtCore.Qt.ItemIsEditable)
        if saved:
            self.parameterRemoved.emit(item.text())
        else:
            self.params.removeRow(r)

    def _on_param_clicked(self, row, column):
        item = self.params.item(row, 0)
        if column == 0 and item is not None and (item.data(NAME_ROLE) or item.text()):
            self.parameterClicked.emit(item.data(NAME_ROLE) or item.text())

    def focus_parameters(self):
        self.params.setFocus()

    def set_theme(self, theme):
        self._theme = theme
        self.set_nodes(self._nodes)
