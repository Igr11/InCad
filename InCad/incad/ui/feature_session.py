"""One feature dialog: one undo transaction around create/edit + live previews; OK commits, Cancel aborts."""
from incad.core import log, model, safe
from incad.qt import QtCore
from incad.ui.feature_dialog import FeatureDialog


class FeatureSession(QtCore.QObject):
    def __init__(self, kind, doc, body, profile=None, feature=None, theme="light", parent=None, on_close=None):
        super().__init__(parent)
        self.kind, self.doc, self.body, self.profile = kind, doc, body, profile
        self.feature = feature
        self.creating = feature is None
        self._theme, self._parent, self._on_close = theme, parent, on_close
        self.dialog = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._preview)
        self._pending = None
        self._closed = False

    def start(self):
        doc = self.doc
        if not doc.UndoMode:
            doc.UndoMode = 1
        if doc.HasPendingTransaction:
            doc.commitTransaction()
        self._broken = safe.snapshot_broken(doc)
        doc.openTransaction(self.kind.TITLE)
        safe.set_busy(self.kind.TITLE)
        try:
            if self.creating:
                values = self.kind.defaults(doc, self.body, self.profile)
                self.feature = self.kind.create(doc, self.body, self.profile, values)
                self._created_with = values.get("operation")
            else:
                values = self.kind.read(doc, self.feature)
            doc.recompute()
        except Exception as e:
            log.report("error", "%s could not start: %s" % (self.kind.TITLE, e))
            self._finish(commit=False)
            return False
        self.dialog = FeatureDialog(self.kind.TITLE, self.kind.ICON, self.kind.FIELDS, values, self._theme, self._parent)
        if not self.creating:
            for value in ("intersect", "new_solid"):
                if "operation" in self.dialog._widgets and value in self.dialog.field("operation")._buttons:
                    self.dialog.set_choice_enabled("operation", value, False)
        self.dialog.changed.connect(self._changed)
        self.dialog.accepted.connect(self.ok)
        self.dialog.applied.connect(self.apply)
        self.dialog.cancelled.connect(self.cancel)
        self._label_params()
        self.dialog.move(16, 16)
        self.dialog.show()
        self.dialog.raise_()
        self._check()
        return True

    def _label_params(self):
        for f in self.kind.FIELDS:
            if f.kind.startswith("value"):
                prop = getattr(self.kind, "PROPS", {}).get(f.key)
                if prop and self.feature is not None:
                    target = self.kind._pad_of(self.feature) if hasattr(self.kind, "_pad_of") else self.feature
                    self.dialog.set_param_name(f.key, model.bound_parameter(target, prop) if target else None)

    def _changed(self, values):
        self._pending = values
        self._timer.start()

    def _preview(self):
        if self._pending is None or self._closed:
            return
        values, self._pending = self._pending, None
        try:
            if self.creating and self._needs_recreate(values):
                self.doc.abortTransaction()
                self.doc.recompute()
                model.relink(self.doc)
                self.doc.openTransaction(self.kind.TITLE)
                self.feature = self.kind.create(self.doc, self.body, self.profile, values)
                self._created_with = values.get("operation")
            else:
                self.feature = self.kind.update(self.doc, self.feature, values)
            self.doc.recompute()
        except Exception as e:
            self.dialog.set_error(str(e))
            return
        self._check()
        self._label_params()

    def _needs_recreate(self, values):
        """While creating, Join/Cut switch in place; New Solid and Intersect build a different structure."""
        before, after = getattr(self, "_created_with", None), values.get("operation")
        structural = ("new_solid", "intersect")
        return before != after and (before in structural or after in structural)

    def _check(self):
        found = safe.problems(self.doc, self._broken, {o.Name for o in self.doc.Objects})
        self.dialog.set_error("; ".join(found))

    def insert(self, name):
        field = self.dialog.focused_value_field() if self.dialog is not None else None
        if field is not None:
            field.insert(name)
            return True
        return False

    def ok(self):
        if self._pending is not None:
            self._timer.stop()
            self._preview()
        if self.dialog is not None and self.dialog.error_text():
            return
        self._finish(commit=True)

    def apply(self):
        kind = self.kind
        self.ok()
        if self._closed:
            from incad.ui import shell
            QtCore.QTimer.singleShot(0, lambda: shell.start_feature(kind))

    def cancel(self):
        self._timer.stop()
        self._finish(commit=False)

    def _finish(self, commit):
        if self._closed:
            return
        self._closed = True
        try:
            if commit:
                self.doc.commitTransaction()
            else:
                self.doc.abortTransaction()
                self.doc.recompute()
                model.relink(self.doc)  # objects restored by the abort lose their formula links (FreeCAD quirk)
        except Exception as e:
            log.report("warning", "Could not close the %s step cleanly: %s" % (self.kind.TITLE, e))
        safe.set_busy(None)
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self._on_close is not None:
            self._on_close(self)
