"""Rectangular / Circular Pattern and Mirror (Inventor) = PartDesign LinearPattern (two directions, Extent mode:
probed — the second direction ignores Spacing mode), PolarPattern and Mirrored."""
import json
import re
from types import SimpleNamespace

from incad.features.common import (Field, built_on_features, format_picks, parse_picks, repeatable_of, resolve,
                                   value_param, value_text)


def _origin(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def _origin_name(body, role):
    try:
        return _origin(body, role).Name
    except Exception:
        return ""


def _features(doc, body, text, f, children=False):
    """Picked features (plus the features built on them when `children`); else the ones it already patterns. A new
    pattern with nothing picked asks for a feature: the field starts empty (a feature selected before the command
    is seeded into it), never with a guess at what the user wants to repeat."""
    picks = []
    for o, s in parse_picks(doc, text):
        feature = repeatable_of(resolve(o, s)[0])  # a thread, fillet… stands for the feature it modifies
        if feature is not None and feature not in picks:
            picks.append(feature)
    if picks:
        chosen = [p for p in picks if p is not f]
    elif list(f.Originals):
        chosen = list(f.Originals)
    else:
        raise ValueError("Click a feature (tree or view) to repeat")
    if children:
        chosen = chosen + _dependents(body, chosen, f)
        group = list(body.Group)
        chosen.sort(key=lambda o: group.index(o) if o in group else 0)
    return chosen


_support_features = built_on_features


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


def _summary(doc, f):
    """What the Features field shows after a preview: the picked features by name and how many dependents the
    'Include dependent features' switch added (they are not picks, so the field would not mention them)."""
    from incad.features.common import pick_label
    picks, children = _picks_and_children(f)
    roots = len([x for x in picks.split(",") if x])
    deps = len(list(f.Originals)) - roots if children else 0
    text = pick_label("feature", picks)
    return {"features": "%s (+%d dependent)" % (text, deps) if deps else text}


def _picks_and_children(f):
    """(the originals that are not built on another original, True if some are): the toggle stands for the rest."""
    originals = list(f.Originals)
    names = {o.Name for o in originals}
    built_on = [o for o in originals if _patternable(o) and any(s.Name in names for s in _support_features(o))]
    roots = [o for o in originals if o not in built_on]
    return format_picks([(o, "") for o in roots]), bool(built_on)


_PATTERNABLE = ("PartDesign::Pad", "PartDesign::Pocket", "PartDesign::Revolution", "PartDesign::Groove",
                "PartDesign::Hole")


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
    """Unit vector of a pattern direction: an origin/work axis, a sketch axis, a straight edge, or a flat face."""
    import FreeCAD as App
    obj, subs = link
    sub = subs[0] if subs else ""
    if sub.startswith("Edge"):
        v = obj.getSubObject(sub).Curve.Direction
    elif sub.startswith("Face"):
        v = obj.getSubObject(sub).Surface.Axis
    elif sub in ("H_Axis", "V_Axis"):
        v = obj.Placement.Rotation.multVec(App.Vector(1, 0, 0) if sub == "H_Axis" else App.Vector(0, 1, 0))
    else:
        v = obj.Placement.Rotation.multVec(App.Vector(1, 0, 0))  # an axis object runs along its own X
    v = App.Vector(v)
    v.normalize()
    return v


def _limit(doc, text):
    """(object, sub, reference point) of a From/To pick (flat face, edge, or work plane); None for no pick."""
    picks = parse_picks(doc, text)
    if not picks:
        return None
    obj, sub = resolve(*picks[0])
    point = obj.getSubObject(sub).CenterOfMass if sub else obj.Placement.Base
    return obj, sub, point


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


def _axis_towards(body, vector):
    """(link, unit vector) of the origin axis (X, Y or Z) that `vector` is closest to."""
    import FreeCAD as App
    best = max((("X_Axis", App.Vector(1, 0, 0)), ("Y_Axis", App.Vector(0, 1, 0)), ("Z_Axis", App.Vector(0, 0, 1))),
               key=lambda a: abs(vector.dot(a[1])))
    return (_origin(body, best[0]), [""]), best[1]


def _fit_direction(doc, body, f, values, start, end, originals):
    """The line the equal-spacing pattern runs along: the normal of a flat From/To face (or work plane), else the
    axis that From → To (or original → To) points along most."""
    import FreeCAD as App
    for pick in (start, end):
        if pick is None:
            continue
        obj, sub, _ = pick
        if sub.startswith("Face"):
            n = App.Vector(obj.getSubObject(sub).Surface.Axis)
        elif not sub:
            n = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        else:
            continue
        link, vec = _axis_towards(body, n)
        if abs(n.dot(vec)) > 0.9999:  # an axis-aligned face: use that axis (its direction is certain)
            return link, vec
        n = App.Vector(n)
        n.normalize()
        return (obj, [sub]), n
    ref = start[2] if start is not None else _extent_centre(originals)
    return _axis_towards(body, end[2] - ref)


def _extent_centre(originals):
    import FreeCAD as App
    centre, n = App.Vector(), 0
    for o in originals:
        if not o.Shape.isNull():
            centre += o.Shape.BoundBox.Center
            n += 1
    return centre * (1.0 / n) if n else centre


def _fit_spacing(doc, body, f, values):
    """Spacing that puts the first copy as far from the start as the last copy is from the end. The FIRST pick (From)
    is the start and the copies run toward the SECOND (To), whichever end the original is nearer to; without a From
    the original's own edge facing To is the start. Flip direction puts the copies on the other side of the original
    (same spacing); it never changes which pick is the start."""
    end = _limit(doc, values.get("to1"))
    if end is None:
        raise ValueError("Pick the To face or edge: where the last copy is spaced from")
    start = _limit(doc, values.get("from1"))
    originals = list(f.Originals)
    link, direction = _fit_direction(doc, body, f, values, start, end, originals)
    lo, hi = _extent_along(originals, direction)
    t_end = end[2].dot(direction)
    t_start = start[2].dot(direction) if start is not None else (lo if t_end > (lo + hi) / 2.0 else hi)
    sign = 1.0 if t_end >= t_start else -1.0  # the copies run from the start toward the end
    f.Direction = link
    f.Reversed = (sign < 0) != bool(values.get("flip1"))
    s = sign * t_start
    e = s + abs(t_end - t_start)
    u_lo, u_hi = (lo, hi) if sign > 0 else (-hi, -lo)
    margin = u_lo - s  # how far the original's near edge is from the start, toward the end
    count = int(round(f.Occurrences))
    if count < 2:
        raise ValueError("Use a count of 2 or more to space the copies between the faces")
    width = u_hi - u_lo
    if margin < -1e-6:
        raise ValueError("The picked feature lies %.1f mm behind the start (the From pick): pick the other end as "
                         "From, or move the limit" % -margin)
    spacing = (e - margin - u_hi) / (count - 1)
    if spacing < width - 1e-6:  # the copies would overlap each other
        raise ValueError("There is no room: the picked feature is %.1f mm wide and %.1f mm from the start, so %d "
                         "copies need %.1f mm, but only %.1f mm lie between the limits. Use fewer copies, move the "
                         "limits, or pick the other end as From" % (width, margin, count, count * width + 2 * margin,
                                                                    e - s))
    return "%.6g mm" % spacing


def _store_fit(f, values):
    if "InCadFit" not in f.PropertiesList:
        f.addProperty("App::PropertyString", "InCadFit", "InCad", "How direction 1 is spaced")
    f.InCadFit = json.dumps({"fit1": values.get("fit1") or "spacing", "from1": values.get("from1") or "",
                             "to1": values.get("to1") or "", "flip1": bool(values.get("flip1"))})


def _load_fit(f):
    try:
        data = json.loads(f.InCadFit) if "InCadFit" in f.PropertiesList else {}
    except ValueError:
        data = {}
    return {"fit1": data.get("fit1", "spacing"), "from1": data.get("from1", ""), "to1": data.get("to1", ""),
            "flip1": bool(data.get("flip1", False))}


def _rect_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"), f, bool(values.get("children")))
    f.Direction = _dir_link(doc, body, values.get("dir1"), "X_Axis")
    f.Mode = "Extent"
    _count(doc, f, "Occurrences", values.get("count1"))
    spacing1 = values.get("spacing1") or "10 mm"
    if values.get("fit1") == "faces":
        f.Reversed = False
        doc.recompute()
        spacing1 = _fit_spacing(doc, body, f, values)
    else:
        f.Reversed = bool(values.get("flip1"))
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
            Field("fit1", "Distribution", "choice", (("spacing", "By spacing"), ("faces", "Equal spacing")),
                  "spacing"),
            Field("dir1", "Direction 1", "pick", pick="axis", show_if=("fit1", ("spacing",))),
            Field("flip1", "Flip direction", "bool", default=False),
            Field("count1", "Count", "value_length", default="2"),
            Field("spacing1", "Spacing", "value_length", default="10 mm", show_if=("fit1", ("spacing",))),
            Field("from1", "From", "pick", pick="limit", show_if=("fit1", ("faces",))),
            Field("to1", "To", "pick", pick="limit", show_if=("fit1", ("faces",))),
            Field("two_directions", "Two directions", "bool", default=False),
            Field("dir2", "Direction 2", "pick", pick="axis", show_if=("two_directions", (True,))),
            Field("count2", "Count 2", "value_length", default="2", show_if=("two_directions", (True,))),
            Field("spacing2", "Spacing 2", "value_length", default="10 mm", show_if=("two_directions", (True,)))),
    defaults=lambda doc, body, profile: {"features": "", "children": False, "dir1": _origin_name(body, "X_Axis"), "count1": "2",
                                         "fit1": "spacing", "from1": "", "to1": "", "flip1": False, "spacing1": "10 mm", "two_directions": False,
                                         "dir2": _origin_name(body, "Y_Axis"), "count2": "2", "spacing2": "10 mm"},
    param_names=lambda f: {k: spacing_param_from(f, k) for k in ("spacing1", "spacing2")
                           if spacing_param_from(f, k)},
    create=_rect_create, read=_rect_read, update=_rect_update, summary=_summary, _pad_of=lambda f: f)


def _rot_axis(doc, body, f, values):
    """The circular pattern's axis: an origin / work axis, a sketch line, a straight or circular edge, a round face
    (its circular edge: FreeCAD takes no face), or two points clicked on the part — a hidden Work Axis through
    them, owned by the pattern (as Revolve's)."""
    from incad.features import revolve
    if (values.get("axis_mode") or "reference") == "two_points":
        points = revolve.parse_points(values.get("axis_points"))
        if len(points) != 2:
            raise ValueError("Click two points for the axis")
        return (revolve._place_helper(doc, f, points), [""])
    revolve._drop_helper(doc, f)
    obj, subs = _dir_link(doc, body, values.get("axis"), "Z_Axis")
    sub = subs[0] if subs else ""
    if sub.startswith("Face"):
        face = obj.getSubObject(sub)
        edge = next((e for e in face.Edges if e.Curve.TypeId == "Part::GeomCircle"), None) \
            if face.Surface.TypeId == "Part::GeomCylinder" else None
        if edge is None:
            raise ValueError("Pick a round face, a circular or straight edge, or an axis")
        n = next(i for i, e in enumerate(obj.Shape.Edges, 1) if e.isSame(edge))
        sub = "Edge%d" % n
    return (obj, [sub])


def _circ_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"), f, bool(values.get("children")))
    f.Axis = _rot_axis(doc, body, f, values)
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
    from incad.features import revolve
    out = {"features": picks, "children": children, "axis_mode": "reference", "axis": _link_text(f.Axis),
           "axis_points": "", "count": value_text(doc, f, "Occurrences") or "4",
           "angle": value_text(doc, f, "Angle") or "360°"}
    obj = f.Axis[0] if f.Axis else None
    if obj is not None and getattr(obj, revolve.HELPER, None) == f.Name:  # the axis through two points
        out.update(axis_mode="two_points", axis="", axis_points=getattr(obj, revolve.POINTS, ""))
    return out


def _circ_update(doc, f, values):
    _circ_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


CIRC = SimpleNamespace(
    __name__="incad.features.circ_pattern", TITLE="Circular Pattern", ICON="circ_pattern",
    TYPES=("PartDesign::PolarPattern",), NEEDS_PROFILE=False, PROPS={"count": "Occurrences", "angle": "Angle"},
    PRESELECT={"features": "feature"},
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("children", "Include dependent features", "bool", default=False),
            Field("axis_mode", "Axis", "choice", (("reference", "Axis or edge"), ("two_points", "Two points")),
                  "reference"),
            Field("axis", "Pick", "pick", pick="rot_axis", show_if=("axis_mode", ("reference",))),
            Field("axis_points", "Points", "pick", pick="two_points", show_if=("axis_mode", ("two_points",))),
            Field("count", "Count", "value_length", default="4"),
            Field("angle", "Angle", "value_angle", default="360 °")),
    defaults=lambda doc, body, profile: {"features": "", "children": False, "axis_mode": "reference",
                                         "axis": _origin_name(body, "Z_Axis"), "axis_points": "", "count": "4",
                                         "angle": "360 °"},
    create=_circ_create, read=_circ_read, update=_circ_update, summary=_summary, _pad_of=lambda f: f)


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
    create=_mirror_create, read=_mirror_read, update=_mirror_update, summary=_summary, _pad_of=lambda f: f)
