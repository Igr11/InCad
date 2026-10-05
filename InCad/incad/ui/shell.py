"""Full UI takeover. While InCad is active FreeCAD's menus, toolbars, docks and status bar are hidden and InCad's
title strip, ribbon, Model Browser and status bar are shown. Everything is restored on exit, also after a quit or
a crash with InCad active: the snapshot stays in InCad's preferences until the restore has been done."""
import json
import traceback

from incad.core import commands, log, prefs
from incad.qt import QAction, QtCore, QtGui, QtWidgets
from incad.ui import ribbon_layout
from incad.ui import theme as themes
from incad.ui.browser import ModelBrowser
from incad.ui.ribbon import Ribbon
from incad.ui.statusbar import StatusBar
from incad.ui.titlebar import TitleStrip
from incad.ui.sketch_session import SketchSession
from incad.ui.value_box import ValueBox
from incad.ui import marking_layout
from incad.ui.marking_menu import MarkingMenu
from incad.ui.nav import Navigator, to_coin
from incad.ui.nav_strip import NavStrip

OURS = ("InCadTop", "InCadBrowserDock", "InCadStatusBar")
MENU_PREFIX = "InCadMenu_"
TOOLBAR_GROUP = "User parameter:BaseApp/MainWindow/Toolbars"
NAV_KEYS = {"NavigationStyle": "String", "ZoomAtCursor": "Bool"}
NAV_VALUES = {"NavigationStyle": ("String", "Gui::CADNavigationStyle"), "ZoomAtCursor": ("Bool", True)}
MENUS = [("File", ["file.new", "file.open", "file.save", "file.save_as", "file.close"]),
         ("Edit", ["edit.undo", "edit.redo"]),
         ("View", ["view.theme_toggle", "view.zoom_all", "view.home", "view.style_shaded",
                   "view.style_wireframe", "view.parameters", None, "view.freecad"])]

_shell = None


def _std_new_actions():
    import FreeCADGui as Gui
    try:
        return list(Gui.Command.get("Std_New").getAction())
    except Exception:
        return []


class _DocObserver:
    """FreeCAD document observer: any change schedules one (coalesced) panel refresh."""

    def __init__(self, callback, sketch_callback=None):
        self.callback = callback
        self.sketch_callback = sketch_callback

    def slotCreatedDocument(self, doc):
        self.callback()

    def slotDeletedDocument(self, doc):
        self.callback()

    def slotRelabelDocument(self, doc):
        self.callback()

    def slotActivateDocument(self, doc):
        self.callback()

    def slotCreatedObject(self, obj):
        self.callback()

    def slotDeletedObject(self, obj):
        self.callback()

    def slotChangedObject(self, obj, prop):
        self.callback()
        if prop in ("Constraints", "Geometry") and getattr(obj, "TypeId", "") == "Sketcher::SketchObject" \
                and self.sketch_callback is not None:
            self.sketch_callback(obj)

    def slotRecomputedDocument(self, doc):
        self.callback()


class Shell(QtCore.QObject):
    def __init__(self, mw, registry):
        super().__init__(mw)
        self.mw, self.registry = mw, registry
        self.active = False
        self.theme = "light"
        self.ribbon = self.title = self.browser = self.status = None
        self._snapshot = None
        self._hidden_by_us = set()
        self._widgets = []
        self._menus = []
        self._observer = None
        self._refresh_pending = False
        self._pending = False
        self.navigator = None
        self.strip = None
        self.sketches = SketchSession(on_change=self.schedule_refresh, on_edit=self._seed_geometry)
        self._box_owner = None
        self.value_box = None
        self._shortcuts = {}
        self._geometry_counts = {}
        self.marking_menu = None
        self.menu_kind = None

    # ----- FreeCAD's own UI -----
    def _mdi(self):
        return self.mw.findChild(QtWidgets.QMdiArea)

    def _freecad_toolbars(self):
        return [t for t in self.mw.findChildren(QtWidgets.QToolBar)
                if t.parent() is self.mw and t.objectName() and t.objectName() not in OURS]

    def _freecad_docks(self):
        return [d for d in self.mw.findChildren(QtWidgets.QDockWidget)
                if d.objectName() and d.objectName() not in OURS]

    def _freecad_menu_actions(self):
        return [a for a in self.mw.menuBar().actions()
                if a.text() and not (a.menu() is not None and a.menu().objectName().startswith(MENU_PREFIX))]

    def _capture(self):
        from incad.core import params
        new = _std_new_actions()
        mdi = self._mdi()
        return {
            "toolbars": {t.objectName(): not t.isHidden() for t in self._freecad_toolbars()},
            "docks": {d.objectName(): not d.isHidden() for d in self._freecad_docks()},
            "menus": {a.text(): a.isVisible() for a in self._freecad_menu_actions()},
            "statusbar": not self.mw.statusBar().isHidden(),
            "view": params.snapshot(themes.VIEW_GROUP, themes.VIEW_KEYS),
            "toolbar_params": params.snapshot_group(TOOLBAR_GROUP),
            "nav": params.snapshot(themes.VIEW_GROUP, NAV_KEYS),
            "navicube": params.snapshot(themes.NAVICUBE_GROUP, themes.NAVICUBE_KEYS),
            "sketch": {g: params.snapshot(g, keys) for g, keys in themes.SKETCH_KEYS.items()},
            "std_new": new[0].shortcut().toString() if new else "",
            "mdi": [mdi.viewMode().name, mdi.tabPosition().name] if mdi is not None else None,
        }

    def _hide_freecad(self):
        for w in self._freecad_toolbars() + self._freecad_docks():
            if not w.isHidden():
                self._hidden_by_us.add(w.objectName())
            w.hide()
        for a in self._freecad_menu_actions():
            a.setVisible(False)
        self.mw.statusBar().hide()
        for a in _std_new_actions():
            a.setShortcut(QtGui.QKeySequence())
        mdi = self._mdi()
        if mdi is not None:
            mdi.setViewMode(QtWidgets.QMdiArea.TabbedView)
            mdi.setTabPosition(QtWidgets.QTabWidget.South)

    def _restore_widgets(self, widgets, saved):
        """Only re-show what InCad hid; FreeCAD itself decides what each workbench keeps hidden."""
        for w in widgets:
            name = w.objectName()
            if saved.get(name) or name in self._hidden_by_us:
                w.show()

    def _restore_mdi(self, saved):
        mdi = self._mdi()
        if mdi is not None and saved:
            mdi.setViewMode(getattr(QtWidgets.QMdiArea.ViewMode, saved[0]))
            mdi.setTabPosition(getattr(QtWidgets.QTabWidget.TabPosition, saved[1]))

    def _restore(self, snap):
        from incad.core import params
        steps = [
            ("toolbars", lambda: self._restore_widgets(self._freecad_toolbars(), snap.get("toolbars", {}))),
            ("panels", lambda: self._restore_widgets(self._freecad_docks(), snap.get("docks", {}))),
            ("menus", lambda: [a.setVisible(snap.get("menus", {}).get(a.text(), True))
                               for a in self._freecad_menu_actions()]),
            ("status bar", lambda: self.mw.statusBar().setVisible(snap.get("statusbar", True))),
            # FreeCAD saves toolbar visibility (hidden by us) before calling Deactivated and re-applies it a moment
            # later, so its saved values must be put back too
            ("toolbar settings", lambda: params.restore(TOOLBAR_GROUP, snap.get("toolbar_params", {}))),
            ("3D view colors", lambda: params.restore(themes.VIEW_GROUP, snap["view"]) if "view" in snap else None),
            ("navigation", lambda: params.restore(themes.VIEW_GROUP, snap["nav"]) if "nav" in snap else None),
            ("ViewCube colors", lambda: params.restore(themes.NAVICUBE_GROUP, snap["navicube"])
             if "navicube" in snap else None),
            ("Sketcher settings", lambda: [params.restore(g, v) for g, v in snap.get("sketch", {}).items()]),
            ("New shortcut", lambda: [a.setShortcut(QtGui.QKeySequence(snap.get("std_new") or "Ctrl+N"))
                                      for a in _std_new_actions()]),
            ("document tabs", lambda: self._restore_mdi(snap.get("mdi"))),
        ]
        for name, step in steps:
            try:
                step()
            except Exception as e:
                log.report("warning", "Could not restore FreeCAD's %s: %s" % (name, e), traceback.format_exc())
        self._hidden_by_us = set()

    # ----- activate / deactivate -----
    @staticmethod
    def _edit_open():
        """An edit InCad cannot take over: anything but a sketch in an InCad part (InCad's sketch mode handles those)."""
        import FreeCADGui as Gui
        from incad.core import document, safe, sketch
        gdoc = Gui.ActiveDocument
        vp = gdoc.getInEdit() if gdoc is not None else None
        obj = getattr(vp, "Object", None)
        if sketch.is_sketch(obj) and document.is_incad_part(obj.Document):
            return False
        return vp is not None or safe.edit_open()

    def _activate_when_edit_done(self):
        import FreeCADGui as Gui
        if not self._pending:
            return
        wb = Gui.activeWorkbench()
        if wb is None or wb.name() != "InCadWorkbench":
            self._pending = False
        elif self._edit_open():
            QtCore.QTimer.singleShot(500, self._activate_when_edit_done)
        else:
            self._pending = False
            self.activate()

    def activate(self):
        if self.active:
            return True
        if self._edit_open():  # its OK/Cancel and its open transaction belong to FreeCAD: wait until it is finished
            if not self._pending:
                self._pending = True
                self.mw.statusBar().showMessage("InCad opens when you finish or cancel the current edit")
                QtCore.QTimer.singleShot(500, self._activate_when_edit_done)
            return False
        stale = prefs.takeover_snapshot()
        try:
            self._snapshot = json.loads(stale) if stale else self._capture()
        except ValueError:
            self._snapshot = self._capture()
        prefs.set_takeover_snapshot(json.dumps(self._snapshot))
        try:
            self._hide_freecad()
            self._build()
            self._install_hooks()
            self.apply_theme()
            self.active = True
            self.refresh()
        except Exception as e:
            log.report("error", "InCad could not start its interface: %s" % e, traceback.format_exc())
            self.active = False
            self._teardown()
            self._restore(self._snapshot)
            prefs.clear_takeover_snapshot()
            self._snapshot = None
            return False
        return True

    def deactivate(self):
        self._pending = False
        if not self.active:
            return
        self.active = False
        self._teardown()
        snap = self._snapshot
        if snap is None:
            text = prefs.takeover_snapshot()
            snap = json.loads(text) if text else None
        if snap is not None:
            self._restore(snap)
        prefs.clear_takeover_snapshot()
        self._snapshot = None

    def _reactivate_if_still_open(self):
        import FreeCADGui as Gui
        if QtWidgets.QApplication.activeModalWidget() is not None:  # e.g. "Save changes?" while quitting
            QtCore.QTimer.singleShot(300, self._reactivate_if_still_open)
            return
        wb = Gui.activeWorkbench()
        if self.mw.isVisible() and wb is not None and wb.name() == "InCadWorkbench":
            self.activate()

    # ----- InCad's UI -----
    @staticmethod
    def _setup_bar(bar):
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.toggleViewAction().setVisible(False)

    def _build(self):
        mw = self.mw
        self.theme = themes.current()
        top = QtWidgets.QToolBar("InCad", mw)
        top.setObjectName("InCadTop")
        self._setup_bar(top)
        self._widgets.append(top)
        box = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.title = TitleStrip(self.registry, self.theme, self._settings_menu)
        self.ribbon = Ribbon(self.registry, ribbon_layout.LAYOUT, mode="empty", size=prefs.ribbon_size(),
                             theme=self.theme)
        self.ribbon.sizeChanged.connect(prefs.set_ribbon_size)
        col.addWidget(self.title)
        col.addWidget(self.ribbon)
        box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        top.addWidget(box)
        mw.addToolBar(QtCore.Qt.TopToolBarArea, top)
        dock = QtWidgets.QDockWidget("Model", mw)
        dock.setObjectName("InCadBrowserDock")
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QtWidgets.QWidget())
        dock.setMinimumWidth(230)
        self._widgets.append(dock)
        self.browser = ModelBrowser(self.theme)
        dock.setWidget(self.browser)
        mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        bottom = QtWidgets.QToolBar("InCad Status", mw)
        bottom.setObjectName("InCadStatusBar")
        self._setup_bar(bottom)
        self._widgets.append(bottom)
        self.status = StatusBar(self.theme)
        self.status.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        bottom.addWidget(self.status)
        mw.addToolBar(QtCore.Qt.BottomToolBarArea, bottom)
        self.browser.featureActivated.connect(self._on_feature_activated)
        self.browser.endOfPartMoved.connect(self._on_end_of_part_moved)
        self.browser.actionTriggered.connect(self._on_browser_action)
        self.browser.parameterSet.connect(self._on_parameter_set)
        self.browser.parameterRemoved.connect(self._on_parameter_removed)
        self.navigator = Navigator(self._open_marking_menu, self._on_nav_mode_changed, self)
        self.browser.markingMenuRequested.connect(self._on_browser_marking_menu)
        mdi = self._mdi()
        if mdi is not None:
            self.strip = NavStrip(self.registry, self.theme, mdi.viewport())
            self.strip.place(mdi.viewport().rect())
            self.strip.show()
        self.browser.parameterRenamed.connect(self._on_parameter_renamed)
        self.browser.parameterClicked.connect(self._on_parameter_clicked)
        self.status.dofClicked.connect(lambda: self.registry.run("sketch.show_dof"))
        self.navigator.click_hook = self._click_hook
        self.navigator.dblclick_hook = self._dblclick_hook
        self._build_shortcuts()

    def _build_menus(self):
        bar = self.mw.menuBar()
        for title, ids in MENUS:
            menu = QtWidgets.QMenu(title, bar)
            menu.setObjectName(MENU_PREFIX + title)
            for cmd_id in ids:
                if cmd_id is None:
                    menu.addSeparator()
                    continue
                if not self.registry.has(cmd_id):
                    continue
                cmd = self.registry.get(cmd_id)
                act = menu.addAction(themes.icon(cmd.icon, self.theme), cmd.label)
                if cmd.shortcut:
                    act.setShortcut(QtGui.QKeySequence(cmd.shortcut))
                act.triggered.connect(lambda _=False, i=cmd_id: self.registry.run(i))
            if title == "View":
                menu.addMenu(self.ribbon.size_menu(menu))
            bar.addAction(menu.menuAction())
            self._menus.append(menu)

    def _remove_menus(self):
        for menu in self._menus:
            self.mw.menuBar().removeAction(menu.menuAction())
            menu.deleteLater()
        self._menus = []

    def _teardown(self):
        self.sketches.close_all()
        self._close_value_box()
        for act in self._shortcuts.values():
            try:
                self.mw.removeAction(act)
                act.deleteLater()
            except RuntimeError:
                pass
        self._shortcuts = {}
        self._remove_hooks()
        self._remove_menus()
        for w in self._widgets:
            try:
                if isinstance(w, QtWidgets.QToolBar):
                    self.mw.removeToolBar(w)
                else:
                    self.mw.removeDockWidget(w)
                w.deleteLater()
            except RuntimeError:
                pass
        if self.marking_menu is not None:
            try:
                self.marking_menu.close()
            except RuntimeError:
                pass
            self.marking_menu = None
        if self.navigator is not None:
            self.navigator.detach_all()
            self.navigator = None
        if self.strip is not None:
            try:
                self.strip.deleteLater()
            except RuntimeError:
                pass
            self.strip = None
        self._widgets = []
        self.ribbon = self.title = self.browser = self.status = None

    def _settings_menu(self, parent):
        menu = QtWidgets.QMenu(parent)
        themes_menu = menu.addMenu("Theme")
        for value, label in (("auto", "Match macOS"), ("light", "Light"), ("dark", "Dark")):
            act = themes_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(prefs.theme() == value)
            act.triggered.connect(lambda _=False, v=value: self._set_theme_pref(v))
        menu.addMenu(self.ribbon.size_menu(menu))
        units = menu.addMenu("Units for New Files")
        current = prefs.default_units() if prefs.remember_new_choice() else "ask"
        for value, label in (("ask", "Ask every time"), ("mm", "Always millimeters"), ("in", "Always inches")):
            act = units.addAction(label)
            act.setCheckable(True)
            act.setChecked(current == value)
            act.triggered.connect(lambda _=False, v=value: self._set_new_units(v))
        dims = menu.addMenu("Dimension Display")
        for value, label in (("value", "Value (40)"), ("name", "Name (d3)"), ("expression", "Expression (d3 = 40)")):
            act = dims.addAction(label)
            act.setCheckable(True)
            act.setChecked(prefs.dimension_display() == value)
            act.triggered.connect(lambda _=False, v=value: (prefs.set_dimension_display(v), self.apply_theme()))
        nav_act = menu.addAction("Mouse Navigation (LMB+RMB orbit, right-click menu)")
        nav_act.setCheckable(True)
        nav_act.setChecked(prefs.navigation_enabled())
        nav_act.triggered.connect(lambda checked: self.set_navigation(checked))
        return menu

    def _set_theme_pref(self, value):
        prefs.set_theme(value)
        self.apply_theme()

    @staticmethod
    def _set_new_units(value):
        if value == "ask":
            prefs.set_remember_new_choice(False)
        else:
            prefs.set_default_units(value)
            prefs.set_remember_new_choice(True)

    def apply_theme(self):
        from incad.core import params
        if self.ribbon is None:
            return
        self.theme = themes.current()
        qss = themes.stylesheet(self.theme)
        for w in self._widgets:
            w.setStyleSheet(qss)
        self.ribbon.set_theme(self.theme)
        self.title.set_theme(self.theme)
        self.browser.set_theme(self.theme)
        self.status.set_theme(self.theme)
        self._remove_menus()
        self._build_menus()
        if self.strip is not None:
            self.strip.set_theme(self.theme)
        params.write(themes.NAVICUBE_GROUP, themes.navicube_params(self.theme))
        for group, values in themes.sketch_params(self.theme, prefs.dimension_display()).items():
            params.write(group, values)
        params.write(themes.VIEW_GROUP, themes.view_params(self.theme))

    def set_navigation(self, enabled):
        """Off gives FreeCAD's own navigation back exactly (the user's style and zoom setting)."""
        from incad.core import params
        prefs.set_navigation_enabled(enabled)
        if self.navigator is None:
            return
        if enabled:
            params.write(themes.VIEW_GROUP, NAV_VALUES)
            self.navigator.attach_all()
        else:
            self.navigator.set_mode(None)
            self.navigator.detach_all()
            snap = self._snapshot or json.loads(prefs.takeover_snapshot() or "{}")
            if "nav" in snap:
                params.restore(themes.VIEW_GROUP, snap["nav"])

    def _raise_strip(self, *_):
        """QMdiArea raises a sub-window when it is added or activated; keep the strip above the 3D view."""
        QtCore.QTimer.singleShot(0, lambda: self.strip.raise_() if self.strip is not None else None)

    def _on_nav_mode_changed(self, mode):
        if self.strip is not None:
            self.strip.refresh_checks()
        if self.status is not None:
            hints = {"orbit": "Orbit: drag with the left button (click Orbit again to stop)",
                     "pan": "Pan: drag with the left button (click Pan again to stop)"}
            self.status.set_prompt(hints.get(mode, "Ready"))

    def _show_marking_menu(self, kind, global_pos, flick=False):
        slots, items = marking_layout.resolve(kind, self.registry)
        if not slots and not items:
            return None
        if self.marking_menu is not None:
            try:
                self.marking_menu.close()
            except RuntimeError:
                pass
        menu = MarkingMenu(self.registry, slots, items, self.theme, self.mw)
        menu.destroyed.connect(lambda _=None: setattr(self, "marking_menu", None))
        self.marking_menu, self.menu_kind = menu, kind
        menu.show_at(global_pos)
        if flick:
            menu.start_flick()
        return menu

    def _open_marking_menu(self, view, viewport, local, global_pos, flick):
        import FreeCAD as App
        import FreeCADGui as Gui
        from incad.core import context, document
        if self.sketches.editing() is not None:
            return self._show_marking_menu("sketch", global_pos, flick)
        doc = App.ActiveDocument
        info = view.getObjectInfo(to_coin(viewport, local.x(), local.y())) if doc is not None else None
        context.set_target(None)
        if info:
            comp = info.get("Component", "")
            kind = "edge" if comp.startswith("Edge") else "vertex" if comp.startswith("Vertex") else "face"
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(info["Document"], info["Object"], comp)
        else:
            kind = "part" if document.is_incad_part(doc) else "empty"
        return self._show_marking_menu(kind, global_pos, flick)

    def _on_browser_marking_menu(self, name, global_pos):
        from incad.core import context
        context.set_target(name)
        self._show_marking_menu("browser", global_pos)

    # ----- sketching -----
    def _build_shortcuts(self):
        """Single-key shortcuts (Inventor defaults) for registry commands; enabled per mode in _refresh."""
        menu_owned = {"file.new"}
        for cmd_id in self.registry.ids():
            cmd = self.registry.get(cmd_id)
            if not cmd.shortcut or cmd_id in menu_owned:
                continue
            act = QAction(cmd.label, self.mw)
            act.setShortcut(QtGui.QKeySequence(cmd.shortcut))
            act.setShortcutContext(QtCore.Qt.WindowShortcut)
            act.triggered.connect(lambda _=False, i=cmd_id: self.registry.run(i))
            self.mw.addAction(act)
            self._shortcuts[cmd_id] = act
        self._esc = QAction("Cancel", self.mw)
        self._esc.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape))
        self._esc.setEnabled(False)
        self._esc.triggered.connect(self.sketches.cancel_pick)
        self.mw.addAction(self._esc)
        self._shortcuts["_esc"] = self._esc

    def shortcut_action(self, cmd_id):
        return self._shortcuts.get(cmd_id)

    def _sketch_changed(self, sk):
        """New dimensions get dN names; one added by the Dimension tool (no new geometry) opens the value box."""
        QtCore.QTimer.singleShot(0, lambda: self._name_dimensions(sk))

    def _name_dimensions(self, sk):
        from incad.core import document
        from incad.core import sketch as sketches
        try:
            doc = sk.Document
            if not document.is_incad_part(doc):
                return
            key = (doc.Name, sk.Name)
            count = sk.GeometryCount
            drawn = count != self._geometry_counts.get(key, count)
            self._geometry_counts[key] = count
            added = sketches.name_new_dimensions(doc)
        except Exception as e:
            log.report("warning", "Could not name new dimensions: %s" % e, traceback.format_exc())
            return
        if len(added) == 1 and not drawn and self.sketches.editing() is sk:
            self.open_value_box(sk, added[0])

    def _seed_geometry(self, sk):
        """Baseline for the 'drawn or dimensioned?' rule when a sketch is opened."""
        self._geometry_counts[(sk.Document.Name, sk.Name)] = sk.GeometryCount

    def _apply_from_box(self, name, text):
        """The value box applies to its own sketch's document; returns (ok, error) so the box can stay red."""
        import FreeCAD as App
        from incad.core import safe
        from incad.core import sketch as sketches
        doc_name, _ = self._box_owner or (None, None)
        try:
            doc = App.getDocument(doc_name)
        except Exception:
            return False, "The sketch's document is closed"
        r = safe.run_safely("Set %s" % name, lambda: sketches.set_dimension(doc, name, text), doc)
        self.schedule_refresh()
        return r.ok, r.error

    def open_value_box(self, sk, name):
        from incad.core import sketch as sketches
        self._close_value_box()
        expr = sketches._expression_of(sk, "Constraints." + name)
        text = sketches.to_display(sk.Document, expr) if expr else \
            sketches.document._format(sk.getDatum(name))
        box = ValueBox(name, text, self.theme, self.mw, apply=self._apply_from_box)
        self._box_owner = (sk.Document.Name, sk.Name)
        box.closed.connect(lambda: self._value_box_closed(box))
        self.value_box = box
        box.show_near(QtGui.QCursor.pos())

    def _close_value_box(self):
        if self.value_box is not None:
            try:
                self.value_box.close()
            except RuntimeError:
                pass
            self.value_box = None

    def _value_box_closed(self, box):
        if self.value_box is box:
            self.value_box = None

    def _on_value_applied(self, name, text):
        self._on_parameter_set(name, text)

    def _on_parameter_renamed(self, old, new):
        from incad.core import safe
        from incad.core import sketch as sketches
        doc = self._doc()
        if doc is not None:
            safe.run_safely("Rename %s" % old, lambda: sketches.rename_dimension(doc, old, new), doc)
        self.schedule_refresh()

    def _on_parameter_clicked(self, name):
        if self.value_box is not None:
            self.value_box.insert(name)

    @staticmethod
    def _preselected_dimension():
        """(sketch, name) of the dimension under the cursor, or (None, None)."""
        import FreeCADGui as Gui
        pre = Gui.Selection.getPreselection()
        obj = getattr(pre, "Object", None)
        subs = getattr(pre, "SubElementNames", ()) or ()
        if obj is None or obj.TypeId != "Sketcher::SketchObject":
            return None, None
        for sub in subs:
            if sub.startswith("Constraint"):
                try:
                    c = obj.Constraints[int(sub[len("Constraint"):]) - 1]
                except (ValueError, IndexError):
                    continue
                if c.Name:
                    return obj, c.Name
        return None, None

    def _click_hook(self, view, viewport, x, y):
        if self.value_box is None:
            return False
        sk, name = self._preselected_dimension()
        if name is None:
            return False
        self.value_box.insert(name)
        return True

    def _dblclick_hook(self, view, viewport, x, y):
        sk, name = self._preselected_dimension()
        if name is None or self.sketches.editing() is None:
            return False
        self.open_value_box(sk, name)
        return True

    # ----- hooks -----
    def _install_hooks(self):
        import FreeCAD as App
        log.set_reporter(self._report)
        self.mw.installEventFilter(self)
        for w in self._freecad_toolbars() + self._freecad_docks():
            w.installEventFilter(self)
        self._observer = _DocObserver(self.schedule_refresh, self._sketch_changed)
        App.addDocumentObserver(self._observer)
        QtWidgets.QApplication.instance().styleHints().colorSchemeChanged.connect(self._on_system_scheme)
        from incad.core import params
        mdi = self._mdi()
        if mdi is not None:
            mdi.viewport().installEventFilter(self)
            mdi.subWindowActivated.connect(self._raise_strip)
        if prefs.navigation_enabled():
            params.write(themes.VIEW_GROUP, NAV_VALUES)
            self.navigator.attach_all()

    def _remove_hooks(self):
        import FreeCAD as App
        mdi = self._mdi()
        if mdi is not None:
            try:
                mdi.viewport().removeEventFilter(self)
                mdi.subWindowActivated.disconnect(self._raise_strip)
            except (RuntimeError, TypeError):
                pass
        if self.navigator is not None:
            self.navigator.detach_all()
        log.set_reporter(None)
        for w in [self.mw] + self._freecad_toolbars() + self._freecad_docks():
            try:
                w.removeEventFilter(self)
            except RuntimeError:
                pass
        if self._observer is not None:
            try:
                App.removeDocumentObserver(self._observer)
            except Exception:
                pass
            self._observer = None
        try:
            QtWidgets.QApplication.instance().styleHints().colorSchemeChanged.disconnect(self._on_system_scheme)
        except (RuntimeError, TypeError):
            pass

    def eventFilter(self, obj, event):
        try:
            mdi = self._mdi()
            if self.strip is not None and mdi is not None and obj is mdi.viewport() \
                    and event.type() == QtCore.QEvent.Resize:
                self.strip.place(mdi.viewport().rect())
                return False
            etype = event.type()
            if obj is self.mw:
                if etype == QtCore.QEvent.Close and self.active:
                    self.deactivate()  # FreeCAD saves its window layout right after this
                    QtCore.QTimer.singleShot(0, self._reactivate_if_still_open)
                elif etype == QtCore.QEvent.ChildAdded and self.active:
                    child = event.child()
                    if isinstance(child, (QtWidgets.QToolBar, QtWidgets.QDockWidget)):
                        QtCore.QTimer.singleShot(0, lambda c=child: self._adopt(c))
            elif etype == QtCore.QEvent.Show and self.active and obj.objectName() not in OURS \
                    and isinstance(obj, (QtWidgets.QToolBar, QtWidgets.QDockWidget)):
                QtCore.QTimer.singleShot(0, lambda o=obj: self._rehide(o))
        except Exception:
            log.logger().exception("InCad event filter")
        return False

    def _adopt(self, widget):
        try:
            if not self.active or widget.objectName() in OURS or widget.parent() is not self.mw:
                return
            if not widget.isHidden():
                self._hidden_by_us.add(widget.objectName())
            widget.hide()
            widget.installEventFilter(self)
        except RuntimeError:
            pass

    def _rehide(self, widget):
        try:
            if self.active and not widget.isHidden():
                self._hidden_by_us.add(widget.objectName())
                widget.hide()
        except RuntimeError:
            pass

    def _on_system_scheme(self, *_):
        if prefs.theme() == "auto":
            self.apply_theme()

    def _report(self, level, message):
        if self.status is not None:
            self.status.show_message(level, message)

    # ----- panels -----
    def schedule_refresh(self):
        if self._refresh_pending or self.ribbon is None:
            return
        self._refresh_pending = True
        QtCore.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        self._refresh_pending = False
        if self.ribbon is None:
            return
        try:
            self._refresh()
        except Exception as e:
            log.report("warning", "InCad could not update its panels: %s" % e, traceback.format_exc())

    def _refresh(self):
        import FreeCAD as App
        from incad.core import document, tree
        doc = App.ActiveDocument
        is_part = document.is_incad_part(doc)
        editing = self.sketches.editing() if is_part else None
        self.sketches.sync()
        if self.value_box is not None and (editing is None or
                                           (editing.Document.Name, editing.Name) != self._box_owner):
            self._close_value_box()
        mode = "sketch" if editing is not None else "part" if is_part else "empty"
        self.ribbon.set_mode(mode)
        self.title.set_document_name(doc.Label if doc is not None else "")
        self.browser.set_nodes(tree.build(doc))
        from incad.core import sketch as sketches
        self.browser.set_parameters(document.list_parameters(doc) if is_part else [],
                                    sketches.model_parameters(doc) if is_part else [])
        self.browser.set_parameters_enabled(is_part)
        self.status.set_units(document.part_units(doc) if is_part else None)
        self.status.set_dof(editing.DoF if editing is not None else None)
        if is_part:
            bodies = document.bodies(doc)
            features = sum(1 for b in bodies for o in b.Group if o.TypeId != "Sketcher::SketchObject")
            self.status.set_stats(len(bodies), features)
            if editing is not None:
                self.status.set_prompt("Sketch: draw and dimension, then Finish Sketch (Esc)")
            elif self.sketches.picking:
                self.status.set_prompt("Pick a plane or a flat face for the new sketch (Esc cancels)")
            else:
                self.status.set_prompt("Ready")
        else:
            self.status.set_stats(None, None)
            self.status.set_prompt("Create or open a part" if doc is None else "This file was not made in InCad")
        for cmd_id, act in self._shortcuts.items():
            if cmd_id == "_esc":
                act.setEnabled(self.sketches.picking)
                continue
            ctx = self.registry.get(cmd_id).contexts
            act.setEnabled(commands.ANY in ctx or mode in ctx)
        if self.navigator is not None and prefs.navigation_enabled():
            self.navigator.attach_all()
        if self.strip is not None:
            self.strip.refresh_checks()
            self.strip.raise_()

    # ----- browser actions -----
    @staticmethod
    def _doc():
        import FreeCAD as App
        return App.ActiveDocument

    def _on_feature_activated(self, name):
        from incad.core import context
        context.set_target(name)
        self.registry.run("browser.edit")

    def _on_end_of_part_moved(self, name):
        from incad.core import document, safe
        doc = self._doc()
        if doc is None:
            return
        obj = doc.getObject(name) if name else None
        body = obj.getParentGeoFeatureGroup() if obj is not None else document.primary_body(doc)
        if body is None or body.TypeId != "PartDesign::Body":
            return
        safe.run_safely("Move End of Part", lambda: document.set_end_of_part(body, obj), doc)
        self.schedule_refresh()

    def _on_browser_action(self, action):
        from incad.core import document, safe
        doc = self._doc()
        if action == "convert" and doc is not None:
            safe.run_safely("Convert to InCad Part",
                            lambda: document.convert_to_part(doc, prefs.default_units()), doc)
            self.schedule_refresh()
        elif action == "freecad":
            self.registry.run("view.freecad")

    def _on_parameter_set(self, name, text):
        from incad.core import document, safe
        from incad.core import sketch as sketches
        doc = self._doc()
        if doc is not None:
            if sketches.find_dimension(doc, name)[0] is not None:
                safe.run_safely("Set %s" % name, lambda: sketches.set_dimension(doc, name, text), doc)
            else:
                safe.run_safely("Set %s" % name, lambda: document.set_parameter(doc, name, text), doc)
        self.schedule_refresh()

    def _on_parameter_removed(self, name):
        from incad.core import document, safe
        doc = self._doc()
        if doc is not None:
            safe.run_safely("Remove %s" % name, lambda: document.remove_parameter(doc, name), doc)
        self.schedule_refresh()


# ----- module API -----
def instance():
    return _shell


def activate():
    global _shell
    import FreeCADGui as Gui
    if _shell is None:
        _shell = Shell(Gui.getMainWindow(), commands.REGISTRY)
    return _shell.activate()


def deactivate():
    if _shell is not None:
        _shell.deactivate()


def apply_theme():
    if _shell is not None and _shell.active:
        _shell.apply_theme()


def focus_parameters():
    if _shell is not None and _shell.active:
        _shell.browser.focus_parameters()


def recover_after_crash():
    """At startup: if a snapshot survived (quit or crash while InCad was active) and InCad is not the active
    workbench, put FreeCAD's interface back the way it was."""
    import FreeCADGui as Gui
    text = prefs.takeover_snapshot()
    if not text:
        return
    wb = Gui.activeWorkbench()
    if wb is not None and wb.name() == "InCadWorkbench":
        return  # activate() reuses the saved snapshot
    try:
        Shell(Gui.getMainWindow(), commands.REGISTRY)._restore(json.loads(text))
        log.report("info", "InCad restored FreeCAD's interface after an unexpected exit")
    except Exception as e:
        log.report("warning", "InCad could not restore FreeCAD's interface: %s" % e, traceback.format_exc())
    finally:
        prefs.clear_takeover_snapshot()


def toggle_nav_mode(mode):
    if _shell is not None and _shell.active and _shell.navigator is not None:
        _shell.navigator.set_mode(None if _shell.navigator.mode == mode else mode)


def nav_mode():
    if _shell is not None and _shell.active and _shell.navigator is not None:
        return _shell.navigator.mode
    return None


def sketch_session():
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    return _shell.sketches
