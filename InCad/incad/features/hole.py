"""Hole (Inventor) = PartDesign Hole. Placement from a sketch's points/circle centres, or concentric to a circular
edge on a flat face (a hidden helper sketch holds the centre point)."""
import FreeCAD as App
import Part

from incad.features.common import Field, parse_picks, resolve, value_param, value_text

TITLE = "Hole"
ICON = "hole"
TYPES = ("PartDesign::Hole",)
NEEDS_PROFILE = False
PROPS = {"diameter": "Diameter", "depth": "Depth", "cbore_diameter": "HoleCutDiameter",
         "cbore_depth": "HoleCutDepth", "csink_diameter": "HoleCutDiameter", "csink_angle": "HoleCutCountersinkAngle"}
FIELDS = (
    Field("placement", "Placement", "choice", (("sketch", "From Sketch"), ("concentric", "Concentric")), "sketch"),
    Field("sketch", "Sketch", "pick", show_if=("placement", ("sketch",)), pick="sketch"),
    Field("face", "Face", "pick", show_if=("placement", ("concentric",)), pick="plane"),
    Field("edge", "Circular edge", "pick", show_if=("placement", ("concentric",)), pick="circular_edge"),
    Field("type", "Type", "choice", (("simple", "Simple"), ("counterbore", "Counterbore"),
                                     ("countersink", "Countersink")), "simple"),
    Field("diameter", "Diameter", "value_length", default="5 mm"),
    Field("depth_type", "Termination", "choice", (("distance", "Distance"), ("through_all", "Through All")),
          "through_all"),
    Field("depth", "Depth", "value_length", default="10 mm", show_if=("depth_type", ("distance",))),
    Field("tip", "Drill point", "choice", (("flat", "Flat"), ("angled", "118°")), "angled",
          show_if=("depth_type", ("distance",))),
    Field("cbore_diameter", "C'bore Ø", "value_length", default="10 mm", show_if=("type", ("counterbore",))),
    Field("cbore_depth", "C'bore depth", "value_length", default="3 mm", show_if=("type", ("counterbore",))),
    Field("csink_diameter", "C'sink Ø", "value_length", default="10 mm", show_if=("type", ("countersink",))),
    Field("csink_angle", "C'sink angle", "value_angle", default="90 °", show_if=("type", ("countersink",))),
)
_CUT = {"simple": "None", "counterbore": "Counterbore", "countersink": "Countersink"}


def defaults(doc, body, profile):
    values = {f.key: f.default for f in FIELDS}
    values.update(sketch="", face="", edge="")
    return values


def _helper_sketch(doc, body, values, sk=None):
    """A hidden sketch on the face with a point at the circular edge's centre (fixed position). The picks are
    kept on the sketch (InCadPicks) so the dialog can show and change them; `sk` reuses an existing helper."""
    faces, edges = parse_picks(doc, values.get("face")), parse_picks(doc, values.get("edge"))
    if not faces or not edges:
        raise ValueError("Pick the flat face and the round edge the hole is centred on")
    face_obj, face = faces[0]
    edge_obj, edge = edges[0]
    centre = edge_obj.getSubObject(edge).Curve.Center
    if sk is None:
        sk = body.newObject("Sketcher::SketchObject", "HoleCentre")
        sk.addProperty("App::PropertyString", "InCadPicks", "InCad")
    sk.deleteAllGeometry()
    sk.AttachmentSupport = [resolve(face_obj, face)]
    sk.MapMode = "FlatFace"
    sk.InCadPicks = "%s|%s" % (values.get("face"), values.get("edge"))
    doc.recompute()
    local = sk.getGlobalPlacement().inverse().multVec(centre)
    sk.addGeometry(Part.Point(App.Vector(local.x, local.y, 0)))
    sk.Visibility = False
    doc.recompute()
    return sk


def _profile(doc, body, values):
    if values.get("placement") == "concentric":
        return _helper_sketch(doc, body, values)
    picks = parse_picks(doc, values.get("sketch"))
    if not picks:
        raise ValueError("Pick a sketch with points or circles for the hole centres")
    return picks[0][0]


def _apply(doc, f, values):
    f.HoleCutType = _CUT.get(values.get("type", "simple"), "None")
    f.DepthType = "ThroughAll" if values.get("depth_type") == "through_all" else "Dimension"
    f.DrillPoint = "Angled" if values.get("tip") == "angled" else "Flat"
    value_param(doc, f, "Diameter", values.get("diameter") or "5 mm", "length")
    if f.DepthType == "Dimension":
        value_param(doc, f, "Depth", values.get("depth") or "10 mm", "length")
    if values.get("type") == "counterbore":
        value_param(doc, f, "HoleCutDiameter", values.get("cbore_diameter") or "10 mm", "length")
        value_param(doc, f, "HoleCutDepth", values.get("cbore_depth") or "3 mm", "length")
    elif values.get("type") == "countersink":
        value_param(doc, f, "HoleCutDiameter", values.get("csink_diameter") or "10 mm", "length")
        value_param(doc, f, "HoleCutCountersinkAngle", values.get("csink_angle") or "90 °", "angle")


def create(doc, body, profile, values):
    sk = _profile(doc, body, values)
    f = body.newObject("PartDesign::Hole", "Hole")
    f.Profile = sk
    _apply(doc, f, values)
    return f


def read(doc, f):
    prof = f.Profile[0] if isinstance(f.Profile, (tuple, list)) else f.Profile
    concentric = _is_helper(prof)
    cut = {v: k for k, v in _CUT.items()}.get(f.HoleCutType, "simple")
    values = defaults(f.Document, None, None)
    values.update(placement="concentric" if concentric else "sketch", sketch="" if concentric else prof.Name,
                  type=cut, depth_type="through_all" if f.DepthType == "ThroughAll" else "distance",
                  tip="angled" if f.DrillPoint == "Angled" else "flat",
                  diameter=value_text(doc, f, "Diameter") or "5 mm", depth=value_text(doc, f, "Depth") or "10 mm")
    if concentric:
        face, _, edge = getattr(prof, "InCadPicks", "").partition("|")
        values.update(face=face, edge=edge)
    if cut == "counterbore":
        values.update(cbore_diameter=value_text(doc, f, "HoleCutDiameter") or "10 mm",
                      cbore_depth=value_text(doc, f, "HoleCutDepth") or "3 mm")
    if cut == "countersink":
        values.update(csink_diameter=value_text(doc, f, "HoleCutDiameter") or "10 mm",
                      csink_angle=value_text(doc, f, "HoleCutCountersinkAngle") or "90°")
    return values


def _is_helper(sk):
    return sk is not None and hasattr(sk, "InCadPicks")


def update(doc, f, values):
    current = f.Profile[0] if isinstance(f.Profile, (tuple, list)) else f.Profile
    body = f.getParentGeoFeatureGroup()
    if values.get("placement") == "concentric":
        if _is_helper(current):
            _helper_sketch(doc, body, values, current)
        else:
            f.Profile = _helper_sketch(doc, body, values)
    else:
        picks = parse_picks(doc, values.get("sketch"))
        if picks and current is not picks[0][0]:
            f.Profile = picks[0][0]
            if _is_helper(current):
                body.removeObject(current)
                doc.removeObject(current.Name)
    _apply(doc, f, values)
    return f


def _pad_of(f):
    return f
