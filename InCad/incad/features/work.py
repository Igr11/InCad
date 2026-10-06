"""Work Plane, Work Axis, Work Point (Inventor) = PartDesign datum Plane / Line / Point (probed map modes)."""
from types import SimpleNamespace

from incad.features.common import Field, parse_picks, resolve


def _first(doc, text):
    picks = parse_picks(doc, text)
    if not picks:
        raise ValueError("Select what the work feature is based on")
    return resolve(*picks[0])


def _support_items(f):
    """'Obj:Sub' for every element of the attachment (FreeCAD groups several subs of one object together)."""
    out = []
    for obj, subs in f.AttachmentSupport:
        subs = subs if isinstance(subs, (tuple, list)) else [subs]
        out.extend("%s:%s" % (obj.Name, s) if s else obj.Name for s in (subs or [""]))
    return out


def _plane_apply(doc, body, f, values):
    if values.get("mode") == "three_points":
        pts = [resolve(o, s) for o, s in parse_picks(doc, values.get("points"))]
        if len(pts) != 3:
            raise ValueError("Pick three points")
        f.AttachmentSupport = pts
        f.MapMode = "ThreePointsPlane"
        return
    obj, sub = _first(doc, values.get("base"))
    f.AttachmentSupport = [(obj, sub)]
    f.MapMode = "FlatFace"
    from incad.core import model
    pname = model.bound_parameter(f, ".AttachmentOffset.Base.z") or model.bound_parameter(f, "AttachmentOffset.Base.z")
    text = values.get("offset") or "10 mm"
    if pname is None:
        pname = model.new_feature_parameter(doc, text, "length")
        f.setExpression(".AttachmentOffset.Base.z", "%s.%s" % (model.MODEL_NAME, pname))
    elif model.parameter_text(doc, pname) != text:
        model.set_model_parameter(doc, pname, text)


def _plane_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Plane", "WorkPlane")
    _plane_apply(doc, body, f, values)
    return f


def _plane_read(doc, f):
    from incad.core import model
    support = f.AttachmentSupport
    if f.MapMode == "ThreePointsPlane":
        return {"mode": "three_points", "base": "", "offset": "10 mm", "points": ",".join(_support_items(f))}
    obj, sub = support[0][0], support[0][1]
    sub = sub[0] if isinstance(sub, (tuple, list)) and sub else (sub or "")
    pname = model.bound_parameter(f, ".AttachmentOffset.Base.z") or model.bound_parameter(f, "AttachmentOffset.Base.z")
    return {"mode": "offset", "base": "%s:%s" % (obj.Name, sub) if sub else obj.Name, "points": "",
            "offset": model.parameter_text(doc, pname) if pname else "10 mm"}


def _plane_update(doc, f, values):
    _plane_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


PLANE = SimpleNamespace(
    __name__="incad.features.work_plane", TITLE="Work Plane", ICON="work_plane", TYPES=("PartDesign::Plane",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"base": "plane"},
    FIELDS=(Field("mode", "Type", "choice", (("offset", "Offset"), ("three_points", "3 points")), "offset"),
            Field("base", "From", "pick", pick="plane", show_if=("mode", ("offset",))),
            Field("offset", "Offset", "value_length", default="10 mm", show_if=("mode", ("offset",))),
            Field("points", "Points", "picks", pick="vertex", show_if=("mode", ("three_points",)))),
    defaults=lambda doc, body, profile: {"mode": "offset", "base": "", "offset": "10 mm", "points": ""},
    create=_plane_create, read=_plane_read, update=_plane_update, _pad_of=lambda f: f)


def _axis_apply(doc, body, f, values):
    if values.get("mode") == "two_points":
        pts = [resolve(o, s) for o, s in parse_picks(doc, values.get("points"))]
        if len(pts) != 2:
            raise ValueError("Pick two points")
        f.AttachmentSupport = pts
    else:
        f.AttachmentSupport = [_first(doc, values.get("edge"))]
    f.MapMode = "TwoPointLine"


def _axis_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Line", "WorkAxis")
    _axis_apply(doc, body, f, values)
    return f


def _axis_read(doc, f):
    items = _support_items(f)
    if len(items) == 2:
        return {"mode": "two_points", "edge": "", "points": ",".join(items)}
    return {"mode": "edge", "edge": items[0] if items else "", "points": ""}


def _axis_update(doc, f, values):
    _axis_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


AXIS = SimpleNamespace(
    __name__="incad.features.work_axis", TITLE="Work Axis", ICON="work_axis", TYPES=("PartDesign::Line",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"edge": "axis"},
    FIELDS=(Field("mode", "Type", "choice", (("edge", "Through edge"), ("two_points", "2 points")), "edge"),
            Field("edge", "Edge", "pick", pick="axis", show_if=("mode", ("edge",))),
            Field("points", "Points", "picks", pick="vertex", show_if=("mode", ("two_points",)))),
    defaults=lambda doc, body, profile: {"mode": "edge", "edge": "", "points": ""},
    create=_axis_create, read=_axis_read, update=_axis_update, _pad_of=lambda f: f)


def _point_apply(doc, body, f, values):
    f.AttachmentSupport = [_first(doc, values.get("vertex"))]
    f.MapMode = "Vertex"


def _point_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Point", "WorkPoint")
    _point_apply(doc, body, f, values)
    return f


def _point_read(doc, f):
    o, s = f.AttachmentSupport[0]
    return {"vertex": "%s:%s" % (o.Name, s[0] if isinstance(s, (tuple, list)) else s)}


def _point_update(doc, f, values):
    _point_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


POINT = SimpleNamespace(
    __name__="incad.features.work_point", TITLE="Work Point", ICON="work_point", TYPES=("PartDesign::Point",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"vertex": "vertex"},
    FIELDS=(Field("vertex", "Vertex", "pick", pick="vertex"),),
    defaults=lambda doc, body, profile: {"vertex": ""},
    create=_point_create, read=_point_read, update=_point_update, _pad_of=lambda f: f)
