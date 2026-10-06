"""The ribbon: a tab bar over a row of command groups, drawn from the command registry and a layout."""
from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes

SIZES = ("small", "medium", "large")


class Ribbon(QtWidgets.QWidget):
    sizeChanged = Signal(str)

    def __init__(self, registry, layout, mode="part", size="large", theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadRibbon")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        if size not in SIZES:
            raise ValueError("unknown ribbon size %r" % size)
        self._registry, self._layout = registry, layout
        self._mode, self._size, self._theme = mode, size, theme
        self._buttons = {}
        self._split_choice = {}  # split button (its first command) -> the variant last chosen
        self._tabs = QtWidgets.QTabBar(self)
        self._tabs.setObjectName("InCadRibbonTabs")
        self._tabs.setDrawBase(False)
        self._tabs.setExpanding(False)
        self._stack = QtWidgets.QStackedWidget(self)
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._tabs)
        col.addWidget(self._stack)
        self._tabs.currentChanged.connect(self._stack.setCurrentIndex)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.rebuild()

    # ----- public -----
    def set_mode(self, mode):
        if mode != self._mode:
            self._mode = mode
            self.rebuild()

    def set_size(self, size):
        if size not in SIZES:
            raise ValueError("unknown ribbon size %r" % size)
        if size != self._size:
            self._size = size
            self.rebuild()
            self.sizeChanged.emit(size)

    def set_theme(self, theme):
        if theme != self._theme:
            self._theme = theme
            self.rebuild()

    def current_size(self):
        return self._size

    def tab_names(self):
        return [self._tabs.tabText(i) for i in range(self._tabs.count())]

    def current_tab(self):
        i = self._tabs.currentIndex()
        return self._tabs.tabText(i) if i >= 0 else ""

    def button(self, cmd_id):
        return self._buttons.get(cmd_id)

    def refresh_checks(self):
        for cmd_id, b in self._buttons.items():
            cmd = self._registry.get(cmd_id)
            if cmd.checkable:
                b.setChecked(bool(cmd.is_checked and cmd.is_checked()))

    def size_menu(self, parent):
        menu = QtWidgets.QMenu("Ribbon Size", parent)
        for size in SIZES:
            act = menu.addAction(size.capitalize())
            act.setCheckable(True)
            act.setChecked(size == self._size)
            act.triggered.connect(lambda _=False, s=size: self.set_size(s))
        return menu

    def rebuild(self):
        keep = self.current_tab()
        self._tabs.blockSignals(True)
        while self._tabs.count():
            self._tabs.removeTab(0)
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._buttons = {}
        for tab_name, groups in self._layout.get(self._mode, []):
            page = self._build_page(groups)
            if page is not None:
                self._stack.addWidget(page)
                self._tabs.addTab(tab_name)
        self._tabs.blockSignals(False)
        names = self.tab_names()
        index = names.index(keep) if keep in names else 0
        if names:
            self._tabs.setCurrentIndex(index)
            self._stack.setCurrentIndex(index)

    # ----- internals -----
    def _build_page(self, groups):
        page = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(page)
        row.setContentsMargins(6, 4, 6, 0)
        row.setSpacing(0)
        count = 0
        for group_name, ids in groups:
            cmds = []
            for item in ids:  # a list is one split button: a command and its variants
                if isinstance(item, (list, tuple)):
                    variants = [self._registry.get(i) for i in item if self._registry.has(i)]
                    if variants:
                        cmds.append(variants)
                elif self._registry.has(item):
                    cmds.append(self._registry.get(item))
            if cmds:
                row.addWidget(self._build_group(group_name, cmds))
                count += 1
        if not count:
            page.deleteLater()
            return None
        row.addStretch(1)
        # a tab wider than the window scrolls sideways instead of widening the window (it pushed the window
        # off the screen with medium/large icons)
        area = QtWidgets.QScrollArea()
        area.setObjectName("InCadRibbonPage")
        area.setWidget(page)
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        area.setMinimumWidth(0)
        area.setMinimumHeight(page.sizeHint().height())
        area.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        area.setStyleSheet("QScrollArea#InCadRibbonPage { background: transparent; border: none; }")
        area.viewport().setAutoFillBackground(False)
        page.setAutoFillBackground(False)
        return area

    def _build_group(self, name, cmds):
        frame = QtWidgets.QFrame()
        frame.setObjectName("InCadRibbonGroup")
        col = QtWidgets.QVBoxLayout(frame)
        col.setContentsMargins(6, 0, 6, 0)
        col.setSpacing(2)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        px = themes.ICON_PX[self._size]
        for cmd in cmds:
            if isinstance(cmd, list):
                row.addWidget(self._split_button(frame, cmd, px))
                continue
            b = QtWidgets.QToolButton(frame)
            b.setIcon(themes.icon(cmd.icon, self._theme))
            b.setIconSize(QtCore.QSize(px, px))
            b.setText(cmd.label)
            b.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if self._size == "small"
                                 else QtCore.Qt.ToolButtonTextUnderIcon)
            tip = cmd.label
            if cmd.shortcut:
                tip += " (%s)" % QtGui.QKeySequence(cmd.shortcut).toString(QtGui.QKeySequence.NativeText)
            if cmd.tooltip:
                tip += "\n" + cmd.tooltip
            b.setToolTip(tip)
            b.setAutoRaise(True)
            if cmd.checkable:
                b.setCheckable(True)
                b.setChecked(bool(cmd.is_checked and cmd.is_checked()))
            b.clicked.connect(lambda _=False, i=cmd.id: self._run(i))
            row.addWidget(b)
            self._buttons[cmd.id] = b
        col.addLayout(row)
        if self._size != "small":
            label = QtWidgets.QLabel(name)
            label.setObjectName("InCadRibbonGroupLabel")
            label.setAlignment(QtCore.Qt.AlignHCenter)
            col.addWidget(label)
        return frame

    def _split_button(self, parent, variants, px):
        """Inventor split button: the face runs the last chosen variant, the arrow lists them all."""
        key = variants[0].id
        chosen = self._split_choice.get(key, key)
        current = next((c for c in variants if c.id == chosen), variants[0])
        b = QtWidgets.QToolButton(parent)
        b.setIconSize(QtCore.QSize(px, px))
        b.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if self._size == "small"
                             else QtCore.Qt.ToolButtonTextUnderIcon)
        b.setAutoRaise(True)
        b.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        menu = QtWidgets.QMenu(b)
        for cmd in variants:
            act = menu.addAction(themes.icon(cmd.icon, self._theme), cmd.label)
            act.setToolTip(cmd.tooltip or cmd.label)
            act.triggered.connect(lambda _=False, c=cmd: self._choose(b, key, c))
        b.setMenu(menu)

        def show(cmd):
            b.setIcon(themes.icon(cmd.icon, self._theme))
            b.setText(cmd.label)
            tip = cmd.label
            if cmd.shortcut:
                tip += " (%s)" % QtGui.QKeySequence(cmd.shortcut).toString(QtGui.QKeySequence.NativeText)
            b.setToolTip(tip + ("\n" + cmd.tooltip if cmd.tooltip else "") + "\n▾ more options")
            b.setProperty("incad_cmd", cmd.id)
        b._incad_show = show
        show(current)
        b.clicked.connect(lambda _=False: self._run(b.property("incad_cmd")))
        for cmd in variants:
            self._buttons[cmd.id] = b
        return b

    def _choose(self, button, key, cmd):
        self._split_choice[key] = cmd.id
        button._incad_show(cmd)
        self._run(cmd.id)

    def _run(self, cmd_id):
        self._registry.run(cmd_id)
        self.refresh_checks()

    def _context_menu(self, pos):
        self.size_menu(self).exec(self.mapToGlobal(pos))
