"""Degrees of freedom of assembly components (Inventor), counted by probing FreeCAD's solver: six small test moves
of a part, each solved; what the solver keeps is a freedom. Relative to what holds the part: every other free part
is held still (temporary grounds) while it is counted. The count runs in a transaction that is aborted, so it leaves
no undo step and nothing in the file. Pure model logic."""
import math
from collections import namedtuple

import FreeCAD as App

from incad.core import assembly

STEP, TURN = 0.5, 1.0  # mm, degrees
TOL = 0.2              # share of a step below which a kept motion counts as none

Freedom = namedtuple("Freedom", "n slides turns error")  # slides / turns in the part's own frame
_CACHE = {}            # doc name -> (signature, {link name: Freedom})


class Busy(Exception):
    """The document is loading or a dialog's step is open: no count now."""


def _num(v):
    return round(float(getattr(v, "Value", v) or 0), 9)


def signature(doc):
    """What the count depends on: every joint's kind, picks, value and suppressed state, the grounded and the
    suppressed parts. Placements are not in it (a drag does not change the freedoms)."""
    out = []
    for j in assembly.joints(doc):
        refs = []
        for p in ("Reference1", "Reference2"):
            ref = getattr(j, p, None)
            refs.append((ref[0].Name, tuple(ref[1])) if ref and ref[0] is not None else None)
        ground = getattr(j, "ObjectToGround", None)
        out.append((j.Name, str(getattr(j, "JointType", "")), tuple(refs), _num(getattr(j, "Distance", 0)),
                    _num(getattr(j, "Angle", 0)), bool(getattr(j, "Suppressed", False)),
                    ground.Name if ground is not None else None))
    out.append(tuple((c.Name, assembly.is_suppressed(c)) for c in assembly.components(doc)))
    return tuple(out)


def cached(doc):
    entry = _CACHE.get(doc.Name)
    return entry[1] if entry is not None and entry[0] == signature(doc) else None


def last(doc):
    entry = _CACHE.get(doc.Name)
    return entry[1] if entry is not None else None


def ensure(doc):
    """(counts, computed): the cached counts, or a fresh count when the constraints changed; the last counts (or
    None) while the document is busy."""
    counts = cached(doc)
    if counts is not None:
        return counts, False
    try:
        counts = compute(doc)
    except Busy:
        return last(doc), False
    _CACHE[doc.Name] = (signature(doc), counts)
    return counts, True


def _held_by_a_joint(doc, link):
    for j in assembly.joints(doc):
        if getattr(j, "Suppressed", False) or hasattr(j, "ObjectToGround"):
            continue
        if link in [(getattr(j, p, None) or (None,))[0] for p in ("Reference1", "Reference2")]:
            return True
    return False


def _centre(link):
    shape = getattr(link, "Shape", None)
    if shape is None or shape.isNull():
        return App.Vector(link.Placement.Base)
    return shape.BoundBox.Center


def _local(link, slides, turns):
    """Global directions / axes -> the part's own frame (so a drag that moves or turns it keeps them right)."""
    inv = link.Placement.inverse()
    rot = inv.Rotation
    return ([rot.multVec(d) for d in slides], [(inv.multVec(p), rot.multVec(a)) for p, a in turns])


def _all_free(link):
    c = _centre(link)
    axes = [App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)]
    return Freedom(6, *_local(link, list(axes), [(c, a) for a in axes]), error="")


def _probe(doc, asm, link, start):
    """The six test moves of one part (every other part held): Freedom in the part's own frame."""
    import numpy as np
    c = _centre(link)
    rows, motions = [], []
    for i in range(6):
        axis = App.Vector(*[1 if k == i % 3 else 0 for k in range(3)])
        if i < 3:
            delta = App.Placement(axis * STEP, App.Rotation())
        else:
            delta = App.Placement(App.Vector(), App.Rotation(axis, TURN), c)
        link.Placement = delta.multiply(start[link.Name])
        if asm.solve() != 0:
            raise ValueError("the solver failed")
        rel = App.Placement(link.Placement).multiply(start[link.Name].inverse())
        for name, plc in start.items():
            doc.getObject(name).Placement = plc
        moved = rel.multVec(c) - c
        angle = math.degrees(rel.Rotation.Angle)
        ax = rel.Rotation.Axis
        rows.append([moved.x / STEP, moved.y / STEP, moved.z / STEP,
                     ax.x * angle / TURN, ax.y * angle / TURN, ax.z * angle / TURN])
        motions.append(rel)
    m = np.array(rows)
    n = int(np.linalg.matrix_rank(m, tol=TOL)) if m.any() else 0
    trans = np.array([r[:3] for r in rows[:3] if np.linalg.norm(r[3:]) < TOL and np.linalg.norm(r[:3]) > TOL])
    slides = []
    if len(trans):
        _, s, vt = np.linalg.svd(trans)
        slides = [App.Vector(*vt[k]).normalize() for k in range(int((s > TOL).sum()))]
    turns = []
    for r, rel in zip(rows[3:], motions[3:]):
        if np.linalg.norm(r[3:]) < TOL:
            continue
        axis = App.Vector(rel.Rotation.Axis).normalize()
        if any(abs(axis.dot(a)) > 0.99 for _, a in turns):
            continue
        rot = np.array(rel.Rotation.toMatrix().A).reshape(4, 4)[:3, :3]
        t = np.array([rel.Base.x, rel.Base.y, rel.Base.z])
        p = np.linalg.lstsq(np.eye(3) - rot, t, rcond=None)[0]  # the line the part turned about
        point = App.Vector(*p)
        point = point + axis * (c - point).dot(axis)  # its point level with the part's centre
        turns.append((point, axis))
    return Freedom(n, *_local(link, slides, turns), error="")


def compute(doc):
    """{link name: Freedom} for every free, unsuppressed component."""
    if getattr(doc, "Restoring", False) or doc.HasPendingTransaction:
        raise Busy()
    asm = assembly.assembly_of(doc)
    comps = assembly.components(doc)
    free = [c for c in comps if not assembly.is_grounded(c) and not assembly.is_suppressed(c)]
    start = {c.Name: App.Placement(c.Placement) for c in comps}
    gdoc = None
    if App.GuiUp:
        import FreeCADGui as Gui
        gdoc = Gui.getDocument(doc.Name)
    modified = gdoc.Modified if gdoc is not None else None
    out, held = {}, []
    opened = bool(doc.UndoMode)
    if opened:
        doc.openTransaction("InCad DOF count")
    try:
        for c in free:
            if not _held_by_a_joint(doc, c):
                out[c.Name] = _all_free(c)  # nothing holds it (the solver would need a fixed part to say so)
        counted = [c for c in free if c.Name not in out]
        for c in counted:
            assembly.ground(c)
            held.append(c)
        for c in counted:
            assembly.unground(c)
            try:
                out[c.Name] = _probe(doc, asm, c, start)
            except Exception as e:
                out[c.Name] = Freedom(None, [], [], "Could not count: %s" % e)
            finally:
                for name, plc in start.items():
                    doc.getObject(name).Placement = plc
                assembly.ground(c)
    finally:
        for c in held:
            if doc.getObject(c.Name) is not None:
                assembly.unground(c)
        for name, plc in start.items():
            if doc.getObject(name) is not None:
                doc.getObject(name).Placement = plc
        if opened:
            doc.abortTransaction()
        doc.recompute()
        if gdoc is not None:
            gdoc.Modified = modified
    return out
