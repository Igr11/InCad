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
        return "ExternalEdge%d" % (-geo - 2) if geo < -2 else "Edge%d" % (geo + 1)
    v = 0
    while True:
        g, p = sk.getGeoVertexIndex(v)
        if p == 0:  # past the last vertex: FreeCAD answers (-2000, 0)
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
    if sub.startswith("ExternalEdge"):  # projected geometry: ExternalGeo index n -> geo id -(n + 1), 'ExternalEdge1' is -3
        return -int(sub[12:]) - 2, 0
    if sub.startswith("Edge"):
        return int(sub[4:]) - 1, 0
    if sub.startswith("Vertex"):
        geo, pos = sk.getGeoVertexIndex(int(sub[6:]) - 1)
        if pos == 0:  # FreeCAD answers (-2000, 0) for a vertex that does not exist; real ones have a PointPos
            raise ValueError("Not a sketch element: %s" % sub)
        return geo, pos
    raise ValueError("Not a sketch element: %s" % sub)


def geometry_type(sk, geo):
    """The geometry's type; projected (external) geometry has ids -3 and below."""
    return sk.ExternalGeo[-geo - 1].TypeId if geo < -2 else sk.Geometry[geo].TypeId


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


def _add(sk, rec, constraint, expression=None, hidden=True):
    """Queue a constraint of the pattern; _flush adds the whole queue in ONE addConstraint call (each single call
    solves the growing sketch again: a ring of slots took seconds per preview). Returns the name it will get."""
    name = "%s_%d" % (rec["_prefix"], rec["_next"])
    rec["_next"] += 1
    rec["_pending"].append((constraint, name, expression, hidden))
    return name


def _flush(sk, rec):
    pending, rec["_pending"] = rec["_pending"], []
    if not pending:
        return
    indexes = sk.addConstraint([c for c, _, _, _ in pending])
    if isinstance(indexes, int):
        indexes = (indexes,)
    hidden = []
    for i, (_, name, expression, hide) in zip(indexes, pending):
        sk.renameConstraint(i, name)
        rec["constraints"].append(name)
        if expression is not None:
            sk.setExpression("Constraints[%d]" % i, expression)
        if hide:
            hidden.append(i)
    if hidden:
        sk.setVirtualSpace(hidden, True)


def _begin(sk, rec):
    rec.setdefault("copies", [])
    rec.setdefault("constraints", [])
    rec["_prefix"] = PREFIX_OF(rec["name"])
    rec["_next"] = 0
    rec["_pending"] = []
    rec["_points"] = {}  # (orig geo, pos) -> True once tied for this copy: shared corners are tied once


def _apply_params(doc, rec):
    """Write the values the dialog asked for into the pattern's existing parameters. Called by the builds, so
    it runs after the old copies are removed: with no live ties left, nothing but the parameter changes."""
    from incad.core import model
    for name, text in (rec.pop("param_values", None) or {}).items():
        if model.parameter_text(doc, name) != text:
            model.set_model_parameter(doc, name, text)


def _end(sk, rec):
    _flush(sk, rec)
    for key in ("_prefix", "_next", "_points", "_doc", "param_values", "_pending"):
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
    _apply_params(doc, rec)
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
                t = geometry_type(sk, g)
                if t == "Part::GeomCircle":
                    _add(sk, rec, Sketcher.Constraint("Equal", g, c))
                elif t == "Part::GeomArcOfCircle":  # both ends are tied: one equation on the centre fixes the bulge
                    b = _bisector(sk, g)
                    if abs(b.x) >= abs(b.y):
                        _add(sk, rec, Sketcher.Constraint("DistanceX", g, 3, c, 3, offset.x), ex)
                    else:
                        _add(sk, rec, Sketcher.Constraint("DistanceY", g, 3, c, 3, offset.y), ey)
            rec["copies"].append(copy_ids)
    return _end(sk, rec)


def _bisector(sk, arc):
    """Unit vector from the middle of an arc's chord to its centre: the direction the centre moves in when the
    arc's bulge changes with its ends held. The one equation that pins the centre must have a component along it
    (a semicircle's chord already fixes the radius, so an Equal on the radius would be redundant)."""
    a, b, c = point_of(sk, arc, 1), point_of(sk, arc, 2), point_of(sk, arc, 3)
    d = c - (a + b) * 0.5
    if d.Length < 1e-9:  # a semicircle: the centre is on the chord; take the chord's normal
        ch = b - a
        d = App.Vector(-ch.y, ch.x, 0)
    return d.normalize()


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
    _apply_params(doc, rec)
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
        for pos in ref_points(sk, g) + ([3] if geometry_type(sk, g) == "Part::GeomArcOfCircle" else []):
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
        turn = "%d * InCadModel.%s / %r" % (sign * k, rec["angle_param"], divisor)
        for g in originals:
            c = new[g]
            for pos in ref_points(sk, g):  # every point of the copy on a spoke: same length, k steps round
                src = alias.get((g, pos), (g, pos))
                if src in done:
                    _add(sk, rec, Sketcher.Constraint("Coincident", c, pos, new[src[0]], src[1]))
                    continue
                s = _spoke(sk, rec, axis, c, pos)
                done[src] = s
                copy_ids.append(ensure_id(sk, s))
                _add(sk, rec, Sketcher.Constraint("Equal", spoke0[src], s))
                _add(sk, rec, Sketcher.Constraint("Angle", spoke0[src], s, angle), turn)
            t = geometry_type(sk, g)
            if t == "Part::GeomCircle":
                _add(sk, rec, Sketcher.Constraint("Equal", g, c))
            elif t == "Part::GeomArcOfCircle":  # both ends on spokes: one equation on the centre fixes the bulge
                s = _spoke(sk, rec, axis, c, 3)
                copy_ids.append(ensure_id(sk, s))
                b = _bisector(sk, g)
                u = (point_of(sk, g, 3) - centre)
                u = u.normalize() if u.Length > 1e-9 else App.Vector(1, 0, 0)
                if abs(b.dot(u)) >= abs(b.x * u.y - b.y * u.x):  # the centre moves radially: hold its distance
                    _add(sk, rec, Sketcher.Constraint("Equal", spoke0[(g, 3)], s))
                else:                                            # it moves sideways: hold its angle
                    _add(sk, rec, Sketcher.Constraint("Angle", spoke0[(g, 3)], s, angle), turn)
        rec["copies"].append(copy_ids)
    return _end(sk, rec)


# ----- along a path -----
PATH_TYPES = ("Part::GeomLineSegment", "Part::GeomArcOfCircle", "Part::GeomBSplineCurve")
_JOIN = 1e-6


def _near(a, b):
    return (a - b).Length < _JOIN


def path_chain(sk, geos, start=None):
    """[(geo, edge, reversed)] of this sketch's lines, arcs and splines ordered end to end (edges in sketch
    coordinates). `start`: a point near the free end the chain begins at; None begins at the first picked
    segment's free end. Raises when the segments do not join into one open chain."""
    geos = list(dict.fromkeys(geos))
    if not geos:
        raise ValueError("Pick the path's lines, arcs or splines")
    for g in geos:
        if geometry_type(sk, g) not in PATH_TYPES:
            raise ValueError("The path takes lines, arcs and splines")
    edges = {g: sk.Geometry[g].toShape() for g in geos}
    ends = {g: (edges[g].firstVertex().Point, edges[g].lastVertex().Point) for g in geos}
    if len(geos) == 1:
        free = [(geos[0], 0), (geos[0], 1)]
    else:
        free = [(g, i) for g in geos for i in (0, 1)
                if not any(_near(ends[g][i], q) for h in geos if h != g for q in ends[h])]
    if len(free) != 2:
        raise ValueError("The path's segments must join end to end, without branches or gaps")
    if start is not None:
        first = min(free, key=lambda gi: (ends[gi[0]][gi[1]] - start).Length)
    else:
        first = next((gi for gi in free if gi[0] == geos[0]), free[0])
    chain, used = [], set()
    g, i = first
    while True:
        chain.append((g, edges[g], i == 1))
        used.add(g)
        tail = ends[g][1 - i]
        nxt = None
        for h in geos:
            if h in used:
                continue
            for j in (0, 1):
                if _near(ends[h][j], tail):
                    nxt = (h, j)
                    break
            if nxt:
                break
        if nxt is None:
            break
        g, i = nxt
    if len(used) != len(geos):
        raise ValueError("The path's segments must join end to end, without branches or gaps")
    return chain


def path_length(chain):
    return sum(e.Length for _, e, _ in chain)


def _edge_param(e, reversed_, local):
    """Curve parameter of the point `local` mm along the chain's direction on edge `e`."""
    local = min(max(local, 0.0), e.Length)
    return e.getParameterByLength(e.Length - local if reversed_ else local)


def path_point(chain, s):
    """(point, unit tangent) at arc length `s` along the chain (clamped to its ends)."""
    total = path_length(chain)
    s = min(max(s, 0.0), total)
    run = 0.0
    for k, (_, e, rev) in enumerate(chain):
        if s <= run + e.Length + 1e-9 or k == len(chain) - 1:
            par = _edge_param(e, rev, s - run)
            t = e.tangentAt(par)
            if rev:
                t = -t
            return e.valueAt(par), t.normalize()
        run += e.Length
    raise ValueError("The path is empty")


def _wrap(e, par):
    """A periodic curve's parameter (an arc's angle) moved into the edge's own range."""
    first, last = e.FirstParameter, e.LastParameter
    period = 2 * math.pi
    if e.Curve.TypeId in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
        while par < first - 1e-9:
            par += period
        while par > last + 1e-9:
            par -= period
    return min(max(par, first), last)


def path_station(chain, point):
    """Arc length along the chain of the point of the path nearest to `point`."""
    best, best_d, run = 0.0, None, 0.0
    v = Part.Vertex(point)
    for _, e, rev in chain:
        d, pts, _ = e.distToShape(v)
        if best_d is None or d < best_d - 1e-9:
            on_edge = pts[0][0]
            par = _wrap(e, e.Curve.parameter(on_edge))
            local = e.Curve.length(e.FirstParameter, par)
            if rev:
                local = e.Length - local
            best, best_d = run + local, d
        run += e.Length
    return best


def stations(chain, s0, count, spacing):
    """Arc lengths of the original (s0) and its copies: `spacing` mm apart, or spread to the path's end when
    spacing is None (fit). Raises when the copies do not fit."""
    total = path_length(chain)
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    room = total - s0
    if spacing is None:
        if room < 1e-6:
            raise ValueError("No room: the original sits at the end of the path (flip the path)")
        step = room / (count - 1)
        return [s0 + k * step for k in range(count)]
    need = (count - 1) * spacing
    if spacing <= 0:
        raise ValueError("Give the pattern a spacing")
    if need > room + 1e-6:
        raise ValueError("No room: %d copies at %g mm need %g mm, the path has %g mm after the original"
                         % (count, spacing, need, room))
    return [s0 + k * spacing for k in range(count)]


# ----- equal spacing between two limits -----
def _limit(sk, limit):
    """(point, normal) of a limit: a line gives a point on it and its normal; a point gives itself and None."""
    geo, pos = limit
    if geo not in (-1, -2) and pos == 0 and geometry_type(sk, geo) == "Part::GeomLineSegment":
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


def getGeometryId(sk, index):
    return sk.getGeometryId(index)


def is_original(sk, index):
    """True when the geometry is an original a pattern repeats (never deleted as part of a pattern)."""
    gid = sk.getGeometryId(index)
    return gid is not None and any(gid in r.get("originals", []) for r in records(sk))


def is_copy(sk, index):
    gid = sk.getGeometryId(index)
    return gid is not None and any(gid in ids for r in records(sk) for ids in r.get("copies", []))
