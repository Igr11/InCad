"""Extrude (Inventor) = PartDesign Pad (Join) / Pocket (Cut); Intersect = a second body + Boolean Common;
New Solid = the profile sketch moved into a new body."""
import FreeCAD as App

from incad.core import document
from incad.features.common import Field, profile_of, value_param, value_text

TITLE = "Extrude"
ICON = "extrude"
TYPES = ("PartDesign::Pad", "PartDesign::Pocket")
FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut"), ("intersect", "Intersect"),
                                               ("new_solid", "New Solid")), "join"),
    Field("extent", "Extents", "choice", (("distance", "Distance"), ("to_next", "To Next"),
                                          ("through_all", "Through All"), ("to", "To")), "distance"),
    Field("to_face", "Face", "pick", show_if=("extent", ("to",))),
    Field("distance", "Distance", "value_length", default="10 mm", show_if=("extent", ("distance",))),
    Field("direction", "Direction", "choice", (("default", "→"), ("flip", "←"), ("symmetric", "⇆"),
                                               ("two_sides", "⇄ 2")), "default"),
    Field("distance2", "Distance 2", "value_length", default="5 mm", show_if=("direction", ("two_sides",))),
    Field("taper", "Taper", "value_angle", default="0 °"),
)
_TYPE = {"distance": "Length", "to_next": "UpToFirst", "to": "UpToFace"}


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
        obj_name, face = values["to_face"].split(":")
        f.UpToFace = (doc.getObject(obj_name), [face])
    direction = values.get("direction", "default")
    f.SideType = {"symmetric": "Symmetric", "two_sides": "Two sides"}.get(direction, "One side")
    f.Reversed = direction == "flip"
    value_param(doc, f, "Length", values.get("distance") or "10 mm", "length")
    if direction == "two_sides":
        value_param(doc, f, "Length2", values.get("distance2") or "5 mm", "length")
    value_param(doc, f, "TaperAngle", values.get("taper") or "0 °", "angle")


def create(doc, body, profile, values):
    operation = values.get("operation", "join")
    target = body
    if operation in ("new_solid", "intersect"):
        target = document.new_solid(doc)
        body.removeObject(profile)
        target.addObject(profile)
    f = target.newObject(_feature_type("cut" if operation == "cut" else "join"), "Extrude")
    f.Profile = profile
    _apply(doc, f, values)
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
    if f.UpToFace and f.UpToFace[0] is not None and f.UpToFace[1]:
        to_face = "%s:%s" % (f.UpToFace[0].Name, f.UpToFace[1][0])
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


def _replace(doc, old, type_id):
    body = old.getParentGeoFeatureGroup()
    profile = profile_of(old)
    bindings = {p: e for p, e in old.ExpressionEngine}
    was_tip = body.Tip is old
    index = body.Group.index(old)
    after = body.Group[index - 1] if index > 0 else None
    label = old.Label
    body.removeObject(old)
    doc.removeObject(old.Name)
    new = doc.addObject(type_id, "Extrude")
    body.insertObject(new, after, True) if after is not None else body.insertObject(new, body.Group[0] if body.Group else None, False)
    new.Label = label
    new.Profile = profile
    for path, expr in bindings.items():
        new.setExpression(path.lstrip("."), expr)
    if was_tip:
        body.Tip = new
    return new
