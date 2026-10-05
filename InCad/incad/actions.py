"""InCad's stage-1a commands and their handlers. FreeCAD is imported inside handlers, so this module also
loads in widget tests."""
from incad.core import prefs
from incad.core.commands import REGISTRY, Command

STD_COMMANDS = {
    "file.open": "Std_Open", "file.save": "Std_Save", "file.save_as": "Std_SaveAs",
    "file.close": "Std_CloseActiveWindow", "edit.undo": "Std_Undo", "edit.redo": "Std_Redo",
    "view.zoom_all": "Std_ViewFitAll", "view.home": "Std_ViewHome",
    "view.style_shaded": "Std_DrawStyle", "view.style_wireframe": "Std_DrawStyle",
    "view.look_at": "Std_AlignToSelection", "view.zoom_selection": "Std_ViewFitSelection",
}
STD_INDEX = {"view.style_shaded": 6, "view.style_wireframe": 2}  # Std_DrawStyle items: 6 Flat lines, 2 Wireframe


def _gui():
    import FreeCADGui
    return FreeCADGui


def run_std(name, index=0):
    _gui().runCommand(name, index)


def ask_new():
    """Show the New dialog; (kind, units, remember) or None when cancelled."""
    from incad.ui import theme
    from incad.ui.new_dialog import NewDialog
    dlg = NewDialog(units=prefs.default_units(), remember=prefs.remember_new_choice(),
                    theme=theme.current(), parent=_gui().getMainWindow())
    return dlg.choice() if dlg.exec() else None


def new_part(ask=None):
    """Create an InCad Part in a new document. ask() -> (kind, units, remember) | None (default: the New
    dialog). With 'Remember my choice' on, nothing is asked and the saved units are used."""
    import FreeCAD as App
    from incad.core import document
    if prefs.remember_new_choice():
        units = prefs.default_units()
    else:
        answer = (ask or ask_new)()
        if answer is None:
            return None
        _kind, units, remember = answer
        prefs.set_default_units(units)
        prefs.set_remember_new_choice(remember)
    doc = App.newDocument("Part")
    doc.UndoMode = 1
    body = document.make_part(doc, units)
    doc.recompute()
    doc.clearUndos()
    if App.GuiUp:
        view = _gui().getDocument(doc.Name).ActiveView
        view.setActiveObject("pdbody", body)
        view.viewIsometric()
        view.fitAll()
    return doc


def toggle_theme():
    from incad.ui import shell, theme
    prefs.set_theme(theme.toggled(theme.current()))
    shell.apply_theme()


def return_to_freecad():
    _gui().activateWorkbench(prefs.last_workbench())


def focus_parameters():
    from incad.ui import shell
    shell.focus_parameters()


def _target_object():
    import FreeCAD as App
    from incad.core import context
    doc = App.ActiveDocument
    name = context.target()
    obj = doc.getObject(name) if doc is not None and name else None
    if obj is None:
        raise ValueError("Pick a feature in the Model Browser first")
    return obj


def toggle_suppress():
    obj = _target_object()
    if "Suppressed" not in obj.PropertiesList:
        raise ValueError("%s cannot be suppressed" % obj.Label)
    obj.Suppressed = not obj.Suppressed


def _ask_name(current):
    from incad.qt import QtWidgets
    text, ok = QtWidgets.QInputDialog.getText(_gui().getMainWindow(), "Rename", "New name:", text=current)
    return text.strip() if ok else ""


def rename(ask=None):
    obj = _target_object()
    name = (ask or _ask_name)(obj.Label)
    if name:
        obj.Label = name


def move_end_of_part_here():
    from incad.core import document
    obj = document.owning_feature(_target_object())
    body = obj.getParentGeoFeatureGroup()
    if body is None or body.TypeId != "PartDesign::Body":
        raise ValueError("%s is not part of a solid" % obj.Label)
    document.set_end_of_part(body, obj)


def edit_feature():
    from incad.core import log
    log.report("info", "Editing features arrives with the feature tools (plan 1d)")


def toggle_nav_mode(mode):
    from incad.ui import shell
    shell.toggle_nav_mode(mode)


def nav_mode_is(mode):
    from incad.ui import shell
    return shell.nav_mode() == mode


def _std(cmd_id, label, icon):
    name, index = STD_COMMANDS[cmd_id], STD_INDEX.get(cmd_id, 0)
    return Command(id=cmd_id, label=label, icon=icon, handler=lambda: run_std(name, index))


def commands():
    return [
        Command(id="file.new", label="New", icon="new", handler=new_part, shortcut="Ctrl+N",
                tooltip="New part (asks for mm or inch)"),
        _std("file.open", "Open", "open"),
        _std("file.save", "Save", "save"),
        _std("file.save_as", "Save As", "save"),
        _std("file.close", "Close", "close"),
        _std("edit.undo", "Undo", "undo"),
        _std("edit.redo", "Redo", "redo"),
        Command(id="view.theme_toggle", label="Light / Dark", icon="theme_toggle", handler=toggle_theme,
                tooltip="Switch between light and dark"),
        Command(id="view.freecad", label="Return to FreeCAD", icon="freecad", handler=return_to_freecad,
                tooltip="Show FreeCAD's own interface"),
        _std("view.zoom_all", "Zoom All", "zoom_all"),
        _std("view.home", "Home View", "home_view"),
        _std("view.style_shaded", "Shaded", "style_shaded"),
        _std("view.style_wireframe", "Wireframe", "style_wireframe"),
        Command(id="view.parameters", label="Parameters", icon="parameters", handler=focus_parameters),
        _std("view.look_at", "Look At", "look_at"),
        _std("view.zoom_selection", "Zoom Selection", "zoom_selection"),
        Command(id="browser.edit", label="Edit", icon="edit", handler=edit_feature, contexts=frozenset({"browser"})),
        Command(id="browser.move_end_of_part", label="Move End of Part Here", icon="end_of_part",
                handler=move_end_of_part_here, transactional=True, contexts=frozenset({"browser"})),
        Command(id="browser.suppress", label="Suppress / Unsuppress", icon="suppress", handler=toggle_suppress,
                transactional=True, contexts=frozenset({"browser"})),
        Command(id="browser.rename", label="Rename", icon="rename", handler=rename, transactional=True,
                contexts=frozenset({"browser"})),
        Command(id="nav.orbit", label="Orbit", icon="orbit", handler=lambda: toggle_nav_mode("orbit"),
                checkable=True, is_checked=lambda: nav_mode_is("orbit"), tooltip="Left-drag orbits; click again to stop"),
        Command(id="nav.pan", label="Pan", icon="pan", handler=lambda: toggle_nav_mode("pan"),
                checkable=True, is_checked=lambda: nav_mode_is("pan"), tooltip="Left-drag pans; click again to stop"),
    ]


def register_all(registry=REGISTRY):
    for cmd in commands():
        if not registry.has(cmd.id):
            registry.register(cmd)
