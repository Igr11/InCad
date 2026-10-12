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
    """A point inside the solid (its centre of mass when that is inside, else a face's centre)."""
    c = solid.CenterOfMass
    if solid.isInside(c, 1e-6, False):
        return c
    return solid.Faces[0].CenterOfMass


def pieces(doc):
    out = []
    for body in document.bodies(doc):
        if body.Shape.isNull():
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
        raise ValueError("This part is one piece: nothing to assemble")
    return found


def _stem(doc):
    return os.path.splitext(os.path.basename(doc.FileName))[0] if doc.FileName else doc.Label


def default_names(doc, n):
    stem = _stem(doc)
    return "%s-Assembly" % stem, ["%s-Solid%d" % (stem, i + 1) for i in range(n)]


def _path(doc, name):
    return os.path.join(os.path.dirname(doc.FileName), name + ".FCStd")


def check_names(doc, asm_name, names):
    """Why these names can't be used, or ''."""
    every = [asm_name] + list(names)
    if any(not n.strip() or any(ch in n for ch in '/\\:') for n in every):
        return "A name is empty or has / \\ :"
    if len({n.lower() for n in every}) < len(every):
        return "A name is used twice"
    for n in every:
        if os.path.exists(_path(doc, n)):
            return "%s.FCStd exists in this folder (pick another name)" % n
    return ""


def _remove_body(d, body):
    for o in list(body.Group):
        if d.getObject(o.Name) is not None and o.TypeId != "App::Origin":
            body.removeObject(o)
            d.removeObject(o.Name)
    d.removeObject(body.Name)


def _detach_all(d):
    """Every separate piece left in a Solid by an older file goes to a Solid of its own."""
    for _ in range(100):
        lump = next((f for b in document.bodies(d) for f in b.Group if document.is_detached_lump(f)), None)
        if lump is None:
            return
        document.detach_lump(lump)
        d.recompute()


def _finish_copy(path, point):
    """Open the copy, keep only the piece at `point`, save it. Raises with the reason when the piece's copy is not
    one clean solid."""
    d = App.openDocument(path, hidden=True)
    try:
        d.recompute()
        _detach_all(d)
        probe = Part.Vertex(point)
        keep = min((b for b in document.bodies(d) if not b.Shape.isNull()),
                   key=lambda b: b.Shape.distToShape(probe)[0])
        for b in document.bodies(d):
            if b is not keep:
                _remove_body(d, b)
        if len(keep.Shape.Solids) > 1:
            from incad.features import split
            last = next((f for f in reversed(keep.Group) if split.claims(f)), None)
            if last is None:
                raise ValueError("%s: its pieces could not be separated" % os.path.basename(path))
            split.keep_piece(last, point)
        document._meta_set(d, **{document.PRIMARY_KEY: keep.Name})
        d.recompute()
        bad = [o.Label for o in d.Objects if "Invalid" in o.State]
        if bad or len(keep.Shape.Solids) != 1:
            raise ValueError("%s: %s" % (os.path.basename(path), ", ".join(bad) or "not one piece"))
        d.save()
    finally:
        App.closeDocument(d.Name)


def _close_paths(paths):
    wanted = {os.path.abspath(p) for p in paths}
    for d in list(App.listDocuments().values()):
        if d.FileName and os.path.abspath(d.FileName) in wanted:
            App.closeDocument(d.Name)


def make(doc, asm_name, names):
    found = pieces_or_refuse(doc)
    if len(names) != len(found):
        raise ValueError("One name per piece")
    reason = check_names(doc, asm_name, names)
    if reason:
        raise ValueError(reason)
    made = []
    try:
        for piece, name in zip(found, names):
            path = _path(doc, name)
            doc.saveCopy(path)
            made.append(path)
            _finish_copy(path, piece.point)
        asm_path = _path(doc, asm_name)
        a = App.newDocument(asm_name, hidden=True)
        try:
            assembly.make_assembly(a, document.part_units(doc) or "mm")
            a.saveAs(asm_path)
            made.append(asm_path)
            for path in made[:-1]:  # largest first: the first placed is grounded
                assembly.place(a, path, beside=False)
            a.recompute()
            a.save()
        finally:
            App.closeDocument(a.Name)
            _close_paths(made)  # the part files place() opened hidden
        return asm_path
    except Exception:
        _close_paths(made)
        for path in made:
            if os.path.exists(path):
                os.remove(path)
        raise
