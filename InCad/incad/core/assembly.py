"""An InCad Assembly is a FreeCAD document with one native Assembly object (+ its Joints group), marked in
doc.Meta. Components are App::Links to the main solid of separate part (or assembly) files. Pure model logic."""
import os

import FreeCAD as App

from incad.core import document

TYPE = "Assembly"
GAP = 10.0


def make_assembly(doc, units="mm"):
    if document.is_incad_part(doc) or is_assembly(doc):
        raise ValueError("%s is already an InCad file" % doc.Label)
    asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
    asm.newObject("Assembly::JointGroup", "Joints")
    document._meta_set(doc, **{document.TYPE_KEY: TYPE})
    document.set_units(doc, units)
    return asm


def is_assembly(doc):
    return doc is not None and doc.Meta.get(document.TYPE_KEY) == TYPE


def assembly_of(doc):
    return next((o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject"), None) if doc else None


def joint_group(doc):
    asm = assembly_of(doc)
    return next((o for o in asm.Group if o.TypeId == "Assembly::JointGroup"), None) if asm else None


def components(doc):
    asm = assembly_of(doc)
    return [o for o in asm.Group if o.TypeId == "App::Link"] if asm else []


def joints(doc):
    group = joint_group(doc)
    return list(group.Group) if group is not None else []


def _require_saved(doc):
    if not doc.FileName:
        raise ValueError("Save the assembly first, so it can link to part files")


def _open(path):
    path = os.path.abspath(path)
    for d in App.listDocuments().values():
        if d.FileName and os.path.abspath(d.FileName) == path:
            return d
    if not os.path.isfile(path):
        raise ValueError("No file at %s" % path)
    return App.openDocument(path, hidden=True)


def main_solid(doc):
    """What a component links to: the part's main solid, an assembly, or the first solid in a plain file."""
    if is_assembly(doc):
        return assembly_of(doc)
    body = document.primary_body(doc)
    if body is not None:
        return body
    for type_id in ("PartDesign::Body", "App::Part"):
        found = next((o for o in doc.Objects if o.TypeId == type_id), None)
        if found is not None:
            return found
    raise ValueError("%s has no solid to place" % doc.Label)


def _depends_on(doc):
    """Every document `doc` links to, directly or through others."""
    seen, todo = set(), [doc]
    while todo:
        d = todo.pop()
        for o in d.Objects:
            linked = getattr(o, "LinkedObject", None) if o.TypeId == "App::Link" else None
            target = linked.Document if linked is not None else None
            if target is not None and target is not doc and target.Name not in seen:
                seen.add(target.Name)
                todo.append(target)
    return [App.getDocument(n) for n in seen]


def place(doc, path, beside=True):
    """Link a part (or assembly) file; the first component is grounded, later ones go beside the others (or stay
    where the part file has them: beside=False, Make Assembly)."""
    _require_saved(doc)
    asm = assembly_of(doc)
    if asm is None:
        raise ValueError("This file is not an InCad assembly")
    target_doc = _open(path)
    if target_doc is doc:
        raise ValueError("An assembly can't be placed into itself")
    if doc in _depends_on(target_doc):
        raise ValueError("%s already contains this assembly: placing it here would make a loop" % target_doc.Label)
    target = main_solid(target_doc)
    existing = components(doc)
    link = asm.newObject("App::Link", _safe_name(os.path.splitext(os.path.basename(path))[0]))
    link.LinkedObject = target
    link.Label = os.path.splitext(os.path.basename(path))[0]
    doc.recompute()
    if not existing:
        ground(link)
    elif beside:
        boxes = [b for b in (_box(c) for c in existing) if b is not None]  # a part without a solid has no shape
        right = max(bb.XMax for bb in boxes) if boxes else 0.0
        mine = _box(link)
        left = mine.XMin if mine is not None else 0.0
        link.Placement = App.Placement(App.Vector(right + GAP - left, 0, 0), App.Rotation())
        doc.recompute()
    return link


def _box(link):
    shape = getattr(link, "Shape", None)
    return shape.BoundBox if shape is not None and not shape.isNull() else None


def _safe_name(stem):
    name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in stem) or "Component"
    return name if not name[0].isdigit() else "C_" + name


def is_grounded(link):
    return any(getattr(j, "ObjectToGround", None) is link for j in joints(link.Document))


def ground(link):
    if is_grounded(link):
        return
    import JointObject
    j = joint_group(link.Document).newObject("App::FeaturePython", "GroundedJoint")
    JointObject.GroundedJoint(j, link)
    if App.GuiUp:
        JointObject.ViewProviderGroundedJoint(j.ViewObject)
    j.Label = "Grounded %s" % link.Label


def unground(link):
    doc = link.Document
    for j in joints(doc):
        if getattr(j, "ObjectToGround", None) is link:
            doc.removeObject(j.Name)


def create_part(doc, name, units=None):
    """A new InCad part file saved next to the assembly, linked as a component."""
    _require_saved(doc)
    folder = os.path.dirname(doc.FileName)
    stem, n = _safe_name(name or "Part"), 1
    path = os.path.join(folder, stem + ".FCStd")
    while os.path.exists(path):
        n += 1
        path = os.path.join(folder, "%s%d.FCStd" % (stem, n))
    part = App.newDocument(os.path.splitext(os.path.basename(path))[0])
    part.UndoMode = 1
    document.make_part(part, units or document.part_units(doc) or "mm")
    part.recompute()
    part.saveAs(path)
    return place(doc, path)


def part_documents(doc):
    """The part files the components link to, each once, in component order."""
    out = []
    for c in components(doc):
        target = c.LinkedObject
        d = target.Document if target is not None else None
        if d is not None and d is not doc and d not in out:
            out.append(d)
    return out


def _threaded(doc):
    from incad.core import suppress
    return [d for d in part_documents(doc) if suppress.threads(d) or suppress.tapped_holes(d)]


def threads_off(doc):
    """True while every threaded part of the assembly has its threads off."""
    from incad.core import suppress
    parts = _threaded(doc)
    return bool(parts) and all(suppress.threads_off(d) for d in parts)


def toggle_threads(doc):
    """Threads Off / On for the whole assembly: every threaded part's threads off, or (all off) back on, in their
    part files (saved with them); 'off' or 'on'."""
    from incad.core import suppress
    parts = _threaded(doc)
    if not parts:
        raise ValueError("No part of this assembly has threads")
    want = "on" if threads_off(doc) else "off"
    for d in parts:
        if ("off" if suppress.threads_off(d) else "on") != want:
            suppress.toggle_threads(d)
            d.recompute()
    doc.recompute()
    return want


SUPPRESSED = "InCadSuppressed"


def is_suppressed(link):
    return bool(getattr(link, SUPPRESSED, False))


KEPT_OFF = "InCadKeptOff"  # on a suppressed component: its constraints the user had suppressed (they stay off)


def _kept_off(link):
    return list(getattr(link, KEPT_OFF, None) or [])


def toggle_suppressed(link):
    """Suppress (Inventor) a component: hidden and its constraints / joints off, so it no longer counts; again to
    bring it back. A constraint the user suppressed stays suppressed when the part comes back, and one whose other
    part is still suppressed stays off with it. Returns True when it is suppressed now."""
    doc = link.Document
    on = not is_suppressed(link)
    for name, kind, doc_text in ((SUPPRESSED, "App::PropertyBool", "Suppressed in the assembly"),
                                 (KEPT_OFF, "App::PropertyStringList", "Constraints the user had suppressed")):
        if name not in link.PropertiesList:
            link.addProperty(kind, name, "InCad", doc_text)
            link.setPropertyStatus(name, "Hidden")
    mine = []
    for j in joints(doc):
        refs = [(getattr(j, p, None) or (None,))[0] for p in ("Reference1", "Reference2")]
        if link in refs and hasattr(j, "Suppressed"):
            others = [c for c in refs if c is not None and c is not link and is_suppressed(c)]
            mine.append((j, others))
    if on:
        # the user's own: suppressed while no part of it was, or kept off by its other (suppressed) part
        setattr(link, KEPT_OFF, [j.Name for j, others in mine if j.Suppressed and (
            not others or any(j.Name in _kept_off(c) for c in others))])
        for j, _ in mine:
            j.Suppressed = True
    else:
        kept = _kept_off(link)
        for j, others in mine:
            if j.Name not in kept and not others:
                j.Suppressed = False
        setattr(link, KEPT_OFF, [])
    setattr(link, SUPPRESSED, on)
    link.Visibility = not on
    doc.recompute()
    return on



def _frame(link):
    """The placement that takes the linked object's own geometry into the assembly: the link's (it replaces the
    linked object's placement), or both with LinkTransform on."""
    linked = link.LinkedObject
    if getattr(link, "LinkTransform", False):
        return link.Placement.multiply(getattr(linked, "Placement", App.Placement()))
    return App.Placement(link.Placement)


def context_of(doc, link):
    """Edit a part from the assembly: every OTHER visible, unsuppressed component (other instances of the same
    part too) as [(name, shape, placement)] — the linked object's own shape and where it sits in the edited part's
    tab (the part's frame, its body's placement included)."""
    import Part
    linked = link.LinkedObject
    view = getattr(linked, "Placement", App.Placement()) if linked is not None else App.Placement()
    to_view = view.multiply(_frame(link).inverse())
    out = []
    for c in components(doc):
        target = c.LinkedObject
        if c is link or target is None or not c.Visibility or is_suppressed(c):
            continue
        try:
            shape = Part.getShape(target, transform=False)
        except Exception:
            continue
        if shape.isNull() or not shape.Faces:
            continue
        out.append((c.Name, shape, to_view.multiply(_frame(c))))
    return out


def parts_signature(doc):
    """What the components' parts look like now (each part's volume and box): changed when a part was edited in
    its own tab."""
    out = []
    for c in components(doc):
        target = c.LinkedObject
        shape = getattr(target, "Shape", None)
        if shape is None or shape.isNull():
            out.append((c.Name, None))
            continue
        bb = shape.BoundBox
        out.append((c.Name, round(shape.Volume, 6),
                    tuple(round(v, 6) for v in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))))
    return tuple(out)


_NEEDS_UPDATE = set()  # assemblies whose parts changed and whose update was declined (this session)


def parts_changed(doc, seen):
    """True when a part already in the assembly looks different from `seen` (a parts_signature). A part placed or
    removed meanwhile is the assembly's own change, not one to ask about."""
    if seen is None:
        return False
    before = {row[0]: row for row in seen}
    return any(row[0] in before and before[row[0]] != row for row in parts_signature(doc))


def mark_needs_update(doc):
    _NEEDS_UPDATE.add(doc.Name)


def needs_update(doc):
    return doc is not None and doc.Name in _NEEDS_UPDATE


def bring_parts_in(doc):
    """Update the assembly to its parts as they are now (Yes, or Refresh): recompute and solve; the 'needs update'
    sign goes."""
    for c in components(doc):
        c.touch()  # a link to another file is not touched by that file's recompute
    doc.recompute()
    asm = assembly_of(doc)
    if asm is not None and hasattr(asm, "solve"):
        try:
            asm.solve()
        except Exception:
            pass
        doc.recompute()
    _NEEDS_UPDATE.discard(doc.Name)
    return parts_signature(doc)
