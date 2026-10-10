"""Floating feature dialog (Inventor style): fields built from the feature kind's FIELDS, live changes, an error
line, OK / Apply / Cancel. Value fields accept units, parameter names and formulas; clicking a dimension or a
parameter while one has focus inserts the name."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class ValueField(QtWidgets.QLineEdit):
    def insert(self, name):
        super().insert(name)
        self.setFocus()


class ChoiceField(QtWidgets.QWidget):
    changed = Signal()

    def __init__(self, choices, parent=None):
        super().__init__(parent)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for value, label in choices:
            b = QtWidgets.QToolButton(self)
            b.setText(label)
            b.setCheckable(True)
            b.setObjectName("InCadSegment")
            self._group.addButton(b)
            row.addWidget(b)
            self._buttons[value] = b
            b.clicked.connect(lambda _=False: self.changed.emit())

    def button(self, value):
        return self._buttons[value]

    def value(self):
        for v, b in self._buttons.items():
            if b.isChecked():
                return v
        return None

    def set_value(self, value):
        if value in self._buttons:
            self._buttons[value].setChecked(True)


class FeatureDialog(QtWidgets.QFrame):
    changed = Signal(dict)
    accepted = Signal()
    applied = Signal()
    cancelled = Signal()
    pickRequested = Signal(str)
    activePickChanged = Signal(str)  # "" when picking ends

    def __init__(self, title, icon, fields, values, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadFeatureDialog")
        self._fields = {f.key: f for f in fields}
        self._widgets, self._labels, self._rows = {}, {}, {}
        self._loading = False
        self._sent = {}  # the value fields' texts at the last change signal
        self._history, self._future, self._stepping = [], [], False  # Undo/Redo inside the dialog: its changes
        self._type_timer = QtCore.QTimer(self)  # a value typed previews by itself after a pause: no Enter, no
        self._type_timer.setSingleShot(True)    # focus change (a click in the 3D view takes no Qt focus)
        self._type_timer.setInterval(600)
        self._type_timer.timeout.connect(self._emit)
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(10, 8, 10, 8)
        head = QtWidgets.QHBoxLayout()
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(themes.icon(icon, theme).pixmap(18, 18))
        head.addWidget(icon_label)
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("InCadDialogTitle")
        head.addWidget(title_label, 1)
        col.addLayout(head)
        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(8)
        for r, f in enumerate(fields):
            label = QtWidgets.QLabel(f.label)
            widget = self._make(f)
            form.addWidget(label, r, 0)
            form.addWidget(widget, r, 1)
            self._labels[f.key], self._widgets[f.key], self._rows[f.key] = label, widget, (label, widget)
        col.addLayout(form)
        self._error = QtWidgets.QLabel("")
        self._error.setObjectName("InCadDialogError")
        self._error.setWordWrap(True)
        self._error.hide()
        col.addWidget(self._error)
        self.rescue_button = QtWidgets.QPushButton("")  # a way around the error, offered by the feature kind
        self.rescue_button.setObjectName("InCadDialogRescue")
        self.rescue_button.hide()
        self._rescue = None
        self.rescue_button.clicked.connect(lambda: self._rescue() if self._rescue is not None else None)
        col.addWidget(self.rescue_button)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.apply_button = QtWidgets.QPushButton("Apply +")
        self.ok_button = QtWidgets.QPushButton("OK")
        self.ok_button.setDefault(True)
        for b in (self.cancel_button, self.apply_button, self.ok_button):
            buttons.addWidget(b)
        self.cancel_button.clicked.connect(self.cancelled.emit)
        self.apply_button.clicked.connect(self.applied.emit)
        self.ok_button.clicked.connect(self.accepted.emit)
        col.addLayout(buttons)
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadFeatureDialog {{ background: {panel}; border: 1px solid {border}; border-radius: 9px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; }}"
            " QLabel#InCadDialogError {{ color: {error}; }}"
            " QLineEdit {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 4px;"
            " padding: 2px 4px; }} QToolButton#InCadSegment {{ background: {panel_alt}; color: {text};"
            " border: 1px solid {border}; padding: 2px 8px; }} QToolButton#InCadSegment:checked {{"
            " background: {accent}; color: {selection_text}; }}"
            " QPushButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 6px;"
            " padding: 4px 14px; }} QPushButton:default {{ background: {accent}; color: {selection_text}; }}"
            " QPushButton:disabled {{ color: {text_dim}; background: {panel}; }}"
            " QPushButton#InCadPick {{ border-radius: 4px; padding: 2px 8px; text-align: left; }}"
            " QPushButton#InCadPick:checked {{ border: 2px solid {accent}; }}".format(**p))
        self.set_values(values)
        self._history = [self.values()]  # the floor: what the dialog opened with

    # ----- building -----
    def _make(self, f):
        if f.kind in ("value_length", "value_angle"):
            w = ValueField(self)
            w.setMinimumWidth(130)
            w.textChanged.connect(lambda _t: self._typed())
            w.editingFinished.connect(self._finished)
            w.returnPressed.connect(self.accepted.emit)
            w.installEventFilter(self)
            return w
        if f.kind == "choice":
            w = ChoiceField(f.choices, self)
            w.changed.connect(self._emit)
            return w
        if f.kind == "combo":
            w = QtWidgets.QComboBox(self)
            w.setMinimumWidth(130)
            for value, label in f.choices:
                w.addItem(label, value)
            w.currentIndexChanged.connect(lambda _=0: self._emit())
            return w
        if f.kind == "bool":
            w = QtWidgets.QCheckBox(self)
            w.toggled.connect(lambda _=False: self._emit())
            return w
        w = QtWidgets.QPushButton("Select…", self)
        w.setObjectName("InCadPick")
        w.setCheckable(True)
        w.clicked.connect(lambda _=False, k=f.key: self._pick_clicked(k))
        return w

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.FocusIn and isinstance(obj, ValueField):
            self._last_value_field = obj
            if self.active_pick() is not None:
                self.set_active_pick(None)  # typing a value ends picking (the preview shows again)
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self.cancelled.emit()
            return True
        return False

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)

    # ----- values -----
    def values(self):
        out = {}
        for key, f in self._fields.items():
            w = self._widgets[key]
            if f.kind in ("value_length", "value_angle"):
                out[key] = w.text().strip()
            elif f.kind == "choice":
                out[key] = w.value()
            elif f.kind == "combo":
                out[key] = w.currentData() if w.currentIndex() >= 0 else ""
            elif f.kind == "bool":
                out[key] = w.isChecked()
            else:
                out[key] = w.property("pick") or ""
        return out

    def set_values(self, values):
        self._loading = True
        try:
            for key, value in values.items():
                f, w = self._fields.get(key), self._widgets.get(key)
                if f is None:
                    continue
                if f.kind in ("value_length", "value_angle"):
                    w.setText(str(value))
                elif f.kind == "choice":
                    w.set_value(value)
                elif f.kind == "combo":
                    i = w.findData(value)
                    if i >= 0:
                        w.setCurrentIndex(i)
                elif f.kind == "bool":
                    w.setChecked(bool(value))
                else:
                    w.setProperty("pick", value or "")
                    w.setText(self._pick_label(f, value))
        finally:
            self._loading = False
            self._sent = self._value_texts()
        self._update_visibility()

    def _value_texts(self):
        return {k: w.text() for k, w in self._widgets.items() if self._fields[k].kind.startswith("value")}

    def _typed(self):
        if not self._loading:
            self._type_timer.start()

    def _finished(self):
        """Enter or a focus change: preview now if a typed value is still waiting, or if the text changed since
        the last signal; a value already previewed is not previewed again."""
        if self._type_timer.isActive():
            self._type_timer.stop()
            self._emit()
        elif self._value_texts() != self._sent:
            self._emit()

    def _emit(self):
        self._type_timer.stop()
        self._update_visibility()
        if not self._loading:
            self._sent = self._value_texts()
            values = self.values()
            if not self._stepping and (not self._history or values != self._history[-1]):
                self._history.append(values)
                self._future = []  # a new change drops the redo trail
            self.changed.emit(values)

    # ----- Undo / Redo inside the dialog -----
    def reset_history(self):
        """The values now become the floor: what the dialog 'opened with' once its seeding (the selection made
        before the command, a kind's defaults) is in."""
        self._history, self._future = [self.values()], []

    def undo_change(self):
        """Back to the values before the last change made in this dialog (previews like any change). False when
        the dialog is at the values it opened with."""
        if len(self._history) < 2:
            return False
        self._future.append(self._history.pop())
        return self._step_to(self._history[-1])

    def redo_change(self):
        if not self._future:
            return False
        values = self._future.pop()
        self._history.append(values)
        return self._step_to(values)

    def _step_to(self, values):
        self._stepping = True
        try:
            self.set_values(values)
            self._emit()
        finally:
            self._stepping = False
        return True

    def _update_visibility(self):
        from incad.features.common import shown as _shown
        values = self.values()
        for key, f in self._fields.items():
            shown = _shown(f, values)
            for w in self._rows[key]:
                w.setVisible(shown)

    # ----- helpers for the session and tests -----
    def field(self, key):
        return self._widgets[key]

    def row_visible(self, key):
        return not self._rows[key][1].isHidden()

    def label_text(self, key):
        return self._labels[key].text()

    def set_param_name(self, key, name):
        f = self._fields[key]
        self._labels[key].setText("%s  (%s)" % (f.label, name) if name else f.label)

    def _pick_label(self, f, value):
        from incad.features.common import pick_label
        return pick_label(f.pick or "item", value or "")

    def _pick_clicked(self, key):
        if key == self.active_pick():
            self.set_active_pick(None)
            return
        self.set_active_pick(key)
        self.pickRequested.emit(key)

    def set_active_pick(self, key):
        """The pick field that takes the next selection in the 3D view (one at a time, shown pressed)."""
        for k, f in self._fields.items():
            if f.kind in ("pick", "picks"):
                self._widgets[k].setChecked(k == key)
        changed = key != self.active_pick()
        self._active_pick = key
        if changed:
            self.activePickChanged.emit(key or "")

    def active_pick(self):
        return getattr(self, "_active_pick", None)

    def set_pick(self, key, text):
        w = self._widgets[key]
        w.setProperty("pick", text or "")
        w.setText(self._pick_label(self._fields[key], text))
        self._emit()

    def field_def(self, key):
        return self._fields[key]

    def set_pick_text(self, key, text):
        self._widgets[key].setText(text or "Select…")

    def pick_text(self, key):
        return self._widgets[key].text()

    def set_options(self, key, options):
        """Replace a combo's items; keeps the current value when still offered, else the first. No signal."""
        w = self._widgets[key]
        current = w.currentData()
        was = self._loading
        self._loading = True
        try:
            w.clear()
            for value, label in options:
                w.addItem(label, value)
            i = w.findData(current)
            w.setCurrentIndex(i if i >= 0 else (0 if w.count() else -1))
        finally:
            self._loading = was
        self._update_visibility()

    def set_choice_enabled(self, key, value, enabled):
        self._widgets[key].button(value).setEnabled(enabled)

    def set_error(self, text, rescue=None):
        """Show why the feature fails; `rescue` = (button label, callable) offers a way around it."""
        self._error.setText(text)
        self._error.setVisible(bool(text))
        self.ok_button.setEnabled(not text)
        self.apply_button.setEnabled(not text)
        self._rescue = rescue[1] if rescue else None
        self.rescue_button.setText(rescue[0] if rescue else "")
        self.rescue_button.setVisible(bool(text and rescue))
        self.adjustSize()  # grow (or shrink back) so the reason never squeezes the fields

    def error_text(self):
        return self._error.text()

    def focused_value_field(self):
        for key, f in self._fields.items():
            w = self._widgets[key]
            if f.kind in ("value_length", "value_angle") and w.hasFocus():
                return w
        return getattr(self, "_last_value_field", None)
