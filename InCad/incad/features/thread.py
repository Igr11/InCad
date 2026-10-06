"""Thread (Inventor) = a hidden groove-profile sketch on the face's start edge (SectionOfRevolution: a plane
through the axis, x radial, y along the axis) + one PartDesign SubtractiveHelix. Real geometry for printing.

Standard, size, clearance, hand, start end and offset live on the helix (InCadThread, JSON) and regenerate the
profile on edit; the length (Distance mode) is a model parameter bound to Height."""
import json

import FreeCAD as App
import Part

from incad.features.common import Field, parse_picks, resolve, value_param, value_text
from incad.threads import profile, standards

TITLE = "Thread"
ICON = "thread"
TYPES = ("PartDesign::SubtractiveHelix",)
NEEDS_PROFILE = False
PROPS = {"length": "Height"}
PRESELECT = {"face": "cylinder"}
_STORE = "InCadThread"

FIELDS = (
    Field("face", "Face", "pick", pick="cylinder"),
    Field("standard", "Standard", "combo", tuple(standards.STANDARDS), "iso"),
    Field("size", "Size", "combo", (), ""),
    Field("custom_pitch", "Pitch", "value_length", default="1.5 mm", show_if=("standard", ("custom",))),
    Field("custom_angle", "Flank angle", "value_angle", default="60 °", show_if=("standard", ("custom",))),
    Field("custom_depth", "Depth", "value_length", default="0.9 mm", show_if=("standard", ("custom",))),
    Field("length_mode", "Length", "choice", (("full", "Full length"), ("distance", "Distance")), "full"),
    Field("length", "Distance", "value_length", default="10 mm", show_if=("length_mode", ("distance",))),
    Field("offset", "Offset", "value_length", default="0 mm"),
    Field("hand", "Direction", "choice", (("right", "Right hand"), ("left", "Left hand")), "right"),
    Field("clearance", "Print clearance", "value_length", default="0.2 mm"),
    Field("flip", "Start at other end", "bool", default=False),
)


def claims(feature):
    return hasattr(feature, _STORE)


def defaults(doc, body, profile_=None):
    from incad.core import prefs
    values = {f.key: f.default for f in FIELDS}
    values.update(face="", size="", clearance="%g mm" % prefs.thread_clearance(), internal=False)
    return values


def _mm(text, default=0.0):
    try:
        q = App.Units.Quantity(text or "")
        return q.Value if str(q.Unit) != str(App.Units.Quantity("1").Unit) else float(text)
    except Exception:
        return default


def _deg(text, default=60.0):
    try:
        return App.Units.Quantity((text or "").replace("°", " deg")).Value
    except Exception:
        return default


# ----- geometry of the picked face -----
def _face(doc, values):
    picks = parse_picks(doc, values.get("face"))
    if not picks:
        raise ValueError("Pick the cylindrical face to thread (a shaft or a hole)")
    obj, sub = resolve(*picks[0])
    face = obj.getSubObject(sub) if sub.startswith("Face") else None
    if face is None or face.Surface.TypeId != "Part::GeomCylinder":
        raise ValueError("Pick a cylindrical face (the outside of a shaft or the inside of a hole)")
    return obj, sub, face


def _geometry(obj, face, flip):
    """(internal, radius, start edge name, length along the axis) of a cylindrical face."""
    surf = face.Surface
    axis, centre = App.Vector(surf.Axis).normalize(), surf.Center
    u0, u1, v0, v1 = face.ParameterRange
    u, v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    p, n = face.valueAt(u, v), face.normalAt(u, v)
    radial = (p - centre) - axis * (p - centre).dot(axis)
    internal = n.dot(radial) < 0
    circles = [e for e in face.Edges if e.Curve.TypeId == "Part::GeomCircle"]
    if len(circles) < 2:
        raise ValueError("The face needs two round ends to thread")
    circles.sort(key=lambda e: (e.Curve.Center - centre).dot(axis))
    start, other = (circles[0], circles[-1]) if flip else (circles[-1], circles[0])
    name = next(("Edge%d" % (i + 1) for i, e in enumerate(obj.Shape.Edges) if e.isSame(start)), None)
    if name is None:
        raise ValueError("Could not find the end edge of that face")
    length = abs((other.Curve.Center - start.Curve.Center).dot(axis))
    return internal, surf.Radius, name, length, other.Curve.Center - start.Curve.Center


def _spec(values, diameter, internal, clearance):
    std = values.get("standard") or "iso"
    if std == "custom":
        return standards.spec("custom", "Custom", custom={
            "major": diameter if not internal else diameter + 2 * _mm(values.get("custom_depth"), 0.9) - clearance,
            "pitch": _mm(values.get("custom_pitch"), 1.5), "angle": _deg(values.get("custom_angle"), 60.0),
            "depth": _mm(values.get("custom_depth"), 0.9)})
    size = values.get("size") or ""
    if size not in standards.sizes(std):
        size = standards.suggest(std, diameter, internal, clearance)
    return standards.spec(std, size)


def options(key, values):
    if key == "size":
        std = values.get("standard") or "iso"
        return [(s, s) for s in standards.sizes(std)]
    return None


# ----- build -----
def _store(f, data):
    if not hasattr(f, _STORE):
        f.addProperty("App::PropertyString", _STORE, "InCad", "InCad thread settings")
        f.setPropertyStatus(_STORE, "Hidden")
    setattr(f, _STORE, json.dumps(data, sort_keys=True))


def _load(f):
    try:
        return json.loads(getattr(f, _STORE, "") or "{}")
    except ValueError:
        return {}


def _build(doc, body, f, values):
    obj, sub, face = _face(doc, values)
    internal, radius, edge, face_len, to_other = _geometry(obj, face, bool(values.get("flip")))
    clearance = _mm(values.get("clearance"), 0.2)
    spec = _spec(values, 2 * radius, internal, clearance)
    offset = _mm(values.get("offset"), 0.0)
    sk = f.Profile[0] if isinstance(f.Profile, (tuple, list)) and f.Profile else (f.Profile or None)
    if sk is None:
        sk = body.newObject("Sketcher::SketchObject", "ThreadProfile")
        f.Profile = sk
    sk.AttachmentSupport = [(obj, edge)]
    sk.MapMode = "SectionOfRevolution"
    sk.deleteAllGeometry()
    doc.recompute()
    ly = sk.getGlobalPlacement().Rotation.multVec(App.Vector(0, 1, 0))
    sign = 1.0 if to_other.dot(ly) > 0 else -1.0
    pts = [App.Vector(r, sign * (offset + z), 0) for r, z in profile.groove(spec, internal, clearance)]
    sk.addGeometry([Part.LineSegment(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))])
    sk.Visibility = False
    f.Refine = False  # probed: refining a helical cut corrupts the solid (wrong volume, still "valid")
    f.ReferenceAxis = (sk, ["V_Axis"])
    f.Mode = "pitch-height-angle"
    f.Pitch = spec.pitch
    f.Reversed = sign < 0
    f.LeftHanded = values.get("hand") == "left"
    f.Angle = -spec.taper if internal else spec.taper
    if values.get("length_mode") == "distance":
        value_param(doc, f, "Height", values.get("length") or "10 mm", "length")
    else:
        f.setExpression("Height", None)
        f.Height = max(face_len - offset, spec.pitch)
    _store(f, {"face": values.get("face"), "standard": spec.std, "size": spec.size, "flip": bool(values.get("flip")),
               "clearance": values.get("clearance") or "0.2 mm", "hand": values.get("hand") or "right",
               "offset": values.get("offset") or "0 mm", "length_mode": values.get("length_mode") or "full",
               "internal": internal, "custom_pitch": values.get("custom_pitch"),
               "custom_angle": values.get("custom_angle"), "custom_depth": values.get("custom_depth")})
    return f


def create(doc, body, profile_, values):
    _face(doc, values)  # refuse a wrong face before anything is made
    f = body.newObject("PartDesign::SubtractiveHelix", "Thread")
    _build(doc, body, f, values)
    body.Tip = f
    return f


def read(doc, f):
    data = _load(f)
    values = defaults(doc, None, None)
    values.update({k: v for k, v in data.items() if k in values or k == "internal"})
    if values.get("length_mode") == "distance":
        values["length"] = value_text(doc, f, "Height") or values["length"]
    return values


def update(doc, f, values):
    return _build(doc, f.getParentGeoFeatureGroup(), f, values)


def _pad_of(f):
    return f
