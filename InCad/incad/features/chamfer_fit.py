"""Chamfer: a distance wider than a face it runs onto stops at that face's far edge (the user: a 2 mm face and a
2.5 mm chamfer make a 2 mm chamfer, no error). FreeCAD's chamfer fails from the face's width on, so a chamfer that
doesn't fit gets two steps of its own (InCadHelperOf it, shown and deleted with it): Fit, right before it, passes the
part on unchanged and works out the widest distance that still fits — a hair (EPS) short of the nearest far edge of
each face along a picked edge, halfway when that edge is picked too — and the chamfer's distance becomes
min(the asked one; Fit); Trim, right after it, takes off the hair-thin strip the chamfer leaves of a face it reached
(defeaturing: the faces round it grow over it). Both follow the part: on a wider face the chamfer takes its full
distance again."""
import Part

HELPER, ROLE = "InCadHelperOf", "InCadHelperRole"
EPS = 1e-4     # the chamfer stops this far short of a face's far edge (FreeCAD's chamfer fails exactly on it)
SLIVER = 1e-3  # a face next to the chamfer narrower than this is the strip Trim takes off
NO_LIMIT = 1e6  # Fit when nothing limits the chamfer (mm)
PROPS = ("Size", "Size2")  # the chamfer's distances Fit limits


def _touch(a, b):
    return any((v.Point - w.Point).Length < 1e-7 for v in a.Vertexes for w in b.Vertexes)


def fit(shape, names):
    """The widest distance a chamfer of these edges of `shape` can take, or None when nothing limits it."""
    edges = []
    for n in names:
        try:
            edges.append(shape.getElement(n))
        except Exception:
            pass
    best = None
    for e in edges:
        for face in shape.ancestorsOfType(e, Part.Face):
            for g in face.Edges:
                if g.isSame(e) or _touch(g, e):  # the face's own seam, the edges at the chamfer's ends
                    continue
                d = e.distToShape(g)[0]
                if any(g.isSame(o) for o in edges):
                    d *= 0.5  # two chamfers across one face meet halfway
                if best is None or d < best:
                    best = d
    return None if best is None else max(best - EPS, EPS)


def helpers(f):
    body = f.getParentGeoFeatureGroup()
    return {getattr(o, ROLE, ""): o for o in (body.Group if body is not None else [])
            if getattr(o, HELPER, None) == f.Name and getattr(o, ROLE, "") in ("fit", "trim")}


class FitFeature:
    """The proxy of the step before the chamfer. FreeCAD saves its module path and class name in the file."""
    def __init__(self, obj):
        if "Fit" not in obj.PropertiesList:
            obj.addProperty("App::PropertyLength", "Fit", "Chamfer", "The widest distance the chamfer takes")
            obj.setPropertyStatus("Fit", "Output")
        obj.Proxy = self

    def execute(self, obj):
        base = obj.BaseFeature
        if base is None or base.Shape.isNull():
            return
        shape = base.Shape.copy()
        chamfer = obj.Document.getObject(getattr(obj, HELPER, "") or "")
        names = list(chamfer.Base[1]) if chamfer is not None and chamfer.Base else []
        w = fit(shape, names) if names else None
        w = NO_LIMIT if w is None else w
        if abs(obj.Fit.Value - w) > 1e-9:
            obj.Fit = w
        obj.Shape = shape

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _region(shape, names, reach):
    box = None
    for n in names:
        try:
            bb = shape.getElement(n).BoundBox
        except Exception:
            continue
        if box is None:
            box = bb
        else:
            box.add(bb)
    if box is not None:
        box.enlarge(reach + 1.0)
    return box


def trim(shape, before, box):
    """The shape without the hair-thin faces inside `box` the chamfer made (each a strip it left of a face it
    reached); a small face the part had before (a letter's, a thread's) stays: grown over, it ran 36 mm up a jar."""
    from incad.core import feature_faces
    had = feature_faces._prints(before, "Face")
    strips = []
    for face in shape.Faces:
        if box is not None and not box.intersect(face.BoundBox):
            continue
        try:
            if 2.0 * face.Area / face.OuterWire.Length < SLIVER and feature_faces._fingerprint(face, "Face") not in had:
                strips.append(face)
        except Exception:
            pass
    if not strips:
        return shape
    try:
        out = shape.defeaturing(strips)
    except Exception:
        return shape
    grown = shape.BoundBox
    grown.enlarge(10 * EPS)
    if out.isNull() or not out.isValid() or len(out.Solids) != len(shape.Solids) or not grown.isInside(out.BoundBox) \
            or abs(out.Volume - shape.Volume) > 1e-5 * abs(shape.Volume) + sum(f.Area for f in strips):
        return shape  # the strip stays (0.1 µm wide) rather than a face grown out of the part
    return out


class TrimFeature:
    """The proxy of the step after the chamfer."""
    def __init__(self, obj):
        obj.Proxy = self

    def execute(self, obj):
        chamfer = obj.BaseFeature
        if chamfer is None or chamfer.Shape.isNull():
            return
        shape = chamfer.Shape.copy()
        fitter = helpers(chamfer).get("fit")
        if fitter is not None and chamfer.Base and abs(chamfer.Size.Value - fitter.Fit.Value) < 1e-7:
            shape = trim(shape, fitter.Shape, _region(fitter.Shape, list(chamfer.Base[1]), chamfer.Size.Value))
            if len(shape.Solids) == 1:
                shape = shape.Solids[0]
        obj.Shape = shape

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _make(doc, body, f, role):
    from incad.core import document
    g = doc.addObject("PartDesign::FeaturePython", "ChamferFit" if role == "fit" else "ChamferTrim")
    (FitFeature if role == "fit" else TrimFeature)(g)
    for prop, text in ((HELPER, "The chamfer this belongs to"), (ROLE, "What it does for the chamfer")):
        g.addProperty("App::PropertyString", prop, "InCad", text)
        g.setPropertyStatus(prop, "Hidden")
    setattr(g, HELPER, f.Name)
    setattr(g, ROLE, role)
    if role == "fit":
        base = f.BaseFeature
        body.insertObject(g, f, False)  # right before the chamfer
        g.BaseFeature = base
        g.Visibility = False
    else:
        document.show_like(g, f)  # drawn when it is the Tip (a chamfer made last)
        after = [o for o in body.Group if getattr(o, "BaseFeature", None) is f]
        was_tip = body.Tip is f
        body.insertObject(g, f, True)  # right after the chamfer
        g.BaseFeature = f
        for o in after:
            o.BaseFeature = g
        if was_tip:
            body.Tip = g
    return g


def needed(f, base, names, values):
    """Does the asked distance run past a face (the chamfer would fail)?"""
    import FreeCAD as App
    if base is None or base.Shape.isNull() or not names:
        return False
    w = fit(base.Shape, names)
    if w is None:
        return False
    asked = [values.get("size") or "0.5 mm"] + ([values.get("size2") or "0.5 mm"] if values.get("type") == "two" else [])
    try:
        return any(App.Units.Quantity(a).getValueAs("mm") > w + 1e-9 for a in asked)
    except Exception:
        return False


def sync(doc, f, base, names, values):
    """Give the chamfer its Fit and Trim steps when the asked distance runs past a face (kept once made: they cost
    nothing while it fits); returns what the chamfer's Base must link (the Fit step when there is one)."""
    from incad.core import model
    have = helpers(f)
    if not have and not needed(f, base, names, values):
        return base
    body = f.getParentGeoFeatureGroup()
    fitter = have.get("fit") or _make(doc, body, f, "fit")
    if "trim" not in have:
        _make(doc, body, f, "trim")
    fitter.touch()
    for prop in PROPS:
        name = model.bound_parameter(f, prop)
        if name is not None:
            f.setExpression(prop, model.clamped(name, fitter.Name, "Fit"))
    return fitter
