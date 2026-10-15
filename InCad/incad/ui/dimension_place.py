"""A dead zone for FreeCAD's Dimension tool while it places a distance. FreeCAD picks the type from where the cursor
is against the box of the two points (DrawSketchHandlerDimension::updateDistanceType): above or below it horizontal,
beside it vertical, at a corner or inside it aligned, and flips the instant the cursor crosses a side. InCad keeps
the type until the cursor is DEAD_PX past the side, both ways: in between, FreeCAD gets the cursor held just inside
the current type's area (the label waits at the side). Python cannot change the tool, only the moves it sees."""
from incad.core import log

DEAD_PX = 15  # logical px past a side before the type changes
HOLD_PX = 2  # how far inside the side the held cursor stays (FreeCAD rounds the position it reads)
DISTANCES = ("Distance", "DistanceX", "DistanceY")
GEO_UNDEF = -2000
INF = float("inf")


def _points(sk, c):
    """The two points FreeCAD's tool measures for this distance (sketch coordinates), or None when it is a kind
    whose type the tool never switches (point to line, circle to circle)."""
    if c.Second == GEO_UNDEF:  # a line's length
        if c.FirstPos != 0:
            return None
        return sk.getPoint(c.First, 1), sk.getPoint(c.First, 2)
    if c.FirstPos and c.SecondPos:
        return sk.getPoint(c.First, c.FirstPos), sk.getPoint(c.Second, c.SecondPos)
    return None


def areas(p1, p2):
    """{type: [(x0, x1, y0, y1), ...]}: where FreeCAD's tool makes each type (open rectangles)."""
    x0, x1 = min(p1.x, p2.x), max(p1.x, p2.x)
    y0, y1 = min(p1.y, p2.y), max(p1.y, p2.y)
    return {"DistanceX": [(x0, x1, y1, INF), (x0, x1, -INF, y0)],
            "DistanceY": [(x1, INF, y0, y1), (-INF, x0, y0, y1)],
            "Distance": [(x1, INF, y1, INF), (-INF, x0, y1, INF), (x1, INF, -INF, y0), (-INF, x0, -INF, y0),
                         (x0, x1, y0, y1)]}


def type_at(regions, x, y):
    for kind, rects in regions.items():
        if any(a < x < b and c < y < d for a, b, c, d in rects):
            return kind
    return None  # on a side: FreeCAD keeps what it has


def _shrink(lo, hi, t):
    """[lo, hi] moved in by t from each finite side; a narrow band keeps its middle half."""
    if lo == -INF or hi == INF:
        return (lo + t if lo != -INF else lo), (hi - t if hi != INF else hi)
    t = min(t, (hi - lo) / 4.0)
    return lo + t, hi - t


def clearly_in(rects, x, y, t):
    """(x, y) lies t (sketch units) inside one of the rectangles — a narrow one: within its middle half."""
    for a, b, c, d in rects:
        a, b = _shrink(a, b, t)
        c, d = _shrink(c, d, t)
        if a <= x <= b and c <= y <= d:
            return True
    return False


def nearest_in(rects, x, y, eps):
    """The point of the rectangles nearest to (x, y), eps inside their sides."""
    best, best_d = None, INF
    for a, b, c, d in rects:
        a, b = _shrink(a, b, eps)
        c, d = _shrink(c, d, eps)
        qx, qy = min(max(x, a), b), min(max(y, c), d)
        dist = (qx - x) ** 2 + (qy - y) ** 2
        if dist < best_d:
            best, best_d = (qx, qy), dist
    return best


def held(regions, current, x, y, t, eps):
    """Where FreeCAD should see the cursor at (x, y) while `current` is the type: None for (x, y) itself (the
    same type there, or clearly another), else the nearest point still in `current`'s area."""
    free = type_at(regions, x, y)
    if free is None or free == current or current not in regions:
        return None
    if clearly_in(regions[free], x, y, t):
        return None
    return nearest_in(regions[current], x, y, eps)


class DeadZone:
    """Navigator's place_hook: move(view, viewport, x, y) -> None or the (x, y) FreeCAD gets instead;
    press() on every button press (the placing click ends the placing)."""

    def __init__(self, editing):
        self._editing = editing  # () -> the sketch being edited, or None
        self._placing = False
        self._seen = None  # the last distance's (count, type, label) at the previous move

    def press(self):
        self._placing = False
        self._seen = None

    def move(self, view, viewport, x, y):
        from incad.ui.nav import Navigator
        try:
            sk = self._editing()
            if sk is None or not Navigator.tool_cursor(viewport) or not sk.Constraints:
                self.press()
                return None
            c = sk.Constraints[-1]
            if c.Type not in DISTANCES:
                self.press()
                return None
            seen = (len(sk.Constraints), c.LabelDistance, c.LabelPosition)
            if self._seen is not None and seen[0] == self._seen[0] and seen[1:] != self._seen[1:]:
                self._placing = True  # its label followed the last move: the tool is placing it
            self._seen = seen
            pts = _points(sk, c) if self._placing else None
            if pts is None:
                return None
            here = _on_sketch(view, viewport, sk, x, y)
            step = _on_sketch(view, viewport, sk, x + 1, y)
            if here is None or step is None:
                return None
            per_px = (step - here).Length or 1e-9
            q = held(areas(*pts), c.Type, here.x, here.y, DEAD_PX * per_px, HOLD_PX * per_px)
            if q is None:
                return None
            return _on_screen(view, viewport, sk, q)
        except Exception:
            log.logger().exception("dimension dead zone")
            return None


def _on_sketch(view, viewport, sk, x, y):
    """Viewport position (logical px) -> the point of the sketch plane under it (sketch coordinates)."""
    import FreeCAD as App
    from incad.ui.nav import to_coin
    pl = sk.getGlobalPlacement()
    origin, normal = pl.Base, pl.Rotation.multVec(App.Vector(0, 0, 1))
    p = view.getPoint(*to_coin(viewport, x, y))
    d = App.Vector(*view.getViewDirection())
    denom = d.dot(normal)
    if abs(denom) < 1e-9:
        return None
    hit = p + d * ((origin - p).dot(normal) / denom)
    return pl.inverse().multVec(hit)


def _on_screen(view, viewport, sk, q):
    import FreeCAD as App
    from incad.ui import dof_handles
    return dof_handles.screen(view, viewport, sk.getGlobalPlacement().multVec(App.Vector(q[0], q[1], 0)))
