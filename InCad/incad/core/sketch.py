"""InCad sketches: create on a plane or a flat face, status, named dimensions (d0, d1, …) and formulas that use
parameter and dimension names. Pure model logic: no Qt, no GUI."""
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
    names = {c.Name for sk in _sketches(doc) for c in sk.Constraints if c.Name}
    return names | {n for n, _, _ in document.list_parameters(doc)}


def name_new_dimensions(doc):
    """Give every unnamed driving dimension the next free dN name; returns the names given."""
    numbers = [int(m.group(1)) for m in (_DNAME.match(n) for n in _used_names(doc)) if m]
    nxt = max(numbers) + 1 if numbers else 0
    added = []
    for sk in _sketches(doc):
        for i, c in enumerate(sk.Constraints):
            if c.Type in DIMENSIONAL and not c.Name and c.Driving:
                name = "d%d" % nxt
                nxt += 1
                sk.renameConstraint(i, name)
                added.append(name)
    return added


def _refs(doc):
    """plain name -> FreeCAD expression path, for user parameters and named dimensions."""
    refs = {n: "%s.%s" % (document.PARAMS_NAME, n) for n, _, _ in document.list_parameters(doc)}
    for name, sk, _ in dimensions(doc):
        refs[name] = "%s.Constraints.%s" % (sk.Name, name)
    return refs


def to_expression(doc, text):
    refs = _refs(doc)
    return _TOKEN.sub(lambda m: refs.get(m.group(1), m.group(1)), text)


def to_display(doc, expr):
    for path, name in sorted(((p, n) for n, p in _refs(doc).items()), key=lambda pn: -len(pn[0])):
        expr = expr.replace(path, name)
    return re.sub(r"(?<![\w])\.Constraints\.([A-Za-z_]\w*)", r"\1", expr)


def _expression_of(obj, path):
    for p, e in obj.ExpressionEngine:
        if p.lstrip(".") == path:
            return e
    return ""


def model_parameters(doc):
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
            sk.setExpression(path, to_expression(doc, text))
        except Exception as e:
            raise ValueError("Invalid formula for %s: %s" % (name, e))
    doc.recompute()
    if "Invalid" in sk.State or status(sk)["conflicting"]:
        raise ValueError("%s = %s cannot be satisfied: %s" % (name, text, sk.getStatusString()))


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
