"""3D Model ▸ 3D Line (the user's idea): a line through points clicked on a virtual cube of points round the origin
(incad.core.line3d; the cube shows while the dialog is open: incad.ui.line3d_tool). Lines, a spline on the points
as control points, or a spline through them; open (a closed one, for Loft sections, is not wanted yet). A
Part2DObjectPython in the Solid, as a sketch is, so Sweep takes it as its path; the points and settings are kept on
it (InCadLine3D, JSON) for the dialog."""
import json

import FreeCAD as App

from incad.core import line3d
from incad.features.common import Field

TITLE = "3D Line"
ICON = "line3d"
TYPES = ("Part::Part2DObjectPython",)
MARK = "InCadLine3D"
NEEDS_PROFILE = False
PROPS = {}
FIELDS = (
    Field("shape", "Line", "choice", (("polyline", "Lines"), ("spline", "Spline"), ("through", "Through points")),
          "polyline"),
    Field("curvature", "Curvature", "bool", default=True, same_row=True),
    Field("size", "Cube", "value_length", default="100 mm"),
    Field("step", "Step", "value_length", default="10 mm", same_row=True),
    Field("layer", "Layer", "choice", (("xy", "XY"), ("xz", "XZ"), ("yz", "YZ"), ("cube", "Cube")), "xy"),
    Field("at", "At", "value_length", default="0 mm", signed=True, show_if=("layer", ("xy", "xz", "yz")),
          step=lambda values: _step_of(values)),
    Field("points", "Points", "points"),
)


def _step_of(values):
    """The cube's step (At's arrows move the working layer by it)."""
    try:
        return length(values.get("step"), "Step")
    except ValueError:
        return None


def claims(f):
    return MARK in f.PropertiesList


def settings(f):
    try:
        return json.loads(getattr(f, MARK, "") or "{}")
    except ValueError:
        return {}


def length(text, what):
    try:
        v = App.Units.Quantity(text or "").Value
    except Exception:
        raise ValueError("%s: enter a length such as 10 mm" % what)
    if v <= 0:
        raise ValueError("%s must be above zero" % what)
    return v


class Line3DFeature:
    """The proxy. FreeCAD saves its module path (incad.features.line3d) and class name in the file."""

    def __init__(self, obj):
        if MARK not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", MARK, "InCad", "The 3D line's points and settings")
            obj.setPropertyStatus(MARK, "Hidden")
        obj.Proxy = self

    def execute(self, obj):
        import Part
        s = settings(obj)
        wire = line3d.curve(s.get("points") or [], s.get("shape") or "polyline")
        obj.Shape = wire if wire is not None else Part.Shape()

    def dumps(self):
        return None

    def loads(self, state):
        return None


def marker_points(f):
    """[(kind, global point)] a Point field offers on the 3D line (the user: a plane at its start for a loft): its
    ends and every point it passes through (a spline on control points passes only through its ends)."""
    s = settings(f)
    pts = [App.Vector(*p) for p in s.get("points") or []]
    if (s.get("shape") or "polyline") == "spline":
        pts = pts[:1] + pts[-1:]
    group = f.getParentGeoFeatureGroup()
    g = group.getGlobalPlacement().multiply(f.Placement) if group is not None else f.Placement
    return [("corner", g.multVec(p)) for p in pts]


def defaults(doc, body, profile=None):
    return {f.key: f.default for f in FIELDS if f.key != "points"} | {"points": ""}


def working_layer(values):
    """(axis, level) of the working layer the dialog asks for, or None for the whole cube."""
    name = values.get("layer") or "xy"
    if name not in line3d.LAYERS:
        return None
    try:
        level = App.Units.Quantity((values.get("at") or "0 mm").strip()).Value
    except Exception:
        level = 0.0
    return line3d.LAYERS[name], level


def _apply(doc, f, values):
    size, step = length(values.get("size"), "Cube"), length(values.get("step"), "Step")
    line3d.coords(size, step)  # refuses a step larger than the cube, or too many points
    data = {"shape": values.get("shape") or "polyline", "curvature": bool(values.get("curvature", True)),
            "points": [list(p) for p in line3d.parse_points(values.get("points"))], "size": size, "step": step}
    text = json.dumps(data, sort_keys=True)
    if getattr(f, MARK) != text:
        setattr(f, MARK, text)
        f.touch()


def create(doc, body, profile, values):
    f = doc.addObject("Part::Part2DObjectPython", "Line3D")
    Line3DFeature(f)
    f.Label = TITLE
    body.addObject(f)
    _look(f)
    _apply(doc, f, values)
    f.recompute()
    return f


COLOR = (0.96, 0.56, 0.12)  # orange: seen on the dark and the light background (FreeCAD's default line is black)


class Line3DView:
    """The view proxy: a Python 2D object without one has no display mode, and nothing was drawn."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getDisplayModes(self, vobj):
        return []  # the C++ ones (Flat Lines, Wireframe, Points)

    def getDefaultDisplayMode(self):
        return "Wireframe"

    def setDisplayMode(self, mode):
        return mode

    def getIcon(self):
        from incad.ui import theme as themes
        return themes.icon_path(ICON, "light")

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _look(f):
    vo = getattr(f, "ViewObject", None)
    if vo is None:
        return  # without a window
    Line3DView(vo)
    for prop, value in (("LineColor", COLOR), ("PointColor", COLOR), ("LineWidth", 3.0), ("PointSize", 6.0)):
        if hasattr(vo, prop):
            setattr(vo, prop, value)
    try:
        vo.DisplayMode = "Wireframe"
    except Exception:
        pass


def update(doc, f, values):
    _apply(doc, f, values)
    f.recompute()
    return f


def read(doc, f):
    s = settings(f)
    pts = s.get("points") or []
    return {"shape": s.get("shape") or "polyline", "curvature": bool(s.get("curvature", True)), "layer": "xy",
            "at": "%g mm" % (round(pts[-1][2], 6) if pts else 0),  # the working layer through the last point
            "size": "%g mm" % s.get("size", 100), "step": "%g mm" % s.get("step", 10),
            "points": line3d.format_points(s.get("points") or [])}


def info(values):
    """How to move the working layer (the user did not find it)."""
    if (values.get("layer") or "xy") in line3d.LAYERS:
        return "Tab / Shift+Tab: the layer a step up / down (or At's arrows)"
    return ""


def pending(values):
    n = len(line3d.parse_points(values.get("points")))
    if n >= 2:
        return ""
    return "Click points of the cube, or anywhere on its lines, to draw the line" if not n else \
        "Click the next point"


def overlay(shell, session):
    from incad.ui.line3d_tool import LatticeOverlay
    return LatticeOverlay(shell, session)
