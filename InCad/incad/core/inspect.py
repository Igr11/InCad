"""Inspect (Inventor): Measure and Mass Properties. Read-only."""
import math


def _num(value, unit, digits=3):
    text = ("%.*f" % (digits, value)).rstrip("0").rstrip(".")
    return "%s %s" % (text, unit) if unit != "°" else text + "°"


def _element(obj, sub):
    return obj.getSubObject(sub) if sub else obj.Shape


def measure(pairs):
    if not pairs:
        raise ValueError("Select a face, an edge, or two items to measure between")
    shapes = [_element(o, s) for o, s in pairs]
    if len(shapes) == 1:
        sh = shapes[0]
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
