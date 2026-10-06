"""Section view plane from a selection: three points, a flat face or a work/origin plane (XZ when nothing)."""
import FreeCAD as App


def _rotation_to(normal):
    return App.Rotation(App.Vector(0, 0, 1), normal)


def _usable(obj, sub):
    if sub:
        return sub.startswith(("Vertex", "Face"))
    return obj.TypeId in ("App::Plane", "PartDesign::Plane")


def placement(pairs):
    """Placement whose Z is the section normal, from resolved (obj, sub) picks."""
    pairs = [(o, s) for o, s in pairs if _usable(o, s)]  # edges, whole solids… can't define a plane: ignored
    if not pairs:
        return App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), -90))  # XZ through the origin
    shapes = [o.getSubObject(s) if s else getattr(o, "Shape", None) for o, s in pairs]
    if len(pairs) == 3 and all(sh is not None and sh.ShapeType == "Vertex" for sh in shapes):
        a, b, c = (sh.Point for sh in shapes)
        n = (b - a).cross(c - a)
        if n.Length < 1e-9:
            raise ValueError("Pick three different points that are not in a line")
        n.normalize()
        return App.Placement(a, _rotation_to(n))
    if len(pairs) == 1:
        sh = shapes[0]
        face = sh if sh is not None and sh.ShapeType == "Face" else \
            (sh.Faces[0] if sh is not None and sh.Faces and len(sh.Faces) == 1 else None)
        if face is not None and face.Surface.TypeId == "Part::GeomPlane":
            return App.Placement(face.CenterOfMass, _rotation_to(face.normalAt(0, 0)))
    raise ValueError("For a section, select three points, a flat face or a plane (or nothing for XZ)")


def adjusted(base, offset=0.0, flip=False):
    """`base` moved `offset` along its normal; flipped = the other side is cut away."""
    normal = base.Rotation.multVec(App.Vector(0, 0, 1))
    rot = base.Rotation.multiply(App.Rotation(App.Vector(1, 0, 0), 180)) if flip else base.Rotation
    return App.Placement(base.Base + normal * offset, rot)


def through_points(a, b, c):
    n = (b - a).cross(c - a)
    if n.Length < 1e-9:
        raise ValueError("Pick three different points that are not in a line")
    n.normalize()
    return App.Placement(a, _rotation_to(n))


def snap_points(shape, limit=300):
    """Points worth cutting through: corners and middles of straight and circular edges, circle/arc centres —
    no duplicates, nothing from helix/spline edges or tiny ones (a thread would bury the part in markers)."""
    out = []
    small = max(1e-6, shape.BoundBox.DiagonalLength / 100.0)

    def add(kind, p):
        if len(out) < limit and not any((p - q).Length < 1e-6 for _, q in out):
            out.append((kind, App.Vector(p)))
    edges = [e for e in shape.Edges if e.Curve.TypeId in ("Part::GeomLine", "Part::GeomCircle") and e.Length > small]
    for e in edges:
        for v in e.Vertexes:
            add("corner", v.Point)
    for e in edges:
        if e.Curve.TypeId == "Part::GeomCircle":
            add("centre", e.Curve.Center)
        try:
            add("middle", e.valueAt((e.FirstParameter + e.LastParameter) / 2.0))
        except Exception:
            pass
    return out


def cut_shape(shape, placement, flip=False):
    """What is left of `shape` on one side of the section plane (the other side is cut away). The cut faces
    are real, so the section looks like material, not like sheets."""
    import Part
    size = max(10.0, shape.BoundBox.DiagonalLength * 3)
    box = Part.makeBox(size, size, size, App.Vector(-size / 2, -size / 2, 0))  # z from 0 up: the side to remove
    box.Placement = adjusted(placement, 0.0, flip)
    return shape.cut(box)


def purge_markers(doc):
    """Remove section markers an earlier InCad build left in the file (Part::Feature balls outside any body,
    named MarkN with a Corner/Middle/Centre label). Returns how many were removed."""
    import re
    gone = 0
    for o in list(doc.Objects):
        if o.TypeId == "Part::Feature" and re.match(r"^Mark\d+$", o.Name) and \
                re.match(r"^(Corner|Middle|Centre) \d+$", o.Label) and o.getParentGeoFeatureGroup() is None \
                and not o.InList:
            doc.removeObject(o.Name)
            gone += 1
    return gone


def cap_faces(shape, placement, flip=False):
    """The material cut by the plane: faces of the solid's cross-section at `placement` (global). Empty when the
    plane misses the solid. Cheap (a slice, not a boolean cut) and works where a cut fails (threads)."""
    import Part
    pl = adjusted(placement, 0.0, flip)
    normal = pl.Rotation.multVec(App.Vector(0, 0, 1))
    d = pl.Base.dot(normal)
    try:
        wires = shape.slice(normal, d)
    except Exception:
        return []
    wires = [w for w in wires if w.isClosed()]
    if not wires:
        return []
    try:
        face = Part.makeFace(wires, "Part::FaceMakerBullseye")
        return face.Faces
    except Exception:
        out = []
        for w in wires:
            try:
                out.append(Part.Face(w))
            except Exception:
                pass
        return out


class Caps:
    """Cut faces for many planes through one solid: a triangle mesh of it is sliced (milliseconds) instead of the
    solid (hundreds of ms on a threaded part); the solid is asked only when the mesh gives nothing."""

    def __init__(self, shape):
        import MeshPart
        self.shape = shape
        d = max(0.02, shape.BoundBox.DiagonalLength / 2000.0)
        try:
            self.mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=d, AngularDeflection=0.3, Relative=False)
        except Exception:
            self.mesh = None

    def faces(self, placement, flip=False):
        import Part
        pl = adjusted(placement, 0.0, flip)
        if self.mesh is not None:
            n = pl.Rotation.multVec(App.Vector(0, 0, 1))
            try:
                raw = self.mesh.crossSections([(pl.Base, n)], 0.0001, False)[0]  # segments, chained here
            except Exception:
                raw = []
            segments = []
            for poly in raw:
                pts = [App.Vector(q) for q in poly]
                segments += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
            wires = []
            for loop in _loops(segments, max(1e-5, self.shape.BoundBox.DiagonalLength / 1e5)):
                try:
                    wires.append(Part.makePolygon(loop + [loop[0]]))
                except Exception:
                    pass
            if wires:
                try:
                    return Part.makeFace(wires, "Part::FaceMakerBullseye").Faces
                except Exception:
                    out = []
                    for w in wires:
                        try:
                            out.append(Part.Face(w))
                        except Exception:
                            pass
                    if out:
                        return out
        return cap_faces(self.shape, placement, flip)


def _loops(segments, tol):
    """Closed loops (lists of points) from unordered segments, matching ends within `tol`; open chains and
    loops of fewer than three points are dropped."""
    def key(p):
        return (round(p.x / tol), round(p.y / tol), round(p.z / tol))
    ends = {}
    for i, (a, b) in enumerate(segments):
        if (a - b).Length < tol:
            continue
        ends.setdefault(key(a), []).append(i)
        ends.setdefault(key(b), []).append(i)
    used = [False] * len(segments)
    loops = []
    for start, (a, b) in enumerate(segments):
        if used[start] or (a - b).Length < tol:
            continue
        used[start] = True
        chain = [a, b]
        while True:
            k = key(chain[-1])
            nxt = next((j for j in ends.get(k, []) if not used[j]), None)
            if nxt is None:
                break
            used[nxt] = True
            c, d = segments[nxt]
            chain.append(d if (c - chain[-1]).Length < (d - chain[-1]).Length else c)
            if (chain[-1] - chain[0]).Length < tol:
                chain.pop()
                break
        if len(chain) >= 3 and (chain[-1] - chain[0]).Length < tol * 10 or len(chain) >= 3 and key(chain[-1]) == key(chain[0]):
            loops.append(chain)
        elif len(chain) >= 3:
            # the walk returned to the start without matching within tol: accept when it is close
            if (chain[-1] - chain[0]).Length < tol * 100:
                loops.append(chain)
    return loops
