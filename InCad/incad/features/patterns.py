"""Rectangular / Circular Pattern and Mirror (Inventor) = PartDesign LinearPattern (two directions, Extent mode:
probed — the second direction ignores Spacing mode), PolarPattern and Mirrored."""
from types import SimpleNamespace

from incad.features.common import Field, format_picks, parse_picks, resolve, value_param, value_text


def _origin(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def _features(doc, body, text):
    picks = [resolve(o, s)[0] for o, s in parse_picks(doc, text)]
    return picks or ([body.Tip] if body.Tip is not None else [])


def _dir_link(doc, body, text, default_role):
    picks = parse_picks(doc, text)
    if picks:
        obj, sub = resolve(*picks[0])
        return (obj, [sub])
    return (_origin(body, default_role), [""])


def _link_text(link):
    if not link or link[0] is None:
        return ""
    sub = link[1][0] if link[1] else ""
    return "%s:%s" % (link[0].Name, sub) if sub else link[0].Name


def _count(doc, f, prop, text):
    value_param(doc, f, prop, text or "2", "count")


def _length_from(doc, f, length_prop, count_prop, spacing_text, spacing_key):
    """Length = spacing × (count − 1), with spacing as its own parameter (shown in the dialog)."""
    from incad.core import model
    spacing_name = spacing_param_from(f, spacing_key)
    if spacing_name is None:
        spacing_name = model.new_feature_parameter(doc, spacing_text or "10 mm", "length")
    elif model.parameter_text(doc, spacing_name) != spacing_text and spacing_text:
        model.set_model_parameter(doc, spacing_name, spacing_text)
    count_name = model.bound_parameter(f, count_prop)
    f.setExpression(length_prop, "%s.%s * (%s.%s - 1)" % (model.MODEL_NAME, spacing_name, model.MODEL_NAME,
                                                           count_name))
    return spacing_name


def spacing_param_from(f, key):
    """The spacing parameter is the first name in the Length formula ('InCadModel.dS * (…)')."""
    from incad.core import model
    prop = "Length" if key == "spacing1" else "Length2"
    for path, expr in f.ExpressionEngine:
        if path.lstrip(".") == prop and expr.startswith(model.MODEL_NAME + "."):
            return expr[len(model.MODEL_NAME) + 1:].split(" ", 1)[0]
    return None


def _rect_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"))
    f.Direction = _dir_link(doc, body, values.get("dir1"), "X_Axis")
    f.Mode = "Extent"
    _count(doc, f, "Occurrences", values.get("count1"))
    _length_from(doc, f, "Length", "Occurrences", values.get("spacing1") or "10 mm", "spacing1")
    if values.get("two_directions"):
        f.Direction2 = _dir_link(doc, body, values.get("dir2"), "Y_Axis")
        f.Mode2 = "Extent"
        _count(doc, f, "Occurrences2", values.get("count2"))
        _length_from(doc, f, "Length2", "Occurrences2", values.get("spacing2") or "10 mm", "spacing2")
    else:
        f.setExpression("Occurrences2", None)
        f.Occurrences2 = 1


def _rect_create(doc, body, profile, values):
    f = body.newObject("PartDesign::LinearPattern", "RectangularPattern")
    _rect_apply(doc, body, f, values)
    body.Tip = f  # probed: newObject leaves the Tip on the previous feature for transformed features
    return f


def _rect_read(doc, f):
    from incad.core import model
    def spacing(key):
        name = spacing_param_from(f, key)
        return model.parameter_text(doc, name) if name else "10 mm"
    two = f.Occurrences2 > 1 or model.bound_parameter(f, "Occurrences2") is not None
    return {"features": format_picks([(o, "") for o in f.Originals]), "dir1": _link_text(f.Direction),
            "count1": value_text(doc, f, "Occurrences") or "2", "spacing1": spacing("spacing1"),
            "two_directions": bool(two), "dir2": _link_text(f.Direction2),
            "count2": value_text(doc, f, "Occurrences2") or "2", "spacing2": spacing("spacing2")}


def _rect_update(doc, f, values):
    _rect_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


RECT = SimpleNamespace(
    __name__="incad.features.rect_pattern", TITLE="Rectangular Pattern", ICON="rect_pattern3d",
    TYPES=("PartDesign::LinearPattern",), NEEDS_PROFILE=False, PROPS={"count1": "Occurrences", "count2": "Occurrences2"},
    PRESELECT={"features": "feature"}, spacing_param=lambda f, n: spacing_param_from(f, "spacing%d" % n),
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("dir1", "Direction 1", "pick", pick="axis"),
            Field("count1", "Count", "value_length", default="2"),
            Field("spacing1", "Spacing", "value_length", default="10 mm"),
            Field("two_directions", "Direction 2", "bool", default=False),
            Field("dir2", "Direction 2", "pick", pick="axis", show_if=("two_directions", (True,))),
            Field("count2", "Count 2", "value_length", default="2", show_if=("two_directions", (True,))),
            Field("spacing2", "Spacing 2", "value_length", default="10 mm", show_if=("two_directions", (True,)))),
    defaults=lambda doc, body, profile: {"features": "", "dir1": "", "count1": "2", "spacing1": "10 mm",
                                         "two_directions": False, "dir2": "", "count2": "2", "spacing2": "10 mm"},
    create=_rect_create, read=_rect_read, update=_rect_update, _pad_of=lambda f: f)


def _circ_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"))
    f.Axis = _dir_link(doc, body, values.get("axis"), "Z_Axis")
    f.Mode = "Extent"
    _count(doc, f, "Occurrences", values.get("count"))
    value_param(doc, f, "Angle", values.get("angle") or "360 °", "angle")


def _circ_create(doc, body, profile, values):
    f = body.newObject("PartDesign::PolarPattern", "CircularPattern")
    _circ_apply(doc, body, f, values)
    body.Tip = f  # probed: newObject leaves the Tip on the previous feature for transformed features
    return f


def _circ_read(doc, f):
    return {"features": format_picks([(o, "") for o in f.Originals]), "axis": _link_text(f.Axis),
            "count": value_text(doc, f, "Occurrences") or "4", "angle": value_text(doc, f, "Angle") or "360°"}


def _circ_update(doc, f, values):
    _circ_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


CIRC = SimpleNamespace(
    __name__="incad.features.circ_pattern", TITLE="Circular Pattern", ICON="circ_pattern",
    TYPES=("PartDesign::PolarPattern",), NEEDS_PROFILE=False, PROPS={"count": "Occurrences", "angle": "Angle"},
    PRESELECT={"features": "feature"},
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("axis", "Axis", "pick", pick="axis"),
            Field("count", "Count", "value_length", default="4"),
            Field("angle", "Angle", "value_angle", default="360 °")),
    defaults=lambda doc, body, profile: {"features": "", "axis": "", "count": "4", "angle": "360 °"},
    create=_circ_create, read=_circ_read, update=_circ_update, _pad_of=lambda f: f)


def _mirror_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"))
    f.MirrorPlane = _dir_link(doc, body, values.get("plane"), "YZ_Plane")


def _mirror_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Mirrored", "Mirror")
    _mirror_apply(doc, body, f, values)
    body.Tip = f  # probed: newObject leaves the Tip on the previous feature for transformed features
    return f


def _mirror_read(doc, f):
    return {"features": format_picks([(o, "") for o in f.Originals]), "plane": _link_text(f.MirrorPlane)}


def _mirror_update(doc, f, values):
    _mirror_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


MIRROR = SimpleNamespace(
    __name__="incad.features.mirror", TITLE="Mirror", ICON="mirror3d", TYPES=("PartDesign::Mirrored",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"features": "feature"},
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("plane", "Mirror plane", "pick", pick="plane")),
    defaults=lambda doc, body, profile: {"features": "", "plane": ""},
    create=_mirror_create, read=_mirror_read, update=_mirror_update, _pad_of=lambda f: f)
