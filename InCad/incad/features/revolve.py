"""Revolve (Inventor) = PartDesign Revolution (Join) / Groove (Cut) around an axis chosen one of five ways: the
sketch's vertical or horizontal axis, a construction line of the sketch (listed), a line / axis / edge picked in
the view (a line of the sketch, an origin or work axis, a straight edge of the solid), or two points clicked on
the part — a hidden Work Axis through them, owned by the revolve (shown under it, deleted with it)."""
import json

import FreeCAD as App

from incad.features.common import Field, format_picks, parse_picks, profile_of, value_param, value_text

TITLE = "Revolve"
ICON = "revolve"
TYPES = ("PartDesign::Revolution", "PartDesign::Groove")
PROPS = {"angle": "Angle", "angle2": "Angle2"}
HELPER = "InCadHelperOf"      # on the Work Axis InCad makes for two points: the revolve it belongs to
POINTS = "InCadAxisPoints"    # on that axis: the two points as typed into the field ("x y z;x y z")
AXIS_MODES = (("V_Axis", "Sketch vertical"), ("H_Axis", "Sketch horizontal"),
              ("construction", "Construction line"), ("reference", "Line, axis or edge"),
              ("two_points", "Two points"))
FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut")), "join"),
    Field("axis_mode", "Axis", "combo", AXIS_MODES, "V_Axis"),
    Field("axis_construction", "Line", "combo", (), "", show_if=("axis_mode", ("construction",))),
    Field("axis_ref", "Pick", "pick", pick="axis", show_if=("axis_mode", ("reference",))),
    Field("axis_points", "Points", "pick", pick="two_points", show_if=("axis_mode", ("two_points",))),
    Field("extent", "Extents", "choice", (("full", "Full"), ("angle", "Angle"), ("two_angles", "Two angles")), "full"),
    Field("angle", "Angle", "value_angle", default="90 °", show_if=("extent", ("angle", "two_angles"))),
    Field("angle2", "Angle 2", "value_angle", default="90 °", show_if=("extent", ("two_angles",))),
    Field("flip", "Flip", "bool", default=False, show_if=("extent", ("angle",))),
)


# ----- construction lines of the sketch (FreeCAD names them Axis0, Axis1 … in sketch order) -----
def construction_lines(sk):
    """[(\"AxisN\", label)] for the sketch's construction lines."""
    out = []
    if sk is None:
        return out
    for i, g in enumerate(sk.Geometry):
        if g.TypeId != "Part::GeomLineSegment" or not sk.getConstruction(i):
            continue
        d = g.EndPoint - g.StartPoint
        length = d.Length
        if abs(d.x) < 1e-6 * max(1.0, length):
            direction = "vertical"
        elif abs(d.y) < 1e-6 * max(1.0, length):
            direction = "horizontal"
        else:
            import math
            direction = "at %.0f°" % (math.degrees(math.atan2(abs(d.y), abs(d.x))))
        n = len(out)
        out.append(("Axis%d" % n, "Line %d · %s, %s" % (n + 1, _mm(length), direction)))
    return out


def axis_name(sub):
    """FreeCAD stores the first construction line as 'Axis' (index 0 dropped): the listed name is 'Axis0'."""
    return "Axis0" if sub == "Axis" else sub


def _mm(length):
    text = "%.2f" % length
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return text + " mm"


def options(key, values, profile=None):
    if key == "axis_construction":
        return construction_lines(profile)
    return None


def defaults(doc, body, profile):
    values = {f.key: f.default for f in FIELDS}
    lines = construction_lines(profile)
    if lines:
        values["axis_construction"] = lines[0][0]
        if len(lines) == 1:  # Inventor's centerline: the one construction line is what it was drawn for
            values["axis_mode"] = "construction"
    return values


# ----- the axis -----
def parse_points(text):
    pts = []
    for item in (text or "").split(";"):
        parts = item.replace(",", " ").split()
        if len(parts) == 3:
            pts.append(App.Vector(*(float(v) for v in parts)))
    return pts


def format_points(points):
    return ";".join("%g %g %g" % (p.x, p.y, p.z) for p in points)


def axis_helper(f):
    body = f.getParentGeoFeatureGroup()
    for o in (body.Group if body is not None else []):
        if o.TypeId == "PartDesign::Line" and getattr(o, HELPER, None) == f.Name:
            return o
    return None


def _place_helper(doc, f, points):
    a, b = points
    d = b - a
    if d.Length < 1e-6:
        raise ValueError("The two points must be different")
    d.normalize()
    line = axis_helper(f)
    if line is None:
        body = f.getParentGeoFeatureGroup()
        line = doc.addObject("PartDesign::Line", "RevolveAxis")
        body.insertObject(line, f, False)  # before the revolve: a feature never references a later object
        line.Label = "Revolve axis"
        line.addProperty("App::PropertyString", HELPER, "InCad", "The revolve this axis belongs to")
        line.setPropertyStatus(HELPER, "Hidden")
        line.addProperty("App::PropertyString", POINTS, "InCad", "The two points the axis goes through")
        line.setPropertyStatus(POINTS, "Hidden")
        setattr(line, HELPER, f.Name)
    line.MapMode = "Deactivated"
    line.Placement = App.Placement(a, App.Rotation(App.Vector(0, 0, 1), d))  # a datum line runs along its Z
    setattr(line, POINTS, format_points(points))
    line.Visibility = False
    return line


def _drop_helper(doc, f):
    line = axis_helper(f)
    if line is not None:
        body = line.getParentGeoFeatureGroup()
        if body is not None:
            body.removeObject(line)
        doc.removeObject(line.Name)


def _axis(doc, f, values):
    mode = values.get("axis_mode") or "V_Axis"
    profile = profile_of(f)
    if mode in ("V_Axis", "H_Axis"):
        return profile, [mode]
    if mode == "construction":
        lines = construction_lines(profile)
        if not lines:
            raise ValueError("The sketch has no construction line: draw one (Construction) or choose another axis")
        wanted = values.get("axis_construction") or lines[0][0]
        if wanted not in [v for v, _ in lines]:
            wanted = lines[0][0]
        return profile, [wanted]
    if mode == "reference":
        pairs = parse_picks(doc, values.get("axis_ref"))
        if not pairs:
            raise ValueError("Pick a line of the sketch, an axis or a straight edge for the axis")
        obj, sub = pairs[0]
        return obj, [sub]
    if mode == "two_points":
        points = parse_points(values.get("axis_points"))
        if len(points) != 2:
            raise ValueError("Click two points for the axis")
        return _place_helper(doc, f, points), [""]
    raise ValueError("Unknown axis choice %r" % mode)


def _type(operation):
    return "PartDesign::Groove" if operation == "cut" else "PartDesign::Revolution"


def _apply(doc, f, values):
    f.ReferenceAxis = _axis(doc, f, values)
    if (values.get("axis_mode") or "V_Axis") != "two_points":
        _drop_helper(doc, f)
    extent = values.get("extent", "full")
    f.Type = "TwoAngles" if extent == "two_angles" else "Angle"
    f.Reversed = bool(values.get("flip")) and extent == "angle"
    if extent == "full":
        value_param(doc, f, "Angle", "360 °", "angle")
    else:
        value_param(doc, f, "Angle", values.get("angle") or "90 °", "angle")
    if extent == "two_angles":
        value_param(doc, f, "Angle2", values.get("angle2") or "90 °", "angle")


def create(doc, body, profile, values):
    f = body.newObject(_type(values.get("operation", "join")), "Revolve")
    f.Profile = profile
    _apply(doc, f, values)
    return f


def read(doc, f):
    angle = value_text(doc, f, "Angle") or "90 °"
    extent = "two_angles" if f.Type == "TwoAngles" else ("full" if abs(f.Angle.Value - 360) < 1e-9 else "angle")
    values = {"operation": "cut" if f.TypeId == "PartDesign::Groove" else "join", "extent": extent,
              "angle": angle, "angle2": value_text(doc, f, "Angle2") or "90 °", "flip": bool(f.Reversed),
              "axis_mode": "V_Axis", "axis_construction": "", "axis_ref": "", "axis_points": ""}
    ref = f.ReferenceAxis
    obj, sub = (ref[0], (ref[1][0] if ref[1] else "")) if ref else (None, "")
    profile = profile_of(f)
    lines = construction_lines(profile)
    if lines:
        values["axis_construction"] = lines[0][0]
    if obj is None:
        pass
    elif obj is profile and sub in ("V_Axis", "H_Axis"):
        values["axis_mode"] = sub
    elif obj is profile and sub.startswith("Axis"):
        values.update(axis_mode="construction", axis_construction=axis_name(sub))
    elif getattr(obj, HELPER, None) == f.Name:
        values.update(axis_mode="two_points", axis_points=getattr(obj, POINTS, ""))
    else:
        values.update(axis_mode="reference", axis_ref=format_picks([(obj, sub)]))
    return values


def update(doc, f, values):
    if f.TypeId != _type(values.get("operation", "join")):
        from incad.features import extrude
        helper = axis_helper(f)
        f = extrude._replace(doc, f, _type(values.get("operation", "join")))
        if helper is not None:
            setattr(helper, HELPER, f.Name)  # the axis follows the re-made feature
    _apply(doc, f, values)
    return f


def _pad_of(f):
    return f
