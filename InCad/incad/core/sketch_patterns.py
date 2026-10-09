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
