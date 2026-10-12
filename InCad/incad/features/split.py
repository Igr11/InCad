"""Split by sketch: each line of a sketch (segment, arc, spline) is extruded along the sketch's normal, both ways,
through the whole part into a surface of zero thickness; these knives divide the shape before this step.
Keep all (Inventor's Split Solid): this Solid keeps the largest piece and every other piece becomes a Solid of its own
(a body on a SplitPiece that follows the Split), so each can be hidden, worked on and made a part of its own.
Keep picked: only the pieces at the stored points (a spot picked on each) stay, the nearest piece to each point on
every recompute."""
import json

import FreeCAD as App

from incad.features.common import Field, parse_picks

TITLE = "Split"
ICON = "split"
TYPES = ("PartDesign::FeaturePython",)
NEEDS_PROFILE = False
STRUCTURAL = ()
PICKS_ON_SELF = ("keep",)
PRESELECT = {"sketch": "sketch"}  # a sketch selected before the command fills the field
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


def _nearest(solids, point):
    import Part
    probe = Part.Vertex(point)
    return min(solids, key=lambda s: s.distToShape(probe)[0])


def inside_point(solid):
    """A point strictly inside the solid: its centre of mass when that is inside (a C-shaped piece of a split ring
    has it in the hole), else a face's middle pushed a little into the material — never a point on a face that two
    split pieces share."""
    c = solid.CenterOfMass
    if solid.isInside(c, 1e-7, False):
        return c
    for f in solid.Faces:
        u0, u1, v0, v1 = f.ParameterRange
        p, n = f.valueAt((u0 + u1) / 2, (v0 + v1) / 2), f.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        for step in (1e-3, 1e-2, 0.1):
            for q in (p - n * step, p + n * step):
                if solid.isInside(q, 1e-7, False):
                    return q
    return c


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
        if obj.Keep and (obj.Mode == "split" or not obj.ShowAll):  # Keep all: this Solid's piece; Keep picked
            kept = []
            for p in obj.Keep:
                best = _nearest(pieces, p)
                if best not in kept:
                    kept.append(best)
            pieces = kept
        obj.Shape = pieces[0] if len(pieces) == 1 else Part.makeCompound(pieces)

    def dumps(self):
        return None

    def loads(self, state):
        return None


class SplitPieceFeature:
    """A piece of a Split (Keep all) that is not the Split's own: the base of a Solid of its own. Follows the Split
    (its sketch, the part before it): the piece nearest its point."""
    def __init__(self, obj):
        for prop, kind in (("Source", "App::PropertyLink"), ("Point", "App::PropertyVector")):
            if prop not in obj.PropertiesList:
                obj.addProperty(kind, prop, "Split", "")
        if _PIECE not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", _PIECE, "InCad", "A piece of a Split")
            obj.setPropertyStatus(_PIECE, "Hidden")
        setattr(obj, _PIECE, True)
        obj.Proxy = self

    def execute(self, obj):
        f = obj.Source
        if f is None or f.BaseFeature is None or f.Sketch is None:
            return
        obj.Shape = _nearest(pieces(f), obj.Point)

    def dumps(self):
        return None

    def loads(self, state):
        return None


_PIECE = "InCadSplitPiece"


def claims(feature):
    return hasattr(feature, _STORE)


def piece_bodies(f):
    """The Solids the Split made for its other pieces (Keep all), in the document's order."""
    return [b for b in f.Document.Objects if b.TypeId == "PartDesign::Body" and b.BaseFeature is not None
            and getattr(b.BaseFeature, _PIECE, False) and b.BaseFeature.Source is f]


def _drop_piece_body(doc, body):
    """A piece's Solid goes with its piece, unless something was made on it (then it stays and shows the nearest
    piece)."""
    origin = [body.Origin] + list(body.Origin.OriginFeatures) if body.Origin is not None else []
    stand_in = [o for o in body.Group if o.TypeId == "PartDesign::FeatureBase"]  # FreeCAD's for BaseFeature
    if any(o not in origin and o not in stand_in for o in body.Group):
        return
    piece = body.BaseFeature
    body.BaseFeature = None
    for o in stand_in:
        if doc.getObject(o.Name) is not None:
            doc.removeObject(o.Name)
    doc.removeObject(body.Name)
    if piece is not None:
        doc.removeObject(piece.Name)


def is_piece(obj):
    return bool(getattr(obj, _PIECE, False))


def delete(doc, f):
    """Delete a Split: its empty piece Solids go with it; a piece Solid with work on it stays on a frozen copy of
    its piece (a plain shape: nothing links to the deleted Split)."""
    for b in piece_bodies(f):
        before = len(doc.Objects)
        _drop_piece_body(doc, b)
        if len(doc.Objects) < before:
            continue
        piece = b.BaseFeature
        frozen = doc.addObject("Part::Feature", "SplitPieceShape")
        frozen.Shape = piece.Shape.copy()
        frozen.Visibility = False
        b.BaseFeature = frozen
        doc.removeObject(piece.Name)


def _new_piece_body(doc, f, point):
    from incad.core import document
    piece = doc.addObject("Part::FeaturePython", "SplitPiece")
    SplitPieceFeature(piece)
    piece.Source = f
    piece.Point = point
    piece.Visibility = False
    body = document.new_solid(doc)
    owner = f.getParentGeoFeatureGroup()
    if owner is not None:
        body.Placement = owner.Placement  # the piece is in the Split's body frame
    body.BaseFeature = piece
    return body


def _sync_pieces(doc, f):
    """Keep all: this Solid keeps the largest piece (first time) and every other piece has a Solid; on an edit each
    Solid keeps the piece nearest its point, new pieces get one, Solids left without a piece go. Keep picked: no
    piece Solids."""
    bodies = piece_bodies(f)
    if f.Mode != "split":
        for b in bodies:
            _drop_piece_body(doc, b)
        return
    all_pieces = pieces(f)
    main = _nearest(all_pieces, f.Keep[0]) if f.Keep else all_pieces[0]
    f.Keep = [inside_point(main)]
    claimed = [main]
    for b in bodies:
        free = [p for p in all_pieces if p not in claimed]
        if not free:
            _drop_piece_body(doc, b)
            continue
        best = _nearest(free, b.BaseFeature.Point)
        b.BaseFeature.Point = inside_point(best)
        claimed.append(best)
    for p in all_pieces:
        if p not in claimed:
            _new_piece_body(doc, f, inside_point(p))
            claimed.append(p)


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
    was = f.Mode
    f.Mode = values.get("mode") or "split"
    if f.Mode == "cut":
        f.Keep = _points(doc, values.get("keep"))
    elif was != "split":
        f.Keep = []  # Keep all: _sync_pieces gives this Solid the largest piece
    # the picks as typed ('Split:Face7', named on every piece shown while Keep is picked): edit reads them back, so a
    # click adds to them instead of replacing them
    _store(f, {"sketch": sk.Name, "mode": f.Mode, "keep": (values.get("keep") or "") if f.Mode == "cut" else ""})
    return f


def create(doc, body, profile, values):
    tip = body.Tip
    f = body.newObject("PartDesign::FeaturePython", "Split")
    SplitFeature(f)
    f.BaseFeature = tip
    from incad.core import document
    document.show_like(f, tip)  # the view proxy first: FreeCAD then draws it in the base's display mode
    try:
        _build(doc, f, values)
        body.Tip = f
        sk = f.Sketch
        doc.recompute()
        document.show_like(f, tip)
        if "Invalid" in f.State:
            raise ValueError(f.getStatusString() or "The sketch does not cut the part")
        _sync_pieces(doc, f)
        doc.recompute()
        sk.Visibility = False
    except Exception:
        for b in piece_bodies(f):
            _drop_piece_body(doc, b)
        body.removeObject(f)
        doc.removeObject(f.Name)
        body.Tip = tip
        doc.recompute()
        raise
    return f


def read(doc, f):
    data = _load(f)
    values = defaults(doc, f.getParentGeoFeatureGroup(), None)
    mode = data.get("mode", "split")
    keep = ""
    if mode == "cut":  # Keep all keeps its own piece's point in Keep: that is no pick of the user's
        keep = data.get("keep") or ", ".join("%r %r %r" % (p.x, p.y, p.z) for p in f.Keep)
    values.update(sketch=data.get("sketch", getattr(f.Sketch, "Name", "")), mode=mode, keep=keep)
    return values


def update(doc, f, values):
    _build(doc, f, values)
    doc.recompute()
    if "Invalid" in f.State:
        raise ValueError(f.getStatusString() or "The sketch does not cut the part")
    _sync_pieces(doc, f)
    doc.recompute()
    return f


def pieces(f):
    base = f.BaseFeature
    return _slice(base.Shape, _knives(f.Sketch, f.getParentGeoFeatureGroup(), base.Shape.BoundBox))


def keep_piece(f, point):
    f.Mode = "cut"
    f.Keep = [point]
    data = _load(f)
    data["mode"] = "cut"
    data["keep"] = "%r %r %r" % (point.x, point.y, point.z)
    _store(f, data)
    f.touch()


def picking(f, active):
    """While Keep is picked every piece shows (a removed one can be picked back)."""
    if f.ShowAll != active:
        f.ShowAll = active
        f.touch()


def param_names(f):
    return {}
