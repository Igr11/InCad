"""Thread (Inventor) = a hidden groove-profile sketch on the face's start edge (SectionOfRevolution: a plane
through the axis, x radial, y along the axis) + one PartDesign SubtractiveHelix. Real geometry for printing.

Standard, size, clearance, hand, start end and offset live on the helix (InCadThread, JSON) and regenerate the
profile on edit; the length (Distance mode) is a model parameter bound to Height."""
import dataclasses
import json

import FreeCAD as App
import Part

from incad.features.common import Field, parse_picks, resolve, value_param, value_text
from incad.threads import profile, standards
from incad.core import safe

TITLE = "Thread"
ICON = "thread"
TYPES = ("PartDesign::SubtractiveHelix",)
NEEDS_PROFILE = False
PROPS = {"length": "Height"}
PRESELECT = {"face": "cylinder"}
SOLID_PICKS = True  # its picks are on the part: a sketch line over an edge stands for that edge
_STORE = "InCadThread"

FIELDS = (
    Field("face", "Face", "pick", pick="cylinder"),
    Field("start_face", "Start face", "pick", pick="plane"),
    Field("offset", "Offset", "value_length", default="0 mm"),
    Field("length_mode", "Length", "choice", (("full", "Full length"), ("distance", "Distance")), "full"),
    Field("length", "Distance", "value_length", default="10 mm", show_if=("length_mode", ("distance",))),
    Field("flip", "Flip direction", "bool", default=False),
    Field("standard", "Standard", "combo", tuple(standards.STANDARDS), "iso"),
    Field("size", "Size", "combo", (), ""),
    Field("custom_pitch", "Pitch", "value_length", default="1.5 mm", show_if=("standard", ("custom",))),
    Field("custom_angle", "Flank angle", "value_angle", default="60 °", show_if=("standard", ("custom",))),
    Field("custom_depth", "Depth", "value_length", default="0.9 mm", show_if=("standard", ("custom",))),
    Field("hand", "Hand", "choice", (("right", "Right hand"), ("left", "Left hand")), "right"),
    Field("chamfer", "Chamfer", "choice", (("none", "None"), ("start", "Start"), ("both", "Both ends")), "none"),
    Field("chamfer_size", "Chamfer size", "value_length", default="1 mm", show_if=("chamfer", ("start", "both"))),
    Field("clearance", "Print clearance (on diameter)", "value_length", default="0.2 mm"),
)


def claims(feature):
    return hasattr(feature, _STORE)


def default_clearance(std):
    """The print clearance a thread of this standard starts with (mm): more for print-friendly threads."""
    from incad.core import prefs
    return standards.default_clearance(std, prefs.thread_clearance())


def defaults(doc, body, profile_=None):
    values = {f.key: f.default for f in FIELDS}
    values.update(face="", start_face="", size="", internal=False)
    values["clearance"] = "%g mm" % default_clearance(values.get("standard"))
    return values


def follow(before, values):
    """Dialog values that follow a change: a new standard brings its own print clearance, unless the clearance was
    typed (it is no longer the old standard's default)."""
    old, new = before.get("standard"), values.get("standard")
    if old == new or old is None:
        return {}
    was = _mm(before.get("clearance"), None)
    if was is None or abs(was - default_clearance(old)) > 1e-9:
        return {}
    return {"clearance": "%g mm" % default_clearance(new)}


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


def _lead_in_faces(solid, edge):
    """The chamfer, countersink or round that meets the face at this end: the entrance a bolt or a nut goes in from."""
    return [f for f in solid.Faces
            if f.Surface.TypeId in ("Part::GeomCone", "Part::GeomToroid") and any(e.isSame(edge) for e in f.Edges)]


def _is_lead_in(solid, edge):
    return bool(_lead_in_faces(solid, edge))


def _is_free(solid, edge, outward, radial, radius):
    """No material just beyond this end (inside the thread's radius): a free end, not a shoulder or a floor.
    A chamfered end is probed past its chamfer (next to the chamfer the part is still solid)."""
    centre = edge.Curve.Center
    eps = max(0.05, 0.01 * radius)
    past = max([0.0] + [(p - centre).dot(outward) for f in _lead_in_faces(solid, edge) for e in f.Edges
                        for p in e.discretize(8)])
    probe = centre + outward * (past + eps) + radial * (0.5 * radius)
    return not solid.isInside(probe, 1e-7, True)


def _plane_of(doc, text):
    """(point, normal) of a picked flat face or plane, or None."""
    picks = parse_picks(doc, text)
    if not picks:
        return None
    o, sub = resolve(*picks[0])
    shape = o.getSubObject(sub) if sub else (o.Shape.Faces[0] if getattr(o, "Shape", None) and o.Shape.Faces else None)
    if shape is None or shape.ShapeType != "Face" or shape.Surface.TypeId != "Part::GeomPlane":
        raise ValueError("The start face must be flat (a face or a work plane)")
    return shape.Surface.Position, shape.normalAt(0, 0)


def _geometry(obj, face, flip, start_plane=None):
    """Facts about a cylindrical face: internal?, radius, start edge name, length along the axis, vector to the
    far end, and whether the start / far end are free. The start is a free end (the tip of a shaft, the mouth of
    a hole); with both ends free, the chamfered (or rounded) one, else the one farther from the origin; "flip"
    takes the other end."""
    surf = face.Surface
    axis, centre = App.Vector(surf.Axis).normalize(), surf.Center
    u0, u1, v0, v1 = face.ParameterRange
    u, v = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    p, n = face.valueAt(u, v), face.normalAt(u, v)
    radial = (p - centre) - axis * (p - centre).dot(axis)
    internal = n.dot(radial) < 0
    radial.normalize()
    circles = [e for e in face.Edges if safe.curve_type(e) == "Part::GeomCircle"]
    if len(circles) < 2:
        raise ValueError("The face needs two round ends to thread")
    circles.sort(key=lambda e: (e.Curve.Center - centre).dot(axis))
    ends = [circles[0], circles[-1]]
    free = []
    for e, other in ((ends[0], ends[1]), (ends[1], ends[0])):
        out = e.Curve.Center - other.Curve.Center
        out.normalize()
        free.append(_is_free(obj.Shape, e, out, radial, surf.Radius))
    if start_plane is not None:  # the picked start face names the end
        point, normal = start_plane
        def gap(e):  # a chamfered mouth: the face's end edge lies behind the end face, by the chamfer's depth
            out = e.Curve.Center - (ends[1] if e is ends[0] else ends[0]).Curve.Center
            out.normalize()
            depth = max([0.0] + [(p - e.Curve.Center).dot(out) for f in _lead_in_faces(obj.Shape, e)
                                 for x in f.Edges for p in x.discretize(8)])
            return abs(abs((e.Curve.Center - point).dot(normal)) - depth)
        on = [i for i, e in enumerate(ends) if gap(e) < 1e-4]
        if not on:
            raise ValueError("The start face must be at one end of the threaded face")
        pick = on[0]
    elif free[0] != free[1]:
        pick = 0 if free[0] else 1
    elif free[0] and _is_lead_in(obj.Shape, ends[0]) != _is_lead_in(obj.Shape, ends[1]):
        pick = 0 if _is_lead_in(obj.Shape, ends[0]) else 1  # both open (a through hole, a loose rod)
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


_PREP_TOL = 0.05  # mm (radial): a hole this close to the tap size is threaded as it is
_FIN_TOL = 0.005  # mm (radial): any fin taller than this is turned (bored) away


def _fit(spec, internal, radius, clearance):
    """Check the size and clearance against the face. Returns the run-out that opens the groove at the face and
    the radius the thread works on: a hole off the size's tap diameter is filled or bored to it first (M3 or M4
    in a Ø3 hole), so the thread is always full and has no hair-thin rings."""
    R = spec.major / 2.0
    run = max(0.5, 0.3 * spec.pitch)
    if clearance < 0:
        raise ValueError("Print clearance can't be negative")
    if internal:
        r_min = R - spec.depth_int
        tap = standards.bore_diameter(spec, clearance) / 2.0
        if spec.taper:  # a tapered pipe thread is cut into the hole as it is
            if radius > R + clearance / 2.0 - 0.5 * spec.depth_int:
                raise ValueError("This size is too small for the hole (Ø%.2f): pick a larger size" % (2 * radius))
            if radius < r_min - max(0.5, 0.5 * spec.depth_int):
                raise ValueError("This size is too large for the hole (Ø%.2f): pick a smaller size" % (2 * radius))
            return run + max(0.0, r_min - radius), radius
        if abs(radius - tap) > max(1.0, 0.5 * radius):
            raise ValueError("This size is too %s for the hole (Ø%.2f): pick a %s size" % (
                ("small", 2 * radius, "larger") if tap < radius else ("large", 2 * radius, "smaller")))
        hole = tap if abs(radius - tap) > _PREP_TOL else radius
        crest = profile.knee(spec, True, clearance)  # below it a hair-thin fin would stay on every crest
        if crest > hole + _FIN_TOL:
            hole = crest
        return run + max(0.0, r_min - hole), hole
    root = R - spec.crest_drop - spec.depth - clearance / 2.0
    if root < 0.3 * R:
        raise ValueError("Print clearance is too large for this thread size")
    if radius <= root + 0.5 * spec.depth:
        raise ValueError("This size is too large for the shaft (Ø%.2f): pick a smaller size" % (2 * radius))
    if radius > R + max(0.5, 0.5 * spec.depth):
        raise ValueError("This size is too small for the shaft (Ø%.2f): pick a larger size" % (2 * radius))
    crest = profile.knee(spec, False, clearance)  # above it a hair-thin fin would stay on every crest
    rod = crest if radius > crest + _FIN_TOL and not spec.taper else radius
    return run + max(0.0, rod - R), rod


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
    spec = standards.spec(std, size)
    slack = 2 * max(0.5, 0.5 * spec.depth)  # the same allowance _fit gives (a bigger gap is 'pick a larger size')
    if not internal and not spec.taper and spec.major + 0.02 < diameter <= spec.major + slack:
        # a shaft a little larger than the nominal (Ø4.5 with an M4): the groove cut for the nominal diameter would
        # leave hair-thin ridges above it, so the profile follows the real diameter (same pitch, depth and angle)
        spec = dataclasses.replace(spec, major=diameter)
    return spec


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


def _start_face_on(doc, f, obj, text):
    """A start face picked on the thread or on one of its helpers (ThreadFill is what the view shows) named on
    the threaded feature instead: the helpers come and go with the size."""
    picks = parse_picks(doc, text)
    if not picks:
        return text
    o, sub = resolve(*picks[0])
    if o is not f and getattr(o, HELPER, None) != f.Name or not sub.startswith("Face"):
        return text
    plane = o.getSubObject(sub)
    if plane.Surface.TypeId != "Part::GeomPlane":
        return text
    n = plane.normalAt(0, 0)
    for i, fc in enumerate(obj.Shape.Faces):
        if fc.Surface.TypeId == "Part::GeomPlane" and abs(abs(fc.normalAt(0, 0).dot(n)) - 1) < 1e-7 \
                and abs((fc.Surface.Position - plane.Surface.Position).dot(n)) < 1e-6:
            return "%s:Face%d" % (obj.Name, i + 1)
    return text


def _is_piece(doc, o):
    """A thread or something InCad made for one (its fill, bore, chamfer)."""
    if o is None:
        return False
    if claims(o):
        return True
    owner = getattr(o, HELPER, None)
    return bool(owner) and doc.getObject(owner) is not None and claims(doc.getObject(owner))


def _same_face(base, face):
    """The name of the face of `base` that `face` is part of (same surface, a point of it lies on it), or None."""
    u0, u1, v0, v1 = face.ParameterRange
    point = Part.Vertex(face.valueAt((u0 + u1) / 2.0, (v0 + v1) / 2.0))
    for i, f in enumerate(base.Shape.Faces):
        if f.Surface.TypeId != face.Surface.TypeId:
            continue
        if f.Surface.TypeId == "Part::GeomCylinder":
            a, b = App.Vector(f.Surface.Axis), App.Vector(face.Surface.Axis)
            if abs(f.Surface.Radius - face.Surface.Radius) > 1e-6 or abs(abs(a.normalize().dot(b.normalize())) - 1) > 1e-7:
                continue
        if f.distToShape(point)[0] < 1e-6:
            return "Face%d" % (i + 1)
    return None


def rehome(doc, values):
    """Faces picked on a thread or on its fill / chamfer (the tip when the next hole is threaded) named on the
    feature below the threads: a thread hung on another thread's edges broke when that one was suppressed."""
    out = dict(values)
    for key in ("face", "start_face"):
        picks = parse_picks(doc, out.get(key))
        if not picks:
            continue
        o, sub = resolve(*picks[0])
        if not sub.startswith("Face") or not _is_piece(doc, o):
            continue
        base = o
        while base is not None and _is_piece(doc, base):
            base = base.BaseFeature
        name = _same_face(base, o.getSubObject(sub)) if base is not None else None
        if name:
            out[key] = "%s:%s" % (base.Name, name)
    return out


def repair(doc):
    """Threads an older InCad hung on another thread (their sketches attached to it) are rebuilt on the feature
    below the threads. Returns their names."""
    fixed = []
    for t in [o for o in doc.Objects if claims(o) and not getattr(o, HELPER, None)]:
        sketches = [x.Profile[0] for x in [t] + helpers_of(t)
                    if isinstance(x.Profile, (tuple, list)) and x.Profile]
        if any(_is_piece(doc, a) and a is not t for sk in sketches for a, _ in sk.AttachmentSupport):
            update(doc, t, read(doc, t))
            fixed.append(t.Name)
    return fixed


def _build(doc, body, f, values):
    values = rehome(doc, values)
    obj, sub, face = _face(doc, values)
    if values.get("start_face"):
        values = dict(values, start_face=_start_face_on(doc, f, obj, values.get("start_face")))
    internal, radius, edge, face_len, to_other, start_free, end_free = _geometry(
        obj, face, bool(values.get("flip")), _plane_of(doc, values.get("start_face")))
    clearance = _mm(values.get("clearance"), 0.2)
    spec = _spec(values, 2 * radius, internal, clearance)
    runout, hole = _fit(spec, internal, radius, clearance)
    groove = profile.groove(spec, internal, clearance, runout)
    half = profile.max_width(groove) / 2.0
    offset = _mm(values.get("offset"), 0.0)
    # free end: the helix starts/ends a full pitch outside the part, so the thread runs out cleanly (as a die
    # cuts it); closed end (shoulder, floor): stop half a groove short, never cutting into it
    lead = (-spec.pitch if offset == 0 else half) if start_free else half
    tail = spec.pitch if end_free else -half
    sk = f.Profile[0] if isinstance(f.Profile, (tuple, list)) and f.Profile else (f.Profile or None)
    fresh = sk is None
    if fresh:
        sk = body.newObject("Sketcher::SketchObject", "ThreadProfile")
    sk.AttachmentSupport = [(obj, edge)]
    sk.MapMode = "SectionOfRevolution"
    sk.deleteAllGeometry()
    sk.recompute()  # the sketch alone: the helix is never recomputed with an empty profile ("Linked shape is empty")
    ly = sk.getGlobalPlacement().Rotation.multVec(App.Vector(0, 1, 0))
    sign = 1.0 if to_other.dot(ly) > 0 else -1.0
    pts = [App.Vector(r, sign * (offset + lead + z), 0) for r, z in groove]
    sk.addGeometry([Part.LineSegment(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))])
    sk.Visibility = False
    if fresh:
        f.Profile = sk
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
    expr = dict(f.ExpressionEngine).get("Height")
    height = f.evalExpression(expr).Value if expr else f.Height.Value
    _, reaches = _prep(doc, body, f, obj, edge, radius, hole, sign, offset + lead, offset + lead + height,
                       face_len, start_free, end_free, internal, spec.pitch)
    radii = tuple(hole if r else radius for r in reaches)  # the part's radius at each end
    chamfer = _chamfer(doc, body, f, obj, edge, internal, radii, sign, face_len, start_free, end_free,
                       values.get("chamfer") or "none", _mm(values.get("chamfer_size"), 1.0))
    _store(f, {"face": values.get("face"), "start_face": values.get("start_face") or "", "standard": spec.std, "size": spec.size, "flip": bool(values.get("flip")),
               "chamfer": values.get("chamfer") or "none", "chamfer_size": values.get("chamfer_size") or "1 mm",
               "chamfer_feature": chamfer.Name if chamfer is not None else "",
               "clearance": values.get("clearance") or "0.2 mm", "hand": values.get("hand") or "right",
               "offset": values.get("offset") or "0 mm", "length_mode": values.get("length_mode") or "full",
               "internal": internal, "custom_pitch": values.get("custom_pitch"),
               "custom_angle": values.get("custom_angle"), "custom_depth": values.get("custom_depth")})
    doc.recompute()
    if f.Shape.isNull() or not f.Shape.isValid():
        raise ValueError("The thread can't be built with these values (check the size and the clearance)")
    return f


HELPER = "InCadHelperOf"  # on objects InCad makes for a feature (the thread's chamfer): shown under it, deleted with it
ROLE = "InCadHelperRole"  # "prep" (fill / bore before the thread); none = the chamfer after it


def helpers_of(f):
    body = f.getParentGeoFeatureGroup()
    return [o for o in (body.Group if body is not None else []) if getattr(o, HELPER, None) == f.Name]


def _role(g):
    return getattr(g, ROLE, "") or "chamfer"


def _remove_helpers(doc, body, f, role=None):
    for g in helpers_of(f):
        if role is not None and _role(g) != role:
            continue
        prof = g.Profile[0] if isinstance(g.Profile, (tuple, list)) and g.Profile else None
        if body.Tip is g:
            body.Tip = g.BaseFeature if g.BaseFeature is not None else f
        for o in (g, prof):
            if o is not None and doc.getObject(o.Name) is not None:
                body.removeObject(o)
                doc.removeObject(o.Name)


def _chamfer(doc, body, f, obj, edge, internal, radii, sign, face_len, start_free, end_free, mode, size):
    """A 45° lead-in chamfer at the free end(s) of the threaded face: a revolve cut (Groove) of a triangle on the
    thread's own section plane, so it needs no face names and the thread cuts through it. None when there is
    nothing to chamfer (no free end asked for)."""
    ends = []
    if mode in ("start", "both") and start_free:
        ends.append((0.0, 1.0, radii[0]))
    if mode == "both" and end_free:
        ends.append((face_len, -1.0, radii[1]))
    if not ends or size <= 0:
        _remove_helpers(doc, body, f, "chamfer")
        return None
    existing = [h for h in helpers_of(f) if _role(h) == "chamfer"]
    g = existing[0] if existing else None
    sk = g.Profile[0] if g is not None and isinstance(g.Profile, (tuple, list)) and g.Profile else None
    old_tip = body.Tip
    if g is None:
        body.Tip = f  # the chamfer goes right after its thread
        sk = body.newObject("Sketcher::SketchObject", "ThreadChamferProfile")
    sk.AttachmentSupport = [(obj, edge)]
    sk.MapMode = "SectionOfRevolution"
    sk.deleteAllGeometry()
    sk.recompute()  # the sketch alone: no feature is recomputed with an empty profile
    inward = size if internal else -size  # the end face is inside the shaft, outside the hole
    for at, into, radius in ends:
        y0 = sign * at
        pts = [App.Vector(radius, y0, 0), App.Vector(radius + inward, y0, 0), App.Vector(radius, y0 + sign * into * size, 0)]
        sk.addGeometry([Part.LineSegment(pts[i], pts[(i + 1) % 3]) for i in range(3)])
    sk.Visibility = False
    if g is None:
        g = body.newObject("PartDesign::Groove", "ThreadChamfer")
        g.addProperty("App::PropertyString", HELPER, "InCad", "The thread this chamfer belongs to")
        g.setPropertyStatus(HELPER, "Hidden")
        setattr(g, HELPER, f.Name)
        g.Profile = sk
        g.Angle = 360.0
        body.Tip = g if old_tip is f else old_tip
    g.ReferenceAxis = (sk, ["V_Axis"])
    doc.recompute()
    if g.Shape.isNull() or not g.Shape.isValid():
        raise ValueError("The chamfer can't be built with that size")
    return g


def _prep(doc, body, f, obj, edge, radius, hole, sign, a0, a1, face_len, start_free, end_free, internal=True,
          pitch=0.0):
    """Fill the hole (a Revolution) or bore it out (a Groove) to the thread's tap radius along the threaded span,
    right before the thread; removed when the hole already fits. (helper or None, (reaches the start, reaches
    the end)): a chamfer at an end the helper does not reach starts from the part's own radius."""
    existing = [h for h in helpers_of(f) if _role(h) == "prep"]
    adds = hole < radius if internal else hole > radius  # a hole filled in / a rod built up; else cut
    want = None if abs(hole - radius) < 1e-9 else ("PartDesign::Revolution" if adds else "PartDesign::Groove")
    if existing and (want is None or existing[0].TypeId != want):
        _remove_helpers(doc, body, f, "prep")
        existing = []
    if want is None:
        return None, (False, False)
    g = existing[0] if existing else None
    sk = (g.Profile[0] if isinstance(g.Profile, (tuple, list)) else g.Profile) if g is not None else \
        body.newObject("Sketcher::SketchObject", "ThreadPrepProfile")
    sk.AttachmentSupport = [(obj, edge)]
    sk.MapMode = "SectionOfRevolution"
    sk.deleteAllGeometry()
    sk.recompute()  # placed (the walls are sampled in its frame); no feature is recomputed with an empty profile
    lo, hi = (hole, radius + 0.02) if hole < radius else (radius - 0.02, hole)
    if want == "PartDesign::Revolution":  # new material only where the hole has a wall all round, joined to it
        spans = _walled(obj.Shape, sk.getGlobalPlacement(), sign, radius, max(a0, 0.0), min(a1, face_len))
    else:  # a cut may run past a free end, so the mouth opens cleanly; at a closed end (a shoulder) the thread's
        # last turn reaches it, so the cut does too (never into it)
        b0 = -0.2 if a0 <= 0.0 and start_free else 0.0 if a0 <= pitch else max(a0, 0.0)
        b1 = face_len + 0.2 if a1 >= face_len and end_free else face_len if a1 >= face_len - pitch else \
            min(a1, face_len)
        spans = [(b0, b1)]
    spans = [(b0, b1) for b0, b1 in spans if b1 - b0 > 1e-3]
    if not spans:
        if g is None:
            doc.removeObject(sk.Name)
        _remove_helpers(doc, body, f, "prep")
        return None, (False, False)
    if g is None:
        g = doc.addObject(want, "ThreadFill" if want == "PartDesign::Revolution" else
                          "ThreadBore" if internal else "ThreadTrim")
        base = f.BaseFeature
        body.insertObject(g, f, False)  # right before the thread, which cuts the filled / bored hole
        g.BaseFeature = base
        f.BaseFeature = g
        for prop, text in ((HELPER, "The thread this belongs to"), (ROLE, "What it does for the thread")):
            g.addProperty("App::PropertyString", prop, "InCad", text)
            g.setPropertyStatus(prop, "Hidden")
        setattr(g, HELPER, f.Name)
        setattr(g, ROLE, "prep")
        g.Profile = sk
        g.Angle = 360.0
        g.Refine = False
    for b0, b1 in spans:
        pts = [App.Vector(lo, sign * b0, 0), App.Vector(hi, sign * b0, 0), App.Vector(hi, sign * b1, 0),
               App.Vector(lo, sign * b1, 0)]
        sk.addGeometry([Part.LineSegment(pts[i], pts[(i + 1) % 4]) for i in range(4)])
    sk.Visibility = False
    g.ReferenceAxis = (sk, ["V_Axis"])
    g.Visibility = False
    return g, (any(b0 <= 1e-6 for b0, _ in spans), any(b1 >= face_len - 1e-6 for _, b1 in spans))


def _walled(solid, placement, sign, radius, a0, a1, angles=12):
    """The stretches of [a0, a1] along the hole where it has material all round just outside its wall (a crossing
    bore or a slot opens a window: no fill there, it would grow into that space). In the section sketch's frame
    the hole's axis is the local y axis."""
    import math
    step = 0.1
    n = max(2, int(math.ceil((a1 - a0) / step)) + 1)
    rr = radius + 0.1
    ring = [(rr * math.cos(2 * math.pi * k / angles), rr * math.sin(2 * math.pi * k / angles)) for k in range(angles)]

    def walled(a):
        return all(solid.isInside(placement.multVec(App.Vector(x, sign * a, z)), 1e-6, True) for x, z in ring)

    spans, begin = [], None
    for i in range(n):
        a = a0 + (a1 - a0) * i / (n - 1)
        if walled(a):
            if begin is None:
                begin = a
        elif begin is not None:
            spans.append((begin, a - step))
            begin = None
    if begin is not None:
        spans.append((begin, a1))
    return [(b0, b1) for b0, b1 in spans if b1 - b0 >= 0.3]


def create(doc, body, profile_, values):
    values = rehome(doc, values)
    obj, _, face = _face(doc, values)  # refuse a wrong face or start face before anything is made
    _geometry(obj, face, bool(values.get("flip")), _plane_of(doc, values.get("start_face")))
    tip = body.Tip
    f = body.newObject("PartDesign::SubtractiveHelix", "Thread")
    try:
        _build(doc, body, f, values)
    except Exception:
        sk = f.Profile[0] if isinstance(f.Profile, (tuple, list)) and f.Profile else None
        _remove_helpers(doc, body, f)
        for obj in (f, sk):  # a refused thread leaves nothing behind
            if obj is not None and doc.getObject(obj.Name) is not None:
                body.removeObject(obj)
                doc.removeObject(obj.Name)
        body.Tip = tip
        doc.recompute()
        raise
    after = [h for h in helpers_of(f) if _role(h) == "chamfer"]
    body.Tip = after[-1] if after else f
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
