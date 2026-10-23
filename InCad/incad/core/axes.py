"""The axes of a component's round faces (the user: in an assembly every turned body and hole shows its axis, grey
dashed, to constrain to): one per axis line of a part's cylinders and cones (half way round or more) — a shaft, a bore, a countersink —
as long as those faces along it and a little past their ends. The face it stands for is what a click on it picks
(incad.ui.axis_lines): FreeCAD's joints put a round face's frame on its axis."""
import math

import FreeCAD as App

PAST = 0.15  # past the faces' ends, of the axis' length (at least MIN_PAST mm)
MIN_PAST = 2.0
_SEEN = {}  # (link, placement, shape hash) -> axes


def _round_axis(face):
    """(point, unit direction) of a cylinder or cone going at least half way round (a shaft, a bore — FreeCAD often
    cuts one in two halves —, a slot's round end), else None (a fillet strip)."""
    s = face.Surface
    if s.TypeId not in ("Part::GeomCylinder", "Part::GeomCone"):
        return None
    u0, u1 = face.ParameterRange[:2]
    if u1 - u0 < math.pi - 1e-6:
        return None
    d = App.Vector(s.Axis)
    if d.Length < 1e-12:
        return None
    d.normalize()
    return App.Vector(s.Apex if s.TypeId == "Part::GeomCone" else s.Center), d


def _on_axis_circle(edge, p, d):
    """A circle round the axis (p, d): what Insert takes for it."""
    try:
        c = edge.Curve
        if c.TypeId != "Part::GeomCircle":
            return False
        return abs(abs(App.Vector(c.Axis).normalize().dot(d)) - 1) < 1e-7 and \
            ((c.Center - p) - d * (c.Center - p).dot(d)).Length < 1e-5
    except Exception:
        return False


def axes(link):
    """[(start, end, face index (1-based, the largest face on it), [circular edge indices])] of the component in
    the assembly's coordinates; [] for one without a shape."""
    try:
        shape = link.Shape
    except Exception:
        return []
    if shape is None or shape.isNull():
        return []
    key = (link.Name, str(link.Placement), shape.hashCode())
    if key in _SEEN:
        return _SEEN[key]
    lines = []  # [point, direction, [(face index, face)]]
    for i, f in enumerate(shape.Faces):
        ax = _round_axis(f)
        if ax is None:
            continue
        p, d = ax
        for line in lines:
            q, e = line[0], line[1]
            if abs(abs(d.dot(e)) - 1) < 1e-7 and ((p - q) - e * (p - q).dot(e)).Length < 1e-5:
                line[2].append((i + 1, f))
                break
        else:
            lines.append([p, d, [(i + 1, f)]])
    out = []
    edges = shape.Edges
    for p, d, faces in lines:
        ts = []
        for _, f in faces:  # its corners; a seamless face has none: its box's corners then
            if f.Vertexes:
                ts += [(v.Point - p).dot(d) for v in f.Vertexes]
            else:
                b = f.BoundBox
                ts += [(App.Vector(x, y, z) - p).dot(d) for x in (b.XMin, b.XMax) for y in (b.YMin, b.YMax)
                       for z in (b.ZMin, b.ZMax)]
        lo, hi = (min(ts), max(ts)) if ts else (0.0, 0.0)
        past = max(MIN_PAST, PAST * (hi - lo))
        start, end = p + d * (lo - past), p + d * (hi + past)
        index, face = max(faces, key=lambda t: t[1].Area)
        circles = [k + 1 for k, e in enumerate(edges) if _on_axis_circle(e, p, d)]
        out.append((start, end, index, circles))
    if len(_SEEN) > 200:
        _SEEN.clear()
    _SEEN[key] = out
    return out
