"""Split by sketch: each line of a sketch (segment, arc, spline) is extruded along the sketch's normal, both ways,
through the whole part into a surface of zero thickness; these knives divide the shape before this step. Split keeps
every piece (they touch but are separate solids: Make Assembly makes a part of each); Cut keeps the pieces at the
stored points (a spot picked on each), the nearest piece to each point on every recompute."""
import json

import FreeCAD as App

from incad.features.common import Field, parse_picks

TITLE = "Split"
ICON = "split"
TYPES = ("PartDesign::FeaturePython",)
NEEDS_PROFILE = False
STRUCTURAL = ()
PICKS_ON_SELF = ("keep",)
_STORE = "InCadSplit"

FIELDS = (
    Field("sketch", "Sketch", "pick", pick="sketch"),
    Field("mode", "Mode", "choice", (("split", "Keep all"), ("cut", "Keep picked")), "split"),
    Field("keep", "Keep", "picks", pick="piece", show_if=("mode", ("cut",))),
)


def _knives(sk, body, bb):
    """The knife faces in the body's frame: every edge of the sketch swept along its normal past the part."""
    pl = sk.getGlobalPlacement()
    if body is not None:
        pl = body.getGlobalPlacement().inverse().multiply(pl)
    n = pl.Rotation.multVec(App.Vector(0, 0, 1))
    reach = bb.DiagonalLength + (pl.Base - bb.Center).Length + 10.0
    faces = []
    for e in sk.Shape.Edges:  # sk.Shape is already placed (body frame); pl only gives the normal
        edge = e.copy()
        edge.translate(n * -reach)
        faces.append(edge.extrude(n * (2 * reach)))
    return faces


def _slice(base, knives):
    from BOPTools import SplitAPI
    out = SplitAPI.slice(base, knives, "Split")
    return sorted(out.Solids, key=lambda s: -s.Volume)


class SplitFeature:
    """The proxy. FreeCAD saves its module path (incad.features.split) and class name in the file."""
    def __init__(self, obj):
        for prop, kind in (("Sketch", "App::PropertyLink"), ("Mode", "App::PropertyString"),
                           ("Keep", "App::PropertyVectorList"), ("ShowAll", "App::PropertyBool")):
            if prop not in obj.PropertiesList:
                obj.addProperty(kind, prop, "Split", "")
        obj.setPropertyStatus("ShowAll", ["Hidden", "Transient"])
        obj.Proxy = self

    def execute(self, obj):
        base = obj.BaseFeature
        if base is None or base.Shape.isNull() or obj.Sketch is None:
            return
        before = len(base.Shape.Solids)
        pieces = _slice(base.Shape, _knives(obj.Sketch, obj.getParentGeoFeatureGroup(), base.Shape.BoundBox))
        if len(pieces) <= before:
            raise ValueError("The sketch does not cut the part")
        import Part
        if obj.Mode == "cut" and obj.Keep and not obj.ShowAll:
            kept = []
            for p in obj.Keep:
                probe = Part.Vertex(p)
                best = min(pieces, key=lambda s: s.distToShape(probe)[0])
                if best not in kept:
                    kept.append(best)
            pieces = kept
        obj.Shape = pieces[0] if len(pieces) == 1 else Part.makeCompound(pieces)

    def dumps(self):
        return None

    def loads(self, state):
        return None


def claims(feature):
    return hasattr(feature, _STORE)


def defaults(doc, body, profile=None):
    values = {f.key: f.default for f in FIELDS}
    values.update(sketch=profile.Name if profile is not None else "", keep="")
    return values


def _points(doc, text):
    """Keep: picks on the Split's own pieces ('Split:Face7') or plain 'x y z' triples; each becomes a point."""
    out = []
    for part in [p for p in (text or "").split(",") if p.strip()]:
        nums = part.split()
        if len(nums) == 3:
            try:
                out.append(App.Vector(*[float(v) for v in nums]))
                continue
            except ValueError:
                pass
        for obj, sub in parse_picks(doc, part):
            if sub:
                out.append(obj.Shape.getElement(sub).CenterOfMass)
    return out


def _store(f, data):
    if not hasattr(f, _STORE):
        f.addProperty("App::PropertyString", _STORE, "InCad", "InCad split settings")
        f.setPropertyStatus(_STORE, "Hidden")
    setattr(f, _STORE, json.dumps(data, sort_keys=True))


def _load(f):
    try:
        return json.loads(getattr(f, _STORE, "") or "{}")
    except ValueError:
        return {}


def _build(doc, f, values):
    sk = doc.getObject((values.get("sketch") or "").split(":")[0])
    if sk is None or sk.TypeId != "Sketcher::SketchObject":
        raise ValueError("Pick the sketch whose lines cut the part")
    if sk.Shape.isNull() or "Touched" in sk.State:
        sk.recompute()  # a sketch drawn just now has no shape yet
    if not sk.Shape.Edges:
        raise ValueError("The sketch has no lines")
    f.Sketch = sk
    f.Mode = values.get("mode") or "split"
    f.Keep = _points(doc, values.get("keep")) if f.Mode == "cut" else []
    _store(f, {"sketch": sk.Name, "mode": f.Mode})
    return f


def create(doc, body, profile, values):
    tip = body.Tip
    f = body.newObject("PartDesign::FeaturePython", "Split")
    SplitFeature(f)
    f.BaseFeature = tip
    try:
        _build(doc, f, values)
        body.Tip = f
        sk = f.Sketch
        doc.recompute()
        if "Invalid" in f.State:
            raise ValueError(f.getStatusString() or "The sketch does not cut the part")
        sk.Visibility = False
    except Exception:
        body.removeObject(f)
        doc.removeObject(f.Name)
        body.Tip = tip
        doc.recompute()
        raise
    return f


def read(doc, f):
    data = _load(f)
    values = defaults(doc, f.getParentGeoFeatureGroup(), None)
    values.update(sketch=data.get("sketch", getattr(f.Sketch, "Name", "")), mode=data.get("mode", "split"),
                  keep=", ".join("%g %g %g" % (p.x, p.y, p.z) for p in f.Keep))
    return values


def update(doc, f, values):
    _build(doc, f, values)
    doc.recompute()
    if "Invalid" in f.State:
        raise ValueError(f.getStatusString() or "The sketch does not cut the part")
    return f


def pieces(f):
    base = f.BaseFeature
    return _slice(base.Shape, _knives(f.Sketch, f.getParentGeoFeatureGroup(), base.Shape.BoundBox))


def keep_piece(f, point):
    f.Mode = "cut"
    f.Keep = [point]
    data = _load(f)
    data["mode"] = "cut"
    _store(f, data)
    f.touch()


def picking(f, active):
    """While Keep is picked every piece shows (a removed one can be picked back)."""
    if f.ShowAll != active:
        f.ShowAll = active
        f.touch()


def param_names(f):
    return {}
