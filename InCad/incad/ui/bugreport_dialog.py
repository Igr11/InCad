"""⚙ ▸ Report a Bug: what happened, the steps, a contact if the reporter wants an answer, the end of the log; Send
puts it on GitHub (incad.core.bugreport). The dialog says the report is public. No FreeCAD here: `send(what, steps,
contact, attach_log)` is the shell's, returning (ok, text, link)."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes


class BugReportDialog(QtWidgets.QDialog):
    def __init__(self, product, send, theme="light", parent=None, direct=True):
        super().__init__(parent)
        self.setObjectName("InCadBugReport")
        self.setWindowTitle("Report a Bug")
        self._send = send
        self.sent_link = None
        col = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QLabel("Report a Bug — %s" % product)
        head.setObjectName("InCadDialogTitle")
        col.addWidget(head)
        note = QtWidgets.QLabel(
            "Your report goes to the public issue list of InCad on GitHub%s. Your name is taken out of the "
            "file paths; don't write anything private." % ("" if direct else " (GitHub opens in your browser to "
                                                            "send it)"))
        note.setWordWrap(True)
        col.addWidget(note)
        col.addWidget(QtWidgets.QLabel("What happened? What did you expect?"))
        self.what = QtWidgets.QPlainTextEdit()
        self.what.setPlaceholderText("Split with a gap left the pieces touching…")
        self.what.setMinimumHeight(90)
        col.addWidget(self.what, 2)
        col.addWidget(QtWidgets.QLabel("Steps to make it happen again (optional)"))
        self.steps = QtWidgets.QPlainTextEdit()
        self.steps.setPlaceholderText("1. New part, a box\n2. …")
        self.steps.setMinimumHeight(70)
        col.addWidget(self.steps, 1)
        col.addWidget(QtWidgets.QLabel("Contact for an answer (optional, shown publicly)"))
        self.contact = QtWidgets.QLineEdit()
        self.contact.setPlaceholderText("E-mail or GitHub name")
        col.addWidget(self.contact)
        self.attach = QtWidgets.QCheckBox("Attach the end of the log (what the program did before)")
        self.attach.setChecked(True)
        col.addWidget(self.attach)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.message.setOpenExternalLinks(True)
        col.addWidget(self.message)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.send_button = QtWidgets.QPushButton("Send" if direct else "Open on GitHub")
        self.send_button.setDefault(True)
        self.send_button.clicked.connect(self._on_send)
        row.addWidget(self.cancel_button)
        row.addWidget(self.send_button)
        col.addLayout(row)
        self.resize(520, 520)
        p = themes.PALETTES[theme]
        self._palette = p
        self.setStyleSheet(
            "QDialog#InCadBugReport {{ background: {panel}; color: {text}; }}"
            " QLabel, QCheckBox {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; font-size: 14px; }}"
            " QPlainTextEdit, QLineEdit {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " border-radius: 6px; padding: 4px; }}"
            " QPushButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 6px;"
            " padding: 4px 14px; }} QPushButton:disabled {{ color: {text_dim}; }}".format(**p))

    def set_message(self, text, ok=False):
        self.message.setStyleSheet("color: %s;" % (self._palette["text"] if ok else self._palette["error"]))
        self.message.setText(text)

    def _on_send(self):
        if self.sent_link:
            self.accept()
            return
        what = self.what.toPlainText().strip()
        if not what:
            self.set_message("Say what happened first")
            self.what.setFocus()
            return
        self.send_button.setEnabled(False)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            ok, text, link = self._send(what, self.steps.toPlainText(), self.contact.text(), self.attach.isChecked())
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.send_button.setEnabled(True)
        if not ok:
            self.set_message(text)
            return
        self.sent_link = link
        self.set_message('%s: <a href="%s">%s</a>' % (text, link, link) if link else text, ok=True)
        for w in (self.what, self.steps, self.contact, self.attach):
            w.setEnabled(False)
        self.cancel_button.hide()
        self.send_button.setText("Close")
