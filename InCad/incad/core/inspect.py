"""Inspect (Inventor): Measure and Mass Properties. Read-only."""
import math


def _num(value, unit, digits=3):
    text = ("%.*f" % (digits, value)).rstrip("0").rstrip(".")
    return "%s %s" % (text, unit) if unit != "°" else text + "°"


_NOT_MEASURABLE = ("App::Origin", "App::Plane", "App::Line", "App::Point")


def _element(obj, sub):
    if obj.TypeId in _NOT_MEASURABLE or (not sub and obj.TypeId.startswith("PartDesign::") and
                                        obj.TypeId in ("PartDesign::Plane", "PartDesign::Line",
                                                       "PartDesign::Point")):
        raise ValueError("Select a face or an edge of the part (work and origin items have no size)")
    if not sub and obj.TypeId == "PartDesign::Body" and getattr(obj, "Tip", None) is not None:
        obj = obj.Tip  # the whole part: what it looks like now
    shape = obj.getSubObject(sub) if sub else getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        raise ValueError("Select a face or an edge of the part")
    return shape


MODES = ("auto", "distance", "angle", "length", "area")
PROMPTS = {"auto": "Select a face, an edge, or two items to measure between",
           "distance": "Select two faces, edges or points to measure the distance between",
           "angle": "Select two flat faces or straight edges to measure the angle between",
           "length": "Select edges: their total length (a loop) is measured",
           "area": "Select faces: their total area is measured"}


def measure(pairs, what="auto"):
    """Rows (label, text) for the selection. what: auto (as the selection suggests), distance, angle, length,
    area. A selection that doesn't fit the mode raises the mode's prompt."""
    if what not in MODES:
        raise ValueError("Unknown measure mode %r" % what)
    if not pairs:
        raise ValueError(PROMPTS[what])
    if what != "auto":
        return _measure_mode(pairs, what)
    shapes = [_element(o, s) for o, s in pairs]
    if len(shapes) == 1:
        sh = shapes[0]
        if sh.ShapeType in ("Solid", "Compound", "CompSolid", "Shell") and sh.Volume > 1e-9:
            bb = sh.BoundBox
            return [("Volume", _num(sh.Volume, "mm³")), ("Surface", _num(sh.Area, "mm²")),
                    ("Size", "%s × %s × %s" % (_num(bb.XLength, "mm"), _num(bb.YLength, "mm"), _num(bb.ZLength, "mm")))]
        if sh.ShapeType == "Face":
            return [("Area", _num(sh.Area, "mm²"))]
        if sh.ShapeType == "Edge":
            if sh.Curve.TypeId == "Part::GeomCircle":
                r = sh.Curve.Radius
                return [("Radius", _num(r, "mm")), ("Diameter", _num(2 * r, "mm"))]
            return [("Length", _num(sh.Length, "mm"))]
        raise ValueError("Select a face or an edge (or two items)")
    if len(shapes) == 2:
        rows = [("Distance", _num(shapes[0].distToShape(shapes[1])[0], "mm"))]
        a = _direction(shapes[0])
        b = _direction(shapes[1])
        if a is not None and b is not None:
            angle = math.degrees(a.getAngle(b))
            rows.append(("Angle", _num(min(angle, 180 - angle), "°")))
        return rows
    raise ValueError("Select one or two items")


def _measure_mode(pairs, what):
    shapes = [_element(o, s) for o, s in pairs]
    if what == "length":
        edges = [s for s in shapes if s.ShapeType == "Edge"]
        if not edges or len(edges) != len(shapes):
            raise ValueError(PROMPTS[what])
        rows = [("Length", _num(sum(e.Length for e in edges), "mm"))]
        if len(edges) > 1:
            rows.append(("Edges", str(len(edges))))
        elif edges[0].Curve.TypeId == "Part::GeomCircle":
            r = edges[0].Curve.Radius
            rows += [("Radius", _num(r, "mm")), ("Diameter", _num(2 * r, "mm"))]
        return rows
    if what == "area":
        faces = [s for s in shapes if s.ShapeType == "Face"]
        if not faces or len(faces) != len(shapes):
            raise ValueError(PROMPTS[what])
        rows = [("Area", _num(sum(f.Area for f in faces), "mm²"))]
        if len(faces) > 1:
            rows.append(("Faces", str(len(faces))))
        return rows
    if len(shapes) != 2:
        raise ValueError(PROMPTS[what])
    a, b = shapes
    if what == "distance":
        rows = [("Distance", _num(a.distToShape(b)[0], "mm"))]
        if a.ShapeType == "Vertex" and b.ShapeType == "Vertex":
            d = b.Point - a.Point
            rows += [("ΔX", _num(abs(d.x), "mm")), ("ΔY", _num(abs(d.y), "mm")), ("ΔZ", _num(abs(d.z), "mm"))]
        return rows
    da, db = _direction(a), _direction(b)
    if da is None or db is None:
        raise ValueError(PROMPTS[what])
    angle = math.degrees(da.getAngle(db))
    return [("Angle", _num(min(angle, 180 - angle), "°"))]


def _direction(shape):
    if shape.ShapeType == "Face" and shape.Surface.TypeId == "Part::GeomPlane":
        return shape.normalAt(0, 0)
    if shape.ShapeType == "Edge" and shape.Curve.TypeId == "Part::GeomLine":
        return shape.Curve.Direction
    return None


def mass_properties(body, density_g_cm3=1.24):
    shape = body.Shape
    if shape.isNull():
        raise ValueError("The part is empty")
    bb = shape.BoundBox
    mass_g = shape.Volume / 1000.0 * density_g_cm3
    return [("Volume", _num(shape.Volume, "mm³")), ("Surface area", _num(shape.Area, "mm²")),
            ("Mass", _num(mass_g, "g", 2)),
            ("Size", "%s × %s × %s mm" % tuple(_num(v, "mm").split()[0] for v in (bb.XLength, bb.YLength, bb.ZLength)))]
