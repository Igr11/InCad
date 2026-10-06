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
    Field("threaded", "Threaded", "bool", default=False),
    Field("thread_standard", "Standard", "combo", (("iso", "ISO metric"), ("iso_fine", "ISO metric fine"),
                                                   ("unc", "UNC"), ("unf", "UNF"), ("unef", "UNEF"), ("npt", "NPT"),
                                                   ("g", "G / BSP"), ("bsw", "BSW"), ("bsf", "BSF")), "iso",
          show_if=("threaded", (True,))),
    Field("thread_size", "Size", "combo", (), "", show_if=("threaded", (True,))),
    Field("diameter", "Diameter", "value_length", default="5 mm", show_if=("threaded", (False,))),
    Field("depth_type", "Termination", "choice", (("distance", "Distance"), ("through_all", "Through All")),
          "through_all"),
    Field("depth", "Depth", "value_length", default="10 mm", show_if=("depth_type", ("distance",))),
    Field("tip", "Drill point", "choice", (("flat", "Flat"), ("angled", "118°")), "angled",
          show_if=("depth_type", ("distance",))),
    Field("cbore_diameter", "C'bore Ø", "value_length", default="10 mm", show_if=("type", ("counterbore",))),
    Field("cbore_depth", "C'bore depth", "value_length", default="3 mm", show_if=("type", ("counterbore",))),
    Field("csink_diameter", "C'sink Ø", "value_length", default="10 mm", show_if=("type", ("countersink",))),
    Field("csink_angle", "C'sink angle", "value_angle", default="90 °", show_if=("type", ("countersink",))),
    Field("thread_depth", "Thread", "choice", (("hole", "Whole hole"), ("distance", "Depth")), "hole",
          show_if=("threaded", (True,))),
    Field("thread_length", "Thread depth", "value_length", default="8 mm",
          show_if=(("threaded", (True,)), ("thread_depth", ("distance",)))),
    Field("clearance", "Print clearance", "value_length", default="0.2 mm", show_if=("threaded", (True,))),
    Field("hand", "Direction", "choice", (("right", "Right hand"), ("left", "Left hand")), "right",
          show_if=("threaded", (True,))),
)
_THREAD_TYPES = {"iso": "ISOMetricProfile", "iso_fine": "ISOMetricFineProfile", "unc": "UNC", "unf": "UNF",
                 "unef": "UNEF", "npt": "NPT", "g": "BSP", "bsw": "BSW", "bsf": "BSF"}
_PLAIN = "InCadPlainDiameter"
_SIZES = {}
_CUT = {"simple": "None", "counterbore": "Counterbore", "countersink": "Countersink"}


def defaults(doc, body, profile):
    values = {f.key: f.default for f in FIELDS}
    values.update(sketch="", face="", edge="")
    try:
        from incad.core import prefs
        values["clearance"] = "%g mm" % prefs.thread_clearance()
    except Exception:
        pass
    return values


def thread_sizes(std):
    """FreeCAD's size names for a thread type (asked once from a hidden probe Hole, then cached)."""
    kind = _THREAD_TYPES.get(std, "ISOMetricProfile")
    if kind not in _SIZES:
        doc = App.newDocument("InCadHoleSizes", hidden=True)
        try:
            h = doc.addObject("PartDesign::Hole", "Probe")
            h.ThreadType = kind
            _SIZES[kind] = list(h.getEnumerationsOfProperty("ThreadSize"))
        finally:
            App.closeDocument(doc.Name)
    return _SIZES[kind]


def options(key, values):
    if key == "thread_size":
        return [("", "Auto (from Diameter)")] + [(n, n) for n in thread_sizes(values.get("thread_standard") or "iso")]
    return None


def _default_size(std, names, diameter_text):
    from incad.threads import standards
    try:
        d = App.Units.Quantity(diameter_text or "5 mm").Value
        guess = standards.suggest(std if std in ("iso", "iso_fine", "unc", "unf", "npt", "g") else "iso", d, False)
    except Exception:
        guess = ""
    guess = guess.replace("G", "").split("-")[0] if std in ("g", "unc", "unf", "unef", "bsw", "bsf") else guess
    return next((n for n in names if n == guess or n.startswith(guess + "x")), names[0] if names else "")


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
    _apply_thread(doc, f, values)
    if f.DepthType == "Dimension":
        value_param(doc, f, "Depth", values.get("depth") or "10 mm", "length")
    if values.get("type") == "counterbore":
        value_param(doc, f, "HoleCutDiameter", values.get("cbore_diameter") or "10 mm", "length")
        value_param(doc, f, "HoleCutDepth", values.get("cbore_depth") or "3 mm", "length")
    elif values.get("type") == "countersink":
        value_param(doc, f, "HoleCutDiameter", values.get("csink_diameter") or "10 mm", "length")
        value_param(doc, f, "HoleCutCountersinkAngle", values.get("csink_angle") or "90 °", "angle")


def _apply_thread(doc, f, values):
    from incad.core import model
    if values.get("threaded"):
        name = model.bound_parameter(f, "Diameter")
        if name is not None:  # the thread sets the drill size; keep the plain diameter for switching back
            if not hasattr(f, _PLAIN):
                f.addProperty("App::PropertyString", _PLAIN, "InCad")
                f.setPropertyStatus(_PLAIN, "Hidden")
            setattr(f, _PLAIN, name)
            f.setExpression("Diameter", None)
        std = values.get("thread_standard") or "iso"
        kind = _THREAD_TYPES.get(std, "ISOMetricProfile")
        f.Threaded = True
        f.ModelThread = True
        if f.ThreadType != kind:
            f.ThreadType = kind
        names = list(f.getEnumerationsOfProperty("ThreadSize"))
        size = values.get("thread_size")
        f.ThreadSize = size if size in names else _default_size(std, names, values.get("diameter"))
        f.ThreadDirection = "Left" if values.get("hand") == "left" else "Right"
        f.UseCustomThreadClearance = True
        try:
            f.CustomThreadClearance = App.Units.Quantity(values.get("clearance") or "0.2 mm").Value
        except Exception:
            raise ValueError("Print clearance: enter a length such as 0.2 mm")
        if values.get("thread_depth") == "distance":
            f.ThreadDepthType = "Dimension"
            value_param(doc, f, "ThreadDepth", values.get("thread_length") or "8 mm", "length")
        else:
            f.ThreadDepthType = "Hole Depth"
        return
    if f.Threaded:
        f.Threaded = False
        f.ModelThread = False
        plain = getattr(f, _PLAIN, "")
        if plain and model.bound_parameter(f, "Diameter") is None:
            model.bind(f, "Diameter", plain)
    value_param(doc, f, "Diameter", values.get("diameter") or "5 mm", "length")


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
    if f.Threaded:
        std = {v: k for k, v in _THREAD_TYPES.items()}.get(f.ThreadType, "iso")
        values.update(threaded=True, thread_standard=std, thread_size=f.ThreadSize,
                      clearance="%g mm" % f.CustomThreadClearance.Value,
                      hand="left" if f.ThreadDirection == "Left" else "right",
                      thread_depth="distance" if f.ThreadDepthType == "Dimension" else "hole",
                      thread_length=value_text(doc, f, "ThreadDepth") or "8 mm")
        plain = getattr(f, _PLAIN, "")
        if plain:
            from incad.core import model
            values["diameter"] = model.parameter_text(doc, plain)
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
