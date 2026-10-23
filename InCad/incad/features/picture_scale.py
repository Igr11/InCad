"""Scale / Transparency of an image (the user: a photo of something measured — "this length is so much" — and the rest
scales with it): two points clicked on an imported image and the real length between them; the image is scaled so
that it is, the first point staying where it is. The line made Horizontal or Vertical turns the image about that
point (the user: a line drawn on the photo set horizontal, the photo turns with it); a slider sets how see-through it
is. Edit on the image's row (or a double-click) opens it. The points are kept as fractions of the image (u, v), so
they stay on the same spots of the photo however it is scaled or turned; the dialog works from the size and place
the image had when it opened (Cancel puts it back)."""
import math

import FreeCAD as App

from incad.core import image_reference, line3d
from incad.features.common import Field

TITLE = "Scale / Transparency"
ICON = "scale"
TYPES = ("Image::ImagePlane",)
NEEDS_PROFILE = False
PROPS = {}
FIELDS = (
    Field("points", "Points", "points"),
    Field("align", "Line", "choice", (("as_is", "As is"), ("horizontal", "Horizontal"), ("vertical", "Vertical")),
          "as_is"),
    Field("length", "Real length", "value_length", default=""),
    Field("transparency", "Transparency", "slider", (0, 90), 0),
)
LIVE = ("transparency",)  # set at once by live(), with no preview (a recompute reloads the image's file)
_START = {}  # (document, picture) -> (XSize, YSize, Placement) when its dialog opened
_OPEN = [None]  # (document, picture) of the open dialog (info names the picture by it)


def claims(f):
    return image_reference.is_picture(f)


def defaults(doc, body, profile=None):
    return {"points": "", "align": "as_is", "length": "", "transparency": 0}


def _transparency(f):
    return int(getattr(getattr(f, "ViewObject", None), "Transparency", 0) or 0)


def live(doc, f, values):
    _look(f, values)


def _place(f, w, h, plc):
    """Size and place the image, only what differs (an equal write still recomputes it and reloads its file)."""
    changed = False
    if abs(f.XSize.Value - w) > 1e-9 or abs(f.YSize.Value - h) > 1e-9:
        f.XSize, f.YSize = w, h
        changed = True
    if not f.Placement.isSame(plc, 1e-9):
        f.Placement = plc
        changed = True
    if changed:
        f.recompute()


def _look(f, values):
    """The picture's transparency (only how it looks: Cancel leaves the one chosen)."""
    vo = getattr(f, "ViewObject", None)
    t = int(values.get("transparency") or 0)
    if vo is not None and hasattr(vo, "Transparency") and vo.Transparency != t:
        vo.Transparency = t


def read(doc, f):
    _START[(doc.Name, f.Name)] = (f.XSize.Value, f.YSize.Value, App.Placement(f.Placement))
    _OPEN[0] = (doc.Name, f.Name)
    return {"points": "", "align": "as_is", "length": "", "transparency": _transparency(f)}


def create(doc, body, profile, values):
    raise ValueError("Pick the image's row and use Edit to scale it")


def local(f, u, v, size=None):
    """The point (u, v) of the picture (fractions of its width and height from its lower left corner) in the
    picture's own plane, for its size `size` (XSize, YSize) or its present one."""
    w, h = size or (f.XSize.Value, f.YSize.Value)
    return App.Vector((u - 0.5) * w, (v - 0.5) * h, 0)


def measured(f, pts, size=None):
    """The length between the two points (u, v) on the picture at that size."""
    (u1, v1, _), (u2, v2, _) = pts[:2]
    return (local(f, u2, v2, size) - local(f, u1, v1, size)).Length


def _length(text):
    try:
        v = App.Units.Quantity((text or "").strip()).Value
    except Exception:
        raise ValueError("Real length: enter a length such as 120 mm")
    if v <= 0:
        raise ValueError("The real length must be above zero")
    return v


def _level(plc, a, b, how):
    """The turn about the image's normal that makes the line a -> b (global points) horizontal or vertical in the
    image's plane — horizontal along X (along Y for an image on a YZ plane), vertical square to it — whichever way
    is the nearer, so the image never turns over."""
    n = plc.Rotation.multVec(App.Vector(0, 0, 1))
    h = App.Vector(1, 0, 0) - n * n.x
    if h.Length < 0.5:  # standing square to X: horizontal along Y
        h = App.Vector(0, 1, 0) - n * n.y
    h.normalize()
    want = h if how == "horizontal" else n.cross(h)
    d = (b - a) - n * (b - a).dot(n)
    if d.Length < 1e-9:
        return App.Rotation()
    ang = math.degrees(math.atan2(n.dot(d.cross(want)), d.dot(want)))
    if ang > 90:
        ang -= 180
    elif ang < -90:
        ang += 180
    return App.Rotation(n, ang)


def update(doc, f, values):
    start = _START.get((doc.Name, f.Name))
    if start is None:
        read(doc, f)
        start = _START[(doc.Name, f.Name)]
    w0, h0, plc0 = start
    _look(f, values)
    pts = line3d.parse_points(values.get("points"))
    align = values.get("align") or "as_is"
    sized = bool((values.get("length") or "").strip())
    if len(pts) < 2 or (not sized and align == "as_is"):
        _place(f, w0, h0, plc0)  # nothing to scale or level by yet: as it was
        return f
    span = measured(f, pts, (w0, h0))
    if span < 1e-9:
        raise ValueError("Click two different points of the image")
    p1 = plc0.multVec(local(f, pts[0][0], pts[0][1], (w0, h0)))  # stays where it is
    p2 = plc0.multVec(local(f, pts[1][0], pts[1][1], (w0, h0)))
    plc = App.Placement(plc0)
    if align != "as_is":  # the line made horizontal or vertical: the image turned about the first point
        turn = App.Placement(p1, _level(plc0, p1, p2, align)).multiply(App.Placement(-p1, App.Rotation()))
        plc = turn.multiply(plc)
    k = _length(values.get("length")) / span if sized else 1.0
    plc.Base = p1 + (plc.Base - p1) * k
    _place(f, w0 * k, h0 * k, plc)
    return f


def pending(values):
    """What a scaling still waits for (OK off): none with no point clicked — the transparency alone is kept."""
    n = len(line3d.parse_points(values.get("points")))
    if n == 1:
        return "Click the second point"
    if n >= 2 and not (values.get("length") or "").strip() and (values.get("align") or "as_is") == "as_is":
        return "Type the real length between the two points, or make the line Horizontal or Vertical"
    return ""


def info(values):
    """The length between the points on the picture as it is now (the dialog shows it)."""
    pts = line3d.parse_points(values.get("points"))
    if not pts:
        return "To scale it: click two points of the image whose real distance you know"
    if len(pts) < 2 or _OPEN[0] is None:
        return ""
    try:
        f = App.getDocument(_OPEN[0][0]).getObject(_OPEN[0][1])
    except Exception:
        return ""
    return "On the image now: %g mm" % round(measured(f, pts), 3) if f is not None else ""


def overlay(shell, session):
    from incad.ui.picture_scale_tool import PicturePoints
    return PicturePoints(shell, session)

