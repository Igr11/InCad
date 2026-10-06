"""Full UI takeover. While InCad is active FreeCAD's menus, toolbars, docks and status bar are hidden and InCad's
title strip, ribbon, Model Browser and status bar are shown. Everything is restored on exit, also after a quit or
a crash with InCad active: the snapshot stays in InCad's preferences until the restore has been done."""
import json
import os
import traceback

from incad.core import commands, log, prefs
from incad.qt import dispose, QAction, QtCore, QtGui, QtWidgets
from incad.ui import ribbon_layout
from incad.ui import theme as themes
from incad.ui.browser import ModelBrowser
from incad.ui.ribbon import Ribbon
from incad.ui.statusbar import StatusBar
from incad.ui.titlebar import TitleStrip
from incad.ui.sketch_session import SketchSession
from incad.ui.value_box import ValueBox
from incad.ui.feature_session import FeatureSession
from incad.ui.info_panel import InfoPanel
from incad.ui.plane_panel import PlanePanel
from incad.ui import marking_layout
from incad.ui.marking_menu import MarkingMenu
from incad.ui.nav import Navigator, to_coin
from incad.ui.nav_strip import NavStrip

OURS = ("InCadTop", "InCadBrowserDock", "InCadStatusBar")
MENU_PREFIX = "InCadMenu_"
TOOLBAR_GROUP = "User parameter:BaseApp/MainWindow/Toolbars"
NAV_KEYS = {"NavigationStyle": "String", "ZoomAtCursor": "Bool"}
NAV_VALUES = {"NavigationStyle": ("String", "Gui::CADNavigationStyle"), "ZoomAtCursor": ("Bool", True)}
MENUS = [("File", ["file.new", "file.open", "file.save", "file.save_as", "file.close", None, "file.quit"]),
         ("Edit", ["edit.undo", "edit.redo"]),
         ("View", ["view.theme_toggle", "view.zoom_all", "view.home", "view.style_shaded",
                   "view.style_wireframe", "view.parameters", None, "view.freecad"])]

_shell = None


# FreeCAD commands whose shortcuts InCad's own menus take over while active: FreeCAD's actions sit in its hidden
# menus, where they no longer answer keys (probed: ⌘Z did nothing), so InCad owns the keys and gives them back.
TAKEN_SHORTCUTS = ("Std_New", "Std_Open", "Std_Save", "Std_SaveAs", "Std_CloseActiveWindow", "Std_Undo", "Std_Redo",
                   "Std_Quit")


def _std_actions(name):
    import FreeCADGui as Gui
    try:
        return list(Gui.Command.get(name).getAction())
    except Exception:
        return []


def _std_new_actions():
    return _std_actions("Std_New")


class _DocObserver:
    """FreeCAD document observer: any change schedules one (coalesced) panel refresh."""

    def __init__(self, callback, sketch_callback=None, undo_callback=None):
        self.callback = callback
        self.sketch_callback = sketch_callback
        self.undo_callback = undo_callback

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

    def slotUndoDocument(self, doc):
        self.callback()
        if self.undo_callback is not None:
            self.undo_callback(doc)

    def slotRedoDocument(self, doc):
        self.slotUndoDocument(doc)

    def slotRecomputedDocument(self, doc):
        self.callback()


class _MeasurePicker:
    """While Measure is live: any selection change measures again."""

    def __init__(self, shell, mode):
        self.shell, self.mode = shell, mode

    def _again(self):
        shell = self.shell
        QtCore.QTimer.singleShot(0, lambda: shell._measure is self and shell.active and shell.inspect(self.mode))

    def addSelection(self, doc_name, obj_name, sub, pnt):
        self._again()

    def removeSelection(self, doc_name, obj_name, sub):
        self._again()

    def clearSelection(self, doc_name):
        self._again()


class _RegionPicker:
    """Waits for a click on one of the shown areas of a sketch, then starts the feature on it."""

    def __init__(self, shell, kind, doc_name, body_name, source_name, names, faces):
        self.shell, self.kind = shell, kind
        self.doc_name, self.body_name, self.source_name, self.names, self.faces = doc_name, body_name, source_name, names, faces

    def addSelection(self, doc_name, obj_name, sub, pnt):
        if doc_name == self.doc_name and obj_name in self.names:
            index, shell = self.names.index(obj_name), self.shell
            QtCore.QTimer.singleShot(0, lambda: shell._region_pick is self and shell._region_picked(self, index))


class _ProfilePicker:
    """Waits for the user to pick a sketch with a closed profile, then starts the feature."""

    def __init__(self, shell, kind):
        self.shell, self.kind = shell, kind

    def addSelection(self, doc_name, obj_name, sub, pnt):
        import FreeCAD as App
        from incad.core import sketch
        from incad.features.common import closed_profile
        obj = App.getDocument(doc_name).getObject(obj_name)
        from incad.core import regions
        if sketch.is_sketch(obj) and (closed_profile(obj) or regions.needs_regions(obj)):
            shell, kind = self.shell, self.kind
            QtCore.QTimer.singleShot(0, lambda: (shell._cancel_profile_pick(), shell.start_feature(kind)))


def _is_overlay(w):
    return isinstance(w, QtWidgets.QTabWidget) and w.objectName().startswith("Overlay")


def _overlays(mw):
    return [t for t in mw.findChildren(QtWidgets.QTabWidget) if t.parent() is mw and _is_overlay(t)]


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
        self.feature_session = None
        self.info_panel = None
        self.plane_panel = None
        self.slot_tool = None
        self.construction_mode = False   # InCad's own: FreeCAD's construction mode can't be read back
        self._construction_from = {}     # (doc, sketch) -> geometry count when construction mode was turned on
        self._profile_pick = None
        self.value_box = None
        self._shortcuts = {}
        self._geometry_counts = {}
        self._region_pick = None  # waiting for a click on one of a sketch's shown areas
        self._measure = None  # live Measure (a selection observer) while it is on
        self._dim_known = {}  # (doc, sketch) -> dimension snapshot after the last change (replacement tracking)
        self._box_focus_hooked = False

        self._wait_notice = None
        self._polygons_from = {}
        self.marking_menu = None
        self.menu_kind = None

    # ----- FreeCAD's own UI -----
    def _mdi(self):
        return self.mw.findChild(QtWidgets.QMdiArea)

    def _freecad_toolbars(self):
        return [t for t in self.mw.findChildren(QtWidgets.QToolBar)
                if t.parent() is self.mw and t.objectName() and t.objectName() not in OURS]

    def _freecad_docks(self):
        """FreeCAD's panels, and the overlay containers (OverlayLeft/Right/…) they float in when overlay mode is on
        — those showed FreeCAD's 'Tasks' strip over InCad's view."""
        docks = [d for d in self.mw.findChildren(QtWidgets.QDockWidget)
                 if d.objectName() and d.objectName() not in OURS]
        return docks + _overlays(self.mw)

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
            "std_shortcuts": {c: (_std_actions(c)[0].shortcut().toString() if _std_actions(c) else "")
                              for c in TAKEN_SHORTCUTS},
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
        for name in TAKEN_SHORTCUTS:
            for a in _std_actions(name):
                a.setShortcut(QtGui.QKeySequence())
        # macOS wires the app menu's Quit to the first QuitRole action: FreeCAD's Exit sits in its hidden File menu,
        # where a click on that Quit never reaches Qt (probed with a real menu click). InCad's takes the slot.
        for a in _std_actions("Std_Quit"):
            a.setMenuRole(QAction.NoRole)
        mdi = self._mdi()
        QtCore.QTimer.singleShot(0, self._front_last_view)
        if mdi is not None:
            mdi.setViewMode(QtWidgets.QMdiArea.TabbedView)
            mdi.setTabPosition(QtWidgets.QTabWidget.South)

    def _restore_widgets(self, widgets, saved):
        """Only re-show what InCad hid; FreeCAD itself decides what each workbench keeps hidden."""
        for w in widgets:
            name = w.objectName()
            if saved.get(name) or name in self._hidden_by_us:
                w.show()

    @staticmethod
    def _restore_shortcuts(snap):
        saved = snap.get("std_shortcuts") or {"Std_New": snap.get("std_new") or "Ctrl+N"}  # older snapshots
        for name, seq in saved.items():
            for a in _std_actions(name):
                a.setShortcut(QtGui.QKeySequence(seq))
        for a in _std_actions("Std_Quit"):
            a.setMenuRole(QAction.QuitRole)

    def _on_subwindow(self, window):
        if window is not None and _is_start_page(window):  # FreeCAD's Start page came up (seen after Finish
            QtCore.QTimer.singleShot(0, self._front_last_view)  # Sketch): the part stays in front

    def _front_last_view(self):
        """FreeCAD's Start page never stays in front in InCad: back to the view shown before it. It is not closed
        or hidden: closing it crashes FreeCAD while its setup timer is pending, hiding it breaks the tabbed layout
        (both probed). No Python handle on these windows is kept (handles left at exit crashed FreeCAD)."""
        mdi = self._mdi()
        if mdi is None or not self.active:
            return
        try:
            active = mdi.activeSubWindow()
            if active is None or not _is_start_page(active):
                return
            history = [w for w in mdi.subWindowList(QtWidgets.QMdiArea.ActivationHistoryOrder)
                       if not _is_start_page(w)]
            if history:
                mdi.setActiveSubWindow(history[-1])
        except RuntimeError:
            pass

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
            ("shortcuts", lambda: self._restore_shortcuts(snap)),
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

    @staticmethod
    def _finish_freecad_sketch():
        """A FreeCAD sketch being edited is simply closed (its changes are already in the model), so switching to
        InCad from Sketcher or Part Design takes over at once."""
        import FreeCADGui as Gui
        from incad.core import document, sketch
        gdoc = Gui.ActiveDocument
        vp = gdoc.getInEdit() if gdoc is not None else None
        obj = getattr(vp, "Object", None)
        if sketch.is_sketch(obj) and not document.is_incad_part(obj.Document):
            gdoc.resetEdit()

    def _show_wait_notice(self):
        """Other FreeCAD tasks keep their OK/Cancel: say plainly why InCad's interface isn't there yet."""
        if self._wait_notice is None:
            box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information, "InCad",
                                        "Finish or cancel the current FreeCAD task (OK or Cancel in its panel).\n"
                                        "InCad opens as soon as it is closed.", QtWidgets.QMessageBox.Ok, self.mw)
            box.setObjectName("InCadWaitNotice")
            box.setWindowModality(QtCore.Qt.NonModal)
            self._wait_notice = box
        self._wait_notice.show()
        self._wait_notice.raise_()

    def _close_wait_notice(self):
        if self._wait_notice is not None:
            self._wait_notice.hide()
            dispose(self._wait_notice)
            self._wait_notice = None

    def _activate_when_edit_done(self):
        import FreeCADGui as Gui
        if not self._pending:
            return
        if self._edit_open():
            QtCore.QTimer.singleShot(500, self._activate_when_edit_done)
            return
        self._pending = False
        self._close_wait_notice()
        wb = Gui.activeWorkbench()
        if wb is None or wb.name() != "InCadWorkbench":
            # closing a Part Design task switches back to Part Design by itself; the user asked for InCad
            Gui.activateWorkbench("InCadWorkbench")
        else:
            self.activate()

    def activate(self):
        if self.active:
            return True
        self._finish_freecad_sketch()
        if self._edit_open():  # its OK/Cancel and its open transaction belong to FreeCAD: wait until it is finished
            if not self._pending:
                self._pending = True
                self._show_wait_notice()
                QtCore.QTimer.singleShot(500, self._activate_when_edit_done)
            return False
        self._close_wait_notice()
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
        if self._pending and self._edit_open():  # the user left InCad while the FreeCAD task is still open
            self._pending = False
            self._close_wait_notice()
        # (a task that just closed switches to its own workbench by itself: keep waiting, InCad comes back)
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
        self.browser.featureSelected.connect(self._on_browser_select)
        mdi = self._mdi()
        if mdi is not None:
            self.strip = NavStrip(self.registry, self.theme, mdi.viewport())
            self.strip.place(mdi.viewport().rect())
            self.strip.show()
            self.plane_panel = PlanePanel(self.theme, mdi.viewport())
            self.plane_panel.picked.connect(self._on_plane_picked)
            self.plane_panel.cancelled.connect(self.sketches.cancel_pick)
            self.plane_panel.hide()
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
                if cmd_id == "file.quit":
                    # ours stays a normal File item that owns ⌘Q; a second one, without a shortcut, becomes the app
                    # menu's Quit (macOS moves the QuitRole action there)
                    act.setMenuRole(QAction.NoRole)
                    app_quit = menu.addAction(cmd.label)
                    app_quit.setObjectName("InCadAppQuit")
                    app_quit.setMenuRole(QAction.QuitRole)
                    app_quit.triggered.connect(lambda _=False: self.registry.run("file.quit"))
            if title == "View":
                menu.addMenu(self.ribbon.size_menu(menu))
            bar.addAction(menu.menuAction())
            self._menus.append(menu)

    def _remove_menus(self):
        for menu in self._menus:
            self.mw.menuBar().removeAction(menu.menuAction())
            dispose(menu)
        self._menus = []

    def _teardown(self):
        self.stop_slot_tool()
        self._stop_measuring()
        self._cancel_region_pick()
        self._close_feature_session(cancel=True)
        self._close_info_panel()
        self._cancel_profile_pick()
        self.sketches.close_all()
        self._close_value_box()
        for act in self._shortcuts.values():
            try:
                self.mw.removeAction(act)
                dispose(act)
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
                dispose(w)
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
                dispose(self.strip)
            except RuntimeError:
                pass
            self.strip = None
        if self.plane_panel is not None:
            try:
                dispose(self.plane_panel)
            except RuntimeError:
                pass
            self.plane_panel = None
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
        self._close_info_panel()  # it was drawn for the old theme
        if self.plane_panel is not None:
            self.plane_panel.set_theme(self.theme)
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
        """QMdiArea raises a sub-window when it is added or activated, over InCad's panels in the view area: keep
        them all on top (a buried feature dialog stayed open unseen, and every other command was refused)."""
        QtCore.QTimer.singleShot(0, self._raise_overlays)

    def _dialog_first(self):
        """The error for a command refused while a feature dialog is open, and that dialog brought to the front."""
        self._show_open_dialog()
        return ValueError("Finish the %s dialog first" % self.feature_session.kind.TITLE)

    def _show_open_dialog(self):
        fs = self.feature_session
        if fs is None and self._edit_open():
            self._show_wait_notice()
            return
        if fs is not None and fs.dialog is not None:
            try:
                if not fs.dialog.isVisible():
                    fs.dialog.show()
                fs.dialog.raise_()  # raise only: show() on a visible dialog moves the keyboard focus
            except RuntimeError:
                pass

    def _raise_overlays(self):
        fs = self.feature_session
        for w in (self.strip, self.plane_panel, self.info_panel, self.value_box,
                  fs.dialog if fs is not None else None):
            try:
                if w is not None and w.isVisible():
                    w.raise_()
            except RuntimeError:
                pass

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
        from incad.core import assembly
        if assembly.is_assembly(doc):
            kind = {"face": "asm_face", "edge": "asm_edge", "vertex": "asm_edge"}.get(kind, "assembly")
        return self._show_marking_menu(kind, global_pos, flick)

    def _on_browser_select(self, name):
        """A click in the model tree selects the object in the model too, so a dialog waiting for a sketch or a
        feature takes it (Inventor picks from the browser)."""
        import FreeCAD as App
        import FreeCADGui as Gui
        doc = App.ActiveDocument
        if doc is None or doc.getObject(name) is None:
            return
        waiting = (self.feature_session is not None and self.feature_session.dialog is not None
                   and self.feature_session.dialog.active_pick() is not None) or self._profile_pick is not None \
            or self.sketches.picking
        if not waiting:
            return  # just looking at the tree: the 3D selection stays
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, name)

    def _on_browser_marking_menu(self, name, global_pos):
        import FreeCAD as App
        from incad.core import context
        context.set_target(name)
        obj = App.ActiveDocument.getObject(name) if App.ActiveDocument is not None else None
        kind = "origin" if obj is not None and obj.TypeId in ("App::Plane", "App::Line", "App::Point") else "browser"
        self._show_marking_menu(kind, global_pos)

    # ----- sketching -----
    def _build_shortcuts(self):
        """Single-key shortcuts (Inventor defaults) for registry commands; enabled per mode in _refresh."""
        menu_owned = {i for _, ids in MENUS for i in ids if i}
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
        self._esc.triggered.connect(self._on_escape)
        self.mw.addAction(self._esc)
        self._shortcuts["_esc"] = self._esc

    def _on_escape(self):
        """Esc, Inventor style: the value box first, then InCad's own picks and tools, then the feature dialog,
        else the running Sketcher tool (the sketch itself is left with Finish Sketch, never with Esc)."""
        if self.value_box is not None:
            self._close_value_box()
            return
        if self.sketches.picking or self._profile_pick is not None or self.slot_tool is not None \
                or self._region_pick is not None:
            self.sketches.cancel_pick()
            self._cancel_profile_pick()
            self._cancel_region_pick()
            self.stop_slot_tool()
            return
        if self._measure is not None:
            self._stop_measuring()
            self._close_info_panel()
            self.status.set_prompt("Ready")
            return
        if self.feature_session is not None:
            self.feature_session.cancel()
            return
        import FreeCADGui as Gui
        if self.sketches.editing() is not None:
            Gui.runCommand("Sketcher_StopOperation")  # ends the running Sketcher tool; the sketch stays open
            return
        mdi = self._mdi()
        views = [w for w in mdi.findChildren(QtWidgets.QGraphicsView) if w.isVisible()] if mdi is not None else []
        if views:  # outside a sketch: FreeCAD's own Esc handling, with InCad's shortcut off meanwhile (it would
            vp = views[0].viewport()  # catch its own key again: recursion)
            self._esc.setEnabled(False)
            try:
                for etype in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                    QtWidgets.QApplication.sendEvent(vp, QtGui.QKeyEvent(etype, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier))
            finally:
                self._esc.setEnabled(True)

    # ----- InCad's own sketch tools -----
    def start_slot_tool(self, mode):
        import FreeCADGui as Gui
        from incad.ui.slot_tool import SlotTool
        gdoc = Gui.ActiveDocument
        edit = gdoc.getInEdit() if gdoc is not None else None
        sk = getattr(edit, "Object", None)
        if sk is None or sk.TypeId != "Sketcher::SketchObject":
            raise ValueError("Open a sketch first")
        self.stop_slot_tool()
        Gui.runCommand("Sketcher_StopOperation")  # no FreeCAD tool fighting for the clicks
        self.slot_tool = SlotTool(gdoc.ActiveView, sk, mode, on_finish=self._slot_tool_done)
        self.slot_tool.start()
        self.schedule_refresh()
        return self.slot_tool

    def stop_slot_tool(self):
        tool, self.slot_tool = getattr(self, "slot_tool", None), None
        if tool is not None:
            tool.stop()

    def _slot_tool_done(self, tool):
        if getattr(self, "slot_tool", None) is tool:
            self.slot_tool = None
        self.schedule_refresh()

    def shortcut_action(self, cmd_id):
        return self._shortcuts.get(cmd_id)

    def _sketch_changed(self, sk):
        """New dimensions get dN names; one added by the Dimension tool (no new geometry) opens the value box."""
        QtCore.QTimer.singleShot(0, lambda: self._name_dimensions(sk))
        QtCore.QTimer.singleShot(0, lambda: self._pin_new_polygons(sk))
        QtCore.QTimer.singleShot(0, lambda: self._update_area_profiles(sk))
        if self.construction_mode:
            QtCore.QTimer.singleShot(0, lambda: self._make_construction(sk))

    def toggle_construction(self):
        """Inventor's Construction button: with sketch geometry selected, switch it; otherwise turn the drawing
        mode on/off (new geometry becomes construction while on)."""
        import FreeCADGui as Gui
        from incad.core import log
        sk = self.sketches.editing()
        if sk is None:
            raise ValueError("Open a sketch first")
        picked = [sub for sel in Gui.Selection.getSelectionEx(sk.Document.Name) if sel.Object is sk
                  for sub in sel.SubElementNames if sub.startswith("Edge")]
        if picked:  # the whole profile of each picked edge (a polygon's sides), not one edge at a time
            from incad.core import safe, sketch
            ids = [int(sub[4:]) - 1 for sub in picked]
            safe.run_safely("Construction", lambda: sketch.toggle_construction(sk, ids), sk.Document)
            Gui.Selection.clearSelection()
            return
        self.construction_mode = not self.construction_mode
        self._construction_from[(sk.Document.Name, sk.Name)] = sk.GeometryCount
        log.report("info", "Construction on: new geometry is construction (click again to stop)"
                   if self.construction_mode else "Construction off: normal geometry")
        if self.ribbon is not None:
            self.ribbon.refresh_checks()

    def _make_construction(self, sk):
        if not _alive(sk):
            return  # deleted meanwhile (these handlers run just after the change)
        try:
            key = (sk.Document.Name, sk.Name)
            start = self._construction_from.get(key, sk.GeometryCount)
            new = [i for i in range(start, sk.GeometryCount) if not sk.getConstruction(i)]
            self._construction_from[key] = sk.GeometryCount
            for i in new:
                sk.setConstruction(i, True)
            if new:
                sk.Document.recompute()
        except Exception as e:
            log.report("warning", "Could not make the new geometry construction: %s" % e)

    def _name_dimensions(self, sk):
        from incad.core import document
        from incad.core import sketch as sketches
        try:
            doc = sk.Document
        except Exception:
            return  # its file was closed meanwhile: nothing to name
        try:
            if not document.is_incad_part(doc):
                return
            key = (doc.Name, sk.Name)
            count = sk.GeometryCount
            drawn = count != self._geometry_counts.get(key, count)
            self._geometry_counts[key] = count
            known = self._dim_known.get(key)
            replaced = sketches.reconcile_replaced(sk, known) if known else None
            box = self.value_box
            if replaced and box is not None and box.name == replaced:
                if not box._typed:  # the replacement may be another kind (two lines picked: an angle)
                    box.edit.setText(sketches.document._format(sk.getDatum(replaced)))
                for ms in (150, 400, 800):  # the view takes the keyboard back when the placing click ends
                    QtCore.QTimer.singleShot(ms, lambda b=box: self.value_box is b and b.take_keyboard())
            elif known and box is not None and self._box_owner == key and box.name in sketches.vanished_dimensions(sk, known):
                self._close_value_box()  # its dimension is gone (tool cancelled, undo): nothing to apply to
            added = []
            if not replaced:
                if doc.HasPendingTransaction:
                    added = sketches.name_new_dimensions(doc)
                else:
                    doc.openTransaction("Name dimension")  # the name survives undo/redo with the dimension
                    try:
                        added = sketches.name_new_dimensions(doc)
                    finally:
                        doc.commitTransaction()
            self._dim_known[key] = sketches.dimension_snapshot(sk)
        except Exception as e:
            log.report("warning", "Could not name new dimensions: %s" % e, traceback.format_exc())
            return
        if len(added) == 1 and not drawn and self.sketches.editing() is sk:
            self.open_value_box(sk, added[0])

    def _after_undo(self, doc):
        """Undo/redo can bring objects back without their formula links (FreeCAD quirk): repair them."""
        def repair():
            from incad.core import model
            try:
                model.relink(doc)
            except Exception as e:
                log.report("warning", "Could not repair formula links: %s" % e, traceback.format_exc())
        QtCore.QTimer.singleShot(0, repair)
        box = self.value_box
        if box is not None and self._box_owner and self._box_owner[0] == doc.Name:
            from incad.core import sketch as sketches
            QtCore.QTimer.singleShot(0, lambda: self.value_box is box and sketches.find_dimension(doc, box.name)[0] is None
                                     and self._close_value_box())  # its dimension was undone
        editing = self.sketches.editing()
        if editing is not None:
            from incad.core import sketch as sketches
            QtCore.QTimer.singleShot(0, lambda: _alive(editing) and self._dim_known.__setitem__(
                (editing.Document.Name, editing.Name), sketches.dimension_snapshot(editing)))

    def _seed_geometry(self, sk):
        """Baseline for the 'drawn or dimensioned?' rule when a sketch is opened."""
        from incad.core import sketch as sketches
        self._geometry_counts[(sk.Document.Name, sk.Name)] = sk.GeometryCount
        self._dim_known[(sk.Document.Name, sk.Name)] = sketches.dimension_snapshot(sk)
        self._polygons_from[(sk.Document.Name, sk.Name)] = sk.GeometryCount

    def _update_area_profiles(self, sk):
        """Features built on an area of this sketch follow its edits (the area holding the remembered point)."""
        from incad.core import regions
        if not _alive(sk) or regions.is_profile(sk):
            return
        try:
            profiles = regions.profiles_of(sk)
            if not profiles:
                return
            lost = [p for p in profiles if not regions.update(p)]
            sk.Document.recompute()
            for p in lost:
                log.report("warning", "The area of %s used by %s is gone: it keeps its previous outline" % (
                    sk.Label, ", ".join(o.Label for o in p.InList if getattr(o, "Profile", None) is not None)))
        except Exception as e:
            log.report("warning", "Could not update the areas of %s: %s" % (sk.Label, e), traceback.format_exc())

    def _pin_new_polygons(self, sk):
        """A new polygon keeps its centre's snap to the origin or an axis (only new geometry: a constraint the user
        deleted later is not put back)."""
        from incad.core import sketch as sketches
        if not _alive(sk):
            return  # deleted meanwhile (these handlers run just after the change)
        try:
            key = (sk.Document.Name, sk.Name)
            first = self._polygons_from.get(key, sk.GeometryCount)
            if sk.GeometryCount <= first:
                self._polygons_from[key] = sk.GeometryCount
                return
            if sketches.pin_polygon_centres(sk, first):
                sk.Document.recompute()
            self._polygons_from[key] = sk.GeometryCount
        except Exception as e:
            log.report("warning", "Could not keep the polygon's centre constraint: %s" % e)

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
        sk = doc.getObject(self._box_owner[1])
        key = tuple(self._box_owner)
        if sk is not None and sketches.find_dimension(doc, name)[0] is None and self._dim_known.get(key):
            try:
                sketches.reconcile_replaced(sk, self._dim_known[key])  # replaced by the placing click just now
            except Exception as e:
                log.report("warning", "Could not find %s again: %s" % (name, e))
        r = safe.run_safely("Set %s" % name, lambda: sketches.set_dimension(doc, name, text), doc)
        if r.ok and sk is not None:
            self._dim_known[key] = sketches.dimension_snapshot(sk)
        self.schedule_refresh()
        return r.ok, r.error

    def open_value_box(self, sk, name):
        from incad.core import sketch as sketches
        self._close_value_box(apply_if_typed=True)
        expr = sketches._expression_of(sk, "Constraints." + name)
        text = sketches.to_display(sk.Document, expr) if expr else \
            sketches.document._format(sk.getDatum(name))
        parent = self._mdi().viewport() if self._mdi() is not None else self.mw
        box = ValueBox(name, text, self.theme, parent, apply=self._apply_from_box)
        self._box_owner = (sk.Document.Name, sk.Name)
        box.closed.connect(lambda: self._value_box_closed(box))
        self.value_box = box
        app = QtWidgets.QApplication.instance()
        if not self._box_focus_hooked:
            app.focusChanged.connect(self._keep_box_keyboard)
            self._box_focus_hooked = True
        box.show_near(QtGui.QCursor.pos())

    def _close_value_box(self, apply_if_typed=False):
        """apply_if_typed: the user moved on (next dimension, Finish Sketch, another tab) — what was typed is
        applied first instead of silently dropped; a value that can't be used is reported."""
        box = self.value_box
        if box is None:
            return
        try:
            if apply_if_typed and box._typed and box.edit.text().strip():
                ok, error = self._apply_from_box(box.name, box.edit.text().strip())
                if not ok:
                    log.report("warning", "%s = %s was not applied: %s" % (box.name, box.edit.text().strip(), error))
            box.close()
        except RuntimeError:
            pass
        self.value_box = None

    def _keep_box_keyboard(self, _old, new):
        """FreeCAD's 3D view takes the keyboard whenever the mouse moves over it: while the dimension box is open,
        typing, Enter and Esc belong to the box (other fields, e.g. the parameter table, keep it)."""
        box = self.value_box
        if box is None or new is None or not self.active:
            return
        w = new
        while w is not None:
            if isinstance(w, QtWidgets.QGraphicsView):
                QtCore.QTimer.singleShot(0, lambda b=box: self.value_box is b and b.take_keyboard())
                return
            w = w.parentWidget()

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
            from incad.core import model
            safe.run_safely("Rename %s" % old, lambda: model.rename_model_parameter(doc, old, new), doc)
        self.schedule_refresh()

    def _on_parameter_clicked(self, name):
        if self.value_box is not None:
            if name != self.value_box.name:
                self.value_box.insert(name)
        elif self.feature_session is not None:
            self.feature_session.insert(name)

    @staticmethod
    def _preselected_dimension():
        """(sketch, name) of the dimension under the cursor, or (None, None)."""
        import FreeCADGui as Gui
        try:
            pre = Gui.Selection.getPreselection()
            obj = getattr(pre, "Object", None)
            subs = getattr(pre, "SubElementNames", ()) or ()
            if obj is None or obj.TypeId != "Sketcher::SketchObject":
                return None, None
        except RuntimeError:  # the preselected object was just deleted
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
        if self.value_box is None and self.feature_session is None:
            return False
        sk, name = self._preselected_dimension()
        if name is None and self.value_box is not None:
            # FreeCAD doesn't preselect dimensions while a Sketcher tool runs (the Dimension tool keeps running
            # after placing one): find the label under the click ourselves
            sk, name = self._dimension_near(view, viewport, x, y)
        if name is None:
            return False
        if self.value_box is not None:
            if name == self.value_box.name:
                return True  # the dimension being edited: nothing to insert, the click is not a tool click
            self.value_box.insert(name)
        elif not self.feature_session.insert(name):
            return False
        return True

    LABEL_PICK_PX = 24  # logical pixels around a dimension's text

    def _dimension_near(self, view, viewport, x, y):
        from incad.core import sketch as sketches
        sk = self.sketches.editing()
        if sk is None or view is None or viewport is None:
            return None, None
        try:
            dpr = viewport.devicePixelRatioF()
            px, py = x * dpr, (viewport.height() - y) * dpr  # Coin: device px, bottom-left origin
            best, best_d = None, self.LABEL_PICK_PX * dpr
            for c in sk.Constraints:
                if not c.Name:
                    continue
                pt = sketches.label_point(sk, c.Name)
                if pt is None:
                    continue
                lx, ly = view.getPointOnViewport(pt)
                d = ((lx - px) ** 2 + (ly - py) ** 2) ** 0.5
                if d < best_d:
                    best, best_d = c.Name, d
            return (sk, best) if best else (None, None)
        except Exception:
            log.logger().exception("InCad dimension pick")
            return None, None

    def _dblclick_hook(self, view, viewport, x, y):
        if self.sketches.editing() is None:
            return False
        sk, name = self._preselected_dimension()
        if name is None:
            sk, name = self._dimension_near(view, viewport, x, y)  # FreeCAD preselects nothing while a tool runs
        if name is None:
            return False
        self.open_value_box(sk, name)
        return True

    # ----- features -----
    def _close_feature_session(self, cancel):
        fs = self.feature_session
        if fs is not None:
            fs.cancel() if cancel else fs.ok()
        self.feature_session = None

    def _session_closed(self, fs):
        if self.feature_session is fs:
            self.feature_session = None
        dispose(fs)
        self.schedule_refresh()

    def _profile_for(self, doc, body):
        import FreeCADGui as Gui
        from incad.core import sketch
        from incad.features.common import closed_profile, unconsumed_closed_sketches
        from incad.core import regions
        for sel in Gui.Selection.getSelectionEx(doc.Name):
            if sketch.is_sketch(sel.Object) and (closed_profile(sel.Object) or regions.needs_regions(sel.Object)):
                return sel.Object
        editing = self.sketches.editing()
        if editing is not None and (closed_profile(editing) or regions.needs_regions(editing)):
            self.sketches.finish()
            return editing
        candidates = unconsumed_closed_sketches(body)
        return candidates[0] if len(candidates) == 1 else None

    def _profile_from_areas(self, kind, doc, body, source):
        """Inventor: the areas between the sketch's lines are the profiles. One area: used at once. Several: they
        are shown and the user clicks the one to use (Esc cancels)."""
        from incad.core import regions
        faces = regions.regions(source)
        if not faces:
            raise ValueError("%s has no closed area to %s" % (source.Label, kind.TITLE.lower()))
        if len(faces) == 1:
            prof = regions.make_profile(doc, body, source, faces[0])
            self._open_session(kind, doc, body, profile=prof)
            return
        self._cancel_region_pick()
        doc.openTransaction("Pick area")  # the shown areas vanish with the pick (aborted): no undo step
        names = []
        pl = source.getGlobalPlacement()
        for i, f in enumerate(faces):
            o = doc.addObject("Part::Feature", "Area%d" % (i + 1))
            o.Label = "Area %d" % (i + 1)
            shape = f.copy()
            shape.Placement = pl
            o.Shape = shape
            try:
                vo = o.ViewObject
                vo.ShapeColor = (0.95, 0.62, 0.29)
                vo.Transparency = 55
                vo.LineWidth = 1.0
            except Exception:
                pass
            names.append(o.Name)
        doc.recompute()
        import FreeCADGui as Gui
        self._region_pick = _RegionPicker(self, kind, doc.Name, body.Name, source.Name, names, faces)
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self._region_pick)
        self.status.set_prompt("Click the area to %s (Esc cancels)" % kind.TITLE.lower())
        log.report("info", "%d areas: click the one to %s" % (len(faces), kind.TITLE.lower()))
        self.schedule_refresh()

    def _cancel_region_pick(self):
        import FreeCAD as App
        import FreeCADGui as Gui
        pick = self._region_pick
        if pick is None:
            return
        self._region_pick = None
        try:
            Gui.Selection.removeObserver(pick)
        except Exception:
            pass
        doc = App.getDocument(pick.doc_name) if pick.doc_name in App.listDocuments() else None
        if doc is not None and doc.HasPendingTransaction:
            doc.abortTransaction()  # the shown areas go
            doc.recompute()
        self.schedule_refresh()

    def _region_picked(self, pick, index):
        import FreeCAD as App
        from incad.core import regions
        face, kind = pick.faces[index], pick.kind
        doc = App.getDocument(pick.doc_name)
        self._cancel_region_pick()
        body, source = doc.getObject(pick.body_name), doc.getObject(pick.source_name)
        if body is None or source is None:
            return
        try:
            prof = regions.make_profile(doc, body, source, face)
            self._open_session(kind, doc, body, profile=prof)
        except Exception as e:
            log.report("error", "%s: %s" % (kind.TITLE, e), traceback.format_exc())

    def start_feature(self, kind):
        from incad.core import assembly, document
        doc = self._doc()
        if getattr(kind, "ASSEMBLY", False):
            if not assembly.is_assembly(doc):
                raise ValueError("Open an InCad assembly first")
            if self.feature_session is not None:
                raise self._dialog_first()
            self._open_session(kind, doc, None)
            return
        if not document.is_incad_part(doc):
            raise ValueError("Create or open an InCad part first")
        if self.feature_session is not None:
            raise self._dialog_first()
        body = document.primary_body(doc)
        if not getattr(kind, "NEEDS_PROFILE", True):
            self._open_session(kind, doc, body)
            return
        profile = self._profile_for(doc, body)
        if profile is None:
            self._begin_profile_pick(kind)
            return
        from incad.core import regions
        if regions.needs_regions(profile):
            self._profile_from_areas(kind, doc, body, profile)
            return
        self._open_session(kind, doc, body, profile=profile)

    def edit_feature(self, feature):
        from incad import features
        kind = features.kind_for(feature)
        if kind is None:
            raise ValueError("%s cannot be edited yet" % feature.Label)
        if self.feature_session is not None:
            raise self._dialog_first()
        body = None if getattr(kind, "ASSEMBLY", False) else feature.getParentGeoFeatureGroup()
        self._open_session(kind, feature.Document, body, feature=feature)

    def _open_session(self, kind, doc, body, profile=None, feature=None):
        parent = self._mdi().viewport() if self._mdi() is not None else self.mw
        fs = FeatureSession(kind, doc, body, profile=profile, feature=feature, theme=self.theme, parent=parent,
                            on_close=self._session_closed)
        self.feature_session = fs
        if not fs.start():
            self.feature_session = None
        self.schedule_refresh()

    def _begin_profile_pick(self, kind):
        import FreeCADGui as Gui
        self._cancel_profile_pick()
        self._profile_pick = _ProfilePicker(self, kind)
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self._profile_pick)
        self.status.set_prompt("Select a sketch to %s (Esc cancels)" % kind.TITLE.lower())
        log.report("info", "Select a sketch with a closed profile")

    def _cancel_profile_pick(self):
        import FreeCADGui as Gui
        if self._profile_pick is not None:
            try:
                Gui.Selection.removeObserver(self._profile_pick)
            except Exception:
                pass
            self._profile_pick = None
            self.schedule_refresh()

    # ----- hooks -----
    def _install_hooks(self):
        import FreeCAD as App
        log.set_reporter(self._report)
        from incad.core import safe
        safe.set_refused_hook(self._show_open_dialog)
        self.mw.installEventFilter(self)
        for w in self._freecad_toolbars() + self._freecad_docks():
            w.installEventFilter(self)
        self._observer = _DocObserver(self.schedule_refresh, self._sketch_changed, self._after_undo)
        App.addDocumentObserver(self._observer)
        QtWidgets.QApplication.instance().styleHints().colorSchemeChanged.connect(self._on_system_scheme)
        from incad.core import params
        mdi = self._mdi()
        if mdi is not None:
            mdi.viewport().installEventFilter(self)
            mdi.subWindowActivated.connect(self._raise_strip)
            mdi.subWindowActivated.connect(self._on_subwindow)
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
                mdi.subWindowActivated.disconnect(self._on_subwindow)
            except (RuntimeError, TypeError):
                pass
        if self.navigator is not None:
            self.navigator.detach_all()
        log.set_reporter(None)
        from incad.core import safe
        safe.set_refused_hook(None)
        if self._box_focus_hooked:
            try:
                QtWidgets.QApplication.instance().focusChanged.disconnect(self._keep_box_keyboard)
            except (RuntimeError, TypeError):
                pass
            self._box_focus_hooked = False
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
            etype = event.type()
            # only these matter; anything else returns before touching Qt (widgets being destroyed on quit send
            # events through here, and a findChild on them aborted FreeCAD at exit)
            if etype not in _FILTERED_EVENTS:
                return False
            if etype == QtCore.QEvent.Resize:
                mdi = self._mdi()
                if self.strip is not None and mdi is not None and obj is mdi.viewport():
                    self.strip.place(mdi.viewport().rect())
                    QtCore.QTimer.singleShot(0, self._raise_overlays)  # QMdiArea re-raises the document window
                return False
            if obj is self.mw:
                if etype == QtCore.QEvent.Close and not self.active:
                    shutdown()  # still waiting for a FreeCAD task: nothing to ask, just leave nothing behind
                elif etype == QtCore.QEvent.Close and self.active:
                    # quitting (⌘Q, Dock, app menu, red button): ask about unsaved files while InCad still shows
                    # (Cancel keeps everything), then switch off — FreeCAD saves its layout right after — and
                    # delete InCad's Qt objects now: macOS ends the process inside this close (probed crash)
                    if not _ask_unsaved():
                        event.ignore()
                        return True
                    QtCore.QTimer.singleShot(0, _resume_after_cancelled_quit)  # only runs if the quit is cancelled
                    shutdown()  # deletes this object: nothing may touch self after it
                    _mark_answered()  # switching off may have touched documents: already answered
                elif etype == QtCore.QEvent.ChildAdded and self.active:
                    child = event.child()
                    if isinstance(child, (QtWidgets.QToolBar, QtWidgets.QDockWidget)):
                        QtCore.QTimer.singleShot(0, lambda c=child: self._adopt(c))
            elif etype == QtCore.QEvent.Show and self.active and obj.objectName() not in OURS \
                    and (isinstance(obj, (QtWidgets.QToolBar, QtWidgets.QDockWidget)) or _is_overlay(obj)):
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
        fs = self.feature_session
        if fs is not None and fs.doc_name not in App.listDocuments():
            self._close_feature_session(cancel=True)  # its document was closed: nothing to roll back, free busy
        from incad.core import assembly as assemblies
        is_part = document.is_incad_part(doc)
        is_asm = assemblies.is_assembly(doc)
        editing = self.sketches.editing() if is_part else None
        self.sketches.sync()
        if self.value_box is not None and (editing is None or
                                           (editing.Document.Name, editing.Name) != self._box_owner):
            self._close_value_box(apply_if_typed=True)
        if editing is not None and self._profile_pick is not None:
            self._cancel_profile_pick()  # the user went sketching instead: a pick would finish the sketch under them
        if editing is None and self.slot_tool is not None:
            self.stop_slot_tool()
        if editing is None and self.construction_mode:
            self.construction_mode = False  # each sketch starts with normal geometry
        mode = "sketch" if editing is not None else "part" if is_part else "assembly" if is_asm else "empty"
        self.ribbon.set_mode(mode)
        if self.plane_panel is not None:
            if self.sketches.picking and not self.plane_panel.isVisible():
                self.plane_panel.adjustSize()
                self.plane_panel.move(16, 16)
                self.plane_panel.show()
                self.plane_panel.raise_()
            elif not self.sketches.picking:
                self.plane_panel.hide()
        self.title.set_document_name(doc.Label if doc is not None else "")
        self.browser.set_nodes(tree.build(doc))
        from incad.core import sketch as sketches
        self.browser.set_parameters(document.list_parameters(doc) if is_part or is_asm else [],
                                    sketches.model_parameters(doc) if is_part or is_asm else [])
        self.browser.set_parameters_enabled(is_part or is_asm)
        self.status.set_units(document.part_units(doc) if is_part or is_asm else None)
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
        elif is_asm:
            self._tame_padlocks(doc)
            if self.feature_session is None:
                from incad.core import asm_cut
                try:
                    asm_cut.sync(doc)  # cut parts follow the tools' positions
                except Exception as e:
                    log.report("warning", "Could not update the assembly cuts: %s" % e, traceback.format_exc())
            self.status.set_stats(None, None)
            comps = len(assemblies.components(doc))
            self.status.set_prompt("Place part files (P), then constrain them (C)" if comps < 2 else
                                   "%d components · Constrain (C), Joint (J), Ground" % comps)
        else:
            self.status.set_stats(None, None)
            self.status.set_prompt("Create or open a part" if doc is None else "This file was not made in InCad")
        if self._region_pick is not None:
            self.status.set_prompt("Click the area to %s (Esc cancels)" % self._region_pick.kind.TITLE.lower())
        for cmd_id, act in self._shortcuts.items():
            if cmd_id == "_esc":
                act.setEnabled(mode == "sketch" or self.sketches.picking or self._profile_pick is not None or
                               getattr(self, "slot_tool", None) is not None or self.feature_session is not None
                               or self._measure is not None or self._region_pick is not None)
                continue
            ctx = self.registry.get(cmd_id).contexts
            act.setEnabled(commands.ANY in ctx or mode in ctx)
        if self.navigator is not None and prefs.navigation_enabled():
            self.navigator.attach_all()
        if self.strip is not None:
            self.strip.refresh_checks()
        self._raise_overlays()
        if self._wait_notice is not None and not self._edit_open():
            self._close_wait_notice()

    # ----- assemblies -----
    def _assembly_doc(self):
        from incad.core import assembly
        doc = self._doc()
        if not assembly.is_assembly(doc):
            raise ValueError("Open an InCad assembly first")
        if self.feature_session is not None:
            raise self._dialog_first()
        return doc

    def _ensure_saved(self, doc):
        """Linking needs the assembly on disk: ask for its file the first time."""
        if doc.FileName:
            return True
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self.mw, "Save the assembly first", doc.Label + ".FCStd",
                                                        "FreeCAD files (*.FCStd)")
        if not path:
            return False
        doc.saveAs(path if path.lower().endswith(".fcstd") else path + ".FCStd")
        return True

    def _back_to(self, doc):
        """Opening part files can switch the active tab: show the assembly again."""
        import FreeCAD as App
        import FreeCADGui as Gui
        App.setActiveDocument(doc.Name)
        gdoc = Gui.getDocument(doc.Name)
        if gdoc is not None and gdoc.ActiveView is not None:
            Gui.ActiveDocument = gdoc
            mdi = self._mdi()
            for sub in (mdi.subWindowList() if mdi is not None else []):
                if sub.windowTitle().startswith(doc.Label):
                    mdi.setActiveSubWindow(sub)
                    break

    def assembly_place(self, path=None):
        from incad.core import assembly, safe
        doc = self._assembly_doc()
        if not self._ensure_saved(doc):
            return None
        if path is None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self.mw, "Place a part or assembly",
                                                            os.path.dirname(doc.FileName), "FreeCAD files (*.FCStd)")
            if not path:
                return None
        result = safe.run_safely("Place", lambda: assembly.place(doc, path), doc)
        self._back_to(doc)
        self.schedule_refresh()
        return result.value if result.ok else None

    def assembly_create(self, name=None):
        from incad.core import assembly, safe
        doc = self._assembly_doc()
        if not self._ensure_saved(doc):
            return None
        if name is None:
            name, ok = QtWidgets.QInputDialog.getText(self.mw, "Create component", "New part file name:",
                                                      text="Part")
            if not ok or not name.strip():
                return None
        result = safe.run_safely("Create", lambda: assembly.create_part(doc, name.strip()), doc)
        self.schedule_refresh()
        return result.value if result.ok else None

    def assembly_ground(self, link=None):
        import FreeCADGui as Gui
        from incad.core import assembly, context, safe
        from incad.features import common
        doc = self._assembly_doc()
        if link is None:
            name = context.target()
            link = doc.getObject(name) if name else None
        if link is None:
            for sel in Gui.Selection.getSelectionEx(doc.Name):
                for sub in (sel.SubElementNames or ("",)):
                    obj, _ = common.resolve(sel.Object, sub)
                    if obj is not None and obj.TypeId == "App::Link":
                        link = obj
        if link is None or link not in assembly.components(doc):
            raise ValueError("Select a component to ground or unground")
        action = assembly.unground if assembly.is_grounded(link) else assembly.ground
        safe.run_safely("Ground", lambda: action(link), doc)
        self.schedule_refresh()

    def open_component(self, link):
        """Open the component's file in its own tab (Inventor: Open)."""
        import FreeCAD as App
        import FreeCADGui as Gui
        path = link.LinkedObject.Document.FileName
        part = link.LinkedObject.Document
        if Gui.getDocument(part.Name) is None or Gui.getDocument(part.Name).ActiveView is None:
            if part.FileName:
                part.save()  # changes InCad made there (assembly cuts) belong to that file: never drop them
            App.closeDocument(part.Name)
            part = App.openDocument(path)
            link.Document.recompute()
        App.setActiveDocument(part.Name)
        Gui.ActiveDocument = Gui.getDocument(part.Name)

    PADLOCK_SCALE = 1.2

    def _tame_padlocks(self, doc):
        """FreeCAD draws the grounded padlock big (scale 3) and in loud red: smaller and in the theme's tone."""
        from incad.core import assembly
        p = themes.PALETTES[self.theme]
        c = QtGui.QColor(p["text_dim"])
        for j in assembly.joints(doc):
            proxy = getattr(getattr(j, "ViewObject", None), "Proxy", None)
            scale = getattr(proxy, "scale", None)
            if scale is None:
                continue
            try:
                if abs(scale.scaleFactor.getValue() - self.PADLOCK_SCALE) > 1e-6:
                    scale.scaleFactor = self.PADLOCK_SCALE
                proxy.lockpadColor.rgb.setValue(c.redF(), c.greenF(), c.blueF())
            except Exception:
                pass

    def _on_plane_picked(self, role):
        try:
            self.sketches.pick_origin(role)
        except Exception as e:
            log.report("error", "New sketch failed: %s" % e, traceback.format_exc())
        self.schedule_refresh()

    def inspect(self, what):
        import FreeCADGui as Gui
        from incad.core import document, inspect
        from incad.features import common
        doc = self._doc()
        if not document.is_incad_part(doc):
            raise ValueError("Open an InCad part first")
        if what in inspect.MODES or what == "measure":
            mode = "auto" if what == "measure" else what
            self._start_measuring(mode)
            pairs = [common.resolve(sel.Object, sub) for sel in Gui.Selection.getSelectionEx(doc.Name)
                     for sub in (sel.SubElementNames or ("",))]
            try:
                rows = inspect.measure(pairs, mode)
            except ValueError as e:
                self.status.set_prompt("%s (Esc finishes)" % e)
                self._close_info_panel()
                return
            title = "Measure" if mode == "auto" else "Measure %s" % mode.capitalize()
        else:
            from incad.core import materials
            rows = inspect.mass_properties(document.primary_body(doc), materials.density(doc))
            title = "Mass Properties (%s %.2f g/cm³)" % (materials.material(doc), materials.density(doc))
        self._close_info_panel()
        parent = self._mdi().viewport() if self._mdi() is not None else self.mw
        self.info_panel = InfoPanel(title, rows, self.theme, parent)
        self.info_panel.adjustSize()
        self.info_panel.move(16, parent.height() - self.info_panel.height() - 16)
        self.info_panel.show()

    def _start_measuring(self, mode):
        """Measure stays live, as in Inventor: every change of the selection measures again (Esc finishes)."""
        import FreeCADGui as Gui
        self._stop_measuring()
        self._measure = _MeasurePicker(self, mode)
        Gui.Selection.addObserver(self._measure)

    def _stop_measuring(self):
        import FreeCADGui as Gui
        if self._measure is not None:
            try:
                Gui.Selection.removeObserver(self._measure)
            except Exception:
                pass
            self._measure = None

    def measuring(self):
        return self._measure.mode if self._measure is not None else None

    def _close_info_panel(self):
        if self.info_panel is not None:
            try:
                self.info_panel.close()
                dispose(self.info_panel)
            except RuntimeError:
                pass
            self.info_panel = None

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
            from incad.core import model
            if model.is_model_parameter(doc, name):
                safe.run_safely("Set %s" % name, lambda: model.set_model_parameter(doc, name, text), doc)
            else:
                safe.run_safely("Set %s" % name, lambda: document.set_parameter(doc, name, text), doc)
        self.schedule_refresh()

    def _on_parameter_removed(self, name):
        from incad.core import document, safe
        doc = self._doc()
        if doc is not None:
            from incad.core import model
            remove = model.remove_model_parameter if model.is_model_parameter(doc, name) else document.remove_parameter
            safe.run_safely("Remove %s" % name, lambda: remove(doc, name), doc)
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


SAVE_ASK = None  # tests: callable(files) -> ("save" | "discard" | "cancel", [names]) instead of the dialog


def _finish_open_tools():
    """Open dialogs and tools change documents when they close: close them before asking about saving."""
    if _shell is None or not _shell.active:
        return
    try:
        _shell.stop_slot_tool()
        _shell._close_feature_session(cancel=True)
        _shell._cancel_profile_pick()
        _shell.sketches.cancel_pick()
        if _shell.sketches.editing() is not None:
            _shell.sketches.finish()
    except Exception as e:
        log.report("warning", "Could not close the open tools: %s" % e, traceback.format_exc())


def ask_save(docs, action="quitting"):
    """InCad's Save dialog for the changed documents among `docs`; False when cancelled. Answered documents are
    marked unchanged so FreeCAD doesn't ask again."""
    import FreeCADGui as Gui
    changed = [d for d in docs if Gui.getDocument(d.Name) is not None and Gui.getDocument(d.Name).Modified]
    if not changed:
        return True
    files = [(d.Label, d.FileName) for d in changed]
    if SAVE_ASK is not None:
        choice = SAVE_ASK(files)
    else:
        from incad.ui.save_dialog import SaveDialog
        dlg = SaveDialog(files, _shell.theme if _shell is not None else themes.current(), Gui.getMainWindow(),
                         action)
        dlg.exec()
        choice = dlg.result_choice()
    if choice[0] == "cancel":
        return False
    for d in changed:
        if choice[0] == "save" and d.Label in choice[1]:
            if d.FileName:
                d.save()
            else:
                path, _ = QtWidgets.QFileDialog.getSaveFileName(Gui.getMainWindow(), "Save %s" % d.Label,
                                                                d.Label + ".FCStd", "FreeCAD files (*.FCStd)")
                if not path:
                    return False
                d.saveAs(path if path.lower().endswith(".fcstd") else path + ".FCStd")
        Gui.getDocument(d.Name).Modified = False
    return True


def _ask_unsaved():
    import FreeCAD as App
    _finish_open_tools()
    return ask_save(list(App.listDocuments().values()), "quitting")


def _mark_answered():
    import FreeCAD as App
    import FreeCADGui as Gui
    for d in App.listDocuments().values():
        g = Gui.getDocument(d.Name)
        if g is not None:
            g.Modified = False


def _release_python_markers():
    """PySide marks every Qt object Python has touched with a '_PySideInvalidatePtr' property. On a Dock/app-menu
    quit macOS ends the process before Qt destroys the widgets, after Python is gone, and destroying a marked
    object then crashes (probed). The process is ending: drop the markers while Python still runs."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    objs = list(app.allWidgets()) + list(app.findChildren(QtCore.QObject))
    for top in app.topLevelWidgets():
        objs += list(top.findChildren(QtCore.QObject))
    for o in objs:
        try:
            if b"_PySideInvalidatePtr" in [bytes(n) for n in o.dynamicPropertyNames()]:
                o.setProperty("_PySideInvalidatePtr", None)
        except RuntimeError:
            pass


def _alive(obj):
    try:
        return obj.Document is not None
    except Exception:
        return False


def _is_start_page(window):
    """FreeCAD's Start page, by its tab title (InCad's UI is English; looking inside the window would leave a
    Python handle on it)."""
    try:
        return window.windowTitle() == "Start"
    except RuntimeError:
        return False


_FILTERED_EVENTS = (QtCore.QEvent.Resize, QtCore.QEvent.Close, QtCore.QEvent.ChildAdded, QtCore.QEvent.Show)


def _resume_after_cancelled_quit():
    """FreeCAD cancelled the quit (or the window stayed open): InCad starts again."""
    import FreeCADGui as Gui
    from incad.qt import dispose_now
    if QtWidgets.QApplication.activeModalWidget() is not None:  # e.g. a question still open: wait for it
        QtCore.QTimer.singleShot(300, _resume_after_cancelled_quit)
        return
    try:
        dispose_now(False)
        wb = Gui.activeWorkbench()
        if wb is not None and wb.name() == "InCadWorkbench" and Gui.getMainWindow().isVisible():
            activate()
    except Exception as e:
        log.report("warning", "InCad could not start again: %s" % e, traceback.format_exc())


def shutdown():
    """FreeCAD is quitting: switch InCad off (FreeCAD's interface back, saved clean) and delete every Qt object
    InCad made now — not later, when Python is already finalized."""
    global _shell
    from incad.qt import dispose_now
    try:
        dispose_now(True)
        sh = _shell
        nav = getattr(sh, "navigator", None) if sh is not None else None
        if sh is not None and sh.active:
            sh.deactivate()
        # InCad's own event-filter objects go too: deleting a filter detaches it from every widget, so Qt never
        # calls into Python while the process ends (probed crash: QObjectWrapper::eventFilter at exit)
        for obj in (nav, sh):
            if obj is not None:
                dispose(obj)
        _shell = None
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        _release_python_markers()
    except Exception as e:
        log.report("warning", "InCad could not shut down cleanly: %s" % e, traceback.format_exc())


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


def start_feature(kind):
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    _shell.start_feature(kind)


def inspect(what):
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    _shell.inspect(what)


def measuring():
    return _shell.measuring() if _shell is not None and _shell.active else None


def _active():
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    return _shell


def assembly_place(path=None):
    return _active().assembly_place(path)


def assembly_create(name=None):
    return _active().assembly_create(name)


def assembly_ground(link=None):
    return _active().assembly_ground(link)


def current_tree_object():
    """Name of the model-tree row in focus (a feature or sketch), else None."""
    sh = _shell
    if sh is None or not sh.active or sh.browser is None:
        return None
    try:
        tree = sh.browser.tree
        item = tree.currentItem()
        if item is None or not tree.hasFocus():
            return None
        from incad.ui.browser import KIND_ROLE, NAME_ROLE
        return item.data(0, NAME_ROLE) if item.data(0, KIND_ROLE) in ("feature", "sketch") else None
    except RuntimeError:
        return None


def toggle_construction():
    return _active().toggle_construction()


def start_slot_tool(mode):
    return _active().start_slot_tool(mode)


def open_component(link):
    return _active().open_component(link)


def edit_feature(feature):
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    _shell.edit_feature(feature)
