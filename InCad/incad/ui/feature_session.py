"""One feature dialog: one undo transaction around create/edit + live previews; OK commits, Cancel aborts."""
from incad.core import log, model, safe
from incad.qt import QtCore
from incad.ui.feature_dialog import FeatureDialog


class FeatureSession(QtCore.QObject):
    def __init__(self, kind, doc, body, profile=None, feature=None, theme="light", parent=None, on_close=None):
        super().__init__(parent)
        self.kind, self.doc, self.body, self.profile = kind, doc, body, profile
        self.doc_name = doc.Name
        self.feature = feature
        self.creating = feature is None
        self._theme, self._parent, self._on_close = theme, parent, on_close
        self.dialog = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._preview)
        self._pending = None
        self._applied = None
        self._closed = False
        self._base_shown = None  # the base feature shown instead of the preview while picking geometry
        self._observing = False

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
                if getattr(self.kind, "NEEDS_PROFILE", True):
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
        self._applied = self.dialog.values()
        if not self.creating:
            for value in ("intersect", "new_solid"):
                if "operation" in self.dialog._widgets and value in self.dialog.field("operation")._buttons:
                    self.dialog.set_choice_enabled("operation", value, False)
        self.dialog.changed.connect(self._changed)
        self.dialog.accepted.connect(self.ok)
        self.dialog.applied.connect(self.apply)
        self.dialog.cancelled.connect(self.cancel)
        self.dialog.activePickChanged.connect(lambda _key: self._sync_pick_view())
        self._label_params()
        self.dialog.move(16, 16)
        self.dialog.show()
        self.dialog.raise_()
        if self.feature is None:
            self._apply_preselection()
            first_empty = next((f.key for f in self.kind.FIELDS if f.kind in ("pick", "picks")
                                and self._shown(f) and not self.dialog.values().get(f.key)), None)
            self._pending = self.dialog.values()
            self._preview()  # first try: defaults (+ preselection) may already be enough
            if first_empty is not None:
                self.dialog.set_active_pick(first_empty)
        else:
            self._check()
        self._observe(True)
        return True

    def _shown(self, field):
        if field.show_if is None:
            return True
        return self.dialog.values().get(field.show_if[0]) in field.show_if[1]

    # ----- picking from the 3D view -----
    _GEOMETRY = ("edge", "face", "vertex", "axis", "plane", "circular_edge")

    def _observe(self, on):
        try:
            import FreeCADGui as Gui
        except ImportError:
            return
        if on and not self._observing:
            Gui.Selection.addObserver(self)
        elif not on and self._observing:
            Gui.Selection.removeObserver(self)
        self._observing = on

    def _apply_preselection(self):
        from incad.features import common
        wanted = getattr(self.kind, "PRESELECT", {})
        if not wanted:
            return
        pairs = self._selection()
        for key, pick in wanted.items():
            ok = [p for p in pairs if common.accepts(pick, *p)]
            if ok:
                field = self.dialog.field_def(key)
                self.dialog.set_pick(key, common.format_picks(ok[-1:] if field.kind == "pick" else ok))

    def _selection(self):
        import FreeCADGui as Gui
        from incad.features import common
        pairs = []
        for sel in Gui.Selection.getSelectionEx(self.doc_name):
            for sub in (sel.SubElementNames or ("",)):
                obj, el = common.resolve(sel.Object, sub)
                if obj is not None and obj is self.feature:
                    base = getattr(obj, "BaseFeature", None)
                    if base is None or not el:
                        continue  # the feature being made can't be its own input
                    obj = base
                pairs.append((obj, el))
        return pairs

    def addSelection(self, doc, obj, sub, pnt):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def removeSelection(self, doc, obj, sub):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def setSelection(self, doc):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def _selection_changed(self):
        from incad.features import common
        if self._closed or self.dialog is None:
            return
        key = self.dialog.active_pick()
        if key is None:
            return
        f = self.dialog.field_def(key)
        pairs = self._selection()
        ok = [p for p in pairs if common.accepts(f.pick, *p)]
        if pairs and not ok:
            self.dialog.set_error("Select %s for %s" % (f.pick.replace("_", " "), f.label))
            return
        if not ok:
            return
        self.dialog.set_pick(key, common.format_picks(ok[-1:] if f.kind == "pick" else ok))
        if f.kind == "pick":  # a single pick is done: go on to the next empty one, or stop picking
            nxt = next((g.key for g in self.kind.FIELDS if g.kind in ("pick", "picks") and g.key != key
                        and self._shown(g) and not self.dialog.values().get(g.key)), None)
            self.dialog.set_active_pick(nxt)

    def _sync_pick_view(self):
        """While a geometry pick is active, show the base shape (picks go on it), not the preview."""
        want = None
        key = self.dialog.active_pick() if self.dialog is not None else None
        if key and self.dialog.field_def(key).pick in self._GEOMETRY and self.feature is not None:
            want = getattr(self.feature, "BaseFeature", None)
        if want is self._base_shown:
            return
        self._show_base(False)
        if want is not None:
            self._base_shown = want
            self._set_visible(want, True)
            self._set_visible(self.feature, False)

    def _show_base(self, on):
        if not on and self._base_shown is not None:
            base, self._base_shown = self._base_shown, None
            self._set_visible(base, False)
            if self.feature is not None:
                self._set_visible(self.feature, True)

    @staticmethod
    def _set_visible(obj, visible):
        try:
            obj.ViewObject.Visibility = visible
        except Exception:
            pass

    def _label_params(self):
        extra = self.kind.param_names(self.feature) if hasattr(self.kind, "param_names") and self.feature else {}
        for key, name in extra.items():
            self.dialog.set_param_name(key, name)
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
        self._applied = values
        try:
            if self.creating and (self.feature is None or self._needs_recreate(values)):
                self.doc.abortTransaction()
                self.doc.recompute()
                model.relink(self.doc)
                self.doc.openTransaction(self.kind.TITLE)
                self.feature = None  # the abort removed it; stays None if the new one fails
                self.feature = self.kind.create(self.doc, self.body, self.profile, values)
                self._created_with = values.get("operation")
            else:
                self.feature = self.kind.update(self.doc, self.feature, values)
            self.doc.recompute()
        except Exception as e:
            if self.creating and self.feature is None:
                self._drop_partial()
            self.dialog.set_error(str(e))
            return
        self._check()
        self._label_params()
        self._base_shown = None  # re-apply: the recompute may have shown the (new) preview again
        self._sync_pick_view()

    def _drop_partial(self):
        """A create that failed half-way may have left objects behind: roll them back, keep the step open."""
        try:
            self.doc.abortTransaction()
            self.doc.recompute()
            model.relink(self.doc)
            self.doc.openTransaction(self.kind.TITLE)
        except Exception as e:
            log.report("warning", "Could not roll back the unfinished %s: %s" % (self.kind.TITLE, e))

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
        """Commit what the dialog shows now: a value typed but not yet previewed (Enter, or a click on OK that
        doesn't take focus on macOS) is applied first."""
        self._timer.stop()
        if self.dialog is not None:
            current = self.dialog.values()
            if self._pending is not None or current != self._applied:
                self._pending = current
                self._preview()
        if self.feature is None and self.dialog is not None and not self.dialog.error_text():
            self.dialog.set_error("Nothing to create yet")
        if self.dialog is not None and self.dialog.error_text():
            return
        self._finish(commit=True)

    def apply(self):
        kind = self.kind
        self.ok()
        if self._closed:
            from incad.ui import shell
            try:
                import FreeCADGui as Gui
                Gui.Selection.clearSelection()  # the next round must not pick the profile just used
            except Exception:
                pass
            QtCore.QTimer.singleShot(0, lambda: shell.start_feature(kind))

    def cancel(self):
        self._timer.stop()
        self._finish(commit=False)

    def _finish(self, commit):
        if self._closed:
            return
        self._closed = True
        self._observe(False)
        try:
            self._show_base(False)
        except Exception:
            pass
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
