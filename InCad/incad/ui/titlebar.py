"""Title strip under the macOS title bar: quick-access buttons, document name, theme toggle, ⇄ FreeCAD, ⚙."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes


class TitleStrip(QtWidgets.QWidget):
    QUICK = ("file.new", "file.open", "file.save", "edit.undo", "edit.redo", "edit.update")
    RIGHT = ("view.theme_toggle", "view.freecad")

    def __init__(self, registry, theme="light", settings_menu=None, parent=None):
        super().__init__(parent)
        self.setObjectName("InCadTitle")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._registry, self._theme, self._settings_menu = registry, theme, settings_menu
        self._buttons = {}
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(4)
        for cmd_id in self.QUICK:
            self._add(row, cmd_id, with_text=False)
        row.addStretch(1)
        self._name = QtWidgets.QLabel("")
        self._name.setObjectName("InCadDocName")
        row.addWidget(self._name)
        row.addStretch(1)
        from incad import host
        self._version = QtWidgets.QLabel("%s %s" % (host.app_name(), host.version()))  # the user: which build
        self._version.setObjectName("InCadVersion")
        row.addWidget(self._version)
        for cmd_id in self.RIGHT:
            self._add(row, cmd_id, with_text=(cmd_id == "view.freecad"))
        self.settings_button = QtWidgets.QToolButton(self)
        self.settings_button.setAutoRaise(True)
        self.settings_button.setToolTip(host.brand("InCad settings"))
        self.settings_button.setIcon(themes.icon("settings", theme))
        self.settings_button.setIconSize(QtCore.QSize(18, 18))
        self.settings_button.clicked.connect(self._open_settings)
        row.addWidget(self.settings_button)

    def _add(self, row, cmd_id, with_text):
        if not self._registry.has(cmd_id):
            return
        cmd = self._registry.get(cmd_id)
        b = QtWidgets.QToolButton(self)
        b.setAutoRaise(True)
        b.setIcon(themes.icon(cmd.icon, self._theme))
        b.setIconSize(QtCore.QSize(18, 18))
        b.setToolTip(cmd.label)
        if with_text:
            b.setText("FreeCAD")
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        b.clicked.connect(lambda _=False, i=cmd_id: self._registry.run(i))
        row.addWidget(b)
        self._buttons[cmd_id] = b

    def button(self, cmd_id):
        return self._buttons.get(cmd_id)

    def version_text(self):
        return self._version.text()

    def set_document_name(self, text):
        self._name.setText(text)

    def document_name(self):
        return self._name.text()

    def set_theme(self, theme):
        self._theme = theme
        for cmd_id, b in self._buttons.items():
            b.setIcon(themes.icon(self._registry.get(cmd_id).icon, theme))
        self.settings_button.setIcon(themes.icon("settings", theme))

    def build_settings_menu(self):
        return self._settings_menu(self) if self._settings_menu else None

    def _open_settings(self):
        menu = self.build_settings_menu()
        if menu is not None:
            menu.exec(self.settings_button.mapToGlobal(QtCore.QPoint(0, self.settings_button.height())))
