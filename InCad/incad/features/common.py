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
    """A sketch FreeCAD can pad as it is: closed wires, no crossing or dangling lines (those use areas instead,
    see incad.core.regions)."""
    from incad.core import regions
    try:
        return any(w.isClosed() for w in sk.Shape.Wires) and not regions.needs_regions(sk)
    except Exception:
        return False


def consumers(sk):
    from incad.core import regions
    own = [o for o in sk.InList if getattr(o, "Profile", None) is not None and _profile(o) is sk]
    for prof in regions.profiles_of(sk):  # a feature on one of its areas uses this sketch too
        own += [o for o in prof.InList if getattr(o, "Profile", None) is not None and _profile(o) is prof]
    return own


def _profile(feature):
    prof = getattr(feature, "Profile", None)
    if isinstance(prof, (tuple, list)):
        prof = prof[0] if prof else None
    return prof


def usable_profile(sk):
    """A sketch a feature can be built on: closed, or with areas between crossing lines."""
    from incad.core import regions
    return closed_profile(sk) or regions.needs_regions(sk)


def unconsumed_closed_sketches(body):
    from incad.core import sketch
    return [o for o in body.Group if sketch.is_sketch(o) and usable_profile(o) and not consumers(o)]


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
           "plane": "planes", "sketch": "sketches", "circular_edge": "edges", "cylinder": "faces", "body": "solids", "element": "items", "component": "components"}


def resolve(obj, sub):
    """A pick on a Body means its Tip; 'Pad.Face6' style paths name the object and the element; in an assembly
    'Link.Body.Pad.Face5' means the component (the link) and its element."""
    if obj is not None and obj.TypeId == "Assembly::AssemblyObject" and "." in sub:
        parts = sub.split(".")
        link = obj.Document.getObject(parts[0])
        if link is not None:
            return link, parts[-1]
    if "." in sub:
        parts = sub.split(".")
        child = obj.Document.getObject(parts[-2]) if len(parts) > 1 else None
        obj, sub = (child or obj), parts[-1]
    if obj is not None and obj.TypeId == "PartDesign::Body" and obj.Tip is not None:
        return obj.Tip, sub
    return obj, sub


WHOLE_OBJECT = ("sketch",)  # picks that mean the object, whatever element of it was clicked


def whole(kind, pairs):
    return [(o, "") for o, _ in pairs] if kind in WHOLE_OBJECT else pairs


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


def feature_of(obj, sub):
    """The solid feature a pick stands for: a feature itself (a tree row), or the feature that CREATED the face/edge
    clicked in the view (a hole's wall -> its Hole/Pocket, a block's side -> its Pad). None for anything else."""
    if obj is None or not obj.isDerivedFrom("PartDesign::Feature"):
        return None
    if not sub:
        return obj
    if not sub.startswith(("Face", "Edge")):
        return None
    try:
        history = obj.getElementHistory(sub)
    except Exception:
        return obj
    made_by = [o for o, _, _ in ((h[0], h[1], h[2]) for h in history) if o.isDerivedFrom("PartDesign::Feature")]
    return made_by[-1] if made_by else obj


def accepts(kind, obj, sub):
    if obj is None:
        return False
    tid = obj.TypeId
    if kind == "feature":
        return feature_of(obj, sub) is not None
    if kind == "sketch":  # the sketch itself, or any point/line of it clicked in the view
        return tid == "Sketcher::SketchObject"
    if kind == "body":
        if tid == "PartDesign::Body":
            return True
        parent = obj.getParentGeoFeatureGroup()
        return parent is not None and parent.TypeId == "PartDesign::Body" and tid.startswith("PartDesign::")
    el = _element(obj, sub)
    if kind == "edge":
        return sub.startswith("Edge") and el is not None
    if kind == "circular_edge":
        return sub.startswith("Edge") and el is not None and el.Curve.TypeId == "Part::GeomCircle"
    if kind == "face":
        return sub.startswith("Face") and el is not None
    if kind == "component":
        return tid == "App::Link"
    if kind == "element":
        return sub.startswith(("Face", "Edge", "Vertex")) and el is not None
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


_EMPTY_HINT = {"feature": "Click a feature (tree or view)…", "plane": "Click a face or work plane…"}


def pick_label(kind, text):
    if kind == "two_points":
        n = len([i for i in (text or "").split(";") if i.strip()])
        return "Select…" if not n else ("1 of 2 points" if n == 1 else "2 points")
    items = [i for i in (text or "").split(",") if i.strip()]
    if not items:
        return _EMPTY_HINT.get(kind, "Select…")
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
