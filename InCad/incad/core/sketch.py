"""InCad sketches: create on a plane or a flat face, status, named dimensions (d0, d1, …) and formulas that use
parameter and dimension names. Pure model logic: no Qt, no GUI."""
import math
import re

import FreeCAD as App

from incad.core import document

DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")
_DNAME = re.compile(r"^d(\d+)$")
_TOKEN = re.compile(r"(?<![\w.<>])([A-Za-z_][A-Za-z0-9_]*)(?![\w(.])")


def is_sketch(obj):
    return obj is not None and getattr(obj, "TypeId", "") == "Sketcher::SketchObject"


def valid_support(obj, sub=""):
    """True for an origin plane, a datum plane or a flat face."""
    if obj is None:
        return False
    if obj.TypeId in ("App::Plane", "PartDesign::Plane"):
        return True
    if sub.startswith("Face"):
        try:
            face = obj.getSubObject(sub)
        except Exception:
            return False
        return face is not None and face.Surface.TypeId == "Part::GeomPlane"
    return False


def _next_label(doc, stem):
    used = {o.Label for o in doc.Objects}
    n = 1
    while "%s%d" % (stem, n) in used:
        n += 1
    return "%s%d" % (stem, n)


def make_sketch(body, support, sub=""):
    """A sketch in `body`, attached to `support` (+ face name), placed after End of Part."""
    if not valid_support(support, sub):
        raise ValueError("Pick a plane or a flat face to sketch on")
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    sk.AttachmentSupport = [(support, sub)]
    sk.MapMode = "FlatFace"
    sk.Label = _next_label(body.Document, "Sketch")
    body.Document.recompute()
    return sk


def status(sk):
    return {"dof": sk.DoF, "fully": bool(sk.FullyConstrained), "conflicting": list(sk.ConflictingConstraints),
            "redundant": list(sk.RedundantConstraints), "malformed": list(sk.MalformedConstraints)}


def _sketches(doc):
    return [o for o in doc.Objects if is_sketch(o)]


def dimensions(doc):
    """[(name, sketch, index)] for every named dimension, in document order."""
    out = []
    for sk in _sketches(doc):
        for i, c in enumerate(sk.Constraints):
            if c.Type in DIMENSIONAL and c.Name:
                out.append((c.Name, sk, i))
    return out


def find_dimension(doc, name):
    for n, sk, i in dimensions(doc):
        if n == name:
            return sk, i
    return None, None


def _used_names(doc):
    from incad.core import model
    return model.used_names(doc)


NEXT_KEY = "InCadNextDimension"


def _next_number(doc):
    """Never reuse a dN: a counter in the file (doc.Meta), so a deleted d5 does not come back for a new dimension."""
    numbers = [int(m.group(1)) for m in (_DNAME.match(n) for n in _used_names(doc)) if m]
    try:
        stored = int(doc.Meta.get(NEXT_KEY, "0"))
    except ValueError:
        stored = 0
    return max([stored] + [n + 1 for n in numbers])


def name_new_dimensions(doc):
    """Give every unnamed driving dimension the next dN (never reused; see model.claim_name)."""
    from incad.core import model
    added = []
    for sk in _sketches(doc):
        for i, c in enumerate(sk.Constraints):
            if c.Type in DIMENSIONAL and not c.Name and c.Driving:
                name = model.claim_name(doc)
                sk.renameConstraint(i, name)
                added.append(name)
    return added


def to_expression(doc, text):
    from incad.core import model
    return model.to_expression(doc, text)


def to_display(doc, expr):
    from incad.core import model
    return model.to_display(doc, expr)


def _expression_of(obj, path):
    for p, e in obj.ExpressionEngine:
        if p.lstrip(".") == path:
            return e
    return ""


def dimension_parameters(doc):
    """[(name, formula with plain names or '', value text)] for every named dimension."""
    rows = []
    for name, sk, _ in dimensions(doc):
        expr = _expression_of(sk, "Constraints." + name)
        rows.append((name, to_display(doc, expr) if expr else "", document._format(sk.getDatum(name))))
    return rows


def set_dimension(doc, name, text):
    """Set a named dimension to a value ('40 mm', '12') or a formula ('d3*2', 'Width/2').
    Call inside safe.run_safely: a failing formula raises and must be rolled back."""
    sk, index = find_dimension(doc, name)
    if sk is None:
        raise ValueError("No dimension named %r" % name)
    text = (text or "").strip()
    if not text:
        raise ValueError("%s needs a value" % name)
    path = "Constraints." + name
    try:
        quantity = App.Units.Quantity(text)
    except Exception:
        quantity = None
    if quantity is not None:
        if quantity.Unit == App.Units.Quantity("1").Unit:  # a plain number: the part's length unit or degrees
            unit = "deg" if sk.Constraints[index].Type == "Angle" else (document.part_units(doc) or "mm")
            quantity = App.Units.Quantity("%s %s" % (quantity.Value, unit))
        sk.setExpression(path, None)
        try:
            sk.setDatum(name, quantity)
        except Exception as e:
            raise ValueError("%s cannot be %s: %s" % (name, text, e))
    else:
        try:
            from incad.core import model
            unit = "deg" if sk.Constraints[index].Type == "Angle" else (document.part_units(doc) or "mm")
            sk.setExpression(path, to_expression(doc, model.with_units(text, unit)))
        except Exception as e:
            from incad.core import model
            raise ValueError("%s: %s" % (name, model.friendly(str(e))))
    doc.recompute()
    if "Invalid" in sk.State or status(sk)["conflicting"]:
        from incad.core import model
        raise ValueError("%s = %s cannot be satisfied: %s" % (name, text, model.friendly(sk.getStatusString())))


def rename_dimension(doc, old, new):
    sk, index = find_dimension(doc, old)
    if sk is None:
        raise ValueError("No dimension named %r" % old)
    if not document._NAME_RE.match(new or ""):
        raise ValueError("A name starts with a letter or _ and has only letters, digits and _ (got %r)" % new)
    if document._is_literal(new):
        raise ValueError("%r is a unit symbol; choose another name" % new)
    if new != old and new in _used_names(doc):
        raise ValueError("%r is already used" % new)
    sk.renameConstraint(index, new)
    doc.recompute()


def model_parameters(doc):
    """Dimensions and feature values (see incad.core.model)."""
    from incad.core import model
    return model.model_parameters(doc)


def _symbol_constraints(sk):
    return [i for i, c in enumerate(sk.Constraints) if c.Type not in DIMENSIONAL]


def constraints_hidden(sk):
    """Are the constraint symbols hidden? (dimensions always stay visible, as in Inventor)"""
    ids = _symbol_constraints(sk)
    return bool(ids) and all(sk.getVirtualSpace(i) for i in ids)


def set_constraints_hidden(sk, hide):
    """Hide/show constraint symbols by moving them to FreeCAD's virtual space; dimensions stay."""
    ids = _symbol_constraints(sk)
    if ids:
        sk.setVirtualSpace(ids, bool(hide))


def _joined(c):
    """The two geometries a constraint joins end to end (coincident ends, or a tangent join at the ends)."""
    if c.First < 0 or c.Second < 0 or c.FirstPos == 0 or c.SecondPos == 0:
        return None
    if c.Type == "Coincident" or c.Type == "Tangent":
        return c.First, c.Second
    return None


def chain(sk, geo_ids):
    """The edges joined end to end with the given ones (a polygon's sides, a slot's arcs and lines). Points on a
    curve don't join, so a polygon's guide circle is not part of its sides."""
    links = {}
    for c in sk.Constraints:
        pair = _joined(c)
        if pair:
            a, b = pair
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)
    found, todo = set(), list(geo_ids)
    while todo:
        g = todo.pop()
        if g in found:
            continue
        found.add(g)
        todo.extend(links.get(g, ()))
    return found


def toggle_construction(sk, geo_ids):
    """Inventor's Construction on picked edges: their whole profiles become construction, or normal again when
    already all construction."""
    ids = sorted(chain(sk, geo_ids))
    make = not all(sk.getConstruction(i) for i in ids)
    for i in ids:
        if sk.getConstruction(i) != make:
            sk.setConstruction(i, make)
    sk.Document.recompute()
    return ids


SNAP_TOL = 1e-6


def _polygon_circles(sk, first):
    """Construction circles from `first` on that carry a polygon's corners (points on them from line ends)."""
    found = []
    for i in range(first, sk.GeometryCount):
        if sk.Geometry[i].TypeId != "Part::GeomCircle" or not sk.getConstruction(i):
            continue
        corners = [c for c in sk.Constraints if c.Type == "PointOnObject" and c.Second == i and c.First >= 0]
        if len(corners) >= 3:
            found.append(i)
    return found


def pin_polygon_centres(sk, first=0):
    """Inventor remembers where a polygon's centre was snapped: on the origin it is coincident with it, on an axis
    it lies on that axis. Adds what FreeCAD's polygon tool left out (it can drop its first snap); returns the
    circles pinned."""
    import Sketcher
    pinned = []
    for i in _polygon_circles(sk, first):
        c = sk.Geometry[i].Center
        on_x, on_y = abs(c.y) < SNAP_TOL, abs(c.x) < SNAP_TOL
        ties = {(k.Type, k.Second if k.First == i else k.First) for k in sk.Constraints
                if (k.First == i and k.FirstPos == 3) or (k.Second == i and k.SecondPos == 3)}
        if ("Coincident", -1) in ties:
            continue
        if on_x and on_y:
            sk.addConstraint(Sketcher.Constraint("Coincident", i, 3, -1, 1))
        elif on_x and ("PointOnObject", -1) not in ties:
            sk.addConstraint(Sketcher.Constraint("PointOnObject", i, 3, -1))
        elif on_y and ("PointOnObject", -2) not in ties:
            sk.addConstraint(Sketcher.Constraint("PointOnObject", i, 3, -2))
        else:
            continue
        pinned.append(i)
    return pinned


GEO_UNDEF = -2000


def _datum_points(sk, c):
    """The two points a distance dimension spans (sketch coordinates), as FreeCAD gives its SoDatumLabel."""
    if c.Second == GEO_UNDEF:  # a line's length
        return sk.getPoint(c.First, 1), sk.getPoint(c.First, 2)
    if c.FirstPos and c.SecondPos:
        return sk.getPoint(c.First, c.FirstPos), sk.getPoint(c.Second, c.SecondPos)
    if c.FirstPos and not c.SecondPos:  # point to line: the point and its foot on the line
        p = sk.getPoint(c.First, c.FirstPos)
        a, b = sk.getPoint(c.Second, 1), sk.getPoint(c.Second, 2)
        d = b - a
        t = (p - a).dot(d) / d.dot(d) if d.Length > 1e-12 else 0.0
        return p, a + d * t
    return None


def label_point(sk, name):
    """Where FreeCAD draws the text of a dimension (global), as its SoDatumLabel does: the datum line is the two
    points moved by LabelDistance along the normal; the text sits at its middle, moved by LabelPosition along it.
    None for an unknown name or a kind not handled (angles)."""
    found = [c for c in sk.Constraints if c.Name == name]
    if not found:
        return None
    c = found[0]
    if c.Type in ("Distance", "DistanceX", "DistanceY"):
        pts = _datum_points(sk, c)
        if pts is None:
            return None
        p1, p2 = pts
        if c.Type == "DistanceX":
            d, n = App.Vector(1 if p2.x >= p1.x else -1, 0, 0), App.Vector(0, 1, 0)
        elif c.Type == "DistanceY":
            d, n = App.Vector(0, 1 if p2.y >= p1.y else -1, 0), App.Vector(-1, 0, 0)
        else:
            d = p2 - p1
            if d.Length < 1e-12:
                return None
            d.normalize()
            n = App.Vector(-d.y, d.x, 0)
        local = (p1 + p2) * 0.5 + n * c.LabelDistance + d * c.LabelPosition
    elif c.Type in ("Radius", "Diameter"):
        g = sk.Geometry[c.First]
        d = App.Vector(math.cos(c.LabelPosition), math.sin(c.LabelPosition), 0)
        local = g.Center + d * (g.Radius + c.LabelDistance)
    else:
        return None
    return sk.getGlobalPlacement().multVec(local)
