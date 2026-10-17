"""Inventor's browser link both ways: which faces of the shown solid a feature made (its row lights them in the
3D view) and which feature made a face or edge clicked on the solid (its row lights in the tree).

A feature 'made' an element when a point inside it lies on no element of the same geometry in its base (a face
the feature only trimmed stays its older feature's); a face of the shown solid (the body's Tip) belongs to the
feature whose new element it lies on."""
import Part

TOL = 1e-5
_index = {}  # (shape hash, kind) -> [(enlarged box, element)] of a shape's elements
_points = {}  # (shape hash, kind) -> [(geometry type, a point inside)] of a shape's elements


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


def _cached(store, shape, kind, make):
    key = (shape.hashCode(), kind)
    if key not in store:
        if len(store) > 64:  # shapes of earlier recomputes
            store.clear()
        store[key] = make()
    return store[key]


def _boxes(shape, kind):
    def make():
        out = []
        for o in _elements(shape, kind):
            bb = o.BoundBox
            bb.enlarge(TOL * 10)
            out.append((bb, o))
        return out
    return _cached(_index, shape, kind, make)


def _inner_points(shape, kind):
    return _cached(_points, shape, kind, lambda: [(_geom_type(e, kind), _point(e, kind)) for e in _elements(shape, kind)])


def _on_any(point, t, shape, kind, among=None):
    """The point lies on an element of `shape` (or of `among`, indexes into it) with geometry type t. Boxes first,
    type and distance only for the few elements whose box holds the point."""
    boxes = _boxes(shape, kind)
    for i in (range(len(boxes)) if among is None else among):
        bb, o = boxes[i]
        if bb.isInside(point) and _geom_type(o, kind) == t and o.distToShape(Part.Vertex(point))[0] < TOL:
            return True
    return False


def _brought(feature, point, t, kind):
    """The feature brought in the element at `point` (type t): its shape has one there, its base has none (one
    point tested against each shape: comparing every element with every element of the base took 60-80 s on the
    first click on a 600-face part)."""
    shape = _shape(feature)
    if shape is None or not _on_any(point, t, shape, kind):
        return False
    base = getattr(feature, "BaseFeature", None)
    base_shape = _shape(base) if base is not None else None
    return base_shape is None or not _on_any(point, t, base_shape, kind)


def _made_by(feature, el, kind):
    return _brought(feature, _point(el, kind), _geom_type(el, kind), kind)


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
    # the same rule as creator(): the solid's element whose inner point the feature brought in
    return ["%s%d" % (kind, i + 1) for i, (t, p) in enumerate(_inner_points(shape, kind))
            if _brought(feature, p, t, kind)]


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
    t, p = _geom_type(el, kind), _point(el, kind)
    for f in reversed(group[:upto + 1]):
        if f.isDerivedFrom("PartDesign::Feature") and f.TypeId not in (
                "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point") and _brought(f, p, t, kind):
            return f
    return tip
