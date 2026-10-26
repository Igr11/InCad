"""Right-click menus show only what applies to what is under the pointer (the user: too many buttons, each menu should
show only what applies). The layouts (incad.ui.marking_layout) list what a menu may hold; inapplicable() names the
entries of its list that would do nothing here, and the menu leaves them out. The ring keeps its places (a flick
always lands where it did). The sketch menu has its own rules (shell._sketch_menu)."""

NEEDS_COMPONENT = ("assembly.edit", "assembly.open", "assembly.suppress", "assembly.remove")


def _face_kind(doc):
    """'plane', 'round' or None: the surface of the face the menu was opened on (it is the selection)."""
    import FreeCADGui as Gui
    for sel in Gui.Selection.getSelectionEx(doc.Name):
        for sub, el in zip(sel.SubElementNames or (), sel.SubObjects or ()):
            if sub.split(".")[-1].startswith("Face") and hasattr(el, "Surface"):
                t = el.Surface.TypeId
                if t == "Part::GeomPlane":
                    return "plane"
                if t in ("Part::GeomCylinder", "Part::GeomCone"):
                    return "round"
                return None
    return None


def inapplicable(kind, doc):
    """The ids of `kind`'s list entries that do nothing for what the menu was opened on."""
    out = set()
    if doc is None:
        return out
    from incad import actions
    from incad.core import assembly, document
    try:
        targets = document.visibility_targets(actions._visibility_targets())
    except Exception:
        targets = []
    shown = [t for t in targets if document.is_shown(t)]
    if not shown:
        out.add("view.hide")
    if len(shown) == len(targets):  # nothing of it hidden (or nothing picked)
        out.add("view.show")
    if not targets:
        out.add("tools.appearance")
    try:
        if all(document.is_shown(p) for p in document.all_parts(doc)):
            out.add("view.show_all_parts")
    except Exception:
        pass
    from incad.ui import wire_style
    out.add("view.style_wireframe" if doc.Name in wire_style._active else "view.style_shaded")  # the one in use
    items = [f for o in doc.Objects if o.TypeId == "App::Origin" for f in o.OriginFeatures]
    if items and all(document.is_shown(f) for f in items):
        out.add("view.origin_show_all")
    if not any(document.is_shown(f) for f in items):
        out.add("view.origin_hide_all")
    if kind == "part":
        try:
            solids = document.all_parts(doc)
            if len(solids) < 2 and not any(len(b.Shape.Solids) > 1 for b in solids if not b.Shape.isNull()):
                out.add("file.make_assembly")  # one piece: nothing to split into parts
        except Exception:
            pass
    if kind == "face" and _face_kind(doc) != "round":
        out.add("feature.thread")  # a thread goes on a shaft or in a hole
    if kind == "browser":
        from incad.core import context
        obj = doc.getObject(context.target() or "")
        if obj is None or obj.TypeId not in ("PartDesign::Plane", "App::Plane"):
            out.add("sketch.start")  # a new sketch goes on a plane
    if kind in ("browser", "solid"):
        from incad.core import context
        from incad.features import solid_mirror
        if not solid_mirror.is_linked(doc.getObject(context.target() or "")):
            out.add("browser.break_mirror")  # only a mirror follows an original
    if kind == "assembly" and assembly.is_assembly(doc):
        from incad.ui import dof_handles
        if dof_handles.selected_component(doc) is None:
            out |= set(NEEDS_COMPONENT)
    return out
