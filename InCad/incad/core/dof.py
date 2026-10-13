"""Degrees of freedom of assembly components (Inventor), counted by probing FreeCAD's solver: six small test moves
of a part, each solved; what the solver keeps is a freedom. Relative to what holds the part: every other free part
is held still (temporary grounds) while it is counted. No transaction (opening one, even to abort it, empties FreeCAD's
redo stack): the grounds are removed and every placement put back by hand, so the count leaves no undo step, keeps
Redo working and leaves nothing in the file. Pure model logic."""
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
    slides, turns = _split(m, n, c, start[link.Name].Rotation)
    return Freedom(n, *_local(link, slides, turns), error="")


def _aligned(basis, preferred):
    """An orthonormal basis of the span of `basis` (rows) that takes the `preferred` directions where they lie in it
    (the part's own axes first): any basis spans the same freedoms, but an arrow should move the part straight up or
    sideways, not along a diagonal of its free plane."""
    import numpy as np
    k = len(basis)
    if k == 0:
        return []
    q, _ = np.linalg.qr(np.array(basis).T)  # columns: an orthonormal basis of the span
    q = q[:, :k]
    out = []
    for cand in preferred:
        if len(out) == k:
            break
        p = q @ (q.T @ cand)                  # into the span
        for o in out:
            p = p - o * p.dot(o)
        if np.linalg.norm(p) > 0.5:          # mostly in the span (and new): take it
            out.append(p / np.linalg.norm(p))
    for col in q.T:                          # whatever the preferred ones left: the span's own directions
        if len(out) == k:
            break
        p = col.copy()
        for o in out:
            p = p - o * p.dot(o)
        if np.linalg.norm(p) > 1e-6:
            out.append(p / np.linalg.norm(p))
    return out


def _split(m, n, c, rot=None):
    """The freedoms in the kept test moves `m` (rows: the centre's motion per STEP, the turn per TURN), rank `n`, as
    slides and turns. FreeCAD's solver moves a part about its own origin, which can lie far from the part (a part
    drawn away from its file's origin): a test push then comes back as a slide-and-turn, so no single row is a pure
    slide or turn. Their span is right: the slides are the moves in it with no turn, the turns the rest, each turning
    about its own axis (from the twist: the point where the motion is a pure turn, nearest the centre)."""
    import numpy as np
    if n == 0:
        return [], []
    _, _, vt = np.linalg.svd(m)
    basis = vt[:n]
    v = basis[:, :3] * STEP                      # mm: how the centre moves
    w = basis[:, 3:] * math.radians(TURN)        # rad: how the part turns
    _, sw, vtw = np.linalg.svd(w.T)              # w.T is 3 x n
    r = int((sw > TOL * math.radians(TURN)).sum())
    pure = vtw[r:] @ v                           # the combinations that do not turn: slides
    own = [np.array(list(rot.multVec(App.Vector(*e)))) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))] if rot else []
    world = [np.eye(3)[k] for k in range(3)]
    slides = []
    if len(pure):
        _, sp, vts = np.linalg.svd(pure)
        slides = _aligned([vts[k] for k in range(int((sp > TOL * STEP).sum()))], own + world)
    turns = []
    rot_coeffs = vtw[:r]
    if r:
        dirs = rot_coeffs @ w                 # r x 3: the ways it can turn
        wanted = _aligned(list(dirs), own + world)
        rot_coeffs = [np.linalg.lstsq(dirs.T, a, rcond=None)[0] @ vtw[:r] for a in wanted]
    for coeff in rot_coeffs:
        wv, vv = coeff @ w, coeff @ v
        for sl in slides:  # a free slide may ride along with the turn: take it out
            vv = vv - sl * vv.dot(sl)
        axis = wv / np.linalg.norm(wv)
        point = np.cross(wv, vv) / wv.dot(wv)     # from the centre to the turn's axis
        turns.append((c + App.Vector(*point), App.Vector(*axis)))
    return [App.Vector(*sl).normalize() for sl in slides], turns


def loading():
    """True while any open file is still loading: FreeCAD pumps events for its progress bar, and a solve now would
    recompute a half-restored document."""
    return any(getattr(d, "Restoring", False) for d in App.listDocuments().values())


def compute(doc):
    """{link name: Freedom} for every free, unsuppressed component."""
    if loading() or getattr(doc, "Restoring", False) or doc.HasPendingTransaction:
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
    # no transaction: opening one (even to abort it) empties the redo stack, and a count must not break Redo
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
        try:
            doc.recompute()
        finally:
            if gdoc is not None:
                gdoc.Modified = modified
    return out


Handle = namedtuple("Handle", "kind index line heads axis point u w radius pivot")
"""One freedom's part of the glyph, in global coordinates: kind 'slide' (a double arrow through `point` along `axis`)
or 'turn' (an arc of `radius` around `axis` through `point`, from `u` towards `w`, w = axis x u: a positive turn;
`pivot`: a point of the line the part really turns about — `point` too unless that line is far from the part);
index: its place among the freedom's slides or turns; line: its polyline; heads: [(tip, direction)...]."""
RING = 0.3  # each further turn's arc is this many glyph sizes wider (0.6, 0.9, 1.2)
FAR = 1.5  # a turn axis farther from the part's centre than this many glyph sizes: its arc is drawn at the centre


def handles(freedom, placement, centre, size):
    """The glyph of a part now at `placement`, one Handle per freedom: the slides first, then the turns."""
    out = []
    rot = placement.Rotation
    for i, d in enumerate(freedom.slides):
        g = rot.multVec(d).normalize()
        a, b = centre - g * size, centre + g * size
        out.append(Handle("slide", i, [a, b], [(b, g), (a, g * -1)], g, App.Vector(centre), None, None, None, None))
    for i, (point, axis) in enumerate(freedom.turns):
        ax = rot.multVec(axis).normalize()
        p = placement.multVec(point)
        pivot = p + ax * (centre - p).dot(ax)
        base = App.Vector(centre) if (pivot - centre).Length > FAR * size else pivot  # always on the part
        u = ax.cross(App.Vector(1, 0, 0))
        if u.Length < 1e-6:
            u = ax.cross(App.Vector(0, 1, 0))
        u.normalize()
        w = ax.cross(u)
        r = size * (0.6 + RING * i)  # each turn its own ring: arcs around one centre never meet
        ts = [1.5 * math.pi * k / 24 for k in range(25)]
        pts = [base + (u * math.cos(t) + w * math.sin(t)) * r for t in ts]
        end = ts[-1]
        out.append(Handle("turn", i, pts, [(pts[-1], (u * -math.sin(end) + w * math.cos(end)).normalize())],
                          ax, base, u, w, r, pivot))
    return out


def glyph(freedom, placement, centre, size):
    """Inventor's DOF glyph for a part now at `placement`: a double arrow per slide through `centre`, a 270° arc per
    turn around its axis (level with the centre). ([[Vector…]…] polylines, [(tip, direction)…] arrow heads)."""
    hs = handles(freedom, placement, centre, size)
    return [h.line for h in hs], [hd for h in hs for hd in h.heads]
