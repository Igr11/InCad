"""Fillet, Chamfer and Shell (Inventor) = PartDesign Fillet, Chamfer, Thickness on picked edges/faces."""
from types import SimpleNamespace

from incad.features.common import Field, link_sub, parse_picks, resolve, value_param, value_text


def _base(doc, text, expected):
    """(obj, subs) of the picks; they must lie on `expected` — the shape the feature starts from."""
    pairs = [resolve(o, s) for o, s in parse_picks(doc, text)]
    obj, subs = link_sub(pairs)
    if expected is not None and obj is not expected:
        raise ValueError("Pick on the current shape (%s), not on %s" % (expected.Label, obj.Label))
    return obj, subs


def _expected(f, body=None):
    base = getattr(f, "BaseFeature", None) if f is not None else None
    return base if base is not None else (body.Tip if body is not None else None)


def _picks_text(f, prop="Base"):
    link = getattr(f, prop)
    if not link or link[0] is None:
        return ""
    obj, subs = link[0], link[1]
    return ",".join("%s:%s" % (obj.Name, s) for s in subs)


# ----- Fillet -----
def _fillet_create(doc, body, profile, values):
    obj, subs = _base(doc, values.get("edges"), body.Tip)
    f = body.newObject("PartDesign::Fillet", "Fillet")
    f.Base = (obj, subs)
    value_param(doc, f, "Radius", values.get("radius") or "1 mm", "length")
    return f


def _fillet_read(doc, f):
    return {"edges": _picks_text(f), "radius": value_text(doc, f, "Radius") or "1 mm"}


def _fillet_update(doc, f, values):
    obj, subs = _base(doc, values.get("edges"), _expected(f))
    f.Base = (obj, subs)
    value_param(doc, f, "Radius", values.get("radius") or "1 mm", "length")
    return f


FILLET = SimpleNamespace(
    __name__="incad.features.fillet", TITLE="Fillet", ICON="fillet", TYPES=("PartDesign::Fillet",),
    NEEDS_PROFILE=False, PROPS={"radius": "Radius"}, PRESELECT={"edges": "edge"},
    FIELDS=(Field("edges", "Edges", "picks", pick="edge"),
            Field("radius", "Radius", "value_length", default="1 mm")),
    defaults=lambda doc, body, profile: {"edges": "", "radius": "1 mm"},
    create=_fillet_create, read=_fillet_read, update=_fillet_update, _pad_of=lambda f: f)


# ----- Chamfer -----
_CHAMFER = {"equal": "Equal distance", "two": "Two distances", "angle": "Distance and Angle"}


def _chamfer_apply(doc, f, values):
    obj, subs = _base(doc, values.get("edges"), _expected(f))
    f.Base = (obj, subs)
    kind = values.get("type", "equal")
    f.ChamferType = _CHAMFER.get(kind, "Equal distance")
    f.FlipDirection = bool(values.get("flip"))
    value_param(doc, f, "Size", values.get("size") or "1 mm", "length")
    if kind == "two":
        value_param(doc, f, "Size2", values.get("size2") or "1 mm", "length")
    if kind == "angle":
        value_param(doc, f, "Angle", values.get("angle") or "45 °", "angle")


def _chamfer_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Chamfer", "Chamfer")
    _chamfer_apply(doc, f, values)
    return f


def _chamfer_read(doc, f):
    kind = {v: k for k, v in _CHAMFER.items()}.get(f.ChamferType, "equal")
    return {"edges": _picks_text(f), "type": kind, "size": value_text(doc, f, "Size") or "1 mm",
            "size2": value_text(doc, f, "Size2") or "1 mm", "angle": value_text(doc, f, "Angle") or "45°",
            "flip": bool(f.FlipDirection)}


def _chamfer_update(doc, f, values):
    _chamfer_apply(doc, f, values)
    return f


CHAMFER = SimpleNamespace(
    __name__="incad.features.chamfer", TITLE="Chamfer", ICON="chamfer", TYPES=("PartDesign::Chamfer",),
    NEEDS_PROFILE=False, PROPS={"size": "Size", "size2": "Size2", "angle": "Angle"}, PRESELECT={"edges": "edge"},
    FIELDS=(Field("edges", "Edges", "picks", pick="edge"),
            Field("type", "Type", "choice", (("equal", "Distance"), ("two", "Two distances"),
                                             ("angle", "Distance + angle")), "equal"),
            Field("size", "Distance", "value_length", default="1 mm"),
            Field("size2", "Distance 2", "value_length", default="1 mm", show_if=("type", ("two",))),
            Field("angle", "Angle", "value_angle", default="45 °", show_if=("type", ("angle",))),
            Field("flip", "Flip", "bool", default=False, show_if=("type", ("two", "angle")))),
    defaults=lambda doc, body, profile: {"edges": "", "type": "equal", "size": "1 mm", "size2": "1 mm",
                                         "angle": "45 °", "flip": False},
    create=_chamfer_create, read=_chamfer_read, update=_chamfer_update, _pad_of=lambda f: f)


# ----- Shell -----
def _shell_apply(doc, f, values):
    obj, subs = _base(doc, values.get("faces"), _expected(f))
    f.Base = (obj, subs)
    f.Reversed = values.get("direction", "inside") == "inside"  # probed: Reversed=True keeps the outer size
    value_param(doc, f, "Value", values.get("thickness") or "1 mm", "length")


def _shell_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Thickness", "Shell")
    _shell_apply(doc, f, values)
    return f


def _shell_read(doc, f):
    return {"faces": _picks_text(f), "thickness": value_text(doc, f, "Value") or "1 mm",
            "direction": "inside" if f.Reversed else "outside"}


def _shell_update(doc, f, values):
    _shell_apply(doc, f, values)
    return f


SHELL = SimpleNamespace(
    __name__="incad.features.shell", TITLE="Shell", ICON="shell", TYPES=("PartDesign::Thickness",),
    NEEDS_PROFILE=False, PROPS={"thickness": "Value"}, PRESELECT={"faces": "face"},
    FIELDS=(Field("faces", "Remove faces", "picks", pick="face"),
            Field("thickness", "Thickness", "value_length", default="1 mm"),
            Field("direction", "Direction", "choice", (("inside", "Inside"), ("outside", "Outside")), "inside")),
    defaults=lambda doc, body, profile: {"faces": "", "thickness": "1 mm", "direction": "inside"},
    create=_shell_create, read=_shell_read, update=_shell_update, _pad_of=lambda f: f)
