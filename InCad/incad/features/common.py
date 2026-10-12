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
    listed: bool = False     # picks fields: show the picks as a numbered list (remove, reorder), e.g. Loft sections
    optional: bool = False   # pick fields: an empty one has a default: never made active by itself


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
    """Features that use this sketch: as their Profile, as a Sweep's path (Spine) or a Loft's further section
    (Sections), or through one of its areas."""
    from incad.core import regions
    own = [o for o in sk.InList if _uses(o, sk)]
    for prof in regions.profiles_of(sk):  # a feature on one of its areas uses this sketch too
        own += [o for o in prof.InList if _uses(o, prof)]
    return own


def _linked(value):
    """The object of a link property value (plain, (obj, subs) tuple, or a list of either)."""
    if isinstance(value, (tuple, list)):
        if len(value) == 2 and not isinstance(value[0], (tuple, list)) and isinstance(value[1], (list, tuple, str)) \
                and hasattr(value[0], "TypeId"):
            return [value[0]]
        out = []
        for v in value:
            out += _linked(v)
        return out
    return [value] if value is not None and hasattr(value, "TypeId") else []


def _uses(feature, sk):
    if getattr(feature, "Profile", None) is not None and _profile(feature) is sk:
        return True
    for prop in ("Spine", "Sections"):
        if prop in getattr(feature, "PropertiesList", ()) and sk in _linked(getattr(feature, prop)):
            return True
    return False


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


_STAND_IN_TYPES = ("PartDesign::Fillet", "PartDesign::Chamfer", "PartDesign::Thickness", "PartDesign::Draft",
                   "PartDesign::LinearPattern", "PartDesign::PolarPattern", "PartDesign::Mirrored",
                   "PartDesign::MultiTransform")


def is_stand_in(obj):
    """Features that can't be repeated themselves (a thread's helix, fillets, chamfers, shells, other patterns):
    picking one stands for the feature it modifies."""
    return obj.TypeId.endswith("Helix") or obj.TypeId in _STAND_IN_TYPES


def _profile_supports(owner):
    """(feature, sub-element names) pairs a feature's profile sketch is attached to, through datum planes too."""
    todo, seen = [getattr(owner, "Profile", None)], set()
    while todo:
        x = todo.pop()
        if isinstance(x, (tuple, list)):
            x = x[0] if x else None
        if x is None or x.Name in seen:
            continue
        seen.add(x.Name)
        for support in getattr(x, "AttachmentSupport", None) or []:
            obj, subs = (support[0], support[1]) if isinstance(support, (tuple, list)) else (support, ())
            if obj is None:
                continue
            if obj.isDerivedFrom("PartDesign::Feature"):
                yield obj, [s for s in (subs if isinstance(subs, (tuple, list)) else [subs]) if s]
            else:
                todo.append(obj)


def support_features(owner):
    """The solid features a feature's profile sketch NAMES in its attachment: whatever feature was the Tip when the
    sketch was drawn. See built_on_features for the features that made the faces it stands on."""
    return [obj for obj, _ in _profile_supports(owner)]


def built_on_features(owner):
    """The solid features a feature is BUILT ON: for each face or edge its profile sketch is attached to, the
    feature that created that face (a sketch drawn on the block's top while a boss was the Tip names the boss,
    but stands on the block). A support that names no face or edge stands for the feature itself."""
    found = []
    for obj, subs in _profile_supports(owner):
        for sub in subs or [""]:
            made = raw_feature_of(obj, sub)
            if made is not None and all(made is not f for f in found):
                found.append(made)
    return found


def repeatable_of(obj):
    """The feature that can be repeated for `obj`: itself, or for a thread the shaft/hole it is cut into, for a
    fillet/chamfer/shell/pattern the feature it was made on."""
    seen = set()
    while obj is not None and is_stand_in(obj) and obj.Name not in seen:
        seen.add(obj.Name)
        nxt = None
        if obj.TypeId.endswith("Helix"):
            sup = support_features(obj)
            nxt = sup[0] if sup else None
        if nxt is None:
            nxt = getattr(obj, "BaseFeature", None)
        obj = nxt
    return obj


def feature_of(obj, sub):
    """What a pick means for a pattern: the feature made repeatable (see raw_feature_of and repeatable_of)."""
    raw = raw_feature_of(obj, sub)
    return repeatable_of(raw) if raw is not None else None


def raw_feature_of(obj, sub):
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
    made = made_by[-1] if made_by else obj
    if sub.startswith("Face"):
        made = _older_maker(made, _element(obj, sub))
    return made


def _older_maker(made, face):
    """The element history stops where a feature kept no element names (a thread's helix): walk on down the
    BaseFeature chain while the face was already there, the same surface overlapping this face."""
    if face is None:
        return made
    base = getattr(made, "BaseFeature", None)
    while base is not None and not base.Shape.isNull() and _carries_face(base.Shape, face):
        made, base = base, getattr(base, "BaseFeature", None)
    return made


def _carries_face(shape, face):
    """True when `shape` has a face on the same plane or cylinder as `face` that overlaps it. Other surfaces are
    left to the element history."""
    s = face.Surface
    for g in shape.Faces:
        t = g.Surface
        if t.TypeId != s.TypeId:
            continue
        if s.TypeId == "Part::GeomPlane":
            if abs(abs(s.Axis.dot(t.Axis)) - 1) > 1e-6 or abs((t.Position - s.Position).dot(s.Axis)) > 1e-5:
                continue
        elif s.TypeId == "Part::GeomCylinder":
            if abs(s.Radius - t.Radius) > 1e-6 or abs(abs(s.Axis.dot(t.Axis)) - 1) > 1e-6:
                continue
            d = t.Center - s.Center
            if (d - s.Axis * d.dot(s.Axis)).Length > 1e-5:
                continue
        else:
            continue
        try:
            if face.common(g).Area > 1e-6:
                return True
        except Exception:
            pass
    return False


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
    if kind.startswith("sketch_"):
        return _accepts_sketch(kind, obj, sub)
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
    if kind == "limit":  # where a spaced pattern starts or ends: a flat face, an edge, or a work plane
        if not sub:
            return tid in ("App::Plane", "PartDesign::Plane")
        if sub.startswith("Edge"):
            return el is not None
        return sub.startswith("Face") and el is not None and el.Surface.TypeId == "Part::GeomPlane"
    if kind == "plane":
        if not sub:
            return tid in ("App::Plane", "PartDesign::Plane")
        return sub.startswith("Face") and el is not None and el.Surface.TypeId == "Part::GeomPlane"
    return False


def _accepts_sketch(kind, sk, sub):
    """Picks inside the sketch being edited: its own lines/arcs/circles/points, axes and origin."""
    from incad.core import sketch_patterns as sp
    if sk is None or sk.TypeId != "Sketcher::SketchObject" or not sub:
        return False
    try:
        geo, pos = sp.element(sk, sub)
    except (ValueError, IndexError):
        return False
    if kind == "sketch_point":
        return pos != 0  # any vertex, a projected point, the origin ('RootPoint' is (-1, 1))
    if geo in (-1, -2):  # H_Axis / V_Axis
        return kind == "sketch_direction" and pos == 0
    t = sp.geometry_type(sk, geo)
    if kind == "sketch_geometry":
        return geo >= 0 and pos == 0 and t in sp.SUPPORTED  # the sketch's own geometry, never a projection
    if kind == "sketch_direction":
        return pos == 0 and t == "Part::GeomLineSegment"
    if kind == "sketch_limit":
        return pos != 0 or t == "Part::GeomLineSegment"
    if kind == "sketch_path":
        return geo >= 0 and pos == 0 and t in sp.PATH_TYPES
    return False


_EMPTY_HINT = {"feature": "Click a feature (tree or view)…", "plane": "Click a face or work plane…",
               "limit": "Click a face, edge or work plane…", "sketch_geometry": "Click the geometry to repeat…",
               "sketch_direction": "Click a line (or the X/Y axis)…", "sketch_point": "Click a point…",
               "sketch_limit": "Click a line or a point…", "sketch_path": "Click the path's lines, arcs or splines…"}
_PLURAL.update({"sketch_geometry": "items", "sketch_limit": "items", "sketch_path": "segments"})
_SKETCH_NAMES = {"H_Axis": "X axis", "V_Axis": "Y axis", "RootPoint": "Origin"}


def _sketch_element_label(sk, sub):
    from incad.core import sketch_patterns as sp
    if sub in _SKETCH_NAMES:
        return _SKETCH_NAMES[sub]
    try:
        geo, pos = sp.element(sk, sub)
        kind = {"Part::GeomLineSegment": "Line", "Part::GeomArcOfCircle": "Arc", "Part::GeomCircle": "Circle",
                "Part::GeomPoint": "Point"}.get(sp.geometry_type(sk, geo), "Curve")
    except Exception:
        return sub
    if geo < -2:  # projected (external) geometry: numbered as FreeCAD shows it, points without a number
        if kind == "Point" or pos != 0:
            return "Projected point" if kind == "Point" else "Projected %s %d %s" % (
                kind.lower(), -geo - 2, {1: "start", 2: "end", 3: "centre"}.get(pos, ""))
        return "Projected %s %d" % (kind.lower(), -geo - 2)
    if pos == 3:
        return "%s %d centre" % (kind, geo + 1)
    if pos in (1, 2):
        return "%s %d %s" % (kind, geo + 1, "start" if pos == 1 else "end")
    return "%s %d" % (kind, geo + 1)


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
        if kind.startswith("sketch_") and sub and obj is not None:
            return _sketch_element_label(obj, sub)
        label = obj.Label if obj is not None else name
        return "%s · %s" % (label, sub) if sub else label
    if kind == "feature" and len(items) <= 3:  # names say what is picked; a bare count doesn't
        try:
            import FreeCAD as App
            doc = App.ActiveDocument
            names = [(doc.getObject(i.partition(":")[0]).Label if doc is not None and doc.getObject(
                i.partition(":")[0]) is not None else i.partition(":")[0]) for i in items]
        except Exception:
            names = [i.partition(":")[0] for i in items]
        return " + ".join(names)
    return "%d %s" % (len(items), _PLURAL.get(kind, "items"))


def link_sub(pairs):
    """(obj, [subs]) for a PartDesign LinkSub: every pick must be on the same object."""
    if not pairs:
        raise ValueError("Select at least one item")
    obj = pairs[0][0]
    if any(o is not obj for o, _ in pairs):
        raise ValueError("Pick the items on one feature (the latest one)")
    return obj, [s for _, s in pairs]
