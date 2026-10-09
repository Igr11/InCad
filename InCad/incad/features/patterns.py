"""Rectangular / Circular Pattern and Mirror (Inventor) = PartDesign LinearPattern (two directions, Extent mode:
probed — the second direction ignores Spacing mode), PolarPattern and Mirrored."""
import json
import re
from types import SimpleNamespace

from incad.features.common import Field, format_picks, parse_picks, resolve, value_param, value_text


def _origin(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def _origin_name(body, role):
    try:
        return _origin(body, role).Name
    except Exception:
        return ""


def _features(doc, body, text, f, children=False):
    """Picked features (plus the features built on them when `children`); else the ones it already patterns; else
    the Tip (never the pattern itself)."""
    picks = [resolve(o, s)[0] for o, s in parse_picks(doc, text)]
    if picks:
        chosen = [p for p in picks if p is not f]
    elif list(f.Originals):
        chosen = list(f.Originals)
    else:
        chosen = [x for x in [_last_shape_feature(body, f)] if x is not None]
    if children:
        chosen = chosen + _dependents(body, chosen, f)
        group = list(body.Group)
        chosen.sort(key=lambda o: group.index(o) if o in group else 0)
    return chosen


def _support_features(sketch_owner):
    """The solid features a feature's profile sketch stands on (through datum planes too)."""
    found, todo, seen = [], [getattr(sketch_owner, "Profile", None)], set()
    while todo:
        x = todo.pop()
        if isinstance(x, (tuple, list)):
            x = x[0] if x else None
        if x is None or x.Name in seen:
            continue
        seen.add(x.Name)
        for support in getattr(x, "AttachmentSupport", None) or []:
            obj = support[0] if isinstance(support, (tuple, list)) else support
            if obj is None:
                continue
            if obj.isDerivedFrom("PartDesign::Feature"):
                found.append(obj)
            else:
                todo.append(obj)
    return found


def _dependents(body, roots, pattern):
    """Patternable features later in the body whose profile stands on one of `roots` (or on another dependent):
    the hole cut into a boss, the boss on a block. In body order."""
    known = {o.Name for o in roots}
    found = []
    changed = True
    while changed:
        changed = False
        for g in body.Group:
            if g is pattern or g.Name in known or not _patternable(g):
                continue
            if any(s.Name in known for s in _support_features(g)):
                known.add(g.Name)
                found.append(g)
                changed = True
    return found


def _patternable(obj):
    return obj.TypeId in _PATTERNABLE or obj.TypeId.startswith(("PartDesign::Additive", "PartDesign::Subtractive"))


def _picks_and_children(f):
    """(the originals that are not built on another original, True if some are): the toggle stands for the rest."""
    originals = list(f.Originals)
    names = {o.Name for o in originals}
    built_on = [o for o in originals if _patternable(o) and any(s.Name in names for s in _support_features(o))]
    roots = [o for o in originals if o not in built_on]
    return format_picks([(o, "") for o in roots]), bool(built_on)


_PATTERNABLE = ("PartDesign::Pad", "PartDesign::Pocket", "PartDesign::Revolution", "PartDesign::Groove",
                "PartDesign::Hole")


def _last_shape_feature(body, f):
    """The newest feature FreeCAD can pattern (patterns and dress-ups can't be), walking back from the Tip."""
    x = body.Tip
    while x is not None:
        if x is not f and (x.TypeId in _PATTERNABLE or x.TypeId.startswith(("PartDesign::Additive",
                                                                           "PartDesign::Subtractive"))):
            return x
        x = getattr(x, "BaseFeature", None)
    return None


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


_NUMBER_WITH_UNIT = re.compile(r"^[-+]?\d+(\.\d+)?\s*[A-Za-z°\"'%]+$")


def _check_count(text):
    """A plain number must be a whole number >= 1 and carry no unit; names and formulas are checked by FreeCAD."""
    text = (text or "").strip()
    try:
        number = float(text)
    except ValueError:
        if _NUMBER_WITH_UNIT.match(text):
            raise ValueError("The count must be a whole number without a unit")
        return
    if number != int(number) or number < 1:
        raise ValueError("The count must be a whole number, 1 or more")


def _count(doc, f, prop, text):
    _check_count(text)
    value_param(doc, f, prop, (text or "2").strip(), "count")


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


def _direction_vector(link):
    """Unit vector of a pattern direction: an origin/work axis, a sketch axis, or a straight edge."""
    import FreeCAD as App
    obj, subs = link
    sub = subs[0] if subs else ""
    if sub.startswith("Edge"):
        v = obj.getSubObject(sub).Curve.Direction
    elif sub in ("H_Axis", "V_Axis"):
        v = obj.Placement.Rotation.multVec(App.Vector(1, 0, 0) if sub == "H_Axis" else App.Vector(0, 1, 0))
    else:
        v = obj.Placement.Rotation.multVec(App.Vector(1, 0, 0))  # an axis object runs along its own X
    v = App.Vector(v)
    v.normalize()
    return v


def _plane_position(doc, text, direction):
    """Where the picked face, edge or work plane lies along `direction`; None for no pick."""
    picks = parse_picks(doc, text)
    if not picks:
        return None
    obj, sub = resolve(*picks[0])
    if sub:
        point = obj.getSubObject(sub).CenterOfMass
    else:
        point = obj.Placement.Base
    return point.dot(direction)


def _extent_along(originals, direction):
    """(lo, hi) of what the originals add or remove, measured along `direction`."""
    lo, hi = None, None
    for o in originals:
        base = getattr(o, "BaseFeature", None)
        if base is None or base.Shape.isNull() or o.Shape.isNull():
            continue
        region = o.Shape.cut(base.Shape) if o.Shape.Volume > base.Shape.Volume else base.Shape.cut(o.Shape)
        if region.isNull() or not region.Solids:
            continue
        try:
            box = region.optimalBoundingBox()  # tight on round shapes (a boss has no vertices at its sides)
        except Exception:
            box = region.BoundBox
        import FreeCAD as App
        for x in (box.XMin, box.XMax):
            for y in (box.YMin, box.YMax):
                for z in (box.ZMin, box.ZMax):
                    t = App.Vector(x, y, z).dot(direction)
                    lo = t if lo is None else min(lo, t)
                    hi = t if hi is None else max(hi, t)
    if lo is None:
        raise ValueError("The picked feature changes nothing here: nothing to space between the faces")
    return lo, hi


def _fit_spacing(doc, f, values):
    """Spacing that puts the first copy as far from the From face as the last copy is from the To face (no From
    face: the original's own near edge is the start). Runs the pattern backwards if the To face is behind."""
    to_text = (values.get("to1") or "").strip()
    if not to_text:
        raise ValueError("Pick the To face or edge: where the last copy is spaced from")
    direction = _direction_vector(f.Direction)
    start = _plane_position(doc, values.get("from1"), direction)
    end = _plane_position(doc, to_text, direction)
    reverse = (end < start) if start is not None else False
    if start is None:
        lo0, hi0 = _extent_along(list(f.Originals), direction)
        reverse = end < lo0
    if reverse:
        direction = -direction
        start = _plane_position(doc, values.get("from1"), direction)
        end = _plane_position(doc, to_text, direction)
    f.Reversed = bool(reverse)
    lo, hi = _extent_along(list(f.Originals), direction)
    start = lo if start is None else start
    margin = lo - start
    count = int(round(f.Occurrences))
    if count < 2:
        raise ValueError("Use a count of 2 or more to space the copies between the faces")
    spacing = (end - margin - hi) / (count - 1)
    if margin < -1e-6 or spacing < (hi - lo) - 1e-6:  # copies would overlap each other, or start outside the faces
        raise ValueError("There is no room: %d copies don't fit between the two faces — use fewer, or move the faces"
                         % count)
    return "%.6g mm" % spacing


def _store_fit(f, values):
    if "InCadFit" not in f.PropertiesList:
        f.addProperty("App::PropertyString", "InCadFit", "InCad", "How direction 1 is spaced")
    f.InCadFit = json.dumps({"fit1": values.get("fit1") or "spacing", "from1": values.get("from1") or "",
                             "to1": values.get("to1") or ""})


def _load_fit(f):
    try:
        data = json.loads(f.InCadFit) if "InCadFit" in f.PropertiesList else {}
    except ValueError:
        data = {}
    return {"fit1": data.get("fit1", "spacing"), "from1": data.get("from1", ""), "to1": data.get("to1", "")}


def _rect_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"), f, bool(values.get("children")))
    f.Direction = _dir_link(doc, body, values.get("dir1"), "X_Axis")
    f.Mode = "Extent"
    _count(doc, f, "Occurrences", values.get("count1"))
    spacing1 = values.get("spacing1") or "10 mm"
    if values.get("fit1") == "faces":
        f.Reversed = False
        doc.recompute()
        spacing1 = _fit_spacing(doc, f, values)
    else:
        f.Reversed = False
    _length_from(doc, f, "Length", "Occurrences", spacing1, "spacing1")
    _store_fit(f, values)
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
    picks, children = _picks_and_children(f)
    return {"features": picks, "children": children, **_load_fit(f), "dir1": _link_text(f.Direction),
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
            Field("children", "Include dependent features", "bool", default=False),
            Field("dir1", "Direction 1", "pick", pick="axis"),
            Field("count1", "Count", "value_length", default="2"),
            Field("fit1", "Distribution", "choice", (("spacing", "By spacing"), ("faces", "Equal spacing")),
                  "spacing"),
            Field("spacing1", "Spacing", "value_length", default="10 mm", show_if=("fit1", ("spacing",))),
            Field("from1", "From", "pick", pick="limit", show_if=("fit1", ("faces",))),
            Field("to1", "To", "pick", pick="limit", show_if=("fit1", ("faces",))),
            Field("two_directions", "Two directions", "bool", default=False),
            Field("dir2", "Direction 2", "pick", pick="axis", show_if=("two_directions", (True,))),
            Field("count2", "Count 2", "value_length", default="2", show_if=("two_directions", (True,))),
            Field("spacing2", "Spacing 2", "value_length", default="10 mm", show_if=("two_directions", (True,)))),
    defaults=lambda doc, body, profile: {"features": "", "children": False, "dir1": _origin_name(body, "X_Axis"), "count1": "2",
                                         "fit1": "spacing", "from1": "", "to1": "", "spacing1": "10 mm", "two_directions": False,
                                         "dir2": _origin_name(body, "Y_Axis"), "count2": "2", "spacing2": "10 mm"},
    param_names=lambda f: {k: spacing_param_from(f, k) for k in ("spacing1", "spacing2")
                           if spacing_param_from(f, k)},
    create=_rect_create, read=_rect_read, update=_rect_update, _pad_of=lambda f: f)


def _circ_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"), f, bool(values.get("children")))
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
    picks, children = _picks_and_children(f)
    return {"features": picks, "children": children, "axis": _link_text(f.Axis),
            "count": value_text(doc, f, "Occurrences") or "4", "angle": value_text(doc, f, "Angle") or "360°"}


def _circ_update(doc, f, values):
    _circ_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


CIRC = SimpleNamespace(
    __name__="incad.features.circ_pattern", TITLE="Circular Pattern", ICON="circ_pattern",
    TYPES=("PartDesign::PolarPattern",), NEEDS_PROFILE=False, PROPS={"count": "Occurrences", "angle": "Angle"},
    PRESELECT={"features": "feature"},
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("children", "Include dependent features", "bool", default=False),
            Field("axis", "Axis", "pick", pick="axis"),
            Field("count", "Count", "value_length", default="4"),
            Field("angle", "Angle", "value_angle", default="360 °")),
    defaults=lambda doc, body, profile: {"features": "", "children": False, "axis": _origin_name(body, "Z_Axis"), "count": "4",
                                         "angle": "360 °"},
    create=_circ_create, read=_circ_read, update=_circ_update, _pad_of=lambda f: f)


def _mirror_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"), f, bool(values.get("children")))
    f.MirrorPlane = _dir_link(doc, body, values.get("plane"), "YZ_Plane")


def _mirror_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Mirrored", "Mirror")
    _mirror_apply(doc, body, f, values)
    body.Tip = f  # probed: newObject leaves the Tip on the previous feature for transformed features
    return f


def _mirror_read(doc, f):
    picks, children = _picks_and_children(f)
    return {"features": picks, "children": children, "plane": _link_text(f.MirrorPlane)}


def _mirror_update(doc, f, values):
    _mirror_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


MIRROR = SimpleNamespace(
    __name__="incad.features.mirror", TITLE="Mirror", ICON="mirror3d", TYPES=("PartDesign::Mirrored",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"features": "feature"},
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("children", "Include dependent features", "bool", default=False),
            Field("plane", "Mirror plane", "pick", pick="plane")),
    defaults=lambda doc, body, profile: {"features": "", "children": False, "plane": _origin_name(body, "YZ_Plane")},
    create=_mirror_create, read=_mirror_read, update=_mirror_update, _pad_of=lambda f: f)
