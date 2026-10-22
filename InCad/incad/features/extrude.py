"""Extrude (Inventor) = PartDesign Pad (Join) / Pocket (Cut); Intersect = a second body + Boolean Common;
New Solid = the profile sketch moved into a new body."""
import FreeCAD as App

from incad.core import document
from incad.features.common import Field, profile_of, value_param, value_text

TITLE = "Extrude"
ICON = "extrude"
TYPES = ("PartDesign::Pad", "PartDesign::Pocket")
PROPS = {"distance": "Length", "distance2": "Length2", "taper": "TaperAngle"}
FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut"), ("intersect", "Intersect"),
                                               ("new_solid", "New Solid")), "join"),
    Field("extent", "Extents", "choice", (("distance", "Distance"), ("to_next", "To Next"),
                                          ("through_all", "Through All"), ("to", "To")), "distance"),
    Field("to_face", "To", "pick", show_if=("extent", ("to",)), pick="to_face"),
    Field("distance", "Distance", "value_length", default="10 mm", show_if=("extent", ("distance",))),
    Field("direction", "Direction", "choice", (("default", "→"), ("flip", "←"), ("symmetric", "⇆"),
                                               ("two_sides", "⇄ 2")), "default"),
    Field("distance2", "Distance 2", "value_length", default="5 mm", show_if=("direction", ("two_sides",))),
    Field("taper", "Taper", "value_angle", default="0 °"),
)
_TYPE = {"distance": "Length", "to_next": "UpToFirst", "to": "UpToFace"}
UP_TO = "InCadUpTo"  # on an Extrude whose To target needs a helper: what was picked ('Obj:Sub')
HELPER, ROLE = "InCadHelperOf", "InCadHelperRole"
_POINTS = ("PartDesign::Point", "App::Point")


def _normal(sk):
    return sk.Placement.Rotation.multVec(App.Vector(0, 0, 1))


def default_operation(body, sk):
    """Cut when the profile lies inside the material (Inventor pre-selects Cut there), otherwise Join."""
    shape = body.Shape
    if shape.isNull() or shape.Volume <= 0:
        return "join"
    try:
        centre = sk.Shape.BoundBox.Center
        return "cut" if shape.isInside(centre + _normal(sk) * 0.01, 1e-6, True) else "join"
    except Exception:
        return "join"


def defaults(doc, body, profile):
    values = {f.key: f.default for f in FIELDS}
    values["operation"] = default_operation(body, profile)
    values["to_face"] = ""
    return values


def _feature_type(operation):
    return "PartDesign::Pocket" if operation == "cut" else "PartDesign::Pad"


def _apply(doc, f, values):
    cut = f.TypeId == "PartDesign::Pocket"
    extent = values.get("extent", "distance")
    f.Type = ("ThroughAll" if cut else "UpToLast") if extent == "through_all" else _TYPE.get(extent, "Length")
    if extent == "to" and values.get("to_face"):
        f.UpToFace = _to_target(doc, f, values["to_face"])
    else:
        _drop_helpers(doc, f)
    direction = values.get("direction", "default")
    f.SideType = {"symmetric": "Symmetric", "two_sides": "Two sides"}.get(direction, "One side")
    f.Reversed = direction == "flip"
    if extent == "to_next" and direction == "default" and _material_only_behind(f):
        f.Reversed = True  # Inventor: To Next goes where the part is
    value_param(doc, f, "Length", values.get("distance") or "10 mm", "length")
    if direction == "two_sides":
        value_param(doc, f, "Length2", values.get("distance2") or "5 mm", "length")
    value_param(doc, f, "TaperAngle", values.get("taper") or "0 °", "angle")


def _helper(doc, f, role, type_id, label):
    """The hidden object InCad keeps right before `f` for its To target (made when missing)."""
    body = f.getParentGeoFeatureGroup()
    for o in body.Group:
        if getattr(o, HELPER, None) == f.Name and getattr(o, ROLE, None) == role:
            if o.TypeId == type_id:
                return o
            _remove(doc, o)
            break
    h = doc.addObject(type_id, "ExtrudeTo")
    body.insertObject(h, f, False)  # before the extrude: a feature never references a later object
    h.Label = label
    for prop, doc_text in ((HELPER, "The extrude this belongs to"), (ROLE, "What it is for the extrude")):
        h.addProperty("App::PropertyString", prop, "InCad", doc_text)
        h.setPropertyStatus(prop, "Hidden")
    setattr(h, HELPER, f.Name)
    setattr(h, ROLE, role)
    h.Visibility = False
    return h


def _remove(doc, o):
    body = o.getParentGeoFeatureGroup()
    if body is not None:
        body.removeObject(o)
    doc.removeObject(o.Name)


def _drop_helpers(doc, f, keep=()):
    body = f.getParentGeoFeatureGroup()
    for o in list(body.Group if body is not None else []):
        if getattr(o, HELPER, None) == f.Name and getattr(o, ROLE, "").startswith("to_") and o not in keep:
            _remove(doc, o)
    if not keep and hasattr(f, UP_TO):
        setattr(f, UP_TO, "")


def _bound(doc, f, obj, sub, role):
    """`obj`'s element `sub` as seen from f's Solid: itself when it is in that Solid, else a binder of it (a face
    of another Solid as it is placed: FreeCAD reads another Solid's feature in that Solid's own coordinates)."""
    body = f.getParentGeoFeatureGroup()
    owner = obj.getParentGeoFeatureGroup()
    if owner is body:
        return obj, sub, None
    binder = _helper(doc, f, role, "PartDesign::SubShapeBinder", "Extrude To (binder)")
    path = "%s.%s" % (obj.Name, sub) if sub else obj.Name + "."
    support = [(owner, path)] if owner is not None else [(obj, sub)]
    if list(binder.Support) != support:
        binder.Support = support
    binder.recompute()
    element = "Vertex1" if sub.startswith("Vertex") or obj.TypeId in _POINTS else "Face1"
    return binder, element, binder


def _to_target(doc, f, pick):
    """f.UpToFace for the picked To target: a face or plane of the extrude's own Solid as it is; any face of another
    Solid (flat or curved) through a binder; a point (a corner, a sketch or work point) through a plane parallel to
    the sketch, which follows the point."""
    name, _, sub = pick.partition(":")
    obj = doc.getObject(name)
    if obj is None:
        raise ValueError("Select a face, a plane or a point for To")
    point = sub.startswith("Vertex") or (not sub and obj.TypeId in _POINTS)
    keep = []
    if point:
        target, element, binder = _bound(doc, f, obj, sub, "to_binder")
        keep += [binder] if binder is not None else []
        sk = profile_of(f)
        plane = _helper(doc, f, "to_plane", "PartDesign::Plane", "Extrude To (point)")
        refs = [(sk, ""), (target, element)]
        if list(plane.AttachmentSupport) != refs or plane.MapMode != "ParallelPlane":
            plane.AttachmentSupport = refs
            plane.MapMode = "ParallelPlane"
        plane.recompute()
        if "Invalid" in plane.State:
            raise ValueError("To: no plane through that point (%s)" % plane.getStatusString())
        keep.append(plane)
        result = (plane, [""])
    else:
        target, element, binder = _bound(doc, f, obj, sub, "to_binder")
        keep += [binder] if binder is not None else []
        result = (target, [element] if element else [])
    _drop_helpers(doc, f, keep)
    if keep:
        if not hasattr(f, UP_TO):
            f.addProperty("App::PropertyString", UP_TO, "InCad", "What To was picked on")
            f.setPropertyStatus(UP_TO, "Hidden")
        setattr(f, UP_TO, pick)
    elif hasattr(f, UP_TO):
        setattr(f, UP_TO, "")
    return result


def _material_only_behind(f):
    """True when the part lies only against this feature's default direction (a sketch above the part: To Next
    would find nothing)."""
    import Part
    sk = profile_of(f)
    base = f.BaseFeature.Shape if f.BaseFeature is not None else None
    if sk is None or base is None or base.isNull() or sk.Shape.isNull():
        return False
    n = _normal(sk)
    if f.TypeId == "PartDesign::Pocket":
        n = -n  # a Pocket cuts against the sketch's normal
    c = sk.Shape.BoundBox.Center
    reach = base.BoundBox.DiagonalLength + (c - base.BoundBox.Center).Length + 1.0

    def hits(d):
        ray = Part.LineSegment(c + d * 1e-4, c + d * reach).toShape()
        return any(e.Length > 1e-6 for e in base.common(ray).Edges)
    return not hits(n) and hits(-n)


def _solids(feature):
    try:
        shape = feature.Shape
        return 0 if shape.isNull() else len(shape.Solids)
    except Exception:
        return 0


def create(doc, body, profile, values):
    operation = values.get("operation", "join")
    target = body
    if operation in ("new_solid", "intersect"):
        target = document.new_solid(doc)
        body.removeObject(profile)
        target.addObject(profile)
        document.settle_support(profile, target)  # on a face of the part: not the whole part in the new Solid
    before = _solids(body.Tip) if body.Tip is not None else 0
    f = target.newObject(_feature_type("cut" if operation == "cut" else "join"), "Extrude")
    f.Profile = profile
    _apply(doc, f, values)
    if operation == "join" and before:
        doc.recompute()
        if _solids(f) > before:  # the new solid does not touch the part: a piece of its own, not a second
            _drop_helpers(doc, f)   # lump in the part's body (nothing could be shelled or filleted there)
            target.removeObject(f)
            doc.removeObject(f.Name)
            target = document.new_solid(doc)
            body.removeObject(profile)
            target.addObject(profile)
            document.settle_support(profile, target)
            f = target.newObject(_feature_type("join"), "Extrude")
            f.Profile = profile
            _apply(doc, f, values)
            document.show_result(body)  # the first try, in the part, hid the part's last step (FreeCAD hides a base)
            from incad.core import log
            log.report("info", "%s does not touch the part: made as its own Solid (%s)" % (f.Label, target.Label))
    if operation == "intersect":
        doc.recompute()
        common = body.newObject("PartDesign::Boolean", "Intersect")
        common.Type = "Common"
        common.addObjects([target])
        return common
    return f


def _pad_of(feature):
    if feature.TypeId == "PartDesign::Boolean":
        tool = feature.Group[0] if feature.Group else None
        return tool.Tip if tool is not None else None
    return feature


def read(doc, feature):
    if feature.TypeId == "PartDesign::Boolean":
        values = read(doc, _pad_of(feature))
        values["operation"] = "intersect"
        return values
    f = feature
    operation = "cut" if f.TypeId == "PartDesign::Pocket" else "join"
    body = f.getParentGeoFeatureGroup()
    if operation == "join" and body is not None and document.primary_body(doc) is not body:
        operation = "new_solid"
    extent = {"Length": "distance", "UpToFirst": "to_next", "UpToFace": "to", "ThroughAll": "through_all",
              "UpToLast": "through_all"}.get(f.Type, "distance")
    direction = {"Symmetric": "symmetric", "Two sides": "two_sides"}.get(f.SideType, "flip" if f.Reversed else "default")
    to_face = ""
    if getattr(f, UP_TO, ""):
        to_face = getattr(f, UP_TO)  # through a helper: what was picked
    elif f.UpToFace and f.UpToFace[0] is not None:
        sub = f.UpToFace[1][0] if f.UpToFace[1] else ""
        to_face = "%s:%s" % (f.UpToFace[0].Name, sub) if sub else f.UpToFace[0].Name
    return {"operation": operation, "extent": extent, "direction": direction, "to_face": to_face,
            "distance": value_text(doc, f, "Length") or "10 mm",
            "distance2": value_text(doc, f, "Length2") or "5 mm",
            "taper": value_text(doc, f, "TaperAngle") or "0 °"}


def update(doc, feature, values):
    """Apply dialog values. Join<->Cut replaces Pad/Pocket in place, keeping its parameters."""
    is_boolean = feature.TypeId == "PartDesign::Boolean"  # decided first: a replaced Pad no longer exists
    f = _pad_of(feature)
    wanted = values.get("operation", "join")
    if wanted in ("join", "cut") and f.TypeId != _feature_type(wanted) and not is_boolean:
        f = _replace(doc, f, _feature_type(wanted))
    _apply(doc, f, values)
    return feature if is_boolean else f


def _refers_to(value, target):
    if value is target:
        return True
    if isinstance(value, (list, tuple)):
        return any(_refers_to(v, target) for v in value)
    return False


def _dependents(old, body):
    """Objects (other than the body and the next feature's BaseFeature link) that use `old` — they would lose it."""
    out = []
    for dep in old.InList:
        if dep is body:
            continue
        uses = any(prop != "BaseFeature" and _refers_to(getattr(dep, prop, None), old) for prop in dep.PropertiesList)
        uses = uses or any(old.Name + "." in expr for _, expr in getattr(dep, "ExpressionEngine", []) or [])
        if uses:
            out.append(dep.Label)
    return out


def _replace(doc, old, type_id):
    body = old.getParentGeoFeatureGroup()
    users = _dependents(old, body)
    if users:
        raise ValueError("Join/Cut can't be switched here: %s %s built on this Extrude"
                         % (", ".join(users), "is" if len(users) == 1 else "are"))
    visible = old.Visibility
    profile = profile_of(old)
    bindings = {p: e for p, e in old.ExpressionEngine}
    was_tip = body.Tip is old
    index = body.Group.index(old)
    after = body.Group[index - 1] if index > 0 else None
    label = old.Label
    helpers = [o for o in body.Group if getattr(o, HELPER, None) == old.Name]
    up_to = getattr(old, UP_TO, "")
    body.removeObject(old)
    doc.removeObject(old.Name)
    new = doc.addObject(type_id, "Extrude")
    body.insertObject(new, after, True) if after is not None else body.insertObject(new, body.Group[0] if body.Group else None, False)
    new.Label = label
    new.Profile = profile
    for h in helpers:  # the To target's helpers follow the re-made feature
        setattr(h, HELPER, new.Name)
    if up_to:
        new.addProperty("App::PropertyString", UP_TO, "InCad", "What To was picked on")
        new.setPropertyStatus(UP_TO, "Hidden")
        setattr(new, UP_TO, up_to)
    for path, expr in bindings.items():
        new.setExpression(path.lstrip("."), expr)
    if was_tip:
        body.Tip = new
    else:
        new.Visibility = visible
    return new
