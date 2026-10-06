"""InCad's own slot tools (Inventor's Overall and Center Point slots, which FreeCAD's Sketcher doesn't draw).

Three clicks on the sketch plane — two points along the slot, then one for the width — with a live outline;
continues for the next slot until Esc. The slot is added as one undo step (incad.core.slots)."""
import math

import FreeCAD as App

from incad.core import log, safe, slots

PROMPTS = {"overall": ("Click the first end of the slot", "Click the other end", "Click to set the width"),
           "center": ("Click the slot's center", "Click one end's center", "Click to set the width")}


class SlotTool:
    def __init__(self, view, sketch, mode, on_finish=None):
        self.view, self.sketch, self.mode = view, sketch, mode
        self.points = []
        self._on_finish = on_finish
        self._callbacks = []
        self._preview = None
        self._coords = None

    # ----- lifecycle -----
    def start(self):
        for kind in ("SoMouseButtonEvent", "SoLocation2Event"):
            self._callbacks.append((kind, self.view.addEventCallback(kind, self._event)))
        self._make_preview()
        log.report("info", PROMPTS[self.mode][0] + " (Esc finishes)")

    def stop(self):
        for kind, cb in self._callbacks:
            try:
                self.view.removeEventCallback(kind, cb)
            except Exception:
                pass
        self._callbacks = []
        if self._preview is not None:
            try:
                self.view.getSceneGraph().removeChild(self._preview)
            except Exception:
                pass
            self._preview = None
        if self._on_finish is not None:
            self._on_finish(self)

    # ----- input -----
    def to_sketch(self, x, y):
        """Screen position -> point on the sketch plane, in sketch coordinates."""
        pl = self.sketch.getGlobalPlacement()
        normal = pl.Rotation.multVec(App.Vector(0, 0, 1))
        p = self.view.getPoint(x, y)
        d = self.view.getViewDirection()
        denom = d.dot(normal)
        if abs(denom) < 1e-9:
            return None
        hit = p + d * ((pl.Base - p).dot(normal) / denom)
        local = pl.inverse().multVec(hit)
        return App.Vector(local.x, local.y, 0)

    def _event(self, info):
        pos = info.get("Position")
        if pos is None:
            return
        pt = self.to_sketch(*pos)
        if pt is None:
            return
        if info.get("Type") == "SoMouseButtonEvent":
            if info.get("Button") == "BUTTON1" and info.get("State") == "DOWN":
                self.click(pt)
        else:
            self.hover(pt)

    def click(self, pt):
        self.points.append(pt)
        if len(self.points) < 3:
            log.report("info", PROMPTS[self.mode][len(self.points)] + " (Esc finishes)")
            return None
        a, b, c = self.points
        self.points = []
        self._draw([])
        try:
            c1, c2, r = (slots.overall if self.mode == "overall" else slots.center_point)(a, b, c)
        except ValueError as e:
            log.report("warning", str(e))
            return None
        doc = self.sketch.Document
        result = safe.run_safely("Slot", lambda: slots.add(self.sketch, c1, c2, r), doc)
        log.report("info", PROMPTS[self.mode][0] + " for the next slot (Esc finishes)")
        return result.value if result.ok else None

    def hover(self, pt):
        if not self.points:
            return
        if len(self.points) == 1:
            a = self.points[0]
            ref = a - (pt - a) if self.mode == "center" else a
            self._draw([ref, pt])
            return
        try:
            c1, c2, r = (slots.overall if self.mode == "overall" else slots.center_point)(self.points[0],
                                                                                         self.points[1], pt)
        except ValueError:
            return
        self._draw(_outline(c1, c2, r))

    # ----- preview (Coin overlay on the sketch plane) -----
    def _make_preview(self):
        from pivy import coin
        sep = coin.SoSeparator()
        tr = coin.SoTransform()
        pl = self.sketch.getGlobalPlacement()
        tr.translation.setValue(*pl.Base)
        q = pl.Rotation.Q
        tr.rotation.setValue(q[0], q[1], q[2], q[3])
        color = coin.SoBaseColor()
        color.rgb.setValue(0.95, 0.62, 0.29)
        style = coin.SoDrawStyle()
        style.lineWidth = 2
        self._coords = coin.SoCoordinate3()
        self._lines = coin.SoLineSet()
        for node in (tr, color, style, self._coords, self._lines):
            sep.addChild(node)
        self.view.getSceneGraph().addChild(sep)
        self._preview = sep
        self._draw([])

    def _draw(self, pts):
        if self._coords is None:
            return
        self._coords.point.setValues(0, len(pts), [(p.x, p.y, 0.01) for p in pts])
        self._coords.point.setNum(len(pts))
        self._lines.numVertices.setValues(0, 1, [len(pts)]) if pts else self._lines.numVertices.setNum(0)


def _outline(c1, c2, r, steps=16):
    th = math.atan2(c2.y - c1.y, c2.x - c1.x)
    pts = []
    for c, start in ((c2, th - math.pi / 2), (c1, th + math.pi / 2)):
        for i in range(steps + 1):
            a = start + math.pi * i / steps
            pts.append(App.Vector(c.x + r * math.cos(a), c.y + r * math.sin(a), 0))
    pts.append(pts[0])
    return pts
