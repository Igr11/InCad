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
    "sketch.line": ("Line", "line", "Sketcher_CreatePolyline", "L"),  # polyline: chains, arcs with M
    "sketch.circle": ("Circle", "circle", "Sketcher_CreateCircle", "C"),
    "sketch.arc": ("3-Point Arc", "arc", "Sketcher_CreateArc", "A"),
    "sketch.rectangle": ("Rectangle", "rectangle", "Sketcher_CreateRectangle", "R"),
    "sketch.slot": ("Center-to-Center Slot", "slot", "Sketcher_CreateSlot", ""),
    "sketch.polygon": ("Hexagon", "polygon", "Sketcher_CreateHexagon", ""),
    "sketch.spline": ("Spline", "spline", "Sketcher_CreateBSplineByInterpolation", ""),
    "sketch.point": ("Point", "sk_point", "Sketcher_CreatePoint", ""),
    "sketch.fillet": ("Fillet", "sk_fillet", "Sketcher_CreateFillet", ""),
    "sketch.chamfer": ("Chamfer", "sk_chamfer", "Sketcher_CreateChamfer", ""),
    "sketch.trim": ("Trim", "trim", "Sketcher_Trimming", "X"),
    "sketch.extend": ("Extend", "extend", "Sketcher_Extend", ""),
    "sketch.offset": ("Offset", "offset", "Sketcher_Offset", ""),
    "sketch.project": ("Project Geometry", "project", "Sketcher_Projection", ""),
    "sketch.mirror": ("Mirror", "mirror", "Sketcher_Symmetry", ""),
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

# Variants (Inventor split buttons). Modes are FreeCAD's construction methods, set in its tool widget after start
# (FreeCAD remembers the last method, so every variant sets its own).
SKETCH_VARIANTS = {  # InCad id: (label, icon, FreeCAD command, construction method or None)
    "sketch.rectangle_center": ("Center Rectangle", "rect_center", "Sketcher_CreateRectangle", "Center, width, height"),
    "sketch.rectangle_3pt": ("3-Point Rectangle", "rect_3pt", "Sketcher_CreateRectangle", "3 corners"),
    "sketch.rectangle_center_3pt": ("3-Point Center Rect.", "rect_center_3pt", "Sketcher_CreateRectangle",
                                    "Center, 2 corners"),
    "sketch.rectangle_rounded": ("Rounded Rectangle", "rect_rounded", "Sketcher_CreateOblong", None),
    "sketch.circle_3pt": ("3-Point Circle", "circle_3pt", "Sketcher_CreateCircle", "3 rim points"),
    "sketch.ellipse": ("Ellipse", "ellipse", "Sketcher_CreateEllipseByCenter", None),
    "sketch.ellipse_3pt": ("3-Point Ellipse", "ellipse_3pt", "Sketcher_CreateEllipseBy3Points", None),
    "sketch.arc_center": ("Center Arc", "arc_center", "Sketcher_CreateArc", "Center"),
    "sketch.arc_ellipse": ("Elliptical Arc", "arc_ellipse", "Sketcher_CreateArcOfEllipse", None),
    "sketch.line_single": ("Single Line", "line_single", "Sketcher_CreateLine", None),
    "sketch.triangle": ("Triangle", "triangle", "Sketcher_CreateTriangle", None),
    "sketch.square": ("Square", "square", "Sketcher_CreateSquare", None),
    "sketch.pentagon": ("Pentagon", "pentagon", "Sketcher_CreatePentagon", None),
    "sketch.octagon": ("Octagon", "octagon", "Sketcher_CreateOctagon", None),
    "sketch.polygon_n": ("Polygon (N sides)", "polygon_n", "Sketcher_CreateRegularPolygon", None),
    "sketch.slot_arc": ("Arc Slot", "slot_arc", "Sketcher_CreateArcSlot", "Arc ends"),
    "sketch.slot_arc_flat": ("Flat-End Arc Slot", "slot_arc_flat", "Sketcher_CreateArcSlot", "Flat ends"),
    "sketch.spline_cv": ("Control-Vertex Spline", "spline_cv", "Sketcher_CreateBSpline", None),
}
# The base tools pin their own method too (FreeCAD would reuse the last one chosen).
_BASE_MODES = {"sketch.rectangle": "Corner, width, height", "sketch.circle": "Center", "sketch.arc": "3 rim points"}


def set_tool_mode(text):
    """Pick a construction method in the running Sketcher tool's widget (hidden while InCad is active)."""
    from incad.qt import QtWidgets
    for w in QtWidgets.QApplication.allWidgets():
        if isinstance(w, QtWidgets.QComboBox) and w.objectName() == "comboBox1" and w.findText(text) >= 0:
            w.setCurrentIndex(w.findText(text))
            return True
    raise ValueError("This FreeCAD version has no '%s' option for this tool" % text)


def run_sketch_tool(name, mode=None):
    run_std(name)
    if mode:
        set_tool_mode(mode)


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
    kind = "part"
    if prefs.remember_new_choice():
        units = prefs.default_units()
    else:
        answer = (ask or ask_new)()
        if answer is None:
            return None
        kind, units, remember = answer
        prefs.set_default_units(units)
        prefs.set_remember_new_choice(remember)
    if kind == "assembly":
        return new_assembly(units)
    doc = App.newDocument("Part")
    doc.UndoMode = 1
    body = document.make_part(doc, units)
    doc.recompute()
    doc.clearUndos()
    if App.GuiUp:
        view = _gui().getDocument(doc.Name).ActiveView
        view.setActiveObject("pdbody", body)
        view.viewIsometric()
        from incad.core import camera
        camera.frame_origin(view.getCameraNode())
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
    if obj.TypeId in ("App::Line", "App::Point"):
        from incad.core import log
        log.report("info", "Double-click a plane to start a sketch on it")
        return
    if obj.TypeId in _PLANES:  # double-click a plane: a new sketch on it (Inventor)
        from incad.ui import shell
        shell.sketch_session().start_on(obj)
        return
    if obj.TypeId == "App::Link":
        from incad.ui import shell
        shell.open_component(obj)
        return
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


_PLANES = ("App::Plane", "PartDesign::Plane")


def start_sketch():
    _refuse_while_busy()
    import FreeCAD as App
    from incad.core import context
    from incad.ui import shell
    name = context.target()
    target = App.ActiveDocument.getObject(name) if App.ActiveDocument is not None and name else None
    if target is not None and target.TypeId in _PLANES and not _gui().Selection.getSelection():
        context.set_target(None)  # right-click New Sketch on a plane in the browser
        return shell.sketch_session().start_on(target)
    return shell.sketch_session().start()


def finish_sketch():
    from incad.ui import shell
    shell.sketch_session().finish()


def start_feature(kind_name):
    from incad import features
    from incad.ui import shell
    kind = {k.__name__.rsplit(".", 1)[-1]: k for k in features.kinds()}[kind_name]
    shell.start_feature(kind)


def _edit_sketch_pattern():
    from incad.ui import shell
    sk, name = shell.instance().selected_sketch_pattern()
    if name is None:
        raise ValueError("Select a copy of a pattern first")
    shell.instance().edit_sketch_pattern(sk, name)


def _delete_sketch_pattern():
    from incad.ui import shell
    sk, name = shell.instance().selected_sketch_pattern()
    if name is None:
        raise ValueError("Select a copy of a pattern first")
    shell.instance().delete_sketch_pattern(sk, name)


def _inspect(what):
    from incad.ui import shell
    shell.inspect(what)


def inspect_measure():
    from incad.ui import shell
    shell.inspect("measure")


def inspect_mass():
    from incad.ui import shell
    shell.inspect("mass")


def look_at():
    """Inventor Look At: the selection; while sketching with nothing selected, the sketch itself."""
    gdoc = _gui().ActiveDocument
    editing = gdoc.getInEdit() if gdoc is not None else None
    if editing is not None and not _gui().Selection.getSelection():
        run_std("Sketcher_ViewSketch")
    else:
        run_std("Std_AlignToSelection")


def _editing_sketch():
    gdoc = _gui().ActiveDocument
    obj = gdoc.getInEdit() if gdoc is not None else None
    obj = getattr(obj, "Object", None)
    if obj is None or obj.TypeId != "Sketcher::SketchObject":
        raise ValueError("Open a sketch first")
    return obj


def _construction():
    from incad.ui import shell
    shell.toggle_construction()


def _construction_on():
    from incad.ui import shell
    inst = shell.instance()
    return bool(inst is not None and getattr(inst, "construction_mode", False))


def _slot(mode):
    from incad.ui import shell
    shell.start_slot_tool(mode)


def constraints_visible(show=None):
    """Inventor F8/F9: show or hide the constraint symbols of the sketch being edited (dimensions stay)."""
    from incad.core import safe, sketch
    sk = _editing_sketch()
    hide = sketch.constraints_hidden(sk) is False if show is None else not show
    safe.run_safely("Constraints", lambda: sketch.set_constraints_hidden(sk, hide), sk.Document)


def quit_freecad():
    """Quit FreeCAD: open dialogs are cancelled and InCad asks about unsaved files (in the main window's close)."""
    run_std("Std_Quit")


def delete_target():
    """Delete with one undo step in every document it changes (opened before anything changes)."""
    from incad.core import delete, safe
    obj = _target_object()
    doc = obj.Document
    from incad.ui import shell
    if shell.sketch_session().editing() is obj:
        shell.sketch_session().finish()  # the edit would be left half-reset on a deleted object
    extras = delete.documents(obj)
    for d in extras:
        if not d.UndoMode:
            d.UndoMode = 1
        if d.HasPendingTransaction:
            d.abortTransaction()
        d.openTransaction("Delete")
    res = safe.run_safely("Delete", lambda: delete.delete(obj), doc)
    for d in extras:
        if res.ok:
            d.commitTransaction()
        else:
            d.abortTransaction()
            d.recompute()


def _sketch_selection(sk):
    """[(geo, pos, sub)] of the sketch elements selected now, dropping names that point past the geometry the
    sketch has (a stale selection after a pattern rebuild made FreeCAD's own delete crash)."""
    from incad.core import sketch_patterns as sp
    out = []
    for sel in _gui().Selection.getSelectionEx(sk.Document.Name):
        if sel.Object is not sk:
            continue
        for sub in sel.SubElementNames or ():
            try:
                geo, pos = sp.element(sk, sub)
            except (ValueError, IndexError):
                out.append((None, 0, sub))  # a dimension ('Constraint7'): the Sketcher's delete handles it
                continue
            if geo >= sk.GeometryCount or geo < -2 - len(sk.ExternalGeo):
                continue
            out.append((geo, pos, sub))
    return out


def _delete_in_sketch(sk):
    """Delete in a sketch: a pattern's copies and spokes go through InCad (the pattern is then broken and rebuilt
    on its next edit); everything else through the Sketcher's own delete, with a selection cleaned of stale names."""
    from incad.core import safe, sketch_patterns as sp
    picked = _sketch_selection(sk)
    mine = sorted({geo for geo, _, _ in picked if geo is not None and geo >= 0 and sp.pattern_of(sk, geo)
                   and sp.index_of(sk, sp.getGeometryId(sk, geo)) is not None and not sp.is_original(sk, geo)}, reverse=True)
    rest = [sub for geo, _, sub in picked if geo not in mine]
    if mine:
        r = safe.run_safely("Delete", lambda: [sk.delGeometry(g) for g in mine], sk.Document)
        if not r.ok:
            raise ValueError(r.error)
        sk.Document.recompute()
    _gui().Selection.clearSelection()
    if rest:
        for sub in rest:
            _gui().Selection.addSelection(sk.Document.Name, sk.Name, sub)
        run_std("Std_Delete")


def delete_selection():
    """Delete / Backspace: in a sketch the selected geometry and dimensions (Sketcher's own delete, whose key
    died with FreeCAD's hidden Edit menu); otherwise the selected objects, or the model-tree row in focus."""
    from incad.core import context
    from incad.ui import shell
    sk = shell.sketch_session().editing()
    if sk is not None:
        _delete_in_sketch(sk)
        return
    from incad.features import common
    names = []
    for sel in _gui().Selection.getSelectionEx():
        for sub in (sel.SubElementNames or ("",)):
            obj, _ = common.resolve(sel.Object, sub)  # a face of the body names its feature ("Body.Thread.Face5")
            if obj is not None and obj.Name not in names:
                names.append(obj.Name)
    if not names:
        row = shell.current_tree_object()
        names = [row] if row else []
    if not names:
        raise ValueError("Select what to delete (in the model or the Model Browser)")
    for name in names:
        context.set_target(name)
        delete_target()


def choose_material(ask=None):
    """Pick the part's material (density for Mass Properties, colour). ask() -> name | None."""
    import FreeCAD as App
    from incad.core import document, materials, safe
    doc = App.ActiveDocument
    if not document.is_incad_part(doc):
        raise ValueError("Open an InCad part first")
    if ask is None:
        from incad.qt import QtWidgets
        names = materials.names()
        name, ok = QtWidgets.QInputDialog.getItem(_gui().getMainWindow(), "Material", "Part material:", names,
                                                  names.index(materials.material(doc)), False)
        ask = (lambda: name if ok else None)
    name = ask()
    if name:
        safe.run_safely("Material", lambda: materials.set_material(doc, name), doc)




def toggle_section():
    """Section view at the selection — three points, a flat face or a plane (XZ with nothing selected);
    clicking Section again switches it off."""
    import FreeCAD as App
    from incad.core import section
    from incad.features import common
    if _gui().ActiveDocument is None:
        raise ValueError("Open a part to see a section")
    from incad.ui import shell
    if section_on():
        shell.stop_section()
        return
    pairs = [common.resolve(sel.Object, sub) for sel in _gui().Selection.getSelectionEx(App.ActiveDocument.Name)
             for sub in (sel.SubElementNames or ("",))]
    base = section.placement(pairs)  # raises when the picks make no plane
    _gui().Selection.clearSelection()
    shell.start_section(base)


def _section_points():
    from incad.ui import shell
    shell.start_section_points()


def section_on():
    """Is the part shown sectioned (the cut solid drawn instead of it)?"""
    from incad.ui import shell
    return shell.section_on()


def _refuse_while_busy():
    """An open feature dialog owns the model: undo, save, close or sketch editing would break its Cancel."""
    from incad.core import safe
    if safe.busy():
        safe.refused()
        raise ValueError("Finish the %s dialog first" % safe.busy())


_GUARDED = {"file.save", "file.save_as"}


def close_document():
    """⌘W: InCad's Save dialog for this file, then close it."""
    import FreeCAD as App
    from incad.ui import shell
    doc = App.ActiveDocument
    if doc is None:
        return
    shell._finish_open_tools()  # an open dialog is cancelled, as in Inventor when its file closes
    if shell.ask_save([doc], "closing"):
        App.closeDocument(doc.Name)


def new_assembly(units=None):
    """Create an InCad Assembly in a new document (saved when the first part is placed)."""
    import FreeCAD as App
    from incad.core import assembly
    doc = App.newDocument("Assembly")
    doc.UndoMode = 1
    assembly.make_assembly(doc, units or prefs.default_units())
    doc.recompute()
    doc.clearUndos()
    if App.GuiUp:
        view = _gui().getDocument(doc.Name).ActiveView
        view.viewIsometric()
        from incad.core import camera
        camera.frame_origin(view.getCameraNode())
    return doc


def _assembly(action):
    from incad.ui import shell
    return getattr(shell, "assembly_" + action)()


def _std(cmd_id, label, icon, shortcut=""):
    name, index = STD_COMMANDS[cmd_id], STD_INDEX.get(cmd_id, 0)

    def handler():
        if cmd_id in _GUARDED:
            _refuse_while_busy()
        return run_std(name, index)
    return Command(id=cmd_id, label=label, icon=icon, handler=handler, shortcut=shortcut)


def _linked_steps(doc, step, redo):
    """A dialog that changed several files (assembly cuts) left one step in each, which FreeCAD marks "-> name":
    undo/redo them together."""
    import FreeCAD as App
    from incad.core import model
    base = step[3:] if step.startswith("-> ") else step
    for other in App.listDocuments().values():
        if other is doc:
            continue
        names = other.RedoNames if redo else other.UndoNames
        if names and (names[0] == "-> " + base or (step.startswith("-> ") and names[0] == base)):
            other.redo() if redo else other.undo()
            other.recompute()
            model.relink(other)


def update_model():
    """Inventor's Update: recompute the model and redraw InCad's panels and the view (a model that got out of
    step with the tree, or a view that stopped following the document, is put right)."""
    import FreeCAD as App
    from incad.core import log
    from incad.ui import shell
    _refuse_while_busy()
    doc = App.ActiveDocument
    if doc is not None:
        from incad.core import document
        doc.recompute()
        for b in document.bodies(doc):  # the display follows the tip again (a view that drifted is put right)
            document.show_result(b)
        bad = [o.Label for o in doc.Objects if "Invalid" in o.State]
        log.report("warning" if bad else "info", "Updated %s: %s failed" % (doc.Label, ", ".join(bad)) if bad
                   else "Updated %s" % doc.Label)
    else:
        log.report("warning", "Nothing to update: no document is active")
    inst = shell.instance()
    if inst is not None:
        inst.refresh()
    gdoc = _gui().ActiveDocument
    view = gdoc.ActiveView if gdoc is not None else None
    if view is not None:
        try:
            view.redraw()
        except Exception:
            pass


def _undo_redo(redo):
    """Undo/Redo the active document. Sketcher's own command while a sketch is edited; otherwise straight on the
    document, so it works whatever tab is active (FreeCAD's Std_Undo talks to the active view)."""
    import FreeCAD as App
    from incad.ui import shell
    sh = shell.instance()
    fs = sh.feature_session if sh is not None else None
    if fs is not None and fs.dialog is not None:  # inside a dialog: step through its own changes
        fs.undo_in_dialog(redo)
        return
    _refuse_while_busy()
    gdoc = _gui().ActiveDocument
    if gdoc is not None and gdoc.getInEdit() is not None:
        run_std("Std_Redo" if redo else "Std_Undo")
        return
    doc = App.ActiveDocument
    if doc is None:
        return
    names = doc.RedoNames if redo else doc.UndoNames
    step = names[0] if names else None
    if step is not None:
        doc.redo() if redo else doc.undo()
        _linked_steps(doc, step, redo)
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
        Command(id="file.close", label="Close", icon="close", handler=close_document, shortcut="Ctrl+W",
                tooltip="Close this file (asks to save changes)"),
        Command(id="file.quit", label="Quit", icon="close", handler=lambda: quit_freecad(), shortcut="Ctrl+Q",
                tooltip="Quit FreeCAD (asks to save changed files)"),
        Command(id="edit.undo", label="Undo", icon="undo", handler=lambda: _undo_redo(False), shortcut="Ctrl+Z"),
        Command(id="edit.redo", label="Redo", icon="redo", handler=lambda: _undo_redo(True), shortcut="Ctrl+Shift+Z"),
        Command(id="edit.update", label="Update", icon="update", handler=update_model,
                tooltip="Recompute the model and refresh the browser and the view"),
        Command(id="view.theme_toggle", label="Light / Dark", icon="theme_toggle", handler=toggle_theme,
                tooltip="Switch between light and dark"),
        Command(id="view.freecad", label="Return to FreeCAD", icon="freecad", handler=return_to_freecad,
                tooltip="Show FreeCAD's own interface"),
        _std("view.zoom_all", "Zoom All", "zoom_all"),
        _std("view.home", "Home View", "home_view"),
        _std("view.style_shaded", "Shaded", "style_shaded"),
        _std("view.style_wireframe", "Wireframe", "style_wireframe"),
        Command(id="view.parameters", label="Parameters", icon="parameters", handler=focus_parameters),
        Command(id="view.look_at", label="Look At", icon="look_at", handler=look_at,
                tooltip="Look straight at the selection, or at the sketch being edited"),
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
        Command(id="file.new_assembly", label="New Assembly", icon="assembly", handler=lambda: new_assembly(),
                tooltip="New assembly of part files"),
        Command(id="assembly.place", label="Place", icon="place", handler=lambda: _assembly("place"), shortcut="P",
                contexts=frozenset({"assembly"}), tooltip="Place a part or assembly file"),
        Command(id="assembly.create", label="Create", icon="create_component", handler=lambda: _assembly("create"),
                contexts=frozenset({"assembly"}), tooltip="Create a new part file in this assembly"),
        Command(id="assembly.ground", label="Ground", icon="ground", handler=lambda: _assembly("ground"),
                contexts=frozenset({"assembly"}), tooltip="Ground or unground the selected component"),
        Command(id="assembly.combine", label="Combine", icon="combine", handler=lambda: start_feature("asm_combine"),
                contexts=frozenset({"assembly"}), tooltip="Cut a component by others (written into its part file)"),
        Command(id="constrain.mate", label="Mate", icon="mate", handler=lambda: start_feature("mate"), shortcut="C",
                contexts=frozenset({"assembly"}), tooltip="Faces against each other (with an offset)"),
        Command(id="constrain.flush", label="Flush", icon="flush", handler=lambda: start_feature("flush"),
                contexts=frozenset({"assembly"}), tooltip="Faces side by side, same direction"),
        Command(id="constrain.angle", label="Angle", icon="angle_c", handler=lambda: start_feature("angle_c"),
                contexts=frozenset({"assembly"})),
        Command(id="constrain.tangent", label="Tangent", icon="tangent", handler=lambda: start_feature("tangent"),
                contexts=frozenset({"assembly"})),
        Command(id="constrain.insert", label="Insert", icon="insert", handler=lambda: start_feature("insert"),
                contexts=frozenset({"assembly"}), tooltip="Pick two round edges: axes aligned, faces together"),
        Command(id="joint.rigid", label="Rigid", icon="rigid", handler=lambda: start_feature("rigid"), shortcut="J",
                contexts=frozenset({"assembly"})),
        Command(id="joint.rotational", label="Rotational", icon="rotational",
                handler=lambda: start_feature("rotational"), contexts=frozenset({"assembly"})),
        Command(id="joint.slider", label="Slider", icon="slider", handler=lambda: start_feature("slider"),
                contexts=frozenset({"assembly"})),
        Command(id="joint.cylindrical", label="Cylindrical", icon="cylindrical",
                handler=lambda: start_feature("cylindrical"), contexts=frozenset({"assembly"})),
        Command(id="joint.ball", label="Ball", icon="ball", handler=lambda: start_feature("ball"),
                contexts=frozenset({"assembly"})),
        Command(id="feature.combine", label="Combine", icon="combine", handler=lambda: start_feature("combine"),
                contexts=frozenset({"part"}), tooltip="Join, cut or intersect solids; tools are kept; print clearance"),
        Command(id="sketch.construction", label="Construction", icon="construction",
                handler=lambda: _construction(), contexts=frozenset({"sketch"}), checkable=True,
                is_checked=lambda: _construction_on(),
                tooltip="On: new geometry is construction; click again for normal geometry. "
                        "With geometry selected: switches that geometry"),
        Command(id="sketch.slot_overall", label="Overall Slot", icon="slot_overall",
                handler=lambda: _slot("overall"), contexts=frozenset({"sketch"}),
                tooltip="Click the two outer ends, then the width"),
        Command(id="sketch.slot_center", label="Center Point Slot", icon="slot_center",
                handler=lambda: _slot("center"), contexts=frozenset({"sketch"}),
                tooltip="Click the center, one end's center, then the width"),
        Command(id="sketch.constraints_toggle", label="Show / Hide Constraints", icon="constraints_toggle",
                handler=lambda: constraints_visible(), contexts=frozenset({"sketch"}),
                tooltip="Hide or show the constraint symbols (dimensions stay)"),
        Command(id="sketch.constraints_show", label="Show Constraints", icon="constraints_toggle",
                handler=lambda: constraints_visible(True), shortcut="F8", contexts=frozenset({"sketch"})),
        Command(id="sketch.constraints_hide", label="Hide Constraints", icon="constraints_toggle",
                handler=lambda: constraints_visible(False), shortcut="F9", contexts=frozenset({"sketch"})),
        Command(id="feature.sweep", label="Sweep", icon="sweep", handler=lambda: start_feature("sweep"),
                contexts=frozenset({"part"}), tooltip="Sweep a profile sketch along a path sketch"),
        Command(id="feature.loft", label="Loft", icon="loft", handler=lambda: start_feature("loft"),
                contexts=frozenset({"part"}), tooltip="Loft through two or more section sketches"),
        Command(id="feature.coil", label="Coil", icon="coil", handler=lambda: start_feature("coil"),
                contexts=frozenset({"part"}), tooltip="Sweep a profile sketch along a helix (springs)"),
        Command(id="feature.draft", label="Draft", icon="draft", handler=lambda: start_feature("draft"),
                contexts=frozenset({"part"}), tooltip="Tilt faces by an angle (for moulding)"),
        Command(id="tools.material", label="Material", icon="material", handler=lambda: choose_material(),
                contexts=frozenset({"part"}), tooltip="Part material: density for Mass Properties, colour"),
        Command(id="view.section_points", label="Section by 3 Points", icon="section",
                handler=lambda: _section_points(), contexts=frozenset({"part", "assembly"}),
                tooltip="Click three marked points (corners, edge middles, circle centres) for the section plane"),
        Command(id="view.section", label="Section", icon="section", handler=toggle_section,
                contexts=frozenset({"part", "assembly"}), checkable=True, is_checked=lambda: section_on(), tooltip="Cut the view open at the selection: 3 points, a flat face or a plane (XZ if nothing); "
                        "click again to close"),
        Command(id="browser.delete", label="Delete", icon="delete", handler=delete_target,
                contexts=frozenset({"browser"}), tooltip="Delete with everything InCad made for it"),
        Command(id="edit.delete", label="Delete", icon="delete", handler=delete_selection, shortcut="Backspace",
                tooltip="Delete the selection (sketch geometry and dimensions, or features)"),
        Command(id="edit.delete_key", label="Delete", icon="delete", handler=delete_selection, shortcut="Del",
                tooltip="Delete the selection"),
        Command(id="feature.thread", label="Thread", icon="thread", handler=lambda: start_feature("thread"),
                contexts=frozenset({"part"}), tooltip="Real thread on a shaft or in a hole (select its face)"),
        Command(id="feature.shell", label="Shell", icon="shell", handler=lambda: start_feature("shell"),
                contexts=frozenset({"part"})),
        Command(id="sketch.rect_pattern", label="Rectangular", icon="rect_pattern",
                handler=lambda: start_feature("sketch_rect"), contexts=frozenset({"sketch"}),
                tooltip="Repeat sketch geometry along a direction, or equally between two limits"),
        Command(id="sketch.circ_pattern", label="Circular", icon="circ_pattern",
                handler=lambda: start_feature("sketch_circ"), contexts=frozenset({"sketch"}),
                tooltip="Repeat sketch geometry around a point"),
        Command(id="sketch.edit_pattern", label="Edit Pattern", icon="rect_pattern", handler=_edit_sketch_pattern,
                contexts=frozenset({"sketch"}), tooltip="Change the selected pattern (or double-click a copy)"),
        Command(id="sketch.delete_pattern", label="Delete Pattern", icon="delete", handler=_delete_sketch_pattern,
                contexts=frozenset({"sketch"}), tooltip="Remove the copies; the original stays"),
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
        Command(id="inspect.distance", label="Distance", icon="measure", handler=lambda: _inspect("distance"),
                contexts=frozenset({"part"}), tooltip="Distance between two faces, edges or points"),
        Command(id="inspect.angle", label="Angle", icon="measure", handler=lambda: _inspect("angle"),
                contexts=frozenset({"part"}), tooltip="Angle between two flat faces or straight edges"),
        Command(id="inspect.length", label="Length", icon="measure", handler=lambda: _inspect("length"),
                contexts=frozenset({"part"}), tooltip="Length of the selected edges (a loop)"),
        Command(id="inspect.area", label="Area", icon="measure", handler=lambda: _inspect("area"),
                contexts=frozenset({"part"}), tooltip="Area of the selected faces"),
        Command(id="inspect.mass", label="Mass Properties", icon="mass", handler=inspect_mass,
                contexts=frozenset({"part"})),
    ] + [Command(id=i, label=lbl, icon=icon, handler=(lambda n=cmd, m=_BASE_MODES.get(i): run_sketch_tool(n, m)),
                 shortcut=sc, contexts=frozenset({"sketch"})) for i, (lbl, icon, cmd, sc) in SKETCHER.items()] + \
        [Command(id=i, label=lbl, icon=icon, handler=(lambda n=cmd, m=mode: run_sketch_tool(n, m)),
                 contexts=frozenset({"sketch"})) for i, (lbl, icon, cmd, mode) in SKETCH_VARIANTS.items()]


# Short ribbon labels (the full name stays in the tooltip and in split-button menus)
SHORT = {"view.section_points": "Section", "inspect.distance": "Measure", "inspect.angle": "Measure", "inspect.length": "Measure", "inspect.area": "Measure",
         "sketch.slot": "Slot", "sketch.slot_overall": "Slot", "sketch.slot_center": "Slot", "sketch.slot_arc": "Arc Slot",
         "sketch.slot_arc_flat": "Arc Slot", "sketch.arc": "Arc", "sketch.arc_center": "Arc", "sketch.arc_ellipse": "Arc",
         "sketch.circle_3pt": "Circle", "sketch.ellipse_3pt": "Ellipse", "sketch.rectangle_center": "Rectangle",
         "sketch.rectangle_3pt": "Rectangle", "sketch.rectangle_center_3pt": "Rectangle",
         "sketch.rectangle_rounded": "Rectangle", "sketch.line_single": "Line", "sketch.polygon": "Polygon",
         "sketch.triangle": "Polygon", "sketch.square": "Polygon", "sketch.pentagon": "Polygon", "sketch.octagon": "Polygon",
         "sketch.polygon_n": "Polygon", "sketch.spline_cv": "Spline", "sketch.rect_pattern": "Pattern",
         "sketch.circ_pattern": "Pattern",
         "sketch.constraints_toggle": "Constraints", "sketch.show_dof": "Free DOF", "sketch.slice": "Slice",
         "sketch.project": "Project", "inspect.mass": "Mass", "feature.rect_pattern": "Pattern",
         "feature.circ_pattern": "Pattern"}


def register_all(registry=REGISTRY):
    import dataclasses
    for cmd in commands():
        if cmd.id in SHORT and not cmd.short:
            cmd = dataclasses.replace(cmd, short=SHORT[cmd.id])
        if not registry.has(cmd.id):
            registry.register(cmd)
