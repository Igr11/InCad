"""Inventor's browser link both ways: which faces of the shown solid a feature made (its row lights them in the
3D view) and which feature made a face or edge clicked on the solid (its row lights in the tree).

A feature 'made' an element when a point inside it lies on no element of the same geometry in its base (a face
the feature only trimmed stays its older feature's); a face of the shown solid (the body's Tip) belongs to the
feature whose new element it lies on."""
import Part

TOL = 1e-5
_cache = {}  # (feature name, shape hash, base hash, kind) -> the elements the feature brought in


def _elements(shape, kind):
    return shape.Faces if kind == "Face" else shape.Edges


def _shape(obj):
    try:
        s = obj.Shape
        return None if s.isNull() else s
    except Exception:
        return None


def _geom_type(el, kind):
    try:
        return (el.Surface if kind == "Face" else el.Curve).TypeId
    except Exception:
        return ""


def _point(el, kind):
    """A point inside the element (a face's centre of mass can lie in its hole)."""
    if kind == "Edge":
        return el.valueAt(0.5 * (el.FirstParameter + el.LastParameter))
    pts, tris = el.tessellate(0.5)
    p = el.CenterOfMass
    if tris:
        a, b, c = (pts[i] for i in tris[0])
        p = (a + b + c) * (1.0 / 3.0)  # inside the face, but on a chord: brought back onto the surface
    try:
        u, v = el.Surface.parameter(p)
        return el.Surface.value(u, v)
    except Exception:
        return p


def _on(point, el):
    bb = el.BoundBox
    bb.enlarge(TOL * 10)
    if not bb.isInside(point):
        return False
    return el.distToShape(Part.Vertex(point))[0] < TOL


def _new(feature, kind):
    shape = _shape(feature)
    if shape is None:
        return []
    base = getattr(feature, "BaseFeature", None)
    base_shape = _shape(base) if base is not None else None
    key = (feature.Name, shape.hashCode(), base_shape.hashCode() if base_shape is not None else 0, kind)
    if key not in _cache:
        old = list(_elements(base_shape, kind)) if base_shape is not None else []
        out = []
        for el in _elements(shape, kind):
            t, p = _geom_type(el, kind), _point(el, kind)
            # trimmed by this feature but on the same face (or edge) as before: still the older feature's
            if not any(_geom_type(o, kind) == t and _on(p, o) for o in old):
                out.append(el)
        _cache[key] = out
    return _cache[key]


def _made_by(feature, el, kind):
    t, p = _geom_type(el, kind), _point(el, kind)
    return any(_geom_type(n, kind) == t and _on(p, n) for n in _new(feature, kind))


def _applied(feature):
    """(body, tip) when the feature is applied (at or above End of Part), else (body, None)."""
    body = feature.getParentGeoFeatureGroup() if hasattr(feature, "getParentGeoFeatureGroup") else None
    if body is None or body.TypeId != "PartDesign::Body" or body.Tip is None:
        return body, None
    group = list(body.Group)
    if feature not in group or body.Tip not in group or group.index(feature) > group.index(body.Tip):
        return body, None
    return body, body.Tip


def on_tip(feature, kind="Face"):
    """Names of the shown solid's faces (or edges) this feature made; [] when it is rolled back or made none."""
    body, tip = _applied(feature)
    shape = _shape(tip) if tip is not None else None
    if shape is None:
        return []
    return ["%s%d" % (kind, i + 1) for i, e in enumerate(_elements(shape, kind)) if _made_by(feature, e, kind)]


def creator(tip, sub):
    """The feature that made this face or edge of the shown solid (the latest one that brought it in)."""
    kind = "Face" if sub.startswith("Face") else "Edge" if sub.startswith("Edge") else None
    shape = _shape(tip)
    body = tip.getParentGeoFeatureGroup() if hasattr(tip, "getParentGeoFeatureGroup") else None
    if kind is None or shape is None or body is None:
        return tip
    try:
        el = shape.getElement(sub)
    except Exception:
        return tip
    group = list(body.Group)
    upto = group.index(tip) if tip in group else len(group) - 1
    for f in reversed(group[:upto + 1]):
        if f.isDerivedFrom("PartDesign::Feature") and f.TypeId not in (
                "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point") and _made_by(f, el, kind):
            return f
    return tip
