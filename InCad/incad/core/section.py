"""Section view plane from a selection: three points, a flat face or a work/origin plane (XZ when nothing)."""
import FreeCAD as App
from incad.core import safe


def _rotation_to(normal):
    return App.Rotation(App.Vector(0, 0, 1), normal)


def _usable(obj, sub):
    if sub:
        return sub.startswith(("Vertex", "Face"))
    return obj.TypeId in ("App::Plane", "PartDesign::Plane")


def picked(pairs):
    """The picks that can make a section plane: points, faces, work and origin planes (edges, whole solids… can't)."""
    return [(o, s) for o, s in pairs if _usable(o, s)]


def placement(pairs):
    """Placement whose Z is the section normal, from resolved (obj, sub) picks."""
    pairs = picked(pairs)
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
            # an origin plane is endless: its centre lies at -5e99 and the section went there (nothing was cut)
            at = face.CenterOfMass if face.BoundBox.DiagonalLength < 1e9 else face.Surface.Position
            return App.Placement(at, _rotation_to(face.normalAt(0, 0)))
    raise ValueError("For a section, select three points, a flat face or a plane (or nothing for XZ)")


_SKIP = ("Sketcher::", "Image::", "Mesh::", "Spreadsheet::", "App::Origin", "App::Line", "App::Plane", "App::Point",
         "Assembly::JointGroup", "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point")
_GROUPS = ("App::Part", "App::DocumentObjectGroup", "Assembly::AssemblyObject")


def shown_shapes(doc):
    """[(object, shape in the document's frame, the object its colour comes from)] of everything shown that has
    faces — an assembly's components (InCad's links, or Bodies and Part shapes put in a FreeCAD assembly), a STEP
    opened in its App::Part groups, shapes from other programs (the user: Section cuts any solid, STEPs, files from
    other programs). Groups are opened, never cut as a whole (their shape is their children's again)."""
    out = []

    def add(o, shape, colour_of):
        if shape is None or shape.isNull() or not shape.Faces:
            return
        parent = o.getGlobalPlacement().multiply(o.Placement.inverse()) if hasattr(o, "getGlobalPlacement") \
            and hasattr(o, "Placement") else App.Placement()
        if not parent.isIdentity():  # inside a moved group: into the document's frame
            shape = shape.copy()
            shape.transformShape(parent.toMatrix())
        out.append((o, shape, colour_of))

    def walk(objs, seen):
        for o in objs:
            if o in seen:
                continue
            seen.add(o)
            t = o.TypeId
            if t.startswith(_SKIP) or not getattr(o, "Visibility", True) or getattr(o, "Suppressed", False):
                continue
            if hasattr(o, "InCadMeshReference"):
                continue  # an STL Reference: something to measure on, not a part
            if t in _GROUPS:
                walk(getattr(o, "Group", []), seen)
            elif t == "App::Link":
                try:
                    add(o, o.Shape, getattr(o, "LinkedObject", None) or o)
                except Exception:
                    pass
            elif hasattr(o, "Shape"):
                try:
                    add(o, o.Shape, o)
                except Exception:
                    pass
    walk(doc.RootObjects, set())
    return out


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
    edges = [e for e in shape.Edges if safe.curve_type(e) in ("Part::GeomLine", "Part::GeomCircle") and e.Length > small]
    for e in edges:
        for v in e.Vertexes:
            add("corner", v.Point)
    for e in edges:
        if safe.curve_type(e) == "Part::GeomCircle":
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
            segs, edges = [], []
            for f, dd in zip(facets[cross], tri[cross]):
                hits, keys = [], []
                for i in range(3):
                    j = (i + 1) % 3
                    a, b = dd[i], dd[j]
                    if (a < 0) != (b < 0):
                        t = a / (a - b)
                        q = pts[f[i]] + (pts[f[j]] - pts[f[i]]) * t
                        hits.append(App.Vector(*q))
                        keys.append((min(f[i], f[j]), max(f[i], f[j])))
                if len(hits) == 2:
                    segs.append((hits[0], hits[1]))
                    edges.append((keys[0], keys[1]))
            self._edges = edges  # the mesh edge each end lies on: chained by those, not by distance
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
        tol = max(1e-5, self.shape.BoundBox.DiagonalLength / 2e4)
        # the mesh is sliced a hair off the plane: a plane through mesh vertices (a gear's middle, where its side
        # faces are meshed) left a hole in the loop at every vertex on it, and the cut showed hollow
        self._edges = None
        segments = self._segments(pl.Base + n * (tol * 0.0123), n)
        chained = _loops_by_edges(segments, self._edges) if self._edges else None
        out = []
        for loop in (chained if chained is not None else _loops(segments, tol)):
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


def _loops_by_edges(segments, edges):
    """Closed loops from the slice's segments, each end known by the mesh edge it lies on: on a closed mesh every
    crossed edge belongs to two crossing triangles, so the loops follow without a tolerance (chaining by distance
    took wrong turns where the outline passes close to itself: a worm's axial section came out in bits). None when
    the mesh isn't closed there (an edge met once or more than twice): chain by distance instead."""
    by_edge = {}
    for i, (ka, kb) in enumerate(edges):
        by_edge.setdefault(ka, []).append(i)
        by_edge.setdefault(kb, []).append(i)
    if any(len(v) != 2 for v in by_edge.values()):
        return None
    used = [False] * len(segments)
    loops = []
    for start in range(len(segments)):
        if used[start]:
            continue
        used[start] = True
        a, b = segments[start]
        first_key, key = edges[start]
        loop = [a, b]
        i = start
        while key != first_key:
            j = by_edge[key][0] if by_edge[key][0] != i else by_edge[key][1]
            if used[j]:
                return None  # not one simple loop: leave it to the distance chaining
            used[j] = True
            ka, kb = edges[j]
            c, d = segments[j]
            nxt, point = (kb, d) if ka == key else (ka, c)
            loop.append(point)
            key, i = nxt, j
        loop.pop()  # its last point is the first again
        if len(loop) >= 3:
            loops.append(loop)
    return loops


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
        """Walk on from the chain's last point; True when the walk came back to the chain's first point. Where more
        segments meet (the outline passing close to itself: a worm's thread at its root), the walk goes on along
        the one that turns least (taking the nearest went off along the other pass and broke the cut into bits)."""
        while True:
            k = key(chain[-1])
            nxt, best = None, None
            came = chain[-1] - chain[-2] if len(chain) > 1 else None
            if came is not None and came.Length > 1e-12:
                came = came * (1.0 / came.Length)
            for j in ends.get(k, []):
                if used[j]:
                    continue
                c, d = segs[j]
                far = d if (c - chain[-1]).Length <= (d - chain[-1]).Length else c
                step = far - chain[-1]
                if came is not None and step.Length > 1e-12:
                    score = -came.dot(step * (1.0 / step.Length))  # straight on: -1, back: +1
                else:
                    score = step.Length
                if best is None or score < best:
                    nxt, best = j, score
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
