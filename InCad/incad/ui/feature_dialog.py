"""Floating feature dialog (Inventor style): fields built from the feature kind's FIELDS, live changes, an error
line, OK / Apply / Cancel. Value fields accept units, parameter names and formulas; clicking a dimension or a
parameter while one has focus inserts the name."""
import re

from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


_NUMBER = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*([^\d\s][^\d]*?)?\s*$")


def step_text(text, delta, kind):
    """The text of a value field one step up or down (delta ±1, ±10 with Shift): 1 of the unit shown (1 mm, 1°,
    1 count; 1/16 in), the number of decimals kept. None when the text is a formula, which cannot be stepped;
    a length never goes below zero."""
    m = _NUMBER.match(text or "")
    if m is None:
        return None
    number, unit = m.group(1), m.group(2) or ""
    if unit and not re.match(r"^(mm|cm|m|in|\"|ft|'|°|deg|rad|µm|um)$", unit):
        return None
    step = 0.0625 if unit in ("in", '"') else 1.0
    value = float(number) + delta * step
    if kind != "value_angle" and value < 0:
        value = 0.0
    decimals = len(number.split(".")[1]) if "." in number else 0
    if unit in ("in", '"'):
        decimals = max(decimals, 4)
    out = "%.*f" % (decimals, value)
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    head = text[:text.index(number)] if number in text else ""
    between = text[m.end(1):m.start(2)] if unit else ""
    return (head.strip() + out + between + unit).strip()


class _StepButton(QtWidgets.QToolButton):
    """An arrow button that remembers whether Shift was down at the press (auto-repeat keeps that)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.big = False

    def mousePressEvent(self, event):
        self.big = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        super().mousePressEvent(event)


class ValueField(QtWidgets.QLineEdit):
    stepped = Signal(int)  # ±1 (±10 with Shift) from the Up/Down keys

    def insert(self, name):
        super().insert(name)
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
            big = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            self.stepped.emit((1 if event.key() == QtCore.Qt.Key_Up else -1) * (10 if big else 1))
            return
        super().keyPressEvent(event)


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
    picksEdited = Signal(str)  # a listed picks field changed from its rows (remove, reorder): the session reselects

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
        self._steppers, self._lists = {}, {}
        for r, f in enumerate(fields):
            label = QtWidgets.QLabel(f.label)
            widget = self._make(f)
            self._widgets[f.key] = widget  # the arrows read it while the row is built
            row = self._with_arrows(f, widget) if f.kind in ("value_length", "value_angle") else \
                self._with_list(f, widget) if f.kind == "picks" and getattr(f, "listed", False) else widget
            form.addWidget(label, r, 0)
            form.addWidget(row, r, 1)
            self._labels[f.key], self._widgets[f.key], self._rows[f.key] = label, widget, (label, row)
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
            " padding: 2px 4px; }} QToolButton#InCadStep {{ background: {panel_alt}; color: {text};"
            " border: 1px solid {border}; padding: 0; font-size: 7px; }} QToolButton#InCadStep:disabled {{"
            " color: {text_dim}; }} QToolButton#InCadSegment {{ background: {panel_alt}; color: {text};"
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

    def _with_arrows(self, f, w):
        """The value field with its ▲▼ arrows: one step per press (Shift ×10), each press previews at once."""
        box = QtWidgets.QWidget(self)
        row = QtWidgets.QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(w, 1)
        col = QtWidgets.QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        arrows = []
        for text, delta in (("▲", 1), ("▼", -1)):
            b = _StepButton(box)
            b.setText(text)
            b.setObjectName("InCadStep")
            b.setFixedSize(18, 11)
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            b.setAutoRepeat(True)
            b.clicked.connect(lambda _=False, k=f.key, d=delta, b=b: self._step(k, d * (10 if b.big else 1)))
            col.addWidget(b)
            arrows.append(b)
        row.addLayout(col)
        self._steppers[f.key] = tuple(arrows)
        w.stepped.connect(lambda d, k=f.key: self._step(k, d))
        w.textChanged.connect(lambda _t, k=f.key: self._update_arrows(k))
        self._update_arrows(f.key)
        return box

    def _with_list(self, f, button):
        """A picks field shown as Inventor shows Loft sections: the pick button, then one numbered row per pick
        with ▲ ▼ (order) and ✕ (remove)."""
        box = QtWidgets.QWidget(self)
        col = QtWidgets.QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        col.addWidget(button)
        rows = QtWidgets.QWidget(box)
        lay = QtWidgets.QVBoxLayout(rows)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        col.addWidget(rows)
        self._lists[f.key] = (rows, [])
        return box

    @staticmethod
    def _object_label(name):
        try:
            import FreeCAD as App
            obj = App.ActiveDocument.getObject(name) if App.ActiveDocument is not None else None
            return obj.Label if obj is not None else name
        except Exception:
            return name

    def _refresh_list(self, key):
        if key not in self._lists:
            return
        rows, old = self._lists[key]
        for w in old:
            w.setParent(None)
            w.deleteLater()
        items = [i.strip() for i in (self._widgets[key].property("pick") or "").split(",") if i.strip()]
        made = []
        for i, item in enumerate(items):
            r = QtWidgets.QWidget(rows)
            h = QtWidgets.QHBoxLayout(r)
            h.setContentsMargins(4, 0, 0, 0)
            h.setSpacing(2)
            label = QtWidgets.QLabel("%d.  %s" % (i + 1, self._object_label(item.partition(":")[0])), r)
            h.addWidget(label, 1)
            buttons = {}
            for name, text, tip in (("up", "▲", "Earlier in the loft"), ("down", "▼", "Later in the loft"),
                                    ("remove", "✕", "Remove this section")):
                b = QtWidgets.QToolButton(r)
                b.setText(text)
                b.setToolTip(tip)
                b.setObjectName("InCadStep")
                b.setFixedSize(18, 16)
                b.setFocusPolicy(QtCore.Qt.NoFocus)
                b.clicked.connect(lambda _=False, k=key, n=i, a=name: self._edit_list(k, n, a))
                h.addWidget(b)
                buttons[name] = b
            buttons["up"].setEnabled(i > 0)
            buttons["down"].setEnabled(i < len(items) - 1)
            r.label, r.buttons = label, buttons
            rows.layout().addWidget(r)
            made.append(r)
        self._lists[key] = (rows, made)
        rows.setVisible(bool(made))
        self._widgets[key].setText(self._list_hint(items))
        self.adjustSize()

    @staticmethod
    def _list_hint(items):
        return "Click sketches in order (2 or more)…" if not items else "Add sketches (click in order)…"

    def _edit_list(self, key, index, action):
        items = [i.strip() for i in (self._widgets[key].property("pick") or "").split(",") if i.strip()]
        if action == "remove":
            items.pop(index)
        elif action == "up" and index > 0:
            items[index - 1], items[index] = items[index], items[index - 1]
        elif action == "down" and index < len(items) - 1:
            items[index + 1], items[index] = items[index], items[index + 1]
        else:
            return
        self.set_pick(key, ",".join(items))
        self.picksEdited.emit(key)

    def list_rows(self, key):
        """The texts of a listed picks field's rows (tests)."""
        return [r.label.text() for r in self._lists[key][1]]

    def row_button(self, key, index, name):
        """A row's 'up' / 'down' / 'remove' button (tests)."""
        return self._lists[key][1][index].buttons[name]

    def _update_arrows(self, key):
        can = step_text(self._widgets[key].text(), 1, self._fields[key].kind) is not None
        for b in self._steppers.get(key, ()):
            b.setEnabled(can)

    def _step(self, key, delta):
        w = self._widgets[key]
        text = step_text(w.text(), delta, self._fields[key].kind)
        if text is None or text == w.text():
            return
        self._type_timer.stop()
        w.setText(text)
        self._emit()  # one preview per press, no waiting for the typing pause

    def step_buttons(self, key):
        """(up, down) arrow buttons of a value field (tests)."""
        return self._steppers[key]

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
                    self._refresh_list(key)
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
        self._refresh_list(key)
        self._emit()

    def field_def(self, key):
        return self._fields[key]

    def set_pick_text(self, key, text):
        if key in self._lists:
            return  # the rows say what is picked
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
