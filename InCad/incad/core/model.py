"""Model parameters, Inventor style: every sketch dimension and every feature value has a name (d0, d1, …) that
formulas can use. Dimensions are named Sketcher constraints; feature values are properties of a hidden VarSet
("InCadModel") bound to the feature properties by FreeCAD expressions."""
import re

import FreeCAD as App

from incad.core import document

MODEL_NAME = "InCadModel"
_GROUP = "Model"
_DNAME = re.compile(r"^d(\d+)$")
_TOKEN = re.compile(r"(?<![\w.<>])([A-Za-z_][A-Za-z0-9_]*)(?![\w(.])")


def friendly(message):
    """FreeCAD's expression errors in plain words (no internal paths)."""
    m = re.search(r"Property '([^']+)' not found", message)
    if m:
        return "Unknown name '%s' (not a parameter or dimension)" % m.group(1)
    if "cyclic" in message.lower():
        return "This formula refers back to itself (a loop)"
    return message.split("\n")[0]


def _model_obj(doc, create=False):
    obj = doc.getObject(MODEL_NAME)
    if obj is None and create:
        obj = doc.addObject("App::VarSet", MODEL_NAME)
        obj.Label = "Model Parameters"
    return obj


def _feature_names(doc):
    obj = _model_obj(doc)
    return [p for p in obj.PropertiesList if obj.getGroupOfProperty(p) == _GROUP] if obj is not None else []


def _dimension_entries(doc):
    from incad.core import sketch
    return sketch.dimensions(doc)


def used_names(doc):
    from incad.core import sketch
    names = {c.Name for sk in doc.Objects if sketch.is_sketch(sk) for c in sk.Constraints if c.Name}
    names |= set(_feature_names(doc))
    return names | {n for n, _, _ in document.list_parameters(doc)}


def next_name(doc, taken=()):
    from incad.core import sketch
    numbers = [int(m.group(1)) for m in (_DNAME.match(n) for n in set(taken)) if m]
    return "d%d" % max([sketch._next_number(doc)] + [n + 1 for n in numbers])


def claim_name(doc):
    """The next dN for a dimension or a feature value; never handed out again (counter kept in the file)."""
    from incad.core import sketch
    name = next_name(doc)
    meta = dict(doc.Meta)
    meta[sketch.NEXT_KEY] = str(int(name[1:]) + 1)
    doc.Meta = meta
    return name


def refs(doc):
    out = {n: "%s.%s" % (document.PARAMS_NAME, n) for n, _, _ in document.list_parameters(doc)}
    for name, sk, _ in _dimension_entries(doc):
        out[name] = "%s.Constraints.%s" % (sk.Name, name)
    for name in _feature_names(doc):
        out[name] = "%s.%s" % (MODEL_NAME, name)
    return out


def to_expression(doc, text):
    r = refs(doc)
    return _TOKEN.sub(lambda m: r.get(m.group(1), m.group(1)), text)


def to_display(doc, expr):
    for path, name in sorted(((p, n) for n, p in refs(doc).items()), key=lambda pn: -len(pn[0])):
        expr = expr.replace(path, name)
    return re.sub(r"(?<![\w])\.Constraints\.([A-Za-z_]\w*)", r"\1", expr)


def _expression(obj, path):
    for p, e in obj.ExpressionEngine:
        if p.lstrip(".") == path:
            return e
    return ""


def feature_parameters(doc):
    obj = _model_obj(doc)
    if obj is None:
        return []
    return [(n, parameter_text(doc, n) if not document._is_literal(_expression(obj, n)) else "",
             document._format(getattr(obj, n))) for n in _feature_names(doc)]


def model_parameters(doc):
    from incad.core import sketch
    return sketch.dimension_parameters(doc) + feature_parameters(doc)


def is_model_parameter(doc, name):
    from incad.core import sketch
    return name in _feature_names(doc) or sketch.find_dimension(doc, name)[0] is not None


def _with_unit(doc, text, unit_kind):
    try:
        q = App.Units.Quantity(text)
    except Exception:
        return text
    if q.Unit == App.Units.Quantity("1").Unit:
        return "%s %s" % (q.Value, "deg" if unit_kind == "angle" else (document.part_units(doc) or "mm"))
    return text


def new_feature_parameter(doc, text, unit_kind="length"):
    obj = _model_obj(doc, create=True)
    name = claim_name(doc)
    obj.addProperty("App::PropertyQuantity", name, _GROUP)
    try:
        obj.setExpression(name, to_expression(doc, _with_unit(doc, text, unit_kind)))
    except Exception as e:
        obj.removeProperty(name)
        raise ValueError("Invalid value %r: %s" % (text, e))
    doc.recompute()
    if "Invalid" in obj.State or "Error" in obj.State:
        message = friendly(obj.getStatusString())
        obj.setExpression(name, None)
        obj.removeProperty(name)
        doc.recompute()
        raise ValueError("Invalid value %r: %s" % (text, message))
    _remember_kind(obj, name, unit_kind)
    return name


def users_of(doc, name):
    """Labels of the objects whose formulas use the feature value `name` (the value itself excluded)."""
    pattern = re.compile(r"(?:%s\.|(?<![\w.]))%s(?!\w)" % (MODEL_NAME, re.escape(name)))
    model_obj = _model_obj(doc)
    out = []
    for obj in doc.Objects:
        for path, expr in getattr(obj, "ExpressionEngine", []) or []:
            if obj is model_obj and path.lstrip(".") == name:
                continue
            if pattern.search(expr):
                out.append(obj.Label if obj is not model_obj else path.lstrip("."))
                break
    return out


def remove_model_parameter(doc, name):
    """Remove a feature value nothing uses any more (left behind by a deleted feature)."""
    from incad.core import sketch
    if sketch.find_dimension(doc, name)[0] is not None:
        raise ValueError("%s is a sketch dimension: delete it in its sketch" % name)
    obj = _model_obj(doc)
    if obj is None or name not in _feature_names(doc):
        raise ValueError("No parameter named %r" % name)
    users = users_of(doc, name)
    if users:
        raise ValueError("%s is used by %s" % (name, ", ".join(users)))
    obj.setExpression(name, None)
    obj.removeProperty(name)
    doc.recompute()


def _remember_kind(obj, name, unit_kind):
    kinds = dict(item.split("=", 1) for item in obj.Label2.split(";") if "=" in item) if obj.Label2 else {}
    kinds[name] = unit_kind
    obj.Label2 = ";".join("%s=%s" % kv for kv in sorted(kinds.items()))


def _unit_kind(obj, name):
    kinds = dict(item.split("=", 1) for item in obj.Label2.split(";") if "=" in item) if obj.Label2 else {}
    return kinds.get(name, "length")


def bind(feature, prop, name):
    feature.setExpression(prop, "%s.%s" % (MODEL_NAME, name))


def bound_parameter(feature, prop):
    expr = _expression(feature, prop)
    prefix = MODEL_NAME + "."
    return expr[len(prefix):] if expr.startswith(prefix) else None


def parameter_text(doc, name):
    """What the user typed: the formula with plain names, or the value."""
    from incad.core import sketch
    obj = _model_obj(doc)
    if obj is not None and name in _feature_names(doc):
        expr = _expression(obj, name)
        return to_display(doc, expr) if expr and not document._is_literal(expr) else document._format(getattr(obj, name))
    sk, _ = sketch.find_dimension(doc, name)
    if sk is not None:
        expr = _expression(sk, "Constraints." + name)
        return to_display(doc, expr) if expr else document._format(sk.getDatum(name))
    raise ValueError("No parameter named %r" % name)


def set_model_parameter(doc, name, text):
    """Set a dimension or a feature value. Call inside safe.run_safely or a feature session's transaction."""
    from incad.core import sketch
    if sketch.find_dimension(doc, name)[0] is not None:
        return sketch.set_dimension(doc, name, text)
    obj = _model_obj(doc)
    if obj is None or name not in _feature_names(doc):
        raise ValueError("No parameter named %r" % name)
    text = (text or "").strip()
    if not text:
        raise ValueError("%s needs a value" % name)
    try:
        obj.setExpression(name, to_expression(doc, _with_unit(doc, text, _unit_kind(obj, name))))
    except Exception as e:
        raise ValueError("%s: %s" % (name, friendly(str(e))))
    doc.recompute()
    if "Invalid" in obj.State or "Error" in obj.State:
        raise ValueError("%s: %s" % (name, friendly(obj.getStatusString())))


def rename_model_parameter(doc, old, new):
    from incad.core import sketch
    if sketch.find_dimension(doc, old)[0] is not None:
        return sketch.rename_dimension(doc, old, new)
    obj = _model_obj(doc)
    if obj is None or old not in _feature_names(doc):
        raise ValueError("No parameter named %r" % old)
    if not document._NAME_RE.match(new or ""):
        raise ValueError("A name starts with a letter or _ and has only letters, digits and _ (got %r)" % new)
    if document._is_literal(new):
        raise ValueError("%r is a unit symbol; choose another name" % new)
    if new != old and new in used_names(doc):
        raise ValueError("%r is already used" % new)
    kind = _unit_kind(obj, old)
    obj.renameProperty(old, new)
    _remember_kind(obj, new, kind)
    doc.recompute()


_TARGET = re.compile(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)\.")


def relink(doc):
    """Repair formula links after undo/abort. FreeCAD (probed) drops the dependency of an object it restores, so the
    object stops following its parameters; clearing and setting the formula again re-registers it.
    Returns the names of the objects repaired."""
    repaired = []
    for obj in doc.Objects:
        entries = list(getattr(obj, "ExpressionEngine", []) or [])
        if not entries:
            continue
        targets = {doc.getObject(n) for _, e in entries for n in _TARGET.findall(e)} - {None, obj}
        if all(t in obj.OutList for t in targets):
            continue
        for path, expr in entries:
            obj.setExpression(path.lstrip("."), None)
            obj.setExpression(path.lstrip("."), expr)
        repaired.append(obj.Name)
    if repaired:
        doc.recompute()
    return repaired
