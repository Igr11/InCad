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
    from incad.features.common import accepts
    picks = parse_picks(doc, values.get("face"))
    if not picks:
        raise ValueError("Pick the cylindrical face to thread (a shaft or a hole)")
    obj, sub = resolve(*picks[0])
    face = obj.getSubObject(sub) if sub.startswith("Face") else None
    if face is None or not accepts("cylinder", obj, sub):
        raise ValueError("Pick a full round cylindrical face (the outside of a shaft or the inside of a hole)")
    return obj, sub, face


def _is_free(solid, centre, outward, radial, radius):
    """No material just beyond this end (inside the thread's radius): a free end, not a shoulder or a floor."""
    eps = max(0.05, 0.01 * radius)
    probe = centre + outward * eps + radial * (0.5 * radius)
    return not solid.isInside(probe, 1e-7, True)


def _geometry(obj, face, flip):
    """Facts about a cylindrical face: internal?, radius, start edge name, length along the axis, vector to the
    far end, and whether the start / far end are free. The start is a free end (the tip of a shaft, the mouth of
    a hole); with both ends free, the one farther from the origin; "flip" takes the other end."""
    surf = face.Surface
    axis, centre = App.Vector(surf.Axis).normalize(), surf.Center
    u0, u1, v0, v1 = face.ParameterRange
    u, v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    p, n = face.valueAt(u, v), face.normalAt(u, v)
    radial = (p - centre) - axis * (p - centre).dot(axis)
    internal = n.dot(radial) < 0
    radial.normalize()
    circles = [e for e in face.Edges if e.Curve.TypeId == "Part::GeomCircle"]
    if len(circles) < 2:
        raise ValueError("The face needs two round ends to thread")
    circles.sort(key=lambda e: (e.Curve.Center - centre).dot(axis))
    ends = [circles[0], circles[-1]]
    free = []
    for e, other in ((ends[0], ends[1]), (ends[1], ends[0])):
        out = e.Curve.Center - other.Curve.Center
        out.normalize()
        free.append(_is_free(obj.Shape, e.Curve.Center, out, radial, surf.Radius))
    if free[0] != free[1]:
        pick = 0 if free[0] else 1
    else:
        pick = 0 if ends[0].Curve.Center.Length > ends[1].Curve.Center.Length else 1
    if flip:
        pick = 1 - pick
    start, other = ends[pick], ends[1 - pick]
    name = next(("Edge%d" % (i + 1) for i, e in enumerate(obj.Shape.Edges) if e.isSame(start)), None)
    if name is None:
        raise ValueError("Could not find the end edge of that face")
    length = abs((other.Curve.Center - start.Curve.Center).dot(axis))
    return internal, surf.Radius, name, length, other.Curve.Center - start.Curve.Center, free[pick], free[1 - pick]


def _fit(spec, internal, radius, clearance):
    """Check the size and clearance against the face; the run-out that opens the groove at the face."""
    R = spec.major / 2.0
    run = max(0.5, 0.3 * spec.pitch)
    if clearance < 0:
        raise ValueError("Print clearance can't be negative")
    if internal:
        r_min = R - spec.depth_int
        if radius > R + clearance / 2.0 - 0.5 * spec.depth_int:
            raise ValueError("This size is too small for the hole (Ø%.2f): pick a larger size" % (2 * radius))
        if radius < r_min - max(0.5, 0.5 * spec.depth_int):
            raise ValueError("This size is too large for the hole (Ø%.2f): pick a smaller size" % (2 * radius))
        return run + max(0.0, r_min - radius)
    root = R - spec.crest_drop - spec.depth - clearance / 2.0
    if root < 0.3 * R:
        raise ValueError("Print clearance is too large for this thread size")
    if radius <= root + 0.5 * spec.depth:
        raise ValueError("This size is too large for the shaft (Ø%.2f): pick a smaller size" % (2 * radius))
    if radius > R + max(0.5, 0.5 * spec.depth):
        raise ValueError("This size is too small for the shaft (Ø%.2f): pick a larger size" % (2 * radius))
    return run + max(0.0, radius - R)


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
        return [("", "Auto (from the face)")] + [(s, s) for s in standards.sizes(std)]
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
    internal, radius, edge, face_len, to_other, start_free, end_free = _geometry(obj, face, bool(values.get("flip")))
    clearance = _mm(values.get("clearance"), 0.2)
    spec = _spec(values, 2 * radius, internal, clearance)
    runout = _fit(spec, internal, radius, clearance)
    groove = profile.groove(spec, internal, clearance, runout)
    half = profile.max_width(groove) / 2.0
    offset = _mm(values.get("offset"), 0.0)
    # free end: the helix starts/ends a full pitch outside the part, so the thread runs out cleanly (as a die
    # cuts it); closed end (shoulder, floor): stop half a groove short, never cutting into it
    lead = (-spec.pitch if offset == 0 else 0.0) if start_free else half
    tail = spec.pitch if end_free else -half
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
    pts = [App.Vector(r, sign * (offset + lead + z), 0) for r, z in groove]
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
        f.Height = max(face_len - offset - lead + tail, spec.pitch)
    _store(f, {"face": values.get("face"), "standard": spec.std, "size": spec.size, "flip": bool(values.get("flip")),
               "clearance": values.get("clearance") or "0.2 mm", "hand": values.get("hand") or "right",
               "offset": values.get("offset") or "0 mm", "length_mode": values.get("length_mode") or "full",
               "internal": internal, "custom_pitch": values.get("custom_pitch"),
               "custom_angle": values.get("custom_angle"), "custom_depth": values.get("custom_depth")})
    doc.recompute()
    if f.Shape.isNull() or not f.Shape.isValid():
        raise ValueError("The thread can't be built with these values (check the size and the clearance)")
    return f


def create(doc, body, profile_, values):
    _face(doc, values)  # refuse a wrong face before anything is made
    tip = body.Tip
    f = body.newObject("PartDesign::SubtractiveHelix", "Thread")
    try:
        _build(doc, body, f, values)
    except Exception:
        sk = f.Profile[0] if isinstance(f.Profile, (tuple, list)) and f.Profile else None
        for obj in (f, sk):  # a refused thread leaves nothing behind
            if obj is not None and doc.getObject(obj.Name) is not None:
                body.removeObject(obj)
                doc.removeObject(obj.Name)
        body.Tip = tip
        doc.recompute()
        raise
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
