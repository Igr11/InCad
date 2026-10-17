"""Work Plane, Work Axis, Work Point (Inventor) = PartDesign datum Plane / Line / Point.

Every method that FreeCAD's attacher can follow stays associative (probed modes). Three Inventor methods have no
attacher mode — midplane, plane at an angle around an edge, axis parallel to an edge through a point — so their
offset is computed from the picks when the feature is created or edited (ruling). The chosen method and picks
are stored on the feature (InCadWork, JSON) so the dialog reads them back."""
import json
from types import SimpleNamespace

import FreeCAD as App

from incad.features.common import Field, parse_picks, resolve

_STORE = "InCadWork"


def _first(doc, text, what="what the work feature is based on"):
    picks = parse_picks(doc, text)
    if not picks:
        raise ValueError("Select %s" % what)
    return resolve(*picks[0])


def _all(doc, text):
    return [resolve(o, s) for o, s in parse_picks(doc, text)]


def _support_items(f):
    """'Obj:Sub' for every element of the attachment (FreeCAD groups several subs of one object together)."""
    out = []
    for obj, subs in f.AttachmentSupport:
        subs = subs if isinstance(subs, (tuple, list)) else [subs]
        out.extend("%s:%s" % (obj.Name, s) if s else obj.Name for s in (subs or [""]))
    return out


def _element(obj, sub):
    if sub:
        return obj.getSubObject(sub)
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return None
    return shape.Faces[0] if shape.Faces else (shape.Edges[0] if shape.Edges else shape)


def _store(f, data):
    if not hasattr(f, _STORE):
        f.addProperty("App::PropertyString", _STORE, "InCad", "InCad work feature settings")
        f.setPropertyStatus(_STORE, "Hidden")
    setattr(f, _STORE, json.dumps(data, sort_keys=True))


def _load(f):
    try:
        return json.loads(getattr(f, _STORE, "") or "{}")
    except ValueError:
        return {}


def _attach(doc, f, refs, mode, offset=None):
    """Attach with zero offset, recompute, then apply a computed offset (from the attached placement)."""
    from incad.core import model
    for path in (".AttachmentOffset.Base.z", "AttachmentOffset.Base.z"):
        if model.bound_parameter(f, path) is not None:
            f.setExpression(path, None)
    f.AttachmentOffset = App.Placement()
    f.AttachmentSupport = refs
    f.MapMode = mode
    doc.recompute()
    if "Invalid" in f.State:
        raise ValueError("These picks don't define the work feature (%s)" % f.getStatusString())
    if offset is not None:
        f.AttachmentOffset = offset(App.Placement(f.Placement))
        doc.recompute()


def _offset_param(doc, f, text):
    from incad.core import model
    pname = model.bound_parameter(f, ".AttachmentOffset.Base.z") or model.bound_parameter(f, "AttachmentOffset.Base.z")
    if pname is None:
        pname = model.new_feature_parameter(doc, text or "10 mm", "length")
        f.setExpression(".AttachmentOffset.Base.z", "%s.%s" % (model.MODEL_NAME, pname))
    elif model.parameter_text(doc, pname) != text:
        model.set_model_parameter(doc, pname, text, everything=False)


def _deg(text):
    try:
        return App.Units.Quantity((text or "90").replace("°", " deg")).Value
    except Exception:
        raise ValueError("Angle: enter an angle such as 30°")


def _modes(*names):
    return ("mode", names)


# ----- planes -----
_PLANE_MODES = (("offset", "Offset from plane"), ("parallel_point", "Parallel through point"),
                ("midplane", "Midplane"), ("angle", "Angle around edge"), ("three_points", "Three points"),
                ("normal_edge", "Normal to edge at point"), ("tangent", "Tangent to surface at point"))


def _plane_apply(doc, body, f, values):
    mode = values.get("mode") or "offset"
    if mode == "offset":
        _attach(doc, f, [_first(doc, values.get("base"), "a plane or a flat face")], "FlatFace")
        _offset_param(doc, f, values.get("offset") or "10 mm")
    elif mode == "parallel_point":
        base = _first(doc, values.get("base"), "a plane or a flat face")
        point = _first(doc, values.get("point"), "a point")
        if not base[1]:  # a whole plane object: FreeCAD follows the point (associative)
            _attach(doc, f, [base, point], "ParallelPlane")
        else:  # a face: FreeCAD's ParallelPlane needs a whole object, so the offset is computed (ruling)
            p = _element(*point).Point

            def to_point(p0):
                return App.Placement(App.Vector(0, 0, p0.inverse().multVec(p).z), App.Rotation())
            _attach(doc, f, [base], "FlatFace", to_point)
    elif mode == "midplane":
        a = _first(doc, values.get("base"), "the first plane")
        fb = _element(*_first(doc, values.get("base2"), "the second plane"))

        def mid(p0):
            z = p0.Rotation.multVec(App.Vector(0, 0, 1))
            if fb is None or fb.ShapeType != "Face" or abs(abs(z.dot(fb.normalAt(0, 0))) - 1) > 1e-6:
                raise ValueError("The two planes must be parallel for a midplane")
            return App.Placement(App.Vector(0, 0, (fb.Surface.Position - p0.Base).dot(z) / 2.0), App.Rotation())
        _attach(doc, f, [a], "FlatFace", mid)
    elif mode == "angle":
        base = _first(doc, values.get("base"), "a plane or a flat face")
        edge = _element(*_first(doc, values.get("edge"), "the edge to turn around"))
        angle = _deg(values.get("angle"))

        def turn(p0):
            inv = p0.inverse()
            l1, l2 = inv.multVec(edge.Vertexes[0].Point), inv.multVec(edge.Vertexes[-1].Point)
            if abs(l1.z) > 1e-6 or abs(l2.z) > 1e-6:
                raise ValueError("The edge must lie in the plane it turns")
            axis = l2 - l1
            axis.normalize()
            return App.Placement(l1, App.Rotation(axis, angle)) * App.Placement(-l1, App.Rotation())
        _attach(doc, f, [base], "FlatFace", turn)
    elif mode == "three_points":
        pts = _all(doc, values.get("points"))
        if len(pts) != 3:
            raise ValueError("Pick three points")
        _attach(doc, f, pts, "ThreePointsPlane")
    elif mode == "normal_edge":
        _attach(doc, f, [_first(doc, values.get("edge"), "an edge"), _first(doc, values.get("point"), "a point")],
                "NormalToEdge")
    elif mode == "tangent":
        _attach(doc, f, [_first(doc, values.get("face"), "a curved face"),
                         _first(doc, values.get("point"), "a point")], "TangentPlane")
    else:
        raise ValueError("Unknown work plane method %r" % mode)
    _store(f, {k: values.get(k, "") for k in ("mode", "base", "base2", "point", "edge", "face", "angle", "points")})


def _plane_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Plane", "WorkPlane")
    _plane_apply(doc, body, f, values)
    return f


def _plane_defaults(doc, body, profile=None):
    return {"mode": "offset", "base": "", "base2": "", "offset": "10 mm", "point": "", "edge": "", "face": "",
            "angle": "90 °", "points": ""}


def _plane_read(doc, f):
    from incad.core import model
    values = _plane_defaults(doc, None)
    data = _load(f)
    if data:
        values.update({k: v for k, v in data.items() if v is not None})
    elif f.MapMode == "ThreePointsPlane":
        values.update(mode="three_points", points=",".join(_support_items(f)))
    else:
        items = _support_items(f)
        values.update(mode="offset", base=items[0] if items else "")
    if values["mode"] == "three_points" and not values.get("points"):
        values["points"] = ",".join(_support_items(f))
    pname = model.bound_parameter(f, ".AttachmentOffset.Base.z") or model.bound_parameter(f, "AttachmentOffset.Base.z")
    if pname:
        values["offset"] = model.parameter_text(doc, pname)
    return values


def _plane_update(doc, f, values):
    _plane_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


PLANE = SimpleNamespace(
    __name__="incad.features.work_plane", TITLE="Work Plane", ICON="work_plane", TYPES=("PartDesign::Plane",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"base": "plane"},
    FIELDS=(Field("mode", "Method", "combo", _PLANE_MODES, "offset"),
            Field("base", "Plane", "pick", pick="plane",
                  show_if=_modes("offset", "parallel_point", "midplane", "angle")),
            Field("base2", "Second plane", "pick", pick="plane", show_if=_modes("midplane")),
            Field("offset", "Offset", "value_length", default="10 mm", show_if=_modes("offset")),
            Field("edge", "Edge", "pick", pick="edge", show_if=_modes("angle", "normal_edge")),
            Field("angle", "Angle", "value_angle", default="90 °", show_if=_modes("angle")),
            Field("face", "Surface", "pick", pick="face", show_if=_modes("tangent")),
            Field("point", "Point", "pick", pick="vertex",
                  show_if=_modes("parallel_point", "normal_edge", "tangent")),
            Field("points", "Points", "picks", pick="vertex", show_if=_modes("three_points"))),
    defaults=_plane_defaults, create=_plane_create, read=_plane_read, update=_plane_update, _pad_of=lambda f: f)


# ----- axes -----
_AXIS_MODES = (("edge", "On edge"), ("two_points", "Two points"), ("intersection", "Intersection of two planes"),
               ("normal_plane", "Normal to plane through point"), ("cylinder", "Axis of a cylinder"),
               ("parallel_point", "Parallel to edge through point"))


def _axis_apply(doc, body, f, values):
    mode = values.get("mode") or "edge"
    if mode == "edge":
        _attach(doc, f, [_first(doc, values.get("edge"), "an edge")], "TwoPointLine")
    elif mode == "two_points":
        pts = _all(doc, values.get("points"))
        if len(pts) != 2:
            raise ValueError("Pick two points")
        _attach(doc, f, pts, "TwoPointLine")
    elif mode == "intersection":
        _attach(doc, f, [_first(doc, values.get("base"), "the first plane"),
                         _first(doc, values.get("base2"), "the second plane")], "IntersectionLine")
    elif mode == "normal_plane":
        _attach(doc, f, [_first(doc, values.get("base"), "a plane or a flat face"),
                         _first(doc, values.get("point"), "a point")], "FaceNormal")
    elif mode == "cylinder":
        obj, sub = _first(doc, values.get("face"), "a cylindrical face or a round edge")
        _attach(doc, f, [(obj, sub)], "AxisOfCurvature" if sub.startswith("Edge") else "AxisOfInertia3")
    elif mode == "parallel_point":
        point = _element(*_first(doc, values.get("point"), "a point"))

        def through(p0):
            local = p0.inverse().multVec(point.Point)
            return App.Placement(App.Vector(local.x, local.y, 0), App.Rotation())
        _attach(doc, f, [_first(doc, values.get("edge"), "an edge")], "TwoPointLine", through)
    else:
        raise ValueError("Unknown work axis method %r" % mode)
    _store(f, {k: values.get(k, "") for k in ("mode", "edge", "points", "base", "base2", "point", "face")})


def _axis_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Line", "WorkAxis")
    _axis_apply(doc, body, f, values)
    return f


def _axis_defaults(doc, body, profile=None):
    return {"mode": "edge", "edge": "", "points": "", "base": "", "base2": "", "point": "", "face": ""}


def _axis_read(doc, f):
    values = _axis_defaults(doc, None)
    data = _load(f)
    if data:
        values.update(data)
    else:
        items = _support_items(f)
        if len(items) == 2:
            values.update(mode="two_points", points=",".join(items))
        else:
            values.update(mode="edge", edge=items[0] if items else "")
    if values["mode"] == "two_points" and not values.get("points"):
        values["points"] = ",".join(_support_items(f))
    return values


def _axis_update(doc, f, values):
    _axis_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


AXIS = SimpleNamespace(
    __name__="incad.features.work_axis", TITLE="Work Axis", ICON="work_axis", TYPES=("PartDesign::Line",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"edge": "axis"},
    FIELDS=(Field("mode", "Method", "combo", _AXIS_MODES, "edge"),
            Field("edge", "Edge", "pick", pick="edge", show_if=_modes("edge", "parallel_point")),
            Field("points", "Points", "picks", pick="vertex", show_if=_modes("two_points")),
            Field("base", "Plane", "pick", pick="plane", show_if=_modes("intersection", "normal_plane")),
            Field("base2", "Second plane", "pick", pick="plane", show_if=_modes("intersection")),
            Field("face", "Cylinder", "pick", pick="element", show_if=_modes("cylinder")),
            Field("point", "Point", "pick", pick="vertex", show_if=_modes("normal_plane", "parallel_point"))),
    defaults=_axis_defaults, create=_axis_create, read=_axis_read, update=_axis_update, _pad_of=lambda f: f)


# ----- points -----
_POINT_MODES = (("vertex", "At vertex"), ("center", "Center of circle"), ("midpoint", "Midpoint of edge"),
                ("edge_plane", "Edge meets plane"), ("two_edges", "Two edges meet"))


def _point_apply(doc, body, f, values):
    mode = values.get("mode") or "vertex"
    if mode == "vertex":
        _attach(doc, f, [_first(doc, values.get("vertex"), "a vertex")], "Vertex")
    elif mode == "center":
        _attach(doc, f, [_first(doc, values.get("edge"), "a round edge")], "CenterOfCurvature")
    elif mode == "midpoint":
        _attach(doc, f, [_first(doc, values.get("edge"), "an edge")], "CenterOfMass")
    elif mode == "edge_plane":
        _attach(doc, f, [_first(doc, values.get("edge"), "an edge"),
                         _first(doc, values.get("base"), "a plane")], "ProximityPoint1")
    elif mode == "two_edges":
        _attach(doc, f, [_first(doc, values.get("edge"), "the first edge"),
                         _first(doc, values.get("edge2"), "the second edge")], "ProximityPoint1")
    else:
        raise ValueError("Unknown work point method %r" % mode)
    _store(f, {k: values.get(k, "") for k in ("mode", "vertex", "edge", "edge2", "base")})


def _point_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Point", "WorkPoint")
    _point_apply(doc, body, f, values)
    return f


def _point_defaults(doc, body, profile=None):
    return {"mode": "vertex", "vertex": "", "edge": "", "edge2": "", "base": ""}


def _point_read(doc, f):
    values = _point_defaults(doc, None)
    data = _load(f)
    if data:
        values.update(data)
    else:
        items = _support_items(f)
        values.update(mode="vertex", vertex=items[0] if items else "")
    return values


def _point_update(doc, f, values):
    _point_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


POINT = SimpleNamespace(
    __name__="incad.features.work_point", TITLE="Work Point", ICON="work_point", TYPES=("PartDesign::Point",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"vertex": "vertex"},
    FIELDS=(Field("mode", "Method", "combo", _POINT_MODES, "vertex"),
            Field("vertex", "Vertex", "pick", pick="vertex", show_if=_modes("vertex")),
            Field("edge", "Edge", "pick", pick="edge",
                  show_if=_modes("center", "midpoint", "edge_plane", "two_edges")),
            Field("edge2", "Second edge", "pick", pick="edge", show_if=_modes("two_edges")),
            Field("base", "Plane", "pick", pick="plane", show_if=_modes("edge_plane"))),
    defaults=_point_defaults, create=_point_create, read=_point_read, update=_point_update, _pad_of=lambda f: f)
