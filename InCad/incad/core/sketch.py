"""InCad sketches: create on a plane or a flat face, status, named dimensions (d0, d1, …) and formulas that use
parameter and dimension names. Pure model logic: no Qt, no GUI."""
import math
import re

import FreeCAD as App

from incad.core import document

DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")
_DNAME = re.compile(r"^d(\d+)$")
PATTERN_PREFIX = "pat"
_PATNAME = re.compile(r"^pat\d+_\d+$")


def is_pattern_name(name):
    """Constraints a sketch pattern added (pat<n>_<i>): never dimensions, never symbols, never auto-named."""
    return bool(name) and _PATNAME.match(name) is not None
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


def is_open_contour(sk):
    """A sketch with normal geometry whose wires are all open (a path, a guide): shown in the part view."""
    try:
        wires = sk.Shape.Wires
        return bool(sk.Shape.Edges) and bool(wires) and not any(w.isClosed() for w in wires)
    except Exception:
        return False


def key_points(sk):
    """[(kind, global Vector)] the view marks on a sketch: a spline's poles ('pole') and the points it passes
    through ('end'), a line's or arc's ends and
    a point ('end'), a circle's or ellipse's centre ('centre'). Projected edges that are normal geometry count;
    construction geometry is skipped; points within
    1e-6 of an earlier one are merged (the first kind wins)."""
    pl = sk.getGlobalPlacement()
    out = []

    def add(kind, p):
        g = pl.multVec(p)
        if not any((g - q).Length < 1e-6 for _, q in out):
            out.append((kind, g))

    normal = []
    for i, geo in enumerate(sk.Geometry):
        try:
            if sk.getConstruction(i):
                continue
        except Exception:
            pass
        normal.append(geo)
    normal += defining_geometry(sk)  # projected edges that are normal geometry (Inventor)
    for geo in normal:
        tid = geo.TypeId
        if tid == "Part::GeomBSplineCurve":
            for p in geo.getPoles():
                add("pole", p)
            for k in geo.getKnots():  # the points the line passes through (a spline drawn through points)
                add("end", geo.value(k))
        elif tid in ("Part::GeomCircle", "Part::GeomEllipse"):
            add("centre", geo.Center)
        elif tid == "Part::GeomPoint":
            add("end", App.Vector(geo.X, geo.Y, geo.Z))
        elif hasattr(geo, "StartPoint") and hasattr(geo, "EndPoint"):
            add("end", geo.StartPoint)
            add("end", geo.EndPoint)
    return out


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
            if c.Type in DIMENSIONAL and c.Name and not is_pattern_name(c.Name):
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


def set_dimension(doc, name, text, everything=True):
    """Set a named dimension to a value ('40 mm', '12') or a formula ('d3*2', 'Width/2').
    Call inside safe.run_safely: a failing formula raises and must be rolled back."""
    sk, index = find_dimension(doc, name)
    if sk is None:
        raise ValueError("No dimension named %r" % name)
    text = (text or "").strip()
    if not text:
        raise ValueError("%s needs a value" % name)
    path = "Constraints." + name
    from incad.core import overall_dims
    held = overall_dims.hold_radii(sk, index)  # an overall length: the slot gets longer, not wider
    try:
        _set_value(doc, sk, index, name, path, text, everything and not held)  # the part once, below
    finally:
        overall_dims.release(sk, held)
    if held:
        doc.recompute() if everything else doc.recompute([sk])


def _set_value(doc, sk, index, name, path, text, everything):
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
    doc.recompute() if everything else doc.recompute([sk])  # the open sketch alone: the part follows on Finish
    if "Invalid" in sk.State or status(sk)["conflicting"]:
        from incad.core import model
        raise ValueError("%s = %s cannot be satisfied: %s" % (name, text, model.friendly(sk.getStatusString())))


def drop_redundant(sk):
    """Take off the constraints the sketch has twice (FreeCAD's own pick), until it solves; the status line says
    which. Returns the types taken off."""
    from incad.core import log
    gone = []
    for _ in range(4):
        if sk.solve() != -2:
            break
        before = [c.Type for c in sk.Constraints]
        sk.autoRemoveRedundants(True)
        after = [c.Type for c in sk.Constraints]
        if len(after) == len(before):
            break
        left = list(before)
        for t in after:
            left.remove(t)
        gone += left
    if gone:
        log.report("info", "Took off what the sketch had already: %s" % ", ".join(gone))
    return gone


IMPLIED = ("Horizontal", "Vertical", "Parallel", "Perpendicular", "Equal")  # ties a newer one may make redundant
TIES = IMPLIED + ("Coincident", "PointOnObject", "Tangent", "Symmetric")  # what the constraint tools add


def redundant(sk):
    """0-based indexes of the constraints FreeCAD finds redundant (none when the sketch solves)."""
    return [i - 1 for i in sk.RedundantConstraints] if sk.solve() == -2 else []


def make_room(sk, new):
    """The constraints `new` (indexes a tool just added, at the end) repeat what older ones tie already (a slot's arc
    centres made symmetric about an axis while its line is Horizontal): the sketch stops solving, FreeCAD naming any
    of the ties that repeat each other. The older ties of the IMPLIED kinds that the new ones cover go instead (the
    named ones first, then newest first); when that is not enough, FreeCAD's own pick goes (drop_redundant).
    Returns the types taken off."""
    from incad.core import log
    red = redundant(sk)
    if not red:
        return []
    first = min(new)
    added = [sk.Constraints[i].Type for i in new]
    gone = []
    while red:
        older = [i for i in range(first) if sk.Constraints[i].Type in IMPLIED]
        older.sort(key=lambda i: (i not in red, -i))
        if not older:
            break
        i = older[0]
        c = sk.Constraints[i]
        sk.delConstraint(i)
        new = [n - 1 for n in new]  # the tool's ties move down by one
        first = min(new)
        left = redundant(sk)
        if len(left) < len(red):
            gone.append(c.Type)
            red = left
        else:
            sk.addConstraint(c)  # needed after all: back at the end, past the tool's (never tried again)
            red = redundant(sk)
    if gone:
        log.report("info", "%s covers what %s tied: took %s off" % (
            ", ".join(sorted(set(added))), ", ".join(gone), "it" if len(gone) == 1 else "them"))
    if red:
        gone += drop_redundant(sk)
    return gone


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
    return [i for i, c in enumerate(sk.Constraints) if c.Type not in DIMENSIONAL and not is_pattern_name(c.Name)]


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


def toggle_construction(sk, geo_ids):
    """Inventor's Construction on picked edges: those edges (only them: one side of a rectangle becomes an axis, the
    user) become construction, or normal again when all of them already are construction.
    A projected (external) edge switches FreeCAD's own 'defining' flag; the choice of construction is remembered
    (CHOSEN_PROP) so adopt_projections leaves it. Returns the ids changed."""
    flags = _projected_flags(sk)
    external = [i for i in geo_ids if i in flags]
    geo_ids = [i for i in geo_ids if 0 <= i < sk.GeometryCount]
    states = [sk.getConstruction(i) for i in geo_ids] + [not flags[i][0] for i in external]
    if not states:
        return []
    make = not all(states)
    ids = sorted(set(geo_ids))
    for i in ids:
        if sk.getConstruction(i) != make:
            sk.setConstruction(i, make)
    changed = set_projected_construction(sk, external, make)
    sk.Document.recompute()
    return ids + changed


# ----- projected (external) edges -----
CHOSEN_PROP = "InCadProjConstruction"  # Refs of projected edges the user switched to construction


def _external_ext(geo):
    for x in geo.getExtensions():
        if "External" in type(x).__name__:
            return x
    return None


def _projected_flags(sk):
    """{geo id: (defining, Ref)} for the projected edges (external geometry minus the H/V axes and points), in
    order; sk.ExternalGeo read once."""
    try:
        geos = sk.ExternalGeo
    except Exception:
        return {}
    out = {}
    for i in range(2, len(geos)):
        if geos[i].TypeId == "Part::GeomPoint":
            continue
        x = _external_ext(geos[i])
        out[-i - 1] = (bool(x is not None and x.testFlag("Defining")), (x.Ref if x is not None else "") or "")
    return out


def projected(sk):
    """Geo ids (-3, -4, …) of the sketch's projected edges: its external geometry minus the H/V axes and points."""
    return list(_projected_flags(sk))


def defining_geometry(sk):
    """The projected edges that are normal geometry (Part geometries, sketch coordinates)."""
    flags = _projected_flags(sk)
    if not flags:
        return []
    geos = sk.ExternalGeo
    return [geos[-g - 1] for g, (on, _ref) in flags.items() if on]


def is_defining(sk, geo_id):
    """Is the projected edge normal geometry (part of the profile)? FreeCAD's getConstruction says True for every
    external edge, so it is never asked."""
    try:
        x = _external_ext(sk.ExternalGeo[-geo_id - 1])
    except Exception:
        return False
    return bool(x is not None and x.testFlag("Defining"))


def set_defining(sk, geo_ids, on):
    """Projected edges become normal (on) or construction; returns the ids changed. The caller recomputes."""
    geos = sk.ExternalGeo
    changed = []
    for g in geo_ids:
        i = -g - 1
        if g > -3 or i >= len(geos):
            continue
        x = _external_ext(geos[i])
        if x is None or bool(x.testFlag("Defining")) == bool(on):
            continue
        x.setFlag("Defining", bool(on))
        geos[i].setExtension(x)
        changed.append(g)
    if changed:
        sk.ExternalGeo = geos
    return changed


def set_projected_construction(sk, geo_ids, construction):
    """The user's choice for projected edges: construction (remembered in CHOSEN_PROP, so adopt_projections leaves
    them) or normal again. Returns the ids changed; the caller recomputes."""
    flags = _projected_flags(sk)
    changed = set_defining(sk, geo_ids, not construction)
    refs = {flags[g][1] for g in geo_ids if g in flags} - {""}
    if refs:
        before = _strings(sk, CHOSEN_PROP)
        after = (before | refs) if construction else (before - refs)
        if after != before:
            _set_strings(sk, CHOSEN_PROP, after, "Projected edges switched to construction by the user")
    return changed


def _strings(sk, prop):
    return set(getattr(sk, prop, None) or [])


def _set_strings(sk, prop, refs, doc):
    if prop not in sk.PropertiesList:
        sk.addProperty("App::PropertyStringList", prop, "InCad", doc, 0, False, True)
    setattr(sk, prop, sorted(refs))


def users(sk):
    """What is built on the sketch: the features that consume it (features.common.consumers: a Profile, a Sweep's
    path or a Loft's section, a Split's knife, the features on its areas), a revolve whose axis is one of its lines,
    and its InCad area profiles that a feature uses (separate sketches that name their source only in their data;
    one left over from a cancelled dialog used nothing, yet kept the sketch's projected edges construction). An
    expression using one of its dimensions, a sketch attached to it or projecting from it does not make it used."""
    from incad.core import regions
    from incad.features import common
    out = list(common.consumers(sk))
    for o in sk.InList:
        axis = getattr(o, "ReferenceAxis", None) if "ReferenceAxis" in getattr(o, "PropertiesList", ()) else None
        if axis and axis[0] is sk and o not in out:
            out.append(o)
    return out + [p for p in regions.profiles_of(sk) if p not in out and regions.users(p)]


def pending_projections(sk):
    """Refs of the projected edges that are construction without being the user's choice: in a used sketch, the
    ones adopt_projections leaves for the user."""
    chosen = _strings(sk, CHOSEN_PROP)
    return {ref for on, ref in _projected_flags(sk).values() if not on and ref not in chosen}


def adopt_projections(sk, notes=None):
    """Inventor: projected edges are normal geometry. In a sketch NOTHING is built on yet (see users), every
    projected edge becomes defining unless the user switched it to construction (CHOSEN_PROP), and the old
    Construction button's tied normal copies are removed, their projected edges taking their place. A used sketch
    is left exactly as it is, so no feature or area changes behind the user's back: its new projections stay
    construction and `notes` (a list) gets one line saying so; once nothing uses the sketch, the next call adopts.
    One burst of changes at most, no trial recomputes; a second call does nothing. True when it changed something
    (then it has recomputed). Makes no undo step. Never inside an open undo step (a feature dialog's, a Sketcher
    tool's) and never while the document restores or recomputes (the GUI's progress bar runs deferred handlers
    mid-recompute): the next call adopts."""
    doc = sk.Document
    if getattr(doc, "Restoring", False) or getattr(doc, "Recomputing", False) or doc.HasPendingTransaction:
        return False
    flags = _projected_flags(sk)
    if not flags:
        return False
    chosen = _strings(sk, CHOSEN_PROP)
    todo = [g for g, (on, ref) in flags.items() if not on and ref not in chosen]
    if not todo:
        return False
    used = users(sk)
    if used:
        if notes is not None:
            notes.append("%s is used by %s: projected edges stay construction — Construction makes them normal" % (
                sk.Label, ", ".join(o.Label for o in used[:3]) + (" …" if len(used) > 3 else "")))
        return False
    copies = _old_copies(sk)
    if copies:
        construction = {ext for copy, ext in copies.items() if sk.getConstruction(copy)}  # a copy switched back
        refs = {flags[g][1] for g in construction} - {""}
        lost = _remove_copies(sk, copies)
        if refs - chosen:
            chosen |= refs
            _set_strings(sk, CHOSEN_PROP, chosen, "Projected edges switched to construction by the user")
        todo = [g for g in todo if g not in construction]
        if lost and notes is not None:
            notes.append("%s: %s on the old copies of projected edges could not move to the projected edges" % (
                sk.Label, ", ".join(lost)))
    set_defining(sk, todo, True)
    doc.recompute()
    return True


def _same_curve(a, b, tol=1e-6):
    import Part
    if a.TypeId != b.TypeId:
        return False
    try:
        ea, eb = a.toShape(), b.toShape()
        if abs(ea.Length - eb.Length) > tol:
            return False
        p0, p1 = ea.FirstParameter, ea.LastParameter
        return all(eb.distToShape(Part.Vertex(ea.valueAt(p0 + (p1 - p0) * k / 4.0)))[0] < tol for k in range(5))
    except Exception:
        return False


def _old_copies(sk):
    """{copy index: projected geo id} for the normal copies the old Construction button put on projected edges:
    the same curve, tied to its ends (centre for a circle or ellipse), or Blocked on a closed spline."""
    out = {}
    ids = projected(sk)
    if not ids:
        return out
    geos = sk.ExternalGeo
    for ext in ids:
        for i in _copies_of_external(sk, ext):
            if i not in out and _same_curve(sk.Geometry[i], geos[-ext - 1]):
                out[i] = ext
    blocked = {c.First for c in sk.Constraints if c.Type == "Block" and c.First >= 0}
    for i in sorted(blocked - set(out)):
        g = sk.Geometry[i]
        if not getattr(g, "isPeriodic", lambda: False)():
            continue
        for ext in ids:
            if _same_curve(g, geos[-ext - 1]):
                out[i] = ext
                break
    return out


def _remove_copies(sk, copies):
    """Delete the copies; constraints joining other geometry to a copy move to its projected edge (same point
    numbers). The ties themselves go; a constraint left on projected geometry alone goes (FreeCAD refuses it).
    Returns the names (or kinds) of constraints that could not move."""
    gone = sorted(copies)
    lost = []

    def moved(g):
        if g in copies:
            return copies[g]
        if g >= 0:
            return g - sum(1 for c in gone if c < g)
        return g

    keep = []
    for c in sk.Constraints:
        refs = [g for g in (c.First, c.Second, c.Third) if g != GEO_UNDEF]
        if not any(g in copies for g in refs):
            continue
        if c.Type == "Block" or (c.Type == "Coincident" and
                                 (copies.get(c.First) == c.Second or copies.get(c.Second) == c.First)):
            continue  # the tie
        if all(moved(g) < 0 for g in refs):
            if c.Name or c.Type in DIMENSIONAL:
                lost.append(c.Name or c.Type)  # a dimension on the copy alone: FreeCAD refuses it on projections
            continue
        for field in ("First", "Second", "Third"):  # c is the sketch's copy (sk.Constraints copies): ours to change
            g = getattr(c, field)
            if g != GEO_UNDEF:
                setattr(c, field, moved(g))
        expr = dict(sk.ExpressionEngine).get(".Constraints.%s" % c.Name) if c.Name else None
        keep.append((c, c.Name, expr))
    for i in reversed(gone):
        sk.delGeometry(i)

    def key(c):
        ends = sorted([(c.First, c.FirstPos), (c.Second, c.SecondPos)]) if c.Type == "Coincident" else \
            [(c.First, c.FirstPos), (c.Second, c.SecondPos)]
        return (c.Type, tuple(ends), c.Third, c.ThirdPos)
    there = {key(c) for c in sk.Constraints}  # FreeCAD 1.1 moves some coincidences itself when a geometry goes
    for n, name, expr in keep:
        if key(n) in there:
            continue
        try:
            k = sk.addConstraint(n)
            if name and sk.Constraints[k].Name != name:
                sk.renameConstraint(k, name)
            if expr:
                sk.setExpression(".Constraints.%s" % name, expr)
        except Exception:
            lost.append(name or n.Type)
    return lost


def _copies_of_external(sk, geo_id):
    """Normal geometry tied by Coincident constraints to the projected edge at both ends or at the centre (what the
    old Construction button made; _old_copies also checks it is the same curve)."""
    tied = {}
    for c in sk.Constraints:
        if c.Type != "Coincident":
            continue
        if c.Second == geo_id and c.First >= 0:
            tied.setdefault(c.First, set()).add(c.FirstPos)
        elif c.First == geo_id and c.Second >= 0:
            tied.setdefault(c.Second, set()).add(c.SecondPos)
    return [i for i, ends in tied.items() if ends in ({1, 2}, {3})]


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


def dimension_snapshot(sk):
    """{name: {type, value, expr}} of the named driving dimensions, taken after every change: the next change
    is compared with it (FreeCAD's Dimension tool replaces a dimension when it is placed)."""
    out = {}
    for c in sk.Constraints:
        if c.Name and c.Type in DIMENSIONAL and c.Driving and not is_pattern_name(c.Name):
            out[c.Name] = {"type": c.Type, "value": c.Value, "expr": _expression_of(sk, "Constraints." + c.Name)}
    return out


def vanished_dimensions(sk, known):
    names = {c.Name for c in sk.Constraints if c.Name}
    return [n for n in known if n not in names and not is_pattern_name(n)]


def _fresh_dimensions(sk):
    return [i for i, c in enumerate(sk.Constraints) if c.Type in DIMENSIONAL and not c.Name and c.Driving]


def reconcile_replaced(sk, known):
    """One named dimension gone and one unnamed appeared in the same change: it is the same dimension replaced
    (FreeCAD 1.1's Dimension tool does that at the placing click). It gets its name back and the value or formula
    the user gave it, in one undo step. Returns the name, or None when nothing was replaced."""
    gone, fresh = vanished_dimensions(sk, known), _fresh_dimensions(sk)
    if len(gone) != 1 or len(fresh) != 1:
        return None
    name, index, doc = gone[0], fresh[0], sk.Document
    was = known[name]
    # Never inside an undo step of our own: FreeCAD's Dimension tool keeps its own step open while the dimension
    # is placed, and opening another breaks its bookkeeping (it then re-adds the dimension on every update —
    # probed: a sketch full of copies). While that step is open only the name is put back; the value/formula
    # follows once the tool has committed (the next change).
    sk.renameConstraint(index, name)
    if doc.HasPendingTransaction:
        return name
    if was["expr"]:
        sk.setExpression("Constraints." + name, was["expr"])
    elif sk.Constraints[index].Type == was["type"] and abs(sk.Constraints[index].Value - was["value"]) > 1e-9:
        sk.setDatum(name, App.Units.Quantity(was["value"], "deg" if was["type"] == "Angle" else "mm"))
    doc.recompute()
    return name
