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
    solid (hundreds of ms on a threaded part). The slice's segments are chained into closed loops, projected
    onto the plane exactly, and made into faces; a loop FreeCAD can't make a face of is kept as a polygon
    (`polygons`), drawn as it is."""

    def __init__(self, shape):
        import MeshPart
        self.shape = shape
        self.polygons = []  # loops of the last call that became no face (drawn directly)
        self.last_loops = []
        d = max(0.02, shape.BoundBox.DiagonalLength / 2000.0)
        try:
            self.mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=d, AngularDeflection=0.3, Relative=False)
        except Exception:
            self.mesh = None

    def _topology(self):
        if getattr(self, "_topo", None) is None:
            pts, facets = self.mesh.Topology
            try:
                import numpy as np
                self._topo = (np.array([(p.x, p.y, p.z) for p in pts], dtype=float), np.array(facets, dtype=int))
            except ImportError:
                self._topo = ([App.Vector(p) for p in pts], facets)
        return self._topo

    def _segments(self, base, n):
        """Segments where the plane cuts the mesh's triangles (the mesh's own slicer glues loops together)."""
        pts, facets = self._topology()
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is not None and isinstance(pts, np.ndarray):
            nn = np.array([n.x, n.y, n.z])
            d = (pts - np.array([base.x, base.y, base.z])) @ nn  # signed distance of every point
            tri = d[facets]  # (M, 3)
            cross = (tri.max(axis=1) > 0) & (tri.min(axis=1) < 0)
            segs = []
            for f, dd in zip(facets[cross], tri[cross]):
                hits = []
                for i in range(3):
                    j = (i + 1) % 3
                    a, b = dd[i], dd[j]
                    if (a < 0) != (b < 0):
                        t = a / (a - b)
                        q = pts[f[i]] + (pts[f[j]] - pts[f[i]]) * t
                        hits.append(App.Vector(*q))
                if len(hits) == 2:
                    segs.append((hits[0], hits[1]))
            return segs
        segs = []
        for f in facets:
            dd = [(pts[k] - base).dot(n) for k in f]
            if max(dd) <= 0 or min(dd) >= 0:
                continue
            hits = []
            for i in range(3):
                j = (i + 1) % 3
                a, b = dd[i], dd[j]
                if (a < 0) != (b < 0):
                    t = a / (a - b)
                    hits.append(pts[f[i]] + (pts[f[j]] - pts[f[i]]) * t)
            if len(hits) == 2:
                segs.append((hits[0], hits[1]))
        return segs

    def loops(self, placement, flip=False):
        """Closed loops (lists of points on the plane) of the cut at `placement`."""
        pl = adjusted(placement, 0.0, flip)
        if self.mesh is None:
            return []
        n = pl.Rotation.multVec(App.Vector(0, 0, 1))
        segments = self._segments(pl.Base, n)
        tol = max(1e-5, self.shape.BoundBox.DiagonalLength / 2e4)
        out = []
        for loop in _loops(segments, tol):
            flat = [q - n * (q - pl.Base).dot(n) for q in loop]  # exactly on the plane
            out.append(flat)
        return out

    def faces(self, placement, flip=False):
        import Part
        self.polygons = []
        loops = self.last_loops = self.loops(placement, flip)  # kept for the hatch: sliced once per move
        if not loops:
            return cap_faces(self.shape, placement, flip)
        wires = []
        for loop in loops:
            try:
                wires.append(Part.makePolygon(loop + [loop[0]]))
            except Exception:
                pass
        try:
            return Part.makeFace(wires, "Part::FaceMakerBullseye").Faces
        except Exception:
            pass
        out = []
        for w, loop in zip(wires, loops):
            try:
                out.append(Part.Face(w))
            except Exception:
                self.polygons.append(loop)
        return out


def _loops(segments, tol):
    """Closed loops (lists of points) from unordered segments: walked from a start segment in both directions,
    matching ends within `tol`; a chain that comes back to its start (or within 20·tol of it) is a loop; open
    chains are dropped."""
    def key(p):
        return (round(p.x / tol), round(p.y / tol), round(p.z / tol))
    segs = [(a, b) for a, b in segments if (a - b).Length >= tol]
    ends = {}
    for i, (a, b) in enumerate(segs):
        ends.setdefault(key(a), []).append(i)
        ends.setdefault(key(b), []).append(i)
    used = [False] * len(segs)

    def extend(chain):
        """Walk on from the chain's last point; True when the walk came back to the chain's first point."""
        while True:
            k = key(chain[-1])
            nxt, best = None, None
            for j in ends.get(k, []):
                if used[j]:
                    continue
                c, d = segs[j]
                far = d if (c - chain[-1]).Length <= (d - chain[-1]).Length else c
                dist = (far - chain[-1]).Length
                if best is None or dist < best:
                    nxt, best = j, dist
            if nxt is None:
                return False
            used[nxt] = True
            c, d = segs[nxt]
            chain.append(d if (c - chain[-1]).Length <= (d - chain[-1]).Length else c)
            if (chain[-1] - chain[0]).Length < tol:
                chain.pop()  # the closing point is the first point again
                return True

    loops, open_chains = [], []
    for start, (a, b) in enumerate(segs):
        if used[start]:
            continue
        used[start] = True
        chain = [a, b]
        closed = extend(chain)
        if not closed:  # stuck: go on from the other end
            chain.reverse()
            closed = extend(chain)
        if len(chain) >= 3 and (closed or (chain[-1] - chain[0]).Length < tol * 20):
            loops.append(chain)
        else:
            open_chains.append(chain)
    # mesh seams (a point of one face on an edge of its neighbour) leave chains open: join them end to end
    # within a wider reach, then close what came together
    reach = tol * 500
    changed = True
    while changed and len(open_chains) > 1:
        changed = False
        for i in range(len(open_chains)):
            if changed:
                break
            for j in range(len(open_chains)):
                if i == j:
                    continue
                a, b = open_chains[i], open_chains[j]
                pairs = [((a[-1] - b[0]).Length, a + b), ((a[-1] - b[-1]).Length, a + b[::-1]),
                         ((a[0] - b[0]).Length, a[::-1] + b), ((a[0] - b[-1]).Length, b + a)]
                dist, joined = min(pairs, key=lambda x: x[0])
                if dist < reach:
                    open_chains[i] = joined
                    del open_chains[j]
                    changed = True
                    break
    for chain in open_chains:
        if len(chain) >= 3 and (chain[-1] - chain[0]).Length < reach:
            loops.append(chain)
    return loops


def hatch(loops, placement, spacing, angle_deg=45.0):
    """Hatch lines across the cut (Inventor draws material that way): 3D segments inside the loops, parallel
    lines `spacing` apart at `angle_deg` in the plane, inside/outside by the even-odd rule. Vectorised: a
    threaded shaft gives thousands of loop points and the slider redraws on every move."""
    import math
    import numpy as np
    loops = [loop for loop in (loops or []) if len(loop) >= 2]
    if not loops or spacing <= 0:
        return []
    m = placement.inverse().toMatrix().A  # world -> plane coordinates
    rot = np.array([[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]])
    move = np.array([m[3], m[7], m[11]])
    a = math.radians(angle_deg)
    d = np.array([math.cos(a), math.sin(a), 0.0])   # along the lines
    n2 = np.array([-math.sin(a), math.cos(a), 0.0])  # across them
    kp, kq, sp, sq = [], [], [], []
    for loop in loops:
        pts = np.array([[v.x, v.y, v.z] for v in loop]) @ rot.T + move
        k, s = pts @ n2, pts @ d
        kp.append(k)
        kq.append(np.roll(k, -1))
        sp.append(s)
        sq.append(np.roll(s, -1))
    kp, kq, sp, sq = (np.concatenate(x) for x in (kp, kq, sp, sq))
    lo, hi = float(kp.min()), float(kp.max())
    d3, n3 = App.Vector(*d), App.Vector(*n2)
    out = []
    for k in np.arange(lo + spacing / 2.0, hi, spacing):
        dp, dq = kp - k, kq - k
        cross = (dp < 0) != (dq < 0)
        if not cross.any():
            continue
        t = dp[cross] / (dp[cross] - dq[cross])
        hits = np.sort(sp[cross] + (sq[cross] - sp[cross]) * t)
        for i in range(0, len(hits) - 1, 2):
            s0, s1 = float(hits[i]), float(hits[i + 1])
            if s1 - s0 > 1e-6:
                out.append((placement.multVec(d3 * s0 + n3 * float(k)), placement.multVec(d3 * s1 + n3 * float(k))))
    return out
