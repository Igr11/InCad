"""Full round fillet (Inventor's Full Round): a flat face between two parallel faces — the end of a bar, the narrow
side of a plate — replaced by a half cylinder that runs on smoothly into both: as two fillets meeting in the middle
of the face. The round goes across the narrower pair of the face's neighbours (a plate's end rounds across its
thickness)."""
import math

import FreeCAD as App
import Part

FACE_MSG = "Pick a flat face between two parallel faces (the end of a bar or the side of a plate)"
EDGES_MSG = "Pick the two parallel edges of one flat face to round off between (the end of a bar or a plate)"
_TOL = 1e-6


def _unit(v):
    v = App.Vector(v)
    v.normalize()
    return v


def _normal(face):
    u, v = face.Surface.parameter(face.CenterOfMass)[:2]
    return _unit(face.normalAt(u, v))


def _neighbours(solid, face):
    out = []
    for e in face.Edges:
        try:
            found = solid.ancestorsOfType(e, Part.Face)
        except Exception:
            found = [f for f in solid.Faces if any(x.isSame(e) for x in f.Edges)]
        out += [f for f in found if not f.isSame(face) and not any(f.isSame(g) for g in out)]
    return out


def sides(solid, face, across=None):
    """(the two side faces, the direction across from the first to the second, the width between them) of the
    pair of parallel flat faces beside `face`, both square to it: the one running across `across` when given, else
    the narrowest; ValueError when there is none."""
    if face.Surface.TypeId != "Part::GeomPlane":
        raise ValueError(FACE_MSG)
    n = _normal(face)
    flat = [g for g in _neighbours(solid, face) if g.Surface.TypeId == "Part::GeomPlane"
            and abs(_normal(g).dot(n)) < 1e-6]
    best = None
    for i, a in enumerate(flat):
        na = _normal(a)
        for b in flat[i + 1:]:
            if na.dot(_normal(b)) > -1 + 1e-6:
                continue  # not facing away from each other: not the two sides of a bar
            width = abs((b.CenterOfMass - a.CenterOfMass).dot(na))
            if across is not None and abs(abs(na.dot(_unit(across))) - 1) > 1e-6:
                continue
            if width > _TOL and (best is None or width < best[2]):
                best = ((a, b), na * -1.0, width)  # a's outward normal points away from b
    if best is None:
        raise ValueError(FACE_MSG)
    return best


def between(solid, e1, e2):
    """(the flat face two picked edges bound, the direction across from one to the other) for a full round
    between them; ValueError unless they are two parallel straight edges of one flat face."""
    for e in (e1, e2):
        if type(e.Curve).__name__ not in ("Line", "LineSegment"):
            raise ValueError(EDGES_MSG)
    d1 = _unit(e1.Vertexes[-1].Point - e1.Vertexes[0].Point)
    d2 = _unit(e2.Vertexes[-1].Point - e2.Vertexes[0].Point)
    if abs(abs(d1.dot(d2)) - 1) > 1e-6:
        raise ValueError(EDGES_MSG)
    faces = []
    for e in (e1, e2):
        try:
            faces.append(solid.ancestorsOfType(e, Part.Face))
        except Exception:
            faces.append([f for f in solid.Faces if any(x.isSame(e) for x in f.Edges)])
    common = [f for f in faces[0] if any(f.isSame(g) for g in faces[1]) and f.Surface.TypeId == "Part::GeomPlane"]
    if not common:
        raise ValueError(EDGES_MSG)
    gap = e2.Vertexes[0].Point - e1.Vertexes[0].Point
    across = gap - d1 * gap.dot(d1)
    if across.Length < _TOL:
        raise ValueError(EDGES_MSG)
    return common[0], _unit(across)


def tool(solid, face, across=None):
    """What a full round takes off: between the side faces, from the face down half their distance, everything
    outside the half cylinder whose axis runs along the face midway between the sides."""
    (a, b), m, width = sides(solid, face, across)
    n = _normal(face)
    along = _unit(n.cross(m))
    r = width / 2.0
    plane_d = face.CenterOfMass.dot(n)
    across_a = a.CenterOfMass.dot(m)
    lo = min(v.Point.dot(along) for v in face.Vertexes)
    hi = max(v.Point.dot(along) for v in face.Vertexes)
    if hi - lo <= _TOL:
        raise ValueError(FACE_MSG)
    mid = across_a + r
    origin = along * lo + m * mid + n * plane_d  # on the face's plane, midway across, at its near end

    def at(x, y):  # across x, out of the face y (0 = the face's plane)
        return origin + m * x + n * y

    square = Part.Face(Part.makePolygon([at(-r, 0), at(r, 0), at(r, -r), at(-r, -r), at(-r, 0)]))
    disk = Part.Face(Part.Wire(Part.makeCircle(r, at(0, -r), along)))
    section = square.cut(disk)
    return section.extrude(along * (hi - lo))


def apply(shape, face, across=None):
    """The part with `face` rounded off full (across `across`: from one picked edge towards the other)."""
    cut = tool(shape, face, across)
    before = len(shape.Solids)
    result = shape.cut(cut).removeSplitter()
    if not result.isValid() or len(result.Solids) != before or result.Volume >= shape.Volume - 1e-9:
        raise ValueError("The face could not be rounded off: is it the end of a bar, square to its sides?")
    return result
