"""3D Line (the user's idea): a virtual cube of points round the origin, `step` apart, with construction lines between
neighbours; the line's points snap to the cube's points, or slide freely on its lines. The cube's size and step are
the user's. Pure geometry here (numpy): the lattice, what a ray from the pointer catches, the curve through the
points (lines, a spline on control points, a spline through the points)."""
import numpy as np

KINDS = ("polyline", "spline", "through")


def coords(size, step):
    """The cube's coordinates along one axis: centred on 0, `step` apart, as many as fit in `size`."""
    if step <= 0 or size <= 0:
        raise ValueError("The cube's size and step must be above zero")
    n = int(np.floor(size / step + 1e-9))
    if n < 1:
        raise ValueError("The step must not be larger than the cube")
    if n > 60:
        raise ValueError("At most 60 steps along the cube: make the step larger")
    return (np.arange(n + 1) - n / 2.0) * step


def lattice(size, step):
    """Every point of the cube, (N, 3)."""
    c = coords(size, step)
    x, y, z = np.meshgrid(c, c, c, indexing="ij")
    return np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)


def segments(size, step):
    """The construction lines as (M, 2, 3) ends: whole lines along X, Y and Z through the cube's points."""
    c = coords(size, step)
    lo, hi = c[0], c[-1]
    out = []
    for a in range(3):
        b, d = [i for i in range(3) if i != a]
        for u in c:
            for v in c:
                p, q = np.zeros(3), np.zeros(3)
                p[a], q[a] = lo, hi
                p[b] = q[b] = u
                p[d] = q[d] = v
                out.append((p, q))
    return np.array(out)


def unit_segments(size, step):
    """The construction lines cut at every cube point, (M, 2, 3): each piece can be drawn by its own depth."""
    c = coords(size, step)
    out = []
    for a in range(3):
        b, d = [i for i in range(3) if i != a]
        for i in range(len(c) - 1):
            for u in c:
                for v in c:
                    p, q = np.zeros(3), np.zeros(3)
                    p[a], q[a] = c[i], c[i + 1]
                    p[b] = q[b] = u
                    p[d] = q[d] = v
                    out.append((p, q))
    return np.array(out)


def depth_bins(points, d, half):
    """0 (near), 1, 2 (far) for each point along the view direction d (the cube's half size `half`)."""
    reach = max(half * 3 ** 0.5, 1e-9)
    t = (np.asarray(points) @ np.asarray(d, float) + reach) / (2 * reach)
    return np.clip((t * 3).astype(int), 0, 2)


def comb(edges, samples=60, reach=None):
    """The curvature comb of the line's edges: [(point, tip)] spikes, tips away from the centre of curvature, the
    longest `reach` long (a quarter of the line's length by default). Straight pieces have none."""
    import FreeCAD as App
    found = []
    for e in edges:
        a, b = e.FirstParameter, e.LastParameter
        for i in range(samples + 1):
            u = a + (b - a) * i / samples
            try:
                k = e.curvatureAt(u)
                n = e.normalAt(u) if k > 1e-12 else App.Vector()
            except Exception:
                k, n = 0.0, App.Vector()
            found.append((e.valueAt(u), n, k))
    top = max((k for _, _, k in found), default=0.0)
    if top < 1e-9:
        return []
    if reach is None:
        reach = 0.25 * sum(e.Length for e in edges)
    return [(p, p - n * (k / top * reach)) for p, n, k in found]


def _off_ray(points, o, d):
    """(distance from the ray, depth along it) for each point."""
    v = points - o
    t = v @ d
    return np.linalg.norm(v - np.outer(t, d), axis=1), t


def _choose(dist, depth, tol):
    """The index the pointer means: within tol of the ray; of those about as near as the nearest, the front one."""
    ok = np.nonzero(dist <= tol)[0]
    if not len(ok):
        return None
    near = dist[ok].min()
    close = ok[dist[ok] <= near + 0.35 * tol]
    return int(close[np.argmin(depth[close])])


LAYERS = {"xy": 2, "xz": 1, "yz": 0}  # a working layer by its name: the axis square to it


def layer_points(size, step, axis, level):
    """The points of one layer of the cube: the grid of the two other axes, at `level` along `axis`, (N, 3)."""
    c = coords(size, step)
    b, d = [k for k in range(3) if k != axis]
    gu, gv = np.meshgrid(c, c, indexing="ij")
    out = np.zeros((gu.size, 3))
    out[:, b], out[:, d] = gu.ravel(), gv.ravel()
    out[:, axis] = level
    return out


def layer_segments(size, step, axis, level):
    """The construction lines of one layer, whole, (M, 2, 3)."""
    c = coords(size, step)
    lo, hi = c[0], c[-1]
    out = []
    for a in [k for k in range(3) if k != axis]:
        other = [k for k in range(3) if k not in (a, axis)][0]
        for v in c:
            p, q = np.zeros(3), np.zeros(3)
            p[a], q[a] = lo, hi
            p[other] = q[other] = v
            p[axis] = q[axis] = level
            out.append((p, q))
    return np.array(out)


def snap(o, d, size, step, tol, layer=None):
    """What a ray from the pointer (origin o, unit direction d, in the cube's coordinates) catches, tol mm around it:
    {"kind": "point", "point": p} for a cube point, else {"kind": "line", "point": p, "axis": a, "ends": (lo, hi)}
    for a place on a construction line (lo / hi: the cube points either side of it on that line), else None.
    layer (axis, level): only that layer's points and lines (the user: the whole cube was too hard to read)."""
    o, d = np.asarray(o, float), np.asarray(d, float)
    d = d / np.linalg.norm(d)
    pts = lattice(size, step) if layer is None else layer_points(size, step, *layer)
    dist, depth = _off_ray(pts, o, d)
    i = _choose(dist, depth, tol)
    if i is not None:
        return {"kind": "point", "point": tuple(float(v) for v in pts[i])}
    c = coords(size, step)
    lo, hi = c[0], c[-1]
    best = None
    for a in range(3):
        if layer is not None and a == layer[0]:
            continue  # square to the layer: not one of its lines
        u = np.zeros(3)
        u[a] = 1.0
        b = float(d @ u)
        if 1 - b * b < 1e-9:
            continue  # the line runs along the ray: seen end-on, a point
        bb, dd = [k for k in range(3) if k != a]
        if layer is None:
            gu, gv = np.meshgrid(c, c, indexing="ij")
            base = np.zeros((gu.size, 3))
            base[:, bb], base[:, dd] = gu.ravel(), gv.ravel()
        else:  # the layer's lines along a: the other in-layer axis varies, the layer's axis is its level
            free = bb if dd == layer[0] else dd
            base = np.zeros((len(c), 3))
            base[:, free] = c
            base[:, layer[0]] = layer[1]
        w0 = o - base
        dw, ew = w0 @ d, w0 @ u
        s = np.clip((ew - b * dw) / (1 - b * b), lo, hi)  # the line's parameter nearest the ray
        q = base + np.outer(s, u)
        dist, depth = _off_ray(q, o, d)
        j = _choose(dist, depth, tol)
        if j is not None and (best is None or dist[j] < best[0] - 1e-9 or
                              (abs(dist[j] - best[0]) < 0.35 * tol and depth[j] < best[1])):
            best = (dist[j], depth[j], a, q[j])
    if best is None:
        return None
    _, _, a, q = best
    s = q[a]
    k = int(np.clip(np.searchsorted(c, s), 1, len(c) - 1))
    return {"kind": "line", "point": tuple(float(v) for v in q), "axis": a,
            "ends": (float(c[k - 1]), float(c[k]))}


def parse_points(text):
    """'x y z; x y z; …' -> [(x, y, z), …]."""
    out = []
    for item in (text or "").split(";"):
        item = item.strip()
        if item:
            x, y, z = (float(v) for v in item.split())
            out.append((x, y, z))
    return out


def format_points(points):
    return "; ".join("%.9g %.9g %.9g" % tuple(p) for p in points)


def curve(points, kind="polyline", closed=False):
    """The 3D line's shape (a Part.Wire) through `points`, or None for fewer than two different points."""
    import FreeCAD as App
    import Part
    pts = []
    for p in points:
        v = App.Vector(*p)
        if not pts or (v - pts[-1]).Length > 1e-7:
            pts.append(v)
    if closed and len(pts) > 2 and (pts[0] - pts[-1]).Length < 1e-7:
        pts.pop()
    if len(pts) < 2:
        return None
    if kind == "polyline" or len(pts) == 2:
        return Part.makePolygon(pts + ([pts[0]] if closed and len(pts) > 2 else []))
    if kind == "spline":
        c = Part.BSplineCurve()
        if closed and len(pts) > 2:
            c.buildFromPoles(pts, True, min(3, len(pts) - 1))
        else:
            c.buildFromPoles(pts, False, min(3, len(pts) - 1))
        return Part.Wire([c.toShape()])
    if kind == "through":
        c = Part.BSplineCurve()
        c.interpolate(Points=pts, PeriodicFlag=bool(closed and len(pts) > 2))
        return Part.Wire([c.toShape()])
    raise ValueError("Unknown 3D line kind %r" % kind)
