"""Move Face: flat faces moved along their normal by d (outward > 0) — the slab between the faces' old and new place is
added (d > 0) or cut (d < 0). Three ways for the neighbours (the faces sharing an edge with a moved face):
- step: the slab is the face pushed straight (a slanted neighbour stays, a straight wall appears at its edge);
- inventor: the slab's side walls lie on the neighbours (flat at any angle, or a cylinder along the move), so a chamfer
  keeps its angle and grows / shrinks; a round neighbour across the move cannot follow yet;
- together: the face moves with its neighbours that are not along the move (chamfers, fillets) as one piece; the walls
  around them must run along the move and grow.
Faces are kept by geometry (signature / find), never by name. Pure Part code, headless."""
import FreeCAD as App
import Part

FACES_MSG = "The faces must be flat and face the same way"
PARALLEL_MSG = "Pick a face or plane parallel to the faces"
ROUND_MSG = "A neighbouring face is round: Inventor mode can't follow it yet — try Step or Together"
WALLS_MSG = "The walls around the chamfer / fillet must run along the move — try Inventor or Step"
TOO_LARGE_MSG = "The move is too large: a neighbouring face would vanish"
GONE_MSG = "A face to move is no longer there"
_TOL = 1e-6
_ANG = 1e-6


def _is_plane(face):
    return face.Surface.__class__.__name__ == "Plane"


def _normal(face):
    """The outward normal of a flat face of a solid (FreeCAD's normalAt follows the face's orientation)."""
    return face.normalAt(0, 0)


def signature(face):
    n = _normal(face)
    pts = [v.Point for v in face.OuterWire.OrderedVertexes] or [face.CenterOfMass]
    if len(pts) < 3:  # a round face (a boss top): its outline sampled
        pts = face.OuterWire.discretize(24)
    return {"n": [n.x, n.y, n.z], "p": list(face.CenterOfMass), "outline": [list(p) for p in pts],
            "area": face.Area}


def _sig_face(sig):
    pts = [App.Vector(*p) for p in sig["outline"]]
    return Part.Face(Part.makePolygon(pts + [pts[0]]))


def find(shape, sig):
    """The face again: same direction, its outline overlapping the stored one seen along n; the stored plane first,
    then the most overlap, then the nearest plane (an earlier feature made the part taller: the top moved)."""
    n, p = App.Vector(*sig["n"]), App.Vector(*sig["p"])
    try:
        ref = _sig_face(sig)
    except Exception:
        return None
    best, key = None, None
    for f in shape.Faces:
        if not _is_plane(f) or _normal(f).dot(n) < 1 - _ANG:
            continue
        off = (f.CenterOfMass - p).dot(n)
        try:
            s = f.translated(n * -off).common(ref).Area
        except Exception:
            s = 0.0
        if s <= _TOL:
            continue
        k = (abs(off) > _TOL, -s, abs(off))
        if key is None or k < key:
            best, key = f, k
    return best


def check_faces(faces):
    if not faces or not all(_is_plane(f) for f in faces):
        raise ValueError(FACES_MSG)
    n = _normal(faces[0])
    for f in faces[1:]:
        if _normal(f).dot(n) < 1 - _ANG:
            raise ValueError(FACES_MSG)
    return n


def gap_to(faces, target):
    n = check_faces(faces)
    if isinstance(target, Part.Face):
        if not _is_plane(target):
            raise ValueError(PARALLEL_MSG)
        point, normal = target.CenterOfMass, _normal(target)
    else:
        point, normal = target
    if abs(abs(App.Vector(normal).normalize().dot(n)) - 1) > _ANG:
        raise ValueError(PARALLEL_MSG)
    return (App.Vector(point) - faces[0].CenterOfMass).dot(n)


def _along(face, n):
    """A face the move runs along: a plane containing n, or a cylinder whose axis is n."""
    kind = face.Surface.__class__.__name__
    if kind == "Plane":
        return abs(_normal(face).dot(n)) < _ANG
    if kind == "Cylinder":
        return abs(abs(face.Surface.Axis.normalize().dot(n)) - 1) < _ANG
    return False


def _same(a, b):
    return a.isSame(b)


def _neighbour(shape, face, edge):
    for f in shape.ancestorsOfType(edge, Part.Face):
        if not _same(f, face):
            return f
    return None


def _side_dir(shape, face, vertex):
    """The line a vertex of `face` moves along (inventor): the solid's edge at that vertex that is not on `face`."""
    own = list(face.Edges)
    for e in shape.ancestorsOfType(vertex, Part.Edge):
        if any(_same(e, o) for o in own):
            continue
        if e.Curve.__class__.__name__ != "Line":
            raise ValueError(ROUND_MSG)
        a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
        far = b if a.distanceToPoint(vertex.Point) < _TOL else a
        return (vertex.Point - far).normalize(), e.Length
    raise ValueError(ROUND_MSG)


def _moved_wire(shape, face, wire, n, d):
    """The wire in the new plane, every vertex along its side line, every edge on its neighbour (inventor)."""
    for e in wire.Edges:
        nb = _neighbour(shape, face, e)
        if nb is None or not (_is_plane(nb) or _along(nb, n)):
            raise ValueError(ROUND_MSG)
    moved = {}
    for v in wire.OrderedVertexes:
        u, length = _side_dir(shape, face, v)
        if abs(u.dot(n)) < _ANG:
            raise ValueError(TOO_LARGE_MSG)
        t = d / u.dot(n)
        if t < 0 and -t >= length - _TOL:  # back along its side edge past that edge's far end: the neighbour vanishes
            raise ValueError(TOO_LARGE_MSG)
        moved[v.hashCode()] = v.Point + u * t
    edges = []
    for e in wire.OrderedEdges:
        a, b = moved[e.Vertexes[0].hashCode()], moved[e.Vertexes[-1].hashCode()]
        if e.Curve.__class__.__name__ == "Line":
            if a.distanceToPoint(b) < _TOL:
                raise ValueError(TOO_LARGE_MSG)
            edges.append(Part.LineSegment(a, b).toShape())
        else:  # an arc / circle on a cylinder along the move: it slides
            edges.append(e.translated(n * d))
    w = Part.Wire(Part.__sortEdges__(edges))
    if not w.isClosed():
        raise ValueError(TOO_LARGE_MSG)
    return w


def _loft(a, b):
    return Part.makeLoft([a, b], True, True)


def _inventor_slab(shape, face, n, d):
    outer = Part.Wire(face.OuterWire.OrderedEdges)
    new_outer = _moved_wire(shape, face, face.OuterWire, n, d)
    try:
        if not Part.Face(new_outer).isValid() or Part.Face(new_outer).Area < _TOL:
            raise ValueError(TOO_LARGE_MSG)
    except Part.OCCError:
        raise ValueError(TOO_LARGE_MSG)
    slab = _loft(outer, new_outer)
    for inner in face.Wires:
        if inner.isSame(face.OuterWire):
            continue
        slab = slab.cut(_loft(Part.Wire(inner.OrderedEdges), _moved_wire(shape, face, inner, n, d)))
    return slab


def _together_slab(shape, face, n, d):
    moved = [face] + [nb for nb in (_neighbour(shape, face, e) for e in face.Edges)
                      if nb is not None and not _along(nb, n)]
    group = []
    for f in moved:
        if not any(_same(f, g) for g in group):
            group.append(f)
    count = {}
    for f in group:
        for e in f.Edges:
            key = e.hashCode()
            count[key] = (count.get(key, (0, e))[0] + 1, e)
    rim = [e for c, e in count.values() if c == 1]
    for e in rim:
        wall = next((f for f in shape.ancestorsOfType(e, Part.Face) if not any(_same(f, g) for g in group)), None)
        if wall is not None and not _along(wall, n):
            raise ValueError(WALLS_MSG)
    caps = [f.copy() for f in group] + [f.translated(n * d) for f in group]
    strips = [e.extrude(n * d).Faces[0] for e in rim]
    sh = Part.Shell(caps + strips).sewShape() or Part.Shell(caps + strips)
    if sh.ShapeType != "Shell":
        sh = Part.Shell(sh.Faces)
    return Part.Solid(sh)


def apply(shape, faces, d, mode):
    if abs(d) < _TOL:
        return shape
    n = check_faces(faces)
    slabs = []
    for f in faces:
        if mode == "step":
            slabs.append(f.extrude(n * d))
        elif mode == "together":
            slabs.append(_together_slab(shape, f, n, d))
        else:
            slabs.append(_inventor_slab(shape, f, n, d))
    slab = slabs[0] if len(slabs) == 1 else slabs[0].fuse(slabs[1:])
    result = (shape.fuse(slab) if d > 0 else shape.cut(slab)).removeSplitter()
    if not result.isValid() or len(result.Solids) != len(shape.Solids):
        raise ValueError(TOO_LARGE_MSG)
    return result
