"""Sketch patterns: copies of sketch geometry tied to the original by constraints, remembered on the sketch
(InCadPatterns, JSON) so they can be edited or deleted as one thing. Pure model: no transactions, no UI.
Geometry is addressed by permanent ids (setGeometryId), never by index."""
import json
import math
import re

import FreeCAD as App
import Part
import Sketcher

from incad.core import sketch as sketches

RECORD_PROP = "InCadPatterns"
SUPPORTED = ("Part::GeomLineSegment", "Part::GeomArcOfCircle", "Part::GeomCircle", "Part::GeomPoint")
PARAM_KEYS = ("spacing_param", "spacing_param2", "angle_param")


# ----- records -----
def _load(sk):
    text = getattr(sk, RECORD_PROP, "") or ""
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    data.setdefault("patterns", [])
    data.setdefault("next", 1)
    return data


def _store(sk, data):
    if RECORD_PROP not in sk.PropertiesList:
        sk.addProperty("App::PropertyString", RECORD_PROP, "InCad", "Sketch patterns (JSON)")
    setattr(sk, RECORD_PROP, json.dumps(data))


def records(sk):
    return list(_load(sk)["patterns"])


def save_records(sk, recs):
    data = _load(sk)
    data["patterns"] = list(recs)
    _store(sk, data)


def find(sk, name):
    for r in records(sk):
        if r.get("name") == name:
            return r
    return None


def next_name(sk):
    """'Pattern<n>', never handed out twice (the counter lives in the record)."""
    data = _load(sk)
    name = "Pattern%d" % data["next"]
    data["next"] += 1
    _store(sk, data)
    return name


# ----- geometry ids -----
def ensure_id(sk, index):
    """FreeCAD's own permanent id of a geometry: it gives every geometry one, keeps it across deletions and
    reloads and never reuses it, and its element names (the pad's faces) are derived from it, so it is never
    overwritten. Only a geometry without one gets the next free number."""
    gid = sk.getGeometryId(index)
    if gid is None or gid < 0:
        used = [g for g in (sk.getGeometryId(i) for i in range(sk.GeometryCount)) if g is not None]
        gid = max(used + [0]) + 1
        sk.setGeometryId(index, gid)
    return gid


def ref_of(sk, geo, pos):
    """A pick kept by id: [id, pos] for sketch geometry, [geo, pos] (negative) for the axes and the origin."""
    return [geo, pos] if geo < 0 else [ensure_id(sk, geo), pos]


def deref(sk, ref):
    """(geo index, pos) of a stored ref, or None when that geometry is gone."""
    geo, pos = ref
    if geo < 0:
        return geo, pos
    i = index_of(sk, geo)
    return None if i is None else (i, pos)


def sub_of(sk, geo, pos):
    """The sub-element name of (geo, pos) now: 'Edge3', 'Vertex7', 'H_Axis', 'V_Axis', 'RootPoint'."""
    if geo == -1:
        return "RootPoint" if pos == 1 else "H_Axis"
    if geo == -2:
        return "V_Axis"
    if pos == 0:
        return "Edge%d" % (geo + 1)
    v = 0
    while True:
        g, p = sk.getGeoVertexIndex(v)
        if g < -2:
            raise ValueError("No vertex for geometry %d point %d" % (geo, pos))
        if (g, p) == (geo, pos):
            return "Vertex%d" % (v + 1)
        v += 1


def index_of(sk, gid):
    for i in range(sk.GeometryCount):
        if sk.getGeometryId(i) == gid:
            return i
    return None


# ----- elements -----
def element(sk, sub):
    """(geo, pos) of a sketch sub-element name: 'Edge3' -> (2, 0); 'Vertex2' -> the geometry and its PointPos;
    'H_Axis' -> (-1, 0); 'V_Axis' -> (-2, 0); 'RootPoint' -> (-1, 1)."""
    if sub == "H_Axis":
        return -1, 0
    if sub == "V_Axis":
        return -2, 0
    if sub == "RootPoint":
        return -1, 1
    if sub.startswith("Edge"):
        return int(sub[4:]) - 1, 0
    if sub.startswith("Vertex"):
        geo, pos = sk.getGeoVertexIndex(int(sub[6:]) - 1)
        if geo < -2:  # FreeCAD answers (-2000, 0) for a vertex that does not exist
            raise ValueError("Not a sketch element: %s" % sub)
        return geo, pos
    raise ValueError("Not a sketch element: %s" % sub)


def geometry_type(sk, geo):
    return sk.Geometry[geo].TypeId


def ref_points(sk, geo):
    """The PointPos values a copy is tied by (exactly the copy's degrees of freedom together with Equal for
    round geometry): line and arc ends, a circle's centre, a point."""
    t = geometry_type(sk, geo)
    if t == "Part::GeomLineSegment" or t == "Part::GeomArcOfCircle":
        return [1, 2]
    if t == "Part::GeomCircle":
        return [3]
    if t == "Part::GeomPoint":
        return [1]
    raise ValueError("Pattern repeats lines, arcs, circles and points")


def point_of(sk, geo, pos):
    return sk.getPoint(geo, pos)


# ----- copies -----
def _copy_geometry(sk, geo, offset=None, rotate=None):
    """A new geometry equal to sk.Geometry[geo], translated by `offset` (Vector) or rotated by `rotate`
    (centre Vector, angle in radians); construction flag kept."""
    g = sk.Geometry[geo].copy()
    if offset is not None:
        g.translate(offset)
    if rotate is not None:
        _rotate_in_place(g, *rotate)
    return sk.addGeometry(g, sk.getConstruction(geo))


def _rotate_in_place(g, centre, angle):
    pl = App.Placement(centre, App.Rotation(App.Vector(0, 0, 1), math.degrees(angle))) \
        .multiply(App.Placement(-centre, App.Rotation()))
    g.transform(pl.toMatrix())


def PREFIX_OF(name):
    """'Pattern3' -> 'pat3': the constraint name prefix of a pattern."""
    return sketches.PATTERN_PREFIX + name[len("Pattern"):]


def _name_constraint(sk, rec, index):
    name = "%s_%d" % (rec["_prefix"], rec["_next"])
    rec["_next"] += 1
    sk.renameConstraint(index, name)
    rec["constraints"].append(name)
    return name


def _add(sk, rec, constraint, expression=None, hidden=True):
    i = sk.addConstraint(constraint)
    if expression is not None:
        sk.setExpression("Constraints[%d]" % i, expression)
    if hidden:
        sk.setVirtualSpace(i, True)
    return _name_constraint(sk, rec, i)


def _begin(sk, rec):
    rec.setdefault("copies", [])
    rec.setdefault("constraints", [])
    rec["_prefix"] = PREFIX_OF(rec["name"])
    rec["_next"] = 0
    rec["_points"] = {}  # (orig geo, pos) -> True once tied for this copy: shared corners are tied once


def _end(sk, rec):
    for key in ("_prefix", "_next", "_points", "_doc"):
        rec.pop(key, None)
    recs = [r for r in records(sk) if r.get("name") != rec["name"]]
    recs.append(rec)
    save_records(sk, recs)
    return rec


def _originals(sk, rec):
    out = []
    for gid in rec["originals"]:
        i = index_of(sk, gid)
        if i is None:
            raise ValueError("The pattern's original geometry is gone: delete the pattern")
        ref_points(sk, i)  # raises for unsupported types
        out.append(i)
    return out


def _coincident_points(sk, geos):
    """{(geo, pos): (geo0, pos0)}: for every point of `geos` that is coincident with an earlier point of the
    same set, the earlier one (a closed rectangle's corners are tied once)."""
    alias = {}
    seen = []
    for g in geos:
        for pos in ref_points(sk, g):
            p = point_of(sk, g, pos)
            for (g0, pos0, q) in seen:
                if (p - q).Length < 1e-7:
                    alias[(g, pos)] = (g0, pos0)
                    break
            else:
                seen.append((g, pos, p))
    return alias


def _translation(rec, k, j):
    """Expressions of a copy's offset: k steps along direction 1, j along direction 2 (0 when single)."""
    sign = -1 if rec.get("flip") else 1
    terms_x = ["%d * InCadModel.%s * cos(%s deg)" % (sign * k, rec["spacing_param"], repr(float(rec["angle"])))]
    terms_y = ["%d * InCadModel.%s * sin(%s deg)" % (sign * k, rec["spacing_param"], repr(float(rec["angle"])))]
    if j:
        terms_x.append("%d * InCadModel.%s * cos(%s deg)" % (j, rec["spacing_param2"], repr(float(rec["angle2"]))))
        terms_y.append("%d * InCadModel.%s * sin(%s deg)" % (j, rec["spacing_param2"], repr(float(rec["angle2"]))))
    return " + ".join(terms_x), " + ".join(terms_y)


def _param_value(doc, name):
    from incad.core import model
    return float(getattr(model._model_obj(doc), name).getValueAs("mm"))


def _offset_vector(rec, k, j):
    sign = -1 if rec.get("flip") else 1
    s1 = _param_value(rec["_doc"], rec["spacing_param"])
    a1 = math.radians(rec["angle"])
    v = App.Vector(sign * k * s1 * math.cos(a1), sign * k * s1 * math.sin(a1), 0)
    if j:
        s2 = _param_value(rec["_doc"], rec["spacing_param2"])
        a2 = math.radians(rec["angle2"])
        v += App.Vector(j * s2 * math.cos(a2), j * s2 * math.sin(a2), 0)
    return v


def build_rect(doc, sk, rec):
    """Copies of the originals at k steps along direction 1 (and j along direction 2), each point tied to the
    original's by DistanceX/DistanceY with expressions, round geometry Equal to the original."""
    rec["_doc"] = doc
    _begin(sk, rec)
    originals = _originals(sk, rec)
    alias = _coincident_points(sk, originals)
    count, count2 = int(rec["count"]), int(rec.get("count2") or 1)
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    for j in range(count2):
        for k in range(count):
            if k == 0 and j == 0:
                continue
            offset = _offset_vector(rec, k, j)
            if offset.Length < 1e-9:
                raise ValueError("The copies would land on the original: give the pattern a spacing")
            ex, ey = _translation(rec, k, j)
            copy_ids = []
            new = {}
            for g in originals:
                c = _copy_geometry(sk, g, offset=offset)
                new[g] = c
                copy_ids.append(ensure_id(sk, c))
            for g in originals:
                c = new[g]
                for pos in ref_points(sk, g):
                    src = alias.get((g, pos), (g, pos))
                    if (src, k, j) in rec["_points"]:
                        _add(sk, rec, Sketcher.Constraint("Coincident", c, pos, new[src[0]], src[1]))
                        continue
                    rec["_points"][(src, k, j)] = True
                    _add(sk, rec, Sketcher.Constraint("DistanceX", g, pos, c, pos, offset.x), ex)
                    _add(sk, rec, Sketcher.Constraint("DistanceY", g, pos, c, pos, offset.y), ey)
                if geometry_type(sk, g) in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
                    _add(sk, rec, Sketcher.Constraint("Equal", g, c))
            rec["copies"].append(copy_ids)
    return _end(sk, rec)


def copies_of(sk, name):
    """Geometry indexes of everything a pattern added: the copies and their spokes (circular)."""
    rec = find(sk, name)
    if rec is None:
        return []
    ids = [g for ids in rec.get("copies", []) for g in ids] + list(rec.get("spokes0", []))
    return [i for i in (index_of(sk, g) for g in ids) if i is not None]


def params_of(rec):
    return [rec[k] for k in PARAM_KEYS if rec and rec.get(k)]


def _drop_params(doc, names):
    """Remove model parameters nothing uses any more (a deleted pattern's spacing); ones still in use stay."""
    from incad.core import model
    for n in names:
        try:
            model.remove_model_parameter(doc, n)
        except ValueError:
            pass


def remove(doc, sk, name, keep_params=False):
    """Delete a pattern's copies (spokes included), constraints and, unless kept for a rebuild, its parameters;
    the original stays. Missing pieces (deleted by hand) are skipped."""
    rec = find(sk, name)
    if rec is None:
        return
    names = set(rec.get("constraints", []))
    for i in sorted([i for i, c in enumerate(sk.Constraints) if c.Name in names], reverse=True):
        sk.delConstraint(i)
    for i in sorted(copies_of(sk, name), reverse=True):
        sk.delGeometry(i)
    save_records(sk, [r for r in records(sk) if r.get("name") != name])
    if not keep_params:
        _drop_params(doc, params_of(rec))


def live_params(doc, sk, rec):
    """The pattern's parameter names as they are now: a parameter renamed in Parameters is found again from the
    pattern's own constraint expressions (FreeCAD rewrote them to the new name)."""
    from incad.core import model
    stale = [k for k in PARAM_KEYS if rec.get(k) and not model.is_model_parameter(doc, rec[k])]
    if not stale:
        return rec
    found = set()
    for cname in rec.get("constraints", []):
        expr = sketches._expression_of(sk, "Constraints." + cname) or ""
        found |= set(re.findall(r"InCadModel\.(\w+)", expr))
    known = {rec[k] for k in PARAM_KEYS if rec.get(k) and k not in stale}
    candidates = sorted(found - known)
    if len(stale) == 1 and len(candidates) == 1:
        rec[stale[0]] = candidates[0]
    return rec


# ----- circular -----
def step_angle(total_deg, count, fitted):
    """The angle between neighbouring copies. Fitted spreads the copies within `total`; a full 360° ring
    closes without a copy on the original."""
    if not fitted:
        return float(total_deg)
    if abs(total_deg - 360.0) < 1e-9:
        return 360.0 / count
    return float(total_deg) / (count - 1)


def _circ_points(sk, geo):
    """Points a circular copy is tied by: a line's start (its direction and length come from Equal + Angle),
    an arc's two ends, a circle's centre, a point."""
    t = geometry_type(sk, geo)
    return [1] if t == "Part::GeomLineSegment" else ref_points(sk, geo)


def check_axis(sk, originals, axis):
    centre = point_of(sk, axis[0], axis[1])
    for g in originals:
        for pos in ref_points(sk, g):
            if (point_of(sk, g, pos) - centre).Length < 1e-7:
                raise ValueError("Pick the axis point away from the geometry being repeated")


def _spoke(sk, rec, axis, geo, pos):
    """A construction line from the axis point to (geo, pos), both ends coincident."""
    a = point_of(sk, axis[0], axis[1])
    b = point_of(sk, geo, pos)
    s = sk.addGeometry(Part.LineSegment(a, b), True)
    _add(sk, rec, Sketcher.Constraint("Coincident", s, 1, axis[0], axis[1]))
    _add(sk, rec, Sketcher.Constraint("Coincident", s, 2, geo, pos))
    return s


def build_circ(doc, sk, rec):
    """Copies turned about the axis point: every reference point of a copy sits at the end of a construction
    spoke Equal to the original's spoke and at k × step angle from it (an expression on the angle parameter);
    lines add Equal + Angle to the original, circles and arcs Equal."""
    _begin(sk, rec)
    originals = _originals(sk, rec)
    axis = deref(sk, rec["axis_ref"]) if rec.get("axis_ref") else tuple(rec["axis"])
    if axis is None:
        raise ValueError("The axis point is gone: pick another")
    check_axis(sk, originals, axis)
    count = int(rec["count"])
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    from incad.core import model
    divisor = float(rec.get("divisor") or 1)  # the parameter is the angle the dialog shows; the step divides it
    step = float(getattr(model._model_obj(doc), rec["angle_param"]).getValueAs("deg")) / divisor
    if abs(step) < 1e-9:
        raise ValueError("The copies would land on the original: give the pattern an angle")
    sign = -1 if rec.get("flip") else 1
    alias = _coincident_points(sk, originals)
    centre = point_of(sk, axis[0], axis[1])
    spoke0 = {}
    for g in originals:
        for pos in _circ_points(sk, g):
            src = alias.get((g, pos), (g, pos))
            if src not in spoke0:
                spoke0[src] = _spoke(sk, rec, axis, src[0], src[1])
    rec["spokes0"] = [ensure_id(sk, s) for s in spoke0.values()]
    for k in range(1, count):
        angle = math.radians(sign * k * step)
        new, copy_ids = {}, []
        for g in originals:
            c = _copy_geometry(sk, g, rotate=(centre, angle))
            new[g] = c
            copy_ids.append(ensure_id(sk, c))
        done = {}
        for g in originals:
            c = new[g]
            for pos in _circ_points(sk, g):
                src = alias.get((g, pos), (g, pos))
                if src in done:
                    _add(sk, rec, Sketcher.Constraint("Coincident", c, pos, new[src[0]], src[1]))
                    continue
                s = _spoke(sk, rec, axis, c, pos)
                done[src] = s
                copy_ids.append(ensure_id(sk, s))
                _add(sk, rec, Sketcher.Constraint("Equal", spoke0[src], s))
                _add(sk, rec, Sketcher.Constraint("Angle", spoke0[src], s, angle),
                     "%d * InCadModel.%s / %r" % (sign * k, rec["angle_param"], divisor))
            t = geometry_type(sk, g)
            if t == "Part::GeomLineSegment":
                _add(sk, rec, Sketcher.Constraint("Equal", g, c))
                _add(sk, rec, Sketcher.Constraint("Angle", g, c, angle),
                     "%d * InCadModel.%s / %r" % (sign * k, rec["angle_param"], divisor))
            elif t in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
                _add(sk, rec, Sketcher.Constraint("Equal", g, c))
        rec["copies"].append(copy_ids)
    return _end(sk, rec)


# ----- equal spacing between two limits -----
def _limit(sk, limit):
    """(point, normal) of a limit: a line gives a point on it and its normal; a point gives itself and None."""
    geo, pos = limit
    if geo >= 0 and geometry_type(sk, geo) == "Part::GeomLineSegment" and pos == 0:
        a, b = point_of(sk, geo, 1), point_of(sk, geo, 2)
        d = b - a
        return a, App.Vector(-d.y, d.x, 0).normalize()
    if geo == -1 and pos == 0:
        return App.Vector(0, 0, 0), App.Vector(0, 1, 0)
    if geo == -2 and pos == 0:
        return App.Vector(0, 0, 0), App.Vector(1, 0, 0)
    return point_of(sk, geo, pos), None


def _extent(sk, originals, direction):
    lo = hi = None
    for g in originals:
        shape = sk.Geometry[g].toShape()
        for v in shape.Vertexes:
            t = v.Point.dot(direction)
            lo = t if lo is None else min(lo, t)
            hi = t if hi is None else max(hi, t)
        if geometry_type(sk, g) in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
            c = sk.Geometry[g].Center.dot(direction)
            r = sk.Geometry[g].Radius
            lo, hi = min(lo if lo is not None else c - r, c - r), max(hi if hi is not None else c + r, c + r)
    return lo, hi


def equal_spacing(sk, originals, start, end, count):
    """(spacing in mm, direction angle in degrees) that puts the first copy as far from the From limit as the
    last is from the To limit. From is the start; the copies run toward To."""
    p0, n0 = _limit(sk, start)
    p1, n1 = _limit(sk, end)
    direction = n0 if n0 is not None else (n1 if n1 is not None else (p1 - p0))
    if direction.Length < 1e-9:
        raise ValueError("From and To coincide: pick two different limits")
    direction = App.Vector(direction).normalize()
    t0, t1 = p0.dot(direction), p1.dot(direction)
    if abs(t1 - t0) < 1e-9:
        raise ValueError("From and To coincide: pick two different limits")
    if t1 < t0:
        direction, t0, t1 = -direction, -t0, -t1
    lo, hi = _extent(sk, originals, direction)
    width, margin, room = hi - lo, lo - t0, t1 - t0
    if count < 2:
        raise ValueError("Use a count of 2 or more to space the copies between the limits")
    if margin < -1e-6:
        raise ValueError("The picked geometry lies %.1f mm behind the start (the From pick): pick the other end "
                         "as From, or move the limit" % -margin)
    spacing = (t1 - margin - hi) / (count - 1)  # the part's rule: (end - margin - far edge) / (count - 1)
    if spacing < width - 1e-6:
        raise ValueError("There is no room: the picked geometry is %.1f mm wide and %.1f mm from the start, so %d "
                         "copies need %.1f mm, but only %.1f mm lie between the limits. Use fewer copies, move "
                         "the limits, or pick the other end as From" % (width, margin, count,
                                                                       count * width + 2 * margin, room))
    return spacing, math.degrees(math.atan2(direction.y, direction.x))


# ----- edit -----
def is_broken(sk, name):
    rec = find(sk, name)
    if rec is None:
        return False
    ids = [g for ids in rec.get("copies", []) for g in ids] + list(rec.get("spokes0", []))
    return any(index_of(sk, g) is None for g in ids)


def rebuild(doc, sk, rec):
    """Remove the pattern's copies (whatever is left of them) and build them again from `rec`. A build that
    fails puts the old record back (copies emptied: the pattern is then *broken*, its parameters kept) so the
    next attempt reuses them; a build that succeeds drops the parameters the new record no longer uses."""
    old = find(sk, rec["name"])
    remove(doc, sk, rec["name"], keep_params=True)
    fresh = dict(rec, copies=[], constraints=[], spokes0=[])
    try:
        built = build_rect(doc, sk, fresh) if fresh["kind"] == "rect" else build_circ(doc, sk, fresh)
    except Exception:
        if old is not None:
            save_records(sk, [r for r in records(sk) if r.get("name") != old["name"]]
                         + [dict(old, copies=[], constraints=[], spokes0=[])])
        raise
    _drop_params(doc, set(params_of(old)) - set(params_of(built)))
    return built


def pattern_of(sk, index):
    """The pattern a geometry belongs to (original, copy or spoke), or None."""
    gid = sk.getGeometryId(index)
    if gid is None:
        return None
    for r in records(sk):
        if gid in r.get("originals", []) or gid in r.get("spokes0", []) or any(gid in ids for ids in r.get("copies", [])):
            return r["name"]
    return None


def is_copy(sk, index):
    gid = sk.getGeometryId(index)
    return gid is not None and any(gid in ids for r in records(sk) for ids in r.get("copies", []))
