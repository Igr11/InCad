"""Combine (Inventor) = PartDesign Boolean in the base solid; the tool solids are always kept.

Cut can leave a print clearance (a model parameter):
- on the cavity: the base is cut by the tool grown by the clearance (Part::Offset of the tool body);
- on the tool: the cavity is exact and a fit copy "<Tool> fit" (a Body on a shrunk Part::Offset) is made to print;
- split: half on each.
Settings and helper names live on the Boolean (InCadCombine, JSON)."""
import json

import FreeCAD as App

from incad.features.common import Field, format_picks, parse_picks, resolve

TITLE = "Combine"
ICON = "combine"
TYPES = ("PartDesign::Boolean",)
NEEDS_PROFILE = False
PROPS = {}
_STORE = "InCadCombine"
_TYPE = {"join": "Fuse", "cut": "Cut", "intersect": "Common"}

FIELDS = (
    Field("base", "Base", "pick", pick="body"),
    Field("tools", "Tools", "picks", pick="body"),
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut"), ("intersect", "Intersect")),
          "cut"),
    Field("clearance", "Clearance", "value_length", default="0.2 mm", show_if=("operation", ("cut",))),
    Field("apply_to", "Clearance on", "choice", (("cavity", "Cavity"), ("tool", "Tool"), ("split", "Split")),
          "cavity", show_if=("operation", ("cut",))),
)


def claims(feature):
    return hasattr(feature, _STORE)


def body_of(obj, sub=""):
    if obj is None:
        return None
    if obj.TypeId == "PartDesign::Body":
        return obj
    parent = obj.getParentGeoFeatureGroup()
    return parent if parent is not None and parent.TypeId == "PartDesign::Body" else None


def defaults(doc, body, profile=None):
    from incad.core import prefs
    values = {f.key: f.default for f in FIELDS}
    values.update(base=body.Name if body is not None else "", tools="",
                  clearance="%g mm" % prefs.thread_clearance())
    return values


def preselect(pairs):
    """Selected solids: the first is the base, the others are tools."""
    bodies = []
    for obj, sub in pairs:
        b = body_of(obj, sub)
        if b is not None and b not in bodies:
            bodies.append(b)
    if not bodies:
        return {}
    out = {"base": bodies[0].Name}
    if len(bodies) > 1:
        out["tools"] = format_picks([(b, "") for b in bodies[1:]])
    return out


def _bodies(doc, text):
    out = []
    for obj, sub in parse_picks(doc, text):
        b = body_of(*resolve(obj, sub)) if obj.TypeId != "PartDesign::Body" else obj
        if b is not None and b not in out:
            out.append(b)
    return out


def _load(f):
    try:
        return json.loads(getattr(f, _STORE, "") or "{}")
    except ValueError:
        return {}


def _store(f, data):
    if not hasattr(f, _STORE):
        f.addProperty("App::PropertyString", _STORE, "InCad", "InCad combine settings")
        f.setPropertyStatus(_STORE, "Hidden")
    setattr(f, _STORE, json.dumps(data, sort_keys=True))


def clearance_parameter(f):
    return _load(f).get("clearance_param")


def _mm(text):
    try:
        return App.Units.Quantity(text or "0 mm").Value
    except Exception:
        raise ValueError("Clearance: enter a length such as 0.2 mm")


def _clearance_param(doc, data, text):
    from incad.core import model
    name = data.get("clearance_param")
    if name and name in [p[0] for p in model.feature_parameters(doc)]:
        if model.parameter_text(doc, name) != text:
            model.set_model_parameter(doc, name, text)
        return name
    return model.new_feature_parameter(doc, text, "length")


def _offset(doc, name, label, source, expr):
    obj = doc.getObject(name) if name else None
    if obj is None:
        obj = doc.addObject("Part::Offset", "CombineOffset")
        obj.Join = "Intersection"
        obj.Visibility = False
    obj.Label = label
    obj.Source = source
    obj.setExpression("Value", expr)
    return obj


def _remove(doc, name):
    obj = doc.getObject(name) if name else None
    if obj is None:
        return
    if obj.TypeId == "PartDesign::Body":
        base = obj.BaseFeature
        obj.BaseFeature = None
        for child in list(obj.Group):
            obj.removeObject(child)
            if doc.getObject(child.Name) is not None:
                doc.removeObject(child.Name)
        doc.removeObject(obj.Name)
        if base is not None and doc.getObject(base.Name) is not None:
            doc.removeObject(base.Name)
        return
    doc.removeObject(obj.Name)


def _build(doc, f, base, values):
    from incad.core import model
    tools = _bodies(doc, values.get("tools"))
    if not tools:
        raise ValueError("Pick at least one other solid as a tool")
    if base in tools:
        raise ValueError("The base can't be a tool: pick the other solid(s) as tools")
    op = values.get("operation") or "cut"
    data = _load(f)
    old_helpers = data.get("helpers", {})
    clearance = _mm(values.get("clearance")) if op == "cut" else 0.0
    apply_to = values.get("apply_to") or "cavity"
    name = None
    if op == "cut" and clearance > 0:
        name = _clearance_param(doc, data, values.get("clearance") or "0.2 mm")
    ref = "%s.%s" % (model.MODEL_NAME, name) if name else None
    grow = {"cavity": ref, "split": "%s / 2" % ref} if ref else {}
    shrink = {"tool": "-%s" % ref, "split": "-%s / 2" % ref} if ref else {}
    helpers, group = {}, []
    for tool in tools:
        old = old_helpers.get(tool.Name, {})
        mine = {}
        if apply_to in grow:
            g = _offset(doc, old.get("grown"), "%s grown" % tool.Label, tool, grow[apply_to])
            mine["grown"] = g.Name
            group.append(g)
        else:
            group.append(tool)
        if apply_to in shrink:
            s = _offset(doc, old.get("fit_shape"), "%s fit shape" % tool.Label, tool, shrink[apply_to])
            mine["fit_shape"] = s.Name
            fit = doc.getObject(old["fit"]) if old.get("fit") else None
            if fit is None:
                fit = doc.addObject("PartDesign::Body", "Fit")
                fit.BaseFeature = s
            fit.Label = "%s fit" % tool.Label
            mine["fit"] = fit.Name
        helpers[tool.Name] = mine
        tool.Visibility = False
    f.Type = _TYPE.get(op, "Cut")
    f.Group = group
    for tool_name, old in old_helpers.items():  # drop helpers this setup no longer uses
        mine = helpers.get(tool_name, {})
        for key in ("grown", "fit"):
            if old.get(key) and old.get(key) != mine.get(key):
                _remove(doc, old[key])
        if old.get("fit_shape") and old.get("fit_shape") != mine.get("fit_shape") and \
                doc.getObject(old["fit_shape"]) is not None:
            doc.removeObject(old["fit_shape"])
    _store(f, {"base": base.Name, "tools": [t.Name for t in tools], "operation": op, "apply_to": apply_to,
               "clearance_param": name or data.get("clearance_param"),
               "clearance": values.get("clearance") or "0.2 mm", "helpers": helpers})
    return f


def create(doc, body, profile, values):
    bases = _bodies(doc, values.get("base"))
    base = bases[0] if bases else body
    if base is None:
        raise ValueError("Pick the base solid")
    tools = _bodies(doc, values.get("tools"))
    if not tools:
        raise ValueError("Pick at least one other solid as a tool")
    if base in tools:
        raise ValueError("The base can't be a tool: pick the other solid(s) as tools")
    f = base.newObject("PartDesign::Boolean", "Combine")
    _build(doc, f, base, values)
    base.Tip = f
    return f


def read(doc, f):
    from incad.core import model
    data = _load(f)
    name = data.get("clearance_param")
    clearance = model.parameter_text(doc, name) if name and name in [p[0] for p in model.feature_parameters(doc)] \
        else data.get("clearance", "0.2 mm")
    tools = [doc.getObject(n) for n in data.get("tools", [])]
    return {"base": data.get("base", f.getParentGeoFeatureGroup().Name),
            "tools": format_picks([(t, "") for t in tools if t is not None]),
            "operation": data.get("operation", "cut"), "apply_to": data.get("apply_to", "cavity"),
            "clearance": clearance}


def update(doc, f, values):
    return _build(doc, f, f.getParentGeoFeatureGroup(), values)


def param_names(f):
    name = clearance_parameter(f)
    return {"clearance": name} if name else {}


def _pad_of(f):
    return f
