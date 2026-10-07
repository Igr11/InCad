"""One feature dialog: one undo transaction around create/edit + live previews; OK commits, Cancel aborts."""
import traceback

from incad.core import log, model, safe
from incad.qt import dispose, QtCore
from incad.ui.feature_dialog import FeatureDialog


def _feature_alive(obj):
    try:
        obj.TypeId
        return True
    except Exception:
        return False


class FeatureSession(QtCore.QObject):
    def __init__(self, kind, doc, body, profile=None, feature=None, theme="light", parent=None, on_close=None):
        super().__init__(parent)
        self.kind, self.doc, self.body, self.profile = kind, doc, body, profile
        self.doc_name = doc.Name
        self.feature = feature
        self._feature_name = feature.Name if feature is not None else None
        self.creating = feature is None
        self._theme, self._parent, self._on_close = theme, parent, on_close
        self.dialog = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._preview)
        self._previewing = False
        self._after_preview = None
        self._pending = None
        self._applied = None
        self._closed = False
        self._again = False
        self._committed = False
        self._base_shown = None  # the base feature shown instead of the preview while picking geometry
        self._extra = []  # other documents this dialog changes (assembly cuts): one undo step in each
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
        if not self.creating:  # every document's undo step opens before anything changes
            self._join_documents(self.kind.read(doc, self.feature))
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
            if self._closed:  # Esc or OK while that first preview computed (seconds for a thread)
                return True
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
                    profile = self.profile if self.profile is not None else (
                        __import__("incad.features.common", fromlist=["profile_of"]).profile_of(self.feature)
                        if self.feature is not None else None)
                    items = options(f.key, values, profile) if options.__code__.co_argcount >= 3 \
                        else options(f.key, values)
                except Exception as e:
                    log.report("warning", "Could not list %s: %s" % (f.label, e))
                    items = None
                if items is not None:
                    self.dialog.set_options(f.key, items)

    # ----- picking from the 3D view -----
    _GEOMETRY = ("edge", "face", "vertex", "axis", "plane", "circular_edge")
    _ON_BASE = _GEOMETRY + ("two_points",)  # picks made on the shape: the base is shown while they are active

    def _observe(self, on):
        try:
            import FreeCADGui as Gui
        except ImportError:
            return
        if on and not self._observing and not self._closed:
            Gui.Selection.addObserver(self)
            self._observing = True
        elif not on and self._observing:
            Gui.Selection.removeObserver(self)
            self._observing = False

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
            ok = common.whole(pick, [p for p in pairs if common.accepts(pick, *p)])
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
        if f.pick == "two_points":
            return  # taken by clicks on the markers, not by the selection
        pairs = self._selection()
        if f.pick in self._GEOMETRY and self._off_base(pairs):
            self.dialog.set_error("Pick on the current shape (%s)" % self._expected_base().Label)
            return
        ok = common.whole(f.pick, [p for p in pairs if common.accepts(f.pick, *p)])
        if pairs and not ok:
            if f.pick in self._GEOMETRY and not any(el for _, el in pairs):
                return  # a whole object (a tree row) while a face/edge is wanted: just looking, not an error
            self.dialog.set_error("Select %s for %s" % (f.pick.replace("_", " "), f.label))
            self._pick_error = True
            return
        if not pairs and getattr(self, "_pick_error", False):
            self.dialog.set_error("")
            self._pick_error = False
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
        if key and self.dialog.field_def(key).pick in self._ON_BASE and self.feature is not None:
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
        self._sync_point_pick(key)

    def _sync_point_pick(self, key):
        """A 'two points' field that becomes active shows the part's markers (corners, edge middles, circle
        centres, the profile's points too) and takes two clicks on them; any other active field, or none, ends
        that pick."""
        from incad.ui import shell as shells
        sh = shells.instance()
        if sh is None:
            return
        field = self.dialog.field_def(key) if key else None
        if field is None or field.pick != "two_points":
            if getattr(self, "_point_key", None) is not None:
                self._point_key = None
                sh.cancel_point_pick(quiet=True)
            return
        if getattr(self, "_point_key", None) == key:
            return
        self._point_key = key
        from incad.core import section
        base = self._expected_base()
        points = []
        for shape in ((base.Shape if base is not None else None), (self.profile.Shape if self.profile is not None else None)):
            if shape is not None and not shape.isNull():
                for kind, p in section.snap_points(shape):
                    if not any((p - q).Length < 1e-6 for _, q in points):
                        points.append((kind, p))
        if not points:
            self.dialog.set_error("Nothing to click: draw the profile first")
            self._point_key = None
            self.dialog.set_active_pick(None)
            return
        sh.start_point_pick(points, 2, "Axis: click 2 points — corners, edge middles, circle centres (Esc cancels)",
                            on_done=lambda pts, k=key: self._points_picked(k, pts),
                            on_cancel=lambda k=key: self._points_cancelled(k))

    def _points_picked(self, key, points):
        from incad.features import revolve
        self._point_key = None
        if self._closed or self.dialog is None:
            return
        self.dialog.set_pick(key, revolve.format_points(points))  # emits changed: the preview follows
        self.dialog.set_active_pick(None)

    def _points_cancelled(self, key):
        self._point_key = None
        if self._closed or self.dialog is None:
            return
        if self.dialog.active_pick() == key:
            self.dialog.set_active_pick(None)

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
        if self._previewing:
            self._timer.start()  # FreeCAD runs the event loop while it computes: a value changed meanwhile is
            return               # previewed after this one, never re-entered
        self._previewing = True
        try:
            self._preview_now()
        except Exception as e:  # nothing escapes into the timer slot; the dialog says what went wrong
            log.report("warning", "%s preview: %s" % (self.kind.TITLE, e), traceback.format_exc())
            if self.dialog is not None:
                self.dialog.set_error(str(e))
        finally:
            self._previewing = False
            after, self._after_preview = self._after_preview, None  # never kept for a later preview
        if after and not self._closed:  # OK / Apply / Cancel pressed while the preview computed
            getattr(self, after)()

    def _preview_now(self):
        values, self._pending = self._pending, None
        self._applied = values
        try:
            if self.creating and (self.feature is None or self._needs_recreate(values)):
                # roll back every document, then open all the undo steps again before changing anything
                # (opening a step in one more document commits what is pending in the others)
                self.doc.abortTransaction()
                self.feature = None  # the abort removed it (before anything below can raise)
                self._abort_extras(reopen=False)
                self.doc.recompute()
                model.relink(self.doc)
                self._join_documents(values)
                self.doc.openTransaction(self.kind.TITLE)
                self.feature = None  # the abort removed it; stays None if the new one fails
            if self.feature is None:
                self.feature = self.kind.create(self.doc, self.body, self.profile, values)
                self._created_with = values.get("operation")
                self._created_values = dict(values)
            else:
                self.feature = self.kind.update(self.doc, self.feature, values)
            self.doc.recompute()
        except Exception as e:
            self._recover_deleted_feature()  # a type-swapping update() may have deleted it then failed
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

    def _recover_deleted_feature(self):
        """An update() that swaps a feature's type (Join<->Cut) deletes the old one, then may fail before it
        returns the new one — self.feature is left pointing at a deleted object and the next preview would crash.
        Put it back: None while creating (the next preview recreates), or the restored original while editing."""
        if self.feature is None or _feature_alive(self.feature):
            return
        if self.creating:
            self.feature = None
            return
        try:
            self.doc.abortTransaction()
            self.doc.recompute()
            model.relink(self.doc)
            self.doc.openTransaction(self.kind.TITLE)
            self._abort_extras(reopen=True)
        except Exception as ex:
            log.report("warning", "Could not roll back the unfinished %s: %s" % (self.kind.TITLE, ex))
        self.feature = self.doc.getObject(self._feature_name) if self._feature_name else None

    def _drop_partial(self):
        """A create that failed half-way may have left objects behind: roll them back, keep the step open."""
        try:
            self.doc.abortTransaction()
            self.doc.recompute()
            model.relink(self.doc)
            self.doc.openTransaction(self.kind.TITLE)
            self._abort_extras(reopen=True)
        except Exception as e:
            log.report("warning", "Could not roll back the unfinished %s: %s" % (self.kind.TITLE, e))

    def _join_documents(self, values):
        """Open this dialog's undo step in the other documents it changes (e.g. the part an assembly cut edits)."""
        hook = getattr(self.kind, "documents", None)
        if hook is None:
            return
        for d in hook(self.doc, values):
            if d is self.doc or d in self._extra:
                continue
            if not d.UndoMode:
                d.UndoMode = 1
            if d.HasPendingTransaction:
                d.abortTransaction()  # an empty step FreeCAD pre-opened for linked documents
            d.openTransaction(self.kind.TITLE)
            self._extra.append(d)

    def _abort_extras(self, reopen):
        for d in list(self._extra):
            try:
                d.abortTransaction()
                d.recompute()
                model.relink(d)
                if reopen:
                    d.openTransaction(self.kind.TITLE)
            except Exception as e:
                log.report("warning", "Could not roll back %s: %s" % (d.Label, e))
        if not reopen:
            self._extra = []

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
        if self._previewing:
            self._after_preview = "ok"  # taken when the preview (seconds for a thread) is done
            return
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
        if self._previewing:
            self._after_preview = "apply"
            return
        kind = self.kind
        self.ok()
        # once, and only after a commit: a second Apply that landed during the preview is folded in, and an Esc
        # that landed there means stop (Inventor), not "and now the next one"
        if self._closed and self._committed and not self._again:
            self._again = True
            from incad.ui import shell
            try:
                import FreeCADGui as Gui
                Gui.Selection.clearSelection()  # the next round must not pick the profile just used
            except Exception:
                pass
            def again():
                try:
                    shell.start_feature(kind)
                except Exception as e:  # e.g. no closed sketch left: say so instead of a silent traceback
                    log.report("warning", "%s: %s" % (kind.TITLE, e))
            QtCore.QTimer.singleShot(0, again)

    def cancel(self):
        if self._previewing:
            self._after_preview = "cancel"
            return
        self._timer.stop()
        self._finish(commit=False)

    def _finish(self, commit):
        if self._closed:
            return
        self._closed = True
        self._committed = commit
        self._timer.stop()  # a value edited during the last preview must not preview after the close
        self._observe(False)
        try:
            self._show_base(False)
        except Exception:
            pass
        try:
            if commit:
                self.doc.commitTransaction()
                for d in self._extra:
                    d.commitTransaction()
                self._extra = []
            else:
                self.doc.abortTransaction()
                self.doc.recompute()
                model.relink(self.doc)  # objects restored by the abort lose their formula links (FreeCAD quirk)
                self._abort_extras(reopen=False)
        except Exception as e:
            log.report("warning", "Could not close the %s step cleanly: %s" % (self.kind.TITLE, e))
        safe.set_busy(None)
        if self.dialog is not None:
            self.dialog.close()
            dispose(self.dialog)
            self.dialog = None
        if self._on_close is not None:
            self._on_close(self)
