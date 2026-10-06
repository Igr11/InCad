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
        self._seeding = False
        self._saved_visibility = []

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
                    self._created_values = dict(values)
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
            for value in getattr(self.kind, "STRUCTURAL", ("intersect", "new_solid")):
                if "operation" in self.dialog._widgets and value in self.dialog.field("operation")._buttons:
                    self.dialog.set_choice_enabled("operation", value, False)
            for key in getattr(self.kind, "RECREATE_ON", ()):  # can't change on an existing feature
                if key in self.dialog._widgets:
                    self.dialog.field(key).setEnabled(False)
        self.dialog.changed.connect(self._changed)
        self.dialog.accepted.connect(self.ok)
        self.dialog.applied.connect(self.apply)
        self.dialog.cancelled.connect(self.cancel)
        self.dialog.activePickChanged.connect(lambda _key: self._sync_pick_view(seed=True))
        self._refresh_options()
        if self.feature is not None:
            self.dialog.set_values({f.key: values.get(f.key) for f in self.kind.FIELDS if f.kind == "combo"})
        self._applied = self.dialog.values()
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
        from incad.features.common import shown
        return shown(field, self.dialog.values())

    def _refresh_options(self):
        """Combos whose items depend on other values (e.g. thread sizes of the chosen standard)."""
        options = getattr(self.kind, "options", None)
        if options is None or self.dialog is None:
            return
        values = self.dialog.values()
        for f in self.kind.FIELDS:
            if f.kind == "combo":
                try:
                    items = options(f.key, values)
                except Exception as e:
                    log.report("warning", "Could not list %s: %s" % (f.label, e))
                    items = None
                if items is not None:
                    self.dialog.set_options(f.key, items)

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
        hook = getattr(self.kind, "preselect", None)
        if hook is not None:
            for key, text in hook(self._selection()).items():
                self.dialog.set_pick(key, text)
            return
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
                if obj is not None and obj is not self.feature:  # the feature being made can't be its own input
                    pairs.append((obj, el))
        return pairs

    _DATUMS = ("PartDesign::Plane", "PartDesign::Line", "PartDesign::Point", "PartDesign::CoordinateSystem")

    def _expected_base(self):
        """The shape geometry picks must lie on: what the feature starts from."""
        if self.feature is not None:
            return getattr(self.feature, "BaseFeature", None)
        return self.body.Tip if self.body is not None else None

    def _off_base(self, pairs):
        base = self._expected_base()
        if base is None:
            return []
        return [o for o, el in pairs if el and o is not base and o.TypeId.startswith("PartDesign::")
                and o.TypeId not in self._DATUMS]

    def addSelection(self, doc, obj, sub, pnt):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def removeSelection(self, doc, obj, sub):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def setSelection(self, doc):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def _selection_changed(self):
        from incad.features import common
        if self._closed or self.dialog is None or self._seeding:
            return
        key = self.dialog.active_pick()
        if key is None:
            return
        f = self.dialog.field_def(key)
        pairs = self._selection()
        if f.pick in self._GEOMETRY and self._off_base(pairs):
            self.dialog.set_error("Pick on the current shape (%s)" % self._expected_base().Label)
            return
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

    def _sync_pick_view(self, seed=False):
        """While a geometry pick is active, show the base shape (picks go on it) instead of the preview and of
        any later features; put everything back exactly as it was afterwards."""
        want = None
        key = self.dialog.active_pick() if self.dialog is not None else None
        if key and self.dialog.field_def(key).pick in self._GEOMETRY and self.feature is not None:
            want = self._expected_base()
        if want is not self._base_shown:
            self._show_base(False)
            if want is not None:
                tip = self.body.Tip if self.body is not None else None
                shown = [o for o in (want, self.feature, tip) if o is not None]
                self._saved_visibility = [(o, bool(o.Visibility)) for o in dict.fromkeys(shown)]
                self._base_shown = want
                for o in dict.fromkeys(shown):
                    self._set_visible(o, o is want)
        if seed and key:
            self._seed_selection(key)

    def _show_base(self, on):
        if not on:
            for o, visible in getattr(self, "_saved_visibility", []):
                self._set_visible(o, visible)
            self._saved_visibility = []
            self._base_shown = None

    def _seed_selection(self, key):
        """A picks field that becomes active shows its current items selected, so a click adds or removes one."""
        import FreeCADGui as Gui
        from incad.features import common
        field = self.dialog.field_def(key)
        if field.kind != "picks":
            return
        self._seeding = True
        try:
            Gui.Selection.clearSelection()
            for obj, sub in common.parse_picks(self.doc, self.dialog.values().get(key)):
                Gui.Selection.addSelection(self.doc_name, obj.Name, sub)
        finally:
            QtCore.QTimer.singleShot(0, self._end_seeding)

    def _end_seeding(self):
        self._seeding = False

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
        self._refresh_options()
        values = self.dialog.values() if self.dialog is not None else values
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
                self._created_values = dict(values)
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
        self._fill_empty_picks()
        if self._base_shown is not None:  # re-apply: the recompute (or a re-create) may have shown the preview
            self._show_base(False)
            self._sync_pick_view()

    def _fill_empty_picks(self):
        """Show what a default picked for an empty field (e.g. the feature a pattern repeats)."""
        if self.feature is None:
            return
        try:
            read = self.kind.read(self.doc, self.feature)
        except Exception:
            return
        current = self.dialog.values()
        fill = {f.key: read[f.key] for f in self.kind.FIELDS
                if f.kind in ("pick", "picks") and not current.get(f.key) and read.get(f.key)}
        if fill:
            self.dialog.set_values(fill)

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
        made = getattr(self, "_created_values", {})
        if any(values.get(k) != made.get(k) for k in getattr(self.kind, "RECREATE_ON", ())):
            return True
        before, after = getattr(self, "_created_with", None), values.get("operation")
        structural = getattr(self.kind, "STRUCTURAL", ("new_solid", "intersect"))
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
