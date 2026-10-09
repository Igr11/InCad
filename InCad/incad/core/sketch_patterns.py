"""Sketch patterns: copies of sketch geometry tied to the original by constraints, remembered on the sketch
(InCadPatterns, JSON) so they can be edited or deleted as one thing. Pure model: no transactions, no UI.
Geometry is addressed by permanent ids (setGeometryId), never by index."""
import json
import math

import FreeCAD as App
import Part
import Sketcher

from incad.core import sketch as sketches

RECORD_PROP = "InCadPatterns"
SUPPORTED = ("Part::GeomLineSegment", "Part::GeomArcOfCircle", "Part::GeomCircle", "Part::GeomPoint")
_ID_BASE = 100000  # ids we hand out start here: FreeCAD's own ids (when any) are small


# ----- records -----
def _load(sk):
    text = getattr(sk, RECORD_PROP, "") or ""
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    data.setdefault("patterns", [])
    data.setdefault("next", 1)
    data.setdefault("next_id", _ID_BASE)
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
    gid = sk.getGeometryId(index)
    if gid is None or gid < _ID_BASE:
        data = _load(sk)
        gid = data["next_id"]
        data["next_id"] += 1
        _store(sk, data)
        sk.setGeometryId(index, gid)
    return gid


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
    rec = find(sk, name)
    if rec is None:
        return []
    return [i for ids in rec.get("copies", []) for i in [index_of(sk, g) for g in ids] if i is not None]


def remove(doc, sk, name):
    """Delete a pattern's copies (spokes included) and constraints; the original stays. Missing pieces (deleted
    by hand) are skipped."""
    rec = find(sk, name)
    if rec is None:
        return
    names = set(rec.get("constraints", []))
    for i in sorted([i for i, c in enumerate(sk.Constraints) if c.Name in names], reverse=True):
        sk.delConstraint(i)
    for i in sorted(copies_of(sk, name), reverse=True):
        sk.delGeometry(i)
    save_records(sk, [r for r in records(sk) if r.get("name") != name])
