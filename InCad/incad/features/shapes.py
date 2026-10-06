"""Sweep, Loft, Coil and Draft (Inventor) on native PartDesign features. Join/Cut is chosen when creating."""
from types import SimpleNamespace

from incad.features.common import Field, format_picks, parse_picks, resolve, value_param, value_text

_OP = Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut")), "join")
_TYPES = {"sweep": ("PartDesign::AdditivePipe", "PartDesign::SubtractivePipe"),
          "loft": ("PartDesign::AdditiveLoft", "PartDesign::SubtractiveLoft"),
          "coil": ("PartDesign::AdditiveHelix", "PartDesign::SubtractiveHelix")}


def _sketches(doc, text):
    out = []
    for obj, sub in parse_picks(doc, text):
        obj = resolve(obj, sub)[0] if obj.TypeId != "Sketcher::SketchObject" else obj
        if obj is not None and obj.TypeId == "Sketcher::SketchObject" and obj not in out:
            out.append(obj)
    return out


def _one(doc, text, what):
    found = _sketches(doc, text)
    if not found:
        raise ValueError("Pick the %s sketch" % what)
    return found[0]


def _new(body, key, values, name):
    tid = _TYPES[key][1 if values.get("operation") == "cut" else 0]
    f = body.newObject(tid, name)
    body.Tip = f
    return f


def _op(f, key):
    return "cut" if f.TypeId == _TYPES[key][1] else "join"


def _profile(f):
    p = f.Profile
    return p[0] if isinstance(p, (tuple, list)) and p else p


def _sketch_preselect(keys):
    def pre(pairs):
        found = []
        for obj, sub in pairs:
            if obj.TypeId == "Sketcher::SketchObject" and obj not in found:
                found.append(obj)
        if len(keys) == 1:  # one picks field takes them all in order
            return {keys[0]: format_picks([(o, "") for o in found])} if found else {}
        return {k: o.Name for k, o in zip(keys, found)}
    return pre


# ----- Sweep -----
def _sweep_apply(doc, f, values):
    prof, path = _one(doc, values.get("profile"), "profile"), _one(doc, values.get("path"), "path")
    if prof is path:
        raise ValueError("The path must be another sketch than the profile")
    f.Profile = prof
    f.Spine = (path, [])  # the whole sketch: segments added or redrawn later are followed (probed)
    f.Transition = "Round corner" if "Round corner" in f.getEnumerationsOfProperty("Transition") else f.Transition


def _sweep_create(doc, body, profile, values):
    _one(doc, values.get("profile"), "profile")
    _one(doc, values.get("path"), "path")
    f = _new(body, "sweep", values, "Sweep")
    _sweep_apply(doc, f, values)
    return f


def _sweep_read(doc, f):
    spine = f.Spine[0] if f.Spine else None
    return {"profile": _profile(f).Name if _profile(f) else "", "path": spine.Name if spine else "",
            "operation": _op(f, "sweep")}


SWEEP = SimpleNamespace(
    __name__="incad.features.sweep", TITLE="Sweep", ICON="sweep", TYPES=_TYPES["sweep"], NEEDS_PROFILE=False,
    PROPS={}, STRUCTURAL=("join", "cut"), preselect=_sketch_preselect(["profile", "path"]),
    FIELDS=(Field("profile", "Profile", "pick", pick="sketch"), Field("path", "Path", "pick", pick="sketch"), _OP),
    defaults=lambda doc, body, profile=None: {"profile": "", "path": "", "operation": "join"},
    create=_sweep_create, read=_sweep_read,
    update=lambda doc, f, values: (_sweep_apply(doc, f, values), f)[1], _pad_of=lambda f: f)


# ----- Loft -----
def _loft_apply(doc, f, values):
    secs = _sketches(doc, values.get("sections"))
    if len(secs) < 2:
        raise ValueError("Pick at least two section sketches, in order")
    f.Profile = secs[0]
    f.Sections = secs[1:]
    f.Ruled = bool(values.get("ruled"))
    f.Closed = bool(values.get("closed"))
    doc.recompute()
    shape = f.AddSubShape
    if shape.isNull() or not shape.isValid() or shape.Volume <= 0:  # probed: out-of-order sections give a
        raise ValueError("The sections are out of order: pick them in order along the loft")  # negative volume


def _loft_create(doc, body, profile, values):
    if len(_sketches(doc, values.get("sections"))) < 2:
        raise ValueError("Pick at least two section sketches, in order")
    f = _new(body, "loft", values, "Loft")
    _loft_apply(doc, f, values)
    return f


def _loft_read(doc, f):
    secs = [_profile(f)] + [s if not isinstance(s, (tuple, list)) else s[0] for s in f.Sections]
    return {"sections": ",".join(s.Name for s in secs if s is not None), "ruled": bool(f.Ruled),
            "closed": bool(f.Closed), "operation": _op(f, "loft")}


LOFT = SimpleNamespace(
    __name__="incad.features.loft", TITLE="Loft", ICON="loft", TYPES=_TYPES["loft"], NEEDS_PROFILE=False,
    PROPS={}, STRUCTURAL=("join", "cut"), preselect=_sketch_preselect(["sections"]),
    FIELDS=(Field("sections", "Sections", "picks", pick="sketch"), Field("ruled", "Ruled", "bool", default=False),
            Field("closed", "Closed", "bool", default=False), _OP),
    defaults=lambda doc, body, profile=None: {"sections": "", "ruled": False, "closed": False, "operation": "join"},
    create=_loft_create, read=_loft_read,
    update=lambda doc, f, values: (_loft_apply(doc, f, values), f)[1], _pad_of=lambda f: f)


# ----- Coil -----
def _axis_link(doc, body, text):
    picks = parse_picks(doc, text)
    if picks:
        obj, sub = resolve(*picks[0])
        return (obj, [sub])
    return ([o for o in body.Origin.OriginFeatures if o.Role == "Z_Axis"][0], [""])


def _coil_apply(doc, f, values):
    f.Profile = _one(doc, values.get("profile"), "profile")
    f.ReferenceAxis = _axis_link(doc, f.getParentGeoFeatureGroup(), values.get("axis"))
    f.Mode = "pitch-height-angle"
    f.Refine = False  # probed: refining helical solids can corrupt them
    f.LeftHanded = values.get("hand") == "left"
    value_param(doc, f, "Pitch", values.get("pitch") or "5 mm", "length")
    value_param(doc, f, "Height", values.get("height") or "20 mm", "length")


def _coil_create(doc, body, profile, values):
    _one(doc, values.get("profile"), "profile")
    f = _new(body, "coil", values, "Coil")
    _coil_apply(doc, f, values)
    return f


def _coil_read(doc, f):
    axis = f.ReferenceAxis
    sub = axis[1][0] if axis and axis[1] else ""
    return {"profile": _profile(f).Name if _profile(f) else "",
            "axis": ("%s:%s" % (axis[0].Name, sub) if sub else axis[0].Name) if axis and axis[0] else "",
            "pitch": value_text(doc, f, "Pitch") or "5 mm", "height": value_text(doc, f, "Height") or "20 mm",
            "hand": "left" if f.LeftHanded else "right", "operation": _op(f, "coil")}


COIL = SimpleNamespace(
    __name__="incad.features.coil", TITLE="Coil", ICON="coil", TYPES=_TYPES["coil"], NEEDS_PROFILE=False,
    PROPS={"pitch": "Pitch", "height": "Height"}, STRUCTURAL=("join", "cut"),
    preselect=_sketch_preselect(["profile"]), claims=lambda f: not hasattr(f, "InCadThread"),
    FIELDS=(Field("profile", "Profile", "pick", pick="sketch"), Field("axis", "Axis", "pick", pick="axis"),
            Field("pitch", "Pitch", "value_length", default="5 mm"),
            Field("height", "Height", "value_length", default="20 mm"),
            Field("hand", "Direction", "choice", (("right", "Right hand"), ("left", "Left hand")), "right"), _OP),
    defaults=lambda doc, body, profile=None: {"profile": "", "axis": "", "pitch": "5 mm", "height": "20 mm",
                                              "hand": "right", "operation": "join"},
    create=_coil_create, read=_coil_read,
    update=lambda doc, f, values: (_coil_apply(doc, f, values), f)[1], _pad_of=lambda f: f)


# ----- Draft -----
def _draft_apply(doc, f, values):
    faces = [resolve(o, s) for o, s in parse_picks(doc, values.get("faces"))]
    if not faces:
        raise ValueError("Pick the faces to draft")
    obj = faces[0][0]
    if any(o is not obj for o, _ in faces):
        raise ValueError("Pick the faces on the current shape")
    f.Base = (obj, [s for _, s in faces])
    neutral = parse_picks(doc, values.get("neutral"))
    if not neutral:
        raise ValueError("Pick the neutral plane (a flat face or a plane)")
    n_obj, n_sub = resolve(*neutral[0])
    f.NeutralPlane = (n_obj, [n_sub] if n_sub else [""])
    f.Reversed = bool(values.get("reverse"))
    value_param(doc, f, "Angle", values.get("angle") or "1 °", "angle")


def _draft_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Draft", "Draft")
    _draft_apply(doc, f, values)
    body.Tip = f
    return f


def _draft_read(doc, f):
    base = f.Base
    faces = ",".join("%s:%s" % (base[0].Name, s) for s in base[1]) if base and base[0] else ""
    n = f.NeutralPlane
    n_sub = n[1][0] if n and n[1] else ""
    return {"faces": faces, "neutral": ("%s:%s" % (n[0].Name, n_sub) if n_sub else n[0].Name) if n and n[0] else "",
            "angle": value_text(doc, f, "Angle") or "1 °", "reverse": bool(f.Reversed)}


DRAFT = SimpleNamespace(
    __name__="incad.features.draft", TITLE="Draft", ICON="draft", TYPES=("PartDesign::Draft",),
    NEEDS_PROFILE=False, PROPS={"angle": "Angle"}, PRESELECT={"faces": "face"},
    FIELDS=(Field("faces", "Faces", "picks", pick="face"), Field("neutral", "Neutral plane", "pick", pick="plane"),
            Field("angle", "Angle", "value_angle", default="1 °"), Field("reverse", "Reverse", "bool", default=False)),
    defaults=lambda doc, body, profile=None: {"faces": "", "neutral": "", "angle": "1 °", "reverse": False},
    create=_draft_create, read=_draft_read,
    update=lambda doc, f, values: (_draft_apply(doc, f, values), f)[1], _pad_of=lambda f: f)

KINDS = [SWEEP, LOFT, COIL, DRAFT]
