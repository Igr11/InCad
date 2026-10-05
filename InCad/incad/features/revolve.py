"""Revolve (Inventor) = PartDesign Revolution (Join) / Groove (Cut) around a sketch axis."""
from incad.features.common import Field, profile_of, value_param, value_text

TITLE = "Revolve"
ICON = "revolve"
TYPES = ("PartDesign::Revolution", "PartDesign::Groove")
PROPS = {"angle": "Angle", "angle2": "Angle2"}
FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut")), "join"),
    Field("axis", "Axis", "choice", (("V_Axis", "Sketch vertical"), ("H_Axis", "Sketch horizontal")), "V_Axis"),
    Field("extent", "Extents", "choice", (("full", "Full"), ("angle", "Angle"), ("two_angles", "Two angles")), "full"),
    Field("angle", "Angle", "value_angle", default="90 °", show_if=("extent", ("angle", "two_angles"))),
    Field("angle2", "Angle 2", "value_angle", default="90 °", show_if=("extent", ("two_angles",))),
    Field("flip", "Flip", "bool", default=False, show_if=("extent", ("angle",))),
)


def defaults(doc, body, profile):
    return {f.key: f.default for f in FIELDS}


def _type(operation):
    return "PartDesign::Groove" if operation == "cut" else "PartDesign::Revolution"


def _apply(doc, f, values):
    f.ReferenceAxis = (profile_of(f), [values.get("axis", "V_Axis")])
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
    axis = f.ReferenceAxis[1][0] if f.ReferenceAxis and f.ReferenceAxis[1] else "V_Axis"
    return {"operation": "cut" if f.TypeId == "PartDesign::Groove" else "join", "axis": axis, "extent": extent,
            "angle": angle, "angle2": value_text(doc, f, "Angle2") or "90 °", "flip": bool(f.Reversed)}


def update(doc, f, values):
    if f.TypeId != _type(values.get("operation", "join")):
        from incad.features import extrude
        f = extrude._replace(doc, f, _type(values.get("operation", "join")))
    _apply(doc, f, values)
    return f


def _pad_of(f):
    return f
