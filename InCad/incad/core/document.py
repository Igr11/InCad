"""An InCad Part is a normal FreeCAD document holding PartDesign Bodies. InCad marks it in doc.Meta and keeps
the Body concept away from the user. Pure model logic: no Qt, no GUI."""
import re

import FreeCAD as App

TYPE_KEY = "InCadType"
UNITS_KEY = "InCadUnits"
PRIMARY_KEY = "InCadPrimaryBody"
UNIT_SCHEMES = {"mm": "Standard (mm, kg, s, °)", "in": "Imperial decimal (in, lb)"}
PARAMS_NAME = "InCadParameters"


def _meta_set(doc, **items):
    meta = dict(doc.Meta)
    meta.update(items)
    doc.Meta = meta


def is_incad_part(doc):
    return doc is not None and doc.Meta.get(TYPE_KEY) == "Part"


def part_units(doc):
    units = doc.Meta.get(UNITS_KEY) if doc is not None else None
    return units if units in UNIT_SCHEMES else None


def set_units(doc, units):
    if units not in UNIT_SCHEMES:
        raise ValueError("Units must be 'mm' or 'in', got %r" % (units,))
    _meta_set(doc, **{UNITS_KEY: units})
    if "UnitSystem" in doc.PropertiesList:
        doc.UnitSystem = UNIT_SCHEMES[units]


def bodies(doc):
    return [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]


def primary_body(doc):
    if doc is None:
        return None
    name = doc.Meta.get(PRIMARY_KEY)
    body = doc.getObject(name) if name else None
    return body if body is not None and body.TypeId == "PartDesign::Body" else None


def make_part(doc, units="mm"):
    if units not in UNIT_SCHEMES:
        raise ValueError("Units must be 'mm' or 'in', got %r" % (units,))
    if is_incad_part(doc):
        raise ValueError("%s is already an InCad part" % doc.Label)
    if bodies(doc):
        raise ValueError("This file already has bodies; use Convert to InCad Part")
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = "Solid1"
    _meta_set(doc, **{TYPE_KEY: "Part", PRIMARY_KEY: body.Name})
    set_units(doc, units)
    return body


def convert_to_part(doc, units="mm"):
    found = bodies(doc)
    if len(found) != 1:
        raise ValueError("Only a file with exactly one Body can be converted (this one has %d)" % len(found))
    _meta_set(doc, **{TYPE_KEY: "Part", PRIMARY_KEY: found[0].Name})
    set_units(doc, units)
    return found[0]


def new_solid(doc):
    if not is_incad_part(doc):
        raise ValueError("New Solid needs an InCad part")
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = "Solid%d" % len(bodies(doc))
    return body


def end_of_part(body):
    return body.Tip


def show_result(body):
    """Show only the feature at End of Part (the body Tip), hiding the other features and the sketches, so the 3D
    view follows the model and isn't cluttered by profile sketches. A broken tip (invalid or no shape) would leave
    the view blank, so the nearest earlier feature that still has a shape is shown instead."""
    feats = [o for o in body.Group if o.isDerivedFrom("PartDesign::Feature")]
    tip = body.Tip
    shown = tip
    if tip is not None and _broken_shape(tip) and tip in feats:
        for o in reversed(feats[:feats.index(tip)]):
            if not _broken_shape(o):
                shown = o
                break
    try:
        body.Visibility = True  # a file saved while a sketch was being edited keeps the Body hidden (FreeCAD hides
    except Exception:           # it in sketch edit mode): shown features inside a hidden Body show nothing
        pass
    for o in feats:
        try:
            o.Visibility = (o is shown)
        except Exception:
            pass
    for o in body.Group:  # profile sketches shouldn't linger in the model view after a tip move; an unused
        if o.TypeId == "Sketcher::SketchObject":  # sketch follows the user's choice, else its shape
            try:
                o.Visibility = sketch_shown(o)
            except Exception:
                pass
    return shown


SHOWN_PROP = "InCadShown"  # a sketch the user hid or showed by hand (absent: the default of sketch_shown)
ORIGIN_TYPES = ("App::Plane", "App::Line", "App::Point")
DATUM_TYPES = ("PartDesign::Plane", "PartDesign::Line", "PartDesign::Point")  # work planes, axes, points


def is_unused_sketch(sk):
    from incad.features import common
    return getattr(sk, "TypeId", "") == "Sketcher::SketchObject" and not common.consumers(sk)


def sketch_shown(sk):
    """Whether the part view shows this sketch: never when a feature uses it; else the user's InCadShown
    choice; else an open contour (a path) is shown and a closed sketch hidden."""
    from incad.core import sketch as sketches
    if not is_unused_sketch(sk):
        return False
    if SHOWN_PROP in sk.PropertiesList:
        return bool(getattr(sk, SHOWN_PROP))
    return sketches.is_open_contour(sk)


def origin_items(body):
    return list(body.Origin.OriginFeatures)


def _consumer_label(sk):
    from incad.features import common
    users = common.consumers(sk)
    return users[0].Label if users else ""


def _origin_of(item):
    return next((o for o in item.InList if o.TypeId == "App::Origin"), None)


def is_shown(obj):
    """What the view shows: an origin item needs its Origin group visible too (a new part keeps the group
    hidden while every item says Visible)."""
    if obj.TypeId in ORIGIN_TYPES:
        origin = _origin_of(obj)
        return bool(obj.Visibility) and (origin is None or bool(origin.Visibility))
    return bool(obj.Visibility)


def _record_choice(o, flag):
    """The choice goes into InCadShown: FreeCAD records that in the undo step (a Visibility change alone leaves
    the step empty), and apply_visibility reads it back after undo/redo."""
    if SHOWN_PROP not in o.PropertiesList:
        o.addProperty("App::PropertyBool", SHOWN_PROP, "InCad", "Shown in the part view by choice")
    setattr(o, SHOWN_PROP, bool(flag))


def prepare_choice(objects):
    """Before the Hide / Show step: give every target its InCadShown holding the state it has now. Done outside
    the transaction, so the step changes a value FreeCAD can restore (a property added inside the step would be
    removed by undo, taking the previous state with it)."""
    for o in objects:
        if SHOWN_PROP not in o.PropertiesList and (o.TypeId in ORIGIN_TYPES + DATUM_TYPES
                                                    or o.TypeId == "Sketcher::SketchObject"):
            _record_choice(o, is_shown(o))


def set_visibility(objects, flag, record=True):
    """Show or hide origin items, work features and unused sketches; every one remembers the choice in
    InCadShown (saved, undoable) unless `record` is False (a temporary show). Showing an origin item whose
    group is hidden turns the group on and hides its other items first, so only the chosen one appears."""
    for o in objects:
        if record:
            _record_choice(o, flag)
        if flag and o.TypeId in ORIGIN_TYPES:
            origin = _origin_of(o)
            if origin is not None and not origin.Visibility:
                for other in origin.OriginFeatures:
                    other.Visibility = other in objects
                origin.Visibility = True
        o.Visibility = bool(flag)


def apply_visibility(doc):
    """After undo/redo (which restore InCadShown but not Visibility) and once when a file opens: every origin
    item, work feature and sketch with a choice shows or hides as it says (a sketch: sketch_shown, so a consumed
    one stays hidden); a consumed sketch without a choice is hidden too (redo of its feature leaves it visible);
    anything else is left alone; an Origin group is on when any of its items is shown."""
    origins = set()
    for o in doc.Objects:
        chosen = SHOWN_PROP in o.PropertiesList
        if o.TypeId in ORIGIN_TYPES:
            origin = _origin_of(o)
            if origin is not None:
                origins.add(origin.Name)
            if not chosen:
                continue
            want = bool(getattr(o, SHOWN_PROP))
        elif o.TypeId in DATUM_TYPES:
            if not chosen:
                continue
            want = bool(getattr(o, SHOWN_PROP))
        elif o.TypeId == "Sketcher::SketchObject":
            if not chosen and is_unused_sketch(o):
                continue
            want = sketch_shown(o)
        else:
            continue
        if bool(o.Visibility) != want:
            o.Visibility = want
    for name in origins:
        origin = doc.getObject(name)
        items = list(origin.OriginFeatures)
        chosen_shown = [i for i in items if SHOWN_PROP in i.PropertiesList and getattr(i, SHOWN_PROP)]
        if chosen_shown and not origin.Visibility:  # a chosen item wants to show: the group comes on, and the
            for i in items:                          # items nobody chose stay hidden (a new part keeps them
                if SHOWN_PROP not in i.PropertiesList:  # 'visible' inside a hidden group)
                    i.Visibility = False
            origin.Visibility = True
        elif not chosen_shown and origin.Visibility and not any(bool(i.Visibility) for i in items):
            origin.Visibility = False


def toggle_visibility(objects):
    """Hide / Show: hides when any target is visible, else shows them all. Returns the new state."""
    targets = []
    for o in objects:
        if o.TypeId == "Sketcher::SketchObject":
            if not is_unused_sketch(o):
                raise ValueError("%s belongs to %s" % (o.Label, _consumer_label(o)))
            targets.append(o)
        elif o.TypeId in ORIGIN_TYPES or o.TypeId in DATUM_TYPES:
            targets.append(o)
    if not targets:
        seen = ", ".join(dict.fromkeys(o.Label for o in objects if hasattr(o, "Label")))
        raise ValueError("Nothing to hide or show in %s: select a plane, an axis, a point or an unused sketch"
                         % seen if seen else "Select a plane, an axis, a point or an unused sketch first")
    flag = not any(is_shown(o) for o in targets)
    set_visibility(targets, flag)
    return flag


def _broken_shape(obj):
    try:
        return "Invalid" in obj.State or obj.Shape.isNull()
    except Exception:
        return True


def helpers_of(body, feature):
    """Objects InCad made for `feature` (a thread's chamfer), in body order."""
    return [o for o in body.Group if getattr(o, "InCadHelperOf", None) == feature.Name]


def _is_solid_feature(obj):
    """Only a PartDesign solid feature can be the tip (work planes/axes and sketches are refused or empty)."""
    return obj.isDerivedFrom("PartDesign::Feature")


def set_end_of_part(body, feature):
    """Put End of Part right after `feature` — with the helpers InCad made for it, so "after Thread" includes its
    chamfer; None puts it before the first feature. The shown solid follows: only the tip feature is displayed,
    as FreeCAD's own Move Tip does (the 3D view otherwise keeps showing the last feature it showed, and moving
    End of Part seems to do nothing)."""
    if feature is not None and feature not in body.Group:
        raise ValueError("%s is not part of %s" % (feature.Label, body.Label))
    tip = feature
    if feature is not None:
        group = list(body.Group)
        here = group.index(feature)
        chain = [feature] + [h for h in helpers_of(body, feature) if group.index(h) > here]
        solids = [o for o in chain if _is_solid_feature(o)]
        if solids:
            tip = max(solids, key=group.index)
        else:  # a work plane/axis/sketch cannot be the tip: the last solid feature before it
            before = [o for o in group[:here] if _is_solid_feature(o)]
            tip = before[-1] if before else None
    body.Tip = tip
    body.Document.recompute()
    show_result(body)


_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GROUP = "Parameters"


def parameters(doc, create=True):
    obj = doc.getObject(PARAMS_NAME)
    if obj is None and create:
        obj = doc.addObject("App::VarSet", PARAMS_NAME)
        obj.Label = "Parameters"
    return obj


def _is_param(obj, name):
    return name in obj.PropertiesList and obj.getGroupOfProperty(name) == _GROUP


def list_parameters(doc):
    """[(name, formula or '', value as text)] in the order FreeCAD lists the properties."""
    obj = parameters(doc, create=False) if doc is not None else None
    if obj is None:
        return []
    formulas = {path.lstrip("."): expr for path, expr in obj.ExpressionEngine}
    return [(name, "" if _is_literal(formulas.get(name, "")) else formulas[name], _format(getattr(obj, name)))
            for name in obj.PropertiesList if obj.getGroupOfProperty(name) == _GROUP]


def _is_literal(text):
    """True for a plain value like '80 mm' (stored as an expression so any unit is accepted)."""
    if not text:
        return True
    try:
        App.Units.Quantity(text)
        return True
    except Exception:
        return False


def _format(quantity):
    """'80.00 mm' -> '80 mm', '0.20 mm' -> '0.2 mm' (FreeCAD pads to the decimals setting)."""
    m = re.match(r"^(-?[\d.,]+)(.*)$", quantity.UserString)
    if not m:
        return quantity.UserString
    number, unit = m.groups()
    sep = "." if "." in number else "," if "," in number else ""
    if sep:
        number = number.rstrip("0").rstrip(sep)
    return number + unit


def set_parameter(doc, name, text):
    """Create or update a parameter: a quantity ('80 mm', '12') or a formula ('Width/8').
    Call inside safe.run_safely: a formula that fails to evaluate raises and must be rolled back."""
    if not _NAME_RE.match(name or ""):
        raise ValueError("A parameter name starts with a letter or _ and has only letters, digits and _ (got %r)" % name)
    text = (text or "").strip()
    if not text:
        raise ValueError("Parameter %s needs a value" % name)
    if _is_literal(name):  # 'mm', 'A', 'deg'… are read as units inside formulas
        raise ValueError("%r is a unit symbol; choose another parameter name" % name)
    obj = parameters(doc)
    if name in obj.PropertiesList and not _is_param(obj, name):
        raise ValueError("%r is a reserved name" % name)
    from incad.core import model as _model  # names are unique across user and model parameters
    if name not in obj.PropertiesList and _model.is_model_parameter(doc, name):
        raise ValueError("%r is already a model parameter (a dimension or a feature value)" % name)
    created = name not in obj.PropertiesList
    if created:
        obj.addProperty("App::PropertyQuantity", name, _GROUP)
    try:  # plain values go through the expression engine too: a unitless PropertyQuantity refuses '80 mm'
        obj.setExpression(name, text)
    except Exception as e:
        if created:
            obj.removeProperty(name)
        from incad.core import model as _m
        raise ValueError("%s: %s" % (name, _m.friendly(str(e))))
    doc.recompute()
    if "Invalid" in obj.State or "Error" in obj.State:
        from incad.core import model as _m
        raise ValueError("%s: %s" % (name, _m.friendly(obj.getStatusString())))


def remove_parameter(doc, name):
    obj = parameters(doc, create=False)
    if obj is None or not _is_param(obj, name):
        raise ValueError("No parameter named %r" % name)
    users = _users_of(doc, obj, name)
    if users:
        raise ValueError("%s is used by %s" % (name, ", ".join(users)))
    obj.setExpression(name, None)
    obj.removeProperty(name)
    doc.recompute()


def _users_of(doc, params_obj, name):
    """Labels of the other parameters and objects whose formulas use the user parameter `name`."""
    pattern = re.compile(r"(?:%s\.|(?<![\w.]))%s(?!\w)" % (re.escape(params_obj.Name), re.escape(name)))
    out = []
    for obj in doc.Objects:
        for path, expr in getattr(obj, "ExpressionEngine", []) or []:
            if obj is params_obj and path.lstrip(".") == name:
                continue
            if pattern.search(expr):
                out.append(path.lstrip(".") if obj is params_obj else obj.Label)
                break
    return out


def owning_feature(obj):
    """The feature that uses `obj` as its profile (a sketch's Extrude); obj itself otherwise."""
    for user in obj.InList:
        prof = getattr(user, "Profile", None)
        if isinstance(prof, (tuple, list)):
            prof = prof[0] if prof else None
        if prof is obj:
            return user
    return obj
