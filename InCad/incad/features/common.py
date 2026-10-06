"""Helpers shared by feature kinds."""
from dataclasses import dataclass



@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str                # value_length | value_angle | choice | combo | bool | pick | picks
    choices: tuple = ()      # ((value, label), …) for choice
    default: object = None
    show_if: tuple = None    # (other key, (values…)) or a tuple of those (all must hold)
    pick: str = ""           # pick fields: edge | face | feature | axis | plane | vertex | sketch | circular_edge


def shown(field, values):
    """Is the field shown for these values? show_if is (key, values) or a tuple of those (all must hold)."""
    cond = field.show_if
    if cond is None:
        return True
    conds = cond if isinstance(cond[0], tuple) else (cond,)
    return all(values.get(k) in allowed for k, allowed in conds)


def closed_profile(sk):
    try:
        return any(w.isClosed() for w in sk.Shape.Wires)
    except Exception:
        return False


def consumers(sk):
    return [o for o in sk.InList if getattr(o, "Profile", None) is not None and _profile(o) is sk]


def _profile(feature):
    prof = getattr(feature, "Profile", None)
    if isinstance(prof, (tuple, list)):
        prof = prof[0] if prof else None
    return prof


def unconsumed_closed_sketches(body):
    from incad.core import sketch
    return [o for o in body.Group if sketch.is_sketch(o) and closed_profile(o) and not consumers(o)]


def value_param(doc, feature, prop, text, unit_kind):
    """Bind feature.prop to a model parameter holding `text` (create one if the property has none yet)."""
    from incad.core import model
    name = model.bound_parameter(feature, prop)
    if name is None:
        name = model.new_feature_parameter(doc, text, unit_kind)
        model.bind(feature, prop, name)
    elif model.parameter_text(doc, name) != text:
        model.set_model_parameter(doc, name, text)
    return name


def value_text(doc, feature, prop):
    from incad.core import model
    name = model.bound_parameter(feature, prop)
    return model.parameter_text(doc, name) if name else ""


def profile_of(feature):
    return _profile(feature)


_PLURAL = {"edge": "edges", "face": "faces", "feature": "features", "vertex": "points", "axis": "axes",
           "plane": "planes", "sketch": "sketches", "circular_edge": "edges", "cylinder": "faces"}


def resolve(obj, sub):
    """A pick on a Body means its Tip; 'Pad.Face6' style paths name the object and the element."""
    if "." in sub:
        parts = sub.split(".")
        child = obj.Document.getObject(parts[-2]) if len(parts) > 1 else None
        obj, sub = (child or obj), parts[-1]
    if obj is not None and obj.TypeId == "PartDesign::Body" and obj.Tip is not None:
        return obj.Tip, sub
    return obj, sub


def format_picks(pairs):
    return ",".join(o.Name if not s else "%s:%s" % (o.Name, s) for o, s in pairs)


def parse_picks(doc, text):
    out = []
    for item in (text or "").split(","):
        item = item.strip()
        if not item:
            continue
        name, _, sub = item.partition(":")
        obj = doc.getObject(name)
        if obj is not None:
            out.append((obj, sub))
    return out


def _element(obj, sub):
    try:
        return obj.getSubObject(sub) if sub else None
    except Exception:
        return None


def accepts(kind, obj, sub):
    if obj is None:
        return False
    tid = obj.TypeId
    if kind == "feature":
        return not sub and tid.startswith("PartDesign::") and tid not in ("PartDesign::Body",)
    if kind == "sketch":
        return not sub and tid == "Sketcher::SketchObject"
    el = _element(obj, sub)
    if kind == "edge":
        return sub.startswith("Edge") and el is not None
    if kind == "circular_edge":
        return sub.startswith("Edge") and el is not None and el.Curve.TypeId == "Part::GeomCircle"
    if kind == "face":
        return sub.startswith("Face") and el is not None
    if kind == "cylinder":
        if not (sub.startswith("Face") and el is not None and el.Surface.TypeId == "Part::GeomCylinder"):
            return False
        u0, u1 = el.ParameterRange[:2]
        return u1 - u0 > 2 * 3.14159265 - 1e-6  # a full round face, not a fillet strip
    if kind == "vertex":
        return sub.startswith("Vertex") and el is not None
    if kind == "axis":
        if not sub:
            return tid in ("App::Line", "PartDesign::Line")
        return sub.startswith("Edge") and el is not None and el.Curve.TypeId == "Part::GeomLine"
    if kind == "plane":
        if not sub:
            return tid in ("App::Plane", "PartDesign::Plane")
        return sub.startswith("Face") and el is not None and el.Surface.TypeId == "Part::GeomPlane"
    return False


def pick_label(kind, text):
    items = [i for i in (text or "").split(",") if i.strip()]
    if not items:
        return "Select…"
    if len(items) == 1:
        name, _, sub = items[0].partition(":")
        try:
            import FreeCAD as App
            obj = App.ActiveDocument.getObject(name) if App.ActiveDocument is not None else None
        except Exception:
            obj = None
        label = obj.Label if obj is not None else name
        return "%s · %s" % (label, sub) if sub else label
    return "%d %s" % (len(items), _PLURAL.get(kind, "items"))


def link_sub(pairs):
    """(obj, [subs]) for a PartDesign LinkSub: every pick must be on the same object."""
    if not pairs:
        raise ValueError("Select at least one item")
    obj = pairs[0][0]
    if any(o is not obj for o, _ in pairs):
        raise ValueError("Pick the items on one feature (the latest one)")
    return obj, [s for _, s in pairs]
