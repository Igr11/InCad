"""New file dialog: Part / Assembly and Millimeters / Inches, with 'Remember my choice'."""
from incad.qt import QtWidgets
from incad.ui import theme as themes


class NewDialog(QtWidgets.QDialog):
    def __init__(self, units="mm", remember=False, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadNewDialog")
        self.setWindowTitle("New")
        self.setStyleSheet(themes.stylesheet(theme))
        col = QtWidgets.QVBoxLayout(self)
        self.part = self._tile("Part", "One part file")
        self.assembly = self._tile("Assembly", "Arrives in a later InCad stage")
        self.assembly.setEnabled(False)
        self.part.setChecked(True)
        self.mm = self._tile("Millimeters", "mm · deg · ISO threads first")
        self.inch = self._tile("Inches", "in · deg · UNC/UNF threads first")
        (self.inch if units == "in" else self.mm).setChecked(True)
        for first, second in ((self.part, self.assembly), (self.mm, self.inch)):
            group = QtWidgets.QButtonGroup(self)
            group.setExclusive(True)
            group.addButton(first)
            group.addButton(second)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(first)
            row.addWidget(second)
            col.addLayout(row)
        self.remember = QtWidgets.QCheckBox("Remember my choice")
        self.remember.setChecked(remember)
        col.addWidget(self.remember)
        buttons = QtWidgets.QDialogButtonBox()
        self.create_button = buttons.addButton("Create", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.create_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        col.addWidget(buttons)

    @staticmethod
    def _tile(title, subtitle):
        b = QtWidgets.QPushButton("%s\n%s" % (title, subtitle))
        b.setObjectName("InCadTile")
        b.setCheckable(True)
        b.setMinimumSize(180, 64)
        return b

    def choice(self):
        return ("part", "in" if self.inch.isChecked() else "mm", self.remember.isChecked())
