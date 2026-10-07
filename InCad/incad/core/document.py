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
    for o in feats:
        try:
            o.Visibility = (o is shown)
        except Exception:
            pass
    for o in body.Group:  # profile / construction sketches shouldn't linger in the model view after a tip move
        if o.TypeId == "Sketcher::SketchObject":
            try:
                o.Visibility = False
            except Exception:
                pass
    return shown


def _broken_shape(obj):
    try:
        return "Invalid" in obj.State or obj.Shape.isNull()
    except Exception:
        return True


def helpers_of(body, feature):
    """Objects InCad made for `feature` (a thread's chamfer), in body order."""
    return [o for o in body.Group if getattr(o, "InCadHelperOf", None) == feature.Name]


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
        later = [h for h in helpers_of(body, feature) if group.index(h) > group.index(feature)]
        if later:
            tip = max(later, key=group.index)
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
    obj.setExpression(name, None)
    obj.removeProperty(name)
    doc.recompute()


def owning_feature(obj):
    """The feature that uses `obj` as its profile (a sketch's Extrude); obj itself otherwise."""
    for user in obj.InList:
        prof = getattr(user, "Profile", None)
        if isinstance(prof, (tuple, list)):
            prof = prof[0] if prof else None
        if prof is obj:
            return user
    return obj
