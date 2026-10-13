"""Make Assembly (Inventor's Make Components): every piece of a part — each Solid, and each solid of a Solid's
shape (a box drawn away from the part, the pieces of a Split) — becomes a part file with its history, and an
assembly links them where they were, the largest grounded. The original part file is not changed."""
import os
from collections import namedtuple

import FreeCAD as App
import Part

from incad.core import assembly, document

Piece = namedtuple("Piece", "body_name point volume")


def _inside(solid):
    from incad.features import split
    return split.inside_point(solid)


def pieces(doc):
    """Every solid of every Solid of the part, largest first; a Boolean's used-up tool is no piece (it lives on in the
    hole it cut; its "fit" copy, the printed tool, is one)."""
    from incad.features import combine
    used = combine.used_up_names(doc)
    out = []
    for body in document.bodies(doc):
        if body.Shape.isNull() or body.Name in used:
            continue
        for s in body.Shape.Solids:
            out.append(Piece(body.Name, _inside(s), s.Volume))
    return sorted(out, key=lambda p: -p.volume)


def pieces_or_refuse(doc):
    if not document.is_incad_part(doc):
        raise ValueError("Make Assembly works on an InCad part")
    if not doc.FileName:
        raise ValueError("Save the part first: its folder takes the new files")
    found = pieces(doc)
    if len(found) < 2:
        joiner = _joiner(doc)
        if joiner is not None:
            raise ValueError("This part is one piece: %s joined the split pieces again (make it before the Split, "
                             "or as a New Solid)" % joiner.Label)
        raise ValueError("This part is one piece: nothing to assemble")
    return found


def _joiner(doc):
    """The feature after a Split that fused its pieces back into fewer solids (any additive step does), or None."""
    from incad.features import split
    for b in document.bodies(doc):
        split_count = 0
        for f in b.Group:
            if not f.isDerivedFrom("PartDesign::Feature") or f.Shape.isNull() or not f.Shape.Solids:
                continue
            if split.claims(f) and len(f.Shape.Solids) > 1:
                split_count = len(f.Shape.Solids)
            elif split_count and len(f.Shape.Solids) < split_count:
                return f
    return None


def _stem(doc):
    return os.path.splitext(os.path.basename(doc.FileName))[0] if doc.FileName else doc.Label


def default_names(doc, n):
    stem = _stem(doc)
    return "%s-Assembly" % stem, ["%s-Solid%d" % (stem, i + 1) for i in range(n)]


def _path(doc, name):
    return os.path.join(os.path.dirname(doc.FileName), name + ".FCStd")


def existing(doc, asm_name, names):
    """The names whose files are already in the part's folder (an earlier Make Assembly made them)."""
    return [n for n in [asm_name] + list(names) if n.strip() and os.path.exists(_path(doc, n))]


def check_names(doc, asm_name, names, replace=False):
    """Why these names can't be used, or ''. With `replace` the files already there are overwritten (the user: making
    the assembly again forced new names, Train_2, Train_3…) — never this part's own file."""
    every = [asm_name] + list(names)
    if any(not n.strip() or any(ch in n for ch in '/\\:') for n in every):
        return "A name is empty or has / \\ :"
    if len({n.lower() for n in every}) < len(every):
        return "A name is used twice"
    own = os.path.abspath(doc.FileName)
    for n in every:
        if os.path.abspath(_path(doc, n)) == own:
            return "%s is this part's own file: pick another name" % n
    if not replace:
        for n in every:
            if os.path.exists(_path(doc, n)):
                return "%s.FCStd exists in this folder (pick another name, or replace it)" % n
    return ""


def _remove_body(d, body):
    for o in list(body.Group):
        if d.getObject(o.Name) is not None and o.TypeId != "App::Origin":
            body.removeObject(o)
            d.removeObject(o.Name)
    d.removeObject(body.Name)


def _has_split(body):
    from incad.features import split
    return any(split.claims(f) for f in body.Group)


def _detach_all(d):
    """Every separate piece left in a Solid by an older file goes to a Solid of its own; a Solid with a Split keeps
    them (the Split's Cut picks the piece, lumps before it included: their knife may cross them)."""
    for _ in range(100):
        lump = next((f for b in document.bodies(d) if not _has_split(b) for f in b.Group
                     if document.is_detached_lump(f)), None)
        if lump is None:
            return
        document.detach_lump(lump)
        d.recompute()


def _suppress_lost_steps(d, body, split_feature):
    """Steps after the Split made on another piece (a fillet of its edge) lose their references in this copy: they
    are suppressed here, the copy of that piece keeps them."""
    after = body.Group[body.Group.index(split_feature) + 1:]
    for _ in range(len(after)):
        bad = next((o for o in after if "Invalid" in o.State and hasattr(o, "Suppressed") and not o.Suppressed), None)
        if bad is None:
            return
        bad.Suppressed = True
        d.recompute()


def _finish_copy(path, point):
    """Open the copy, keep only the piece at `point`, save it. Raises with the reason when the piece's copy is not
    one clean solid."""
    d = App.openDocument(path, hidden=True)
    try:
        d.recompute()
        _detach_all(d)
        from incad.features import combine, split
        used = combine.used_up_names(d)
        probe = Part.Vertex(point)
        keep = min((b for b in document.bodies(d) if not b.Shape.isNull() and b.Name not in used),
                   key=lambda b: b.Shape.distToShape(probe)[0])
        needed = {o.getParentGeoFeatureGroup() for o in keep.OutListRecursive if hasattr(o, "getParentGeoFeatureGroup")}
        needed |= {o for o in keep.OutListRecursive if o.TypeId == "PartDesign::Body"}
        for b in document.bodies(d):
            if b is keep:
                continue
            if b in needed:  # a Boolean's tool (or what a fit copy grows from): kept, hidden, so the copy recomputes
                b.Visibility = False
            else:
                _remove_body(d, b)
        if len(keep.Shape.Solids) > 1:
            last = next((f for f in reversed(keep.Group) if split.claims(f)), None)
            if last is None:
                raise ValueError("%s: its pieces could not be separated" % os.path.basename(path))
            split.keep_piece(last, point)
            d.recompute()
            _suppress_lost_steps(d, keep, last)
        document._meta_set(d, **{document.PRIMARY_KEY: keep.Name})
        d.recompute()
        bad = ["%s (%s)" % (o.Label, o.getStatusString()) for o in d.Objects if "Invalid" in o.State]
        if bad or len(keep.Shape.Solids) != 1:
            raise ValueError("%s: %s" % (os.path.basename(path), ", ".join(bad) or "not one piece"))
        d.save()
    finally:
        App.closeDocument(d.Name)


def _drop_backups(paths):
    """FreeCAD keeps a .FCBak when a file is saved again; these files are new, so their backups are only ours."""
    import glob
    for path in paths:
        stem = os.path.splitext(path)[0]
        for bak in glob.glob(glob.escape(stem) + ".*.FCBak"):
            os.remove(bak)


def _close_paths(paths):
    wanted = {os.path.abspath(p) for p in paths}
    for d in list(App.listDocuments().values()):
        if d.FileName and os.path.abspath(d.FileName) in wanted:
            App.closeDocument(d.Name)


def make(doc, asm_name, names, replace=False):
    """Write the part files and the assembly. The part stays FreeCAD's active document: the hidden copies opened here
    become active on open, and closing them would leave none (InCad then showed an empty screen, Undo did nothing)."""
    try:
        return _make(doc, asm_name, names, replace)
    finally:
        if doc.Name in App.listDocuments():
            App.setActiveDocument(doc.Name)


def _make(doc, asm_name, names, replace=False):
    found = pieces_or_refuse(doc)
    if len(names) != len(found):
        raise ValueError("One name per piece")
    reason = check_names(doc, asm_name, names, replace)
    if reason:
        raise ValueError(reason)
    old = [_path(doc, n) for n in existing(doc, asm_name, names)] if replace else []
    _close_paths(old)  # open in a tab (the assembly made last time): its file is about to change under it
    kept = {}
    for path in old:  # set aside, so a failure puts them back as they were
        kept[path] = path + ".incad-replace"
        os.replace(path, kept[path])
    made = []
    try:
        for piece, name in zip(found, names):
            path = _path(doc, name)
            made.append(path)  # before writing: a write that fails half-way is removed too
            doc.saveCopy(path)
            _finish_copy(path, piece.point)
        asm_path = _path(doc, asm_name)
        a = App.newDocument(asm_name, hidden=True)
        try:
            assembly.make_assembly(a, document.part_units(doc) or "mm")
            made.append(asm_path)
            a.saveAs(asm_path)
            for path in made[:-1]:  # largest first: the first placed is grounded
                assembly.place(a, path, beside=False)
            a.recompute()
            a.save()
        finally:
            App.closeDocument(a.Name)
            _close_paths(made)  # the part files place() opened hidden
        _drop_backups(made)
        for aside in kept.values():
            os.remove(aside)
        return asm_path
    except Exception:
        _close_paths(made)
        for path in made:
            if os.path.exists(path):
                os.remove(path)
        _drop_backups(made)
        for path, aside in kept.items():
            os.replace(aside, path)
        raise
