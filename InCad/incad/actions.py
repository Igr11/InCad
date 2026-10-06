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
SKETCHER = {  # InCad id: (label, icon, FreeCAD Sketcher command, shortcut)
    "sketch.line": ("Line", "line", "Sketcher_CreatePolyline", "L"),
    "sketch.circle": ("Circle", "circle", "Sketcher_CreateCircle", "C"),
    "sketch.arc": ("Arc", "arc", "Sketcher_Create3PointArc", "A"),
    "sketch.rectangle": ("Rectangle", "rectangle", "Sketcher_CreateRectangle", "R"),
    "sketch.slot": ("Slot", "slot", "Sketcher_CreateSlot", ""),
    "sketch.polygon": ("Polygon", "polygon", "Sketcher_CreateHexagon", ""),
    "sketch.spline": ("Spline", "spline", "Sketcher_CreateBSplineByInterpolation", ""),
    "sketch.point": ("Point", "sk_point", "Sketcher_CreatePoint", ""),
    "sketch.fillet": ("Fillet", "sk_fillet", "Sketcher_CreateFillet", ""),
    "sketch.chamfer": ("Chamfer", "sk_chamfer", "Sketcher_CreateChamfer", ""),
    "sketch.trim": ("Trim", "trim", "Sketcher_Trimming", "X"),
    "sketch.extend": ("Extend", "extend", "Sketcher_Extend", ""),
    "sketch.offset": ("Offset", "offset", "Sketcher_Offset", ""),
    "sketch.project": ("Project Geometry", "project", "Sketcher_Projection", ""),
    "sketch.construction": ("Construction", "construction", "Sketcher_ToggleConstruction", ""),
    "sketch.mirror": ("Mirror", "mirror", "Sketcher_Symmetry", ""),
    "sketch.rect_pattern": ("Rectangular Pattern", "rect_pattern", "Sketcher_RectangularArray", ""),
    "sketch.dimension": ("Dimension", "dimension", "Sketcher_Dimension", "D"),
    "sketch.coincident": ("Coincident", "coincident", "Sketcher_ConstrainCoincidentUnified", ""),
    "sketch.horizontal": ("Horizontal", "horizontal", "Sketcher_ConstrainHorizontal", ""),
    "sketch.vertical": ("Vertical", "vertical", "Sketcher_ConstrainVertical", ""),
    "sketch.parallel": ("Parallel", "parallel", "Sketcher_ConstrainParallel", ""),
    "sketch.perpendicular": ("Perpendicular", "perpendicular", "Sketcher_ConstrainPerpendicular", ""),
    "sketch.tangent": ("Tangent", "tangent", "Sketcher_ConstrainTangent", ""),
    "sketch.equal": ("Equal", "equal", "Sketcher_ConstrainEqual", ""),
    "sketch.symmetric": ("Symmetric", "symmetric", "Sketcher_ConstrainSymmetric", ""),
    "sketch.fix": ("Fix", "fix", "Sketcher_ConstrainLock", ""),
    "sketch.show_dof": ("Show Free Geometry", "show_dof", "Sketcher_SelectElementsWithDoFs", ""),
    "sketch.stop": ("Stop Tool", "stop", "Sketcher_StopOperation", ""),
    "sketch.slice": ("Slice Graphics", "slice", "Sketcher_ViewSection", "F7"),
}


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
    from incad.core import log, sketch
    obj = _target_object()
    if sketch.is_sketch(obj):
        _refuse_while_busy()
        from incad.ui import shell
        shell.sketch_session().edit(obj)
    else:
        from incad import features
        from incad.ui import shell
        if features.kind_for(obj) is None:
            log.report("info", "Editing this feature arrives with the next feature tools (plan 1d-2)")
        else:
            shell.edit_feature(obj)


def toggle_nav_mode(mode):
    from incad.ui import shell
    shell.toggle_nav_mode(mode)


def nav_mode_is(mode):
    from incad.ui import shell
    return shell.nav_mode() == mode


def start_sketch():
    _refuse_while_busy()
    from incad.ui import shell
    return shell.sketch_session().start()


def finish_sketch():
    from incad.ui import shell
    shell.sketch_session().finish()


def start_feature(kind_name):
    from incad import features
    from incad.ui import shell
    kind = {k.__name__.rsplit(".", 1)[-1]: k for k in features.kinds()}[kind_name]
    shell.start_feature(kind)


def inspect_measure():
    from incad.ui import shell
    shell.inspect("measure")


def inspect_mass():
    from incad.ui import shell
    shell.inspect("mass")


def _refuse_while_busy():
    """An open feature dialog owns the model: undo, save, close or sketch editing would break its Cancel."""
    from incad.core import safe
    if safe.busy():
        raise ValueError("Finish the %s dialog first" % safe.busy())


_GUARDED = {"file.save", "file.save_as", "file.close"}


def _std(cmd_id, label, icon, shortcut=""):
    name, index = STD_COMMANDS[cmd_id], STD_INDEX.get(cmd_id, 0)

    def handler():
        if cmd_id in _GUARDED:
            _refuse_while_busy()
        return run_std(name, index)
    return Command(id=cmd_id, label=label, icon=icon, handler=handler, shortcut=shortcut)


def _undo_redo(redo):
    """Undo/Redo the active document. Sketcher's own command while a sketch is edited; otherwise straight on the
    document, so it works whatever tab is active (FreeCAD's Std_Undo talks to the active view)."""
    import FreeCAD as App
    _refuse_while_busy()
    gdoc = _gui().ActiveDocument
    if gdoc is not None and gdoc.getInEdit() is not None:
        run_std("Std_Redo" if redo else "Std_Undo")
        return
    doc = App.ActiveDocument
    if doc is None:
        return
    if redo and doc.RedoNames:
        doc.redo()
    elif not redo and doc.UndoNames:
        doc.undo()
    doc.recompute()
    from incad.core import model
    repaired = model.relink(doc)  # objects brought back by undo lose their formula links (FreeCAD quirk)
    from incad.core import log
    log.logger().info("undo/redo relinked %s", repaired)


def commands():
    return [
        Command(id="file.new", label="New", icon="new", handler=new_part, shortcut="Ctrl+N",
                tooltip="New part (asks for mm or inch)"),
        _std("file.open", "Open", "open", "Ctrl+O"),
        _std("file.save", "Save", "save", "Ctrl+S"),
        _std("file.save_as", "Save As", "save", "Ctrl+Shift+S"),
        _std("file.close", "Close", "close", "Ctrl+W"),
        Command(id="edit.undo", label="Undo", icon="undo", handler=lambda: _undo_redo(False), shortcut="Ctrl+Z"),
        Command(id="edit.redo", label="Redo", icon="redo", handler=lambda: _undo_redo(True), shortcut="Ctrl+Shift+Z"),
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
        Command(id="sketch.start", label="Start 2D Sketch", icon="start_sketch", handler=start_sketch, shortcut="S",
                contexts=frozenset({"part"}), tooltip="Pick a plane or a flat face to sketch on"),
        Command(id="sketch.finish", label="Finish Sketch", icon="finish", handler=finish_sketch,
                contexts=frozenset({"sketch"}), tooltip="Back to the 3D model (Esc)"),
        Command(id="feature.extrude", label="Extrude", icon="extrude", handler=lambda: start_feature("extrude"),
                shortcut="E", contexts=frozenset({"part"}), tooltip="Extrude a sketch profile"),
        Command(id="feature.revolve", label="Revolve", icon="revolve", handler=lambda: start_feature("revolve"),
                shortcut="R", contexts=frozenset({"part"}), tooltip="Revolve a sketch profile around an axis"),
        Command(id="feature.hole", label="Hole", icon="hole", handler=lambda: start_feature("hole"), shortcut="H",
                contexts=frozenset({"part"})),
        Command(id="feature.fillet", label="Fillet", icon="fillet", handler=lambda: start_feature("fillet"),
                shortcut="F", contexts=frozenset({"part"})),
        Command(id="feature.chamfer", label="Chamfer", icon="chamfer", handler=lambda: start_feature("chamfer"),
                contexts=frozenset({"part"})),
        Command(id="feature.shell", label="Shell", icon="shell", handler=lambda: start_feature("shell"),
                contexts=frozenset({"part"})),
        Command(id="feature.rect_pattern", label="Rectangular", icon="rect_pattern3d",
                handler=lambda: start_feature("rect_pattern"), contexts=frozenset({"part"})),
        Command(id="feature.circ_pattern", label="Circular", icon="circ_pattern",
                handler=lambda: start_feature("circ_pattern"), contexts=frozenset({"part"})),
        Command(id="feature.mirror", label="Mirror", icon="mirror3d", handler=lambda: start_feature("mirror"),
                contexts=frozenset({"part"})),
        Command(id="work.plane", label="Plane", icon="work_plane", handler=lambda: start_feature("work_plane"),
                contexts=frozenset({"part"})),
        Command(id="work.axis", label="Axis", icon="work_axis", handler=lambda: start_feature("work_axis"),
                contexts=frozenset({"part"})),
        Command(id="work.point", label="Point", icon="work_point", handler=lambda: start_feature("work_point"),
                contexts=frozenset({"part"})),
        Command(id="inspect.measure", label="Measure", icon="measure", handler=inspect_measure,
                contexts=frozenset({"part"}), tooltip="Select a face, an edge, or two items"),
        Command(id="inspect.mass", label="Mass Properties", icon="mass", handler=inspect_mass,
                contexts=frozenset({"part"})),
    ] + [Command(id=i, label=lbl, icon=icon, handler=(lambda n=cmd: run_std(n)), shortcut=sc,
                 contexts=frozenset({"sketch"})) for i, (lbl, icon, cmd, sc) in SKETCHER.items()]


def register_all(registry=REGISTRY):
    for cmd in commands():
        if not registry.has(cmd.id):
            registry.register(cmd)
