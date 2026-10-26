"""Sketch ▸ Mirror's last step (incad.core.sketch_mirror; the user selected the shapes, clicked Mirror, then the mirror
line — as FreeCAD's tool had it — and InCad took the last selected line for the mirror). The shapes are taken from
what is selected when the tool starts; one click then picks the mirror line — a line under the pointer first (one of
the shapes' own lines too: a half profile mirrored about its closing line), else the X / Y axis, else a point — and
the copy is made (one undo step, the copy selected), the tool ends. Esc cancels."""
from incad.core import log, safe, sketch_mirror, sketch_symmetric as sym
from incad.ui.overall_dim_tool import OverallDimTool

EDGE_PX = 8
POINT_PX = 10
PROMPT = "Mirror: click the mirror line — a line, the X or Y axis — or a point (Esc cancels)"


def mirror_pick_at(sk, pt, vertex_tol, edge_tol):
    """The mirror for a click: a line or axis first (a click near a line's end means the line), else a point."""
    return sym.pick_at(sk, pt, 0.0, edge_tol) or sym.pick_at(sk, pt, vertex_tol, 0.0)


class MirrorTool:
    to_sketch = OverallDimTool.to_sketch

    def __init__(self, view, sketch, geos, on_finish=None, on_done=None):
        self.view, self.sketch, self.geos = view, sketch, list(geos)
        self._on_finish, self._on_done = on_finish, on_done
        self._input = None
        self.copies = None

    def start(self):
        from incad.ui.view_clicks import ViewClicks
        self._input = ViewClicks(self.view, self._qt_press, lambda x, y: None)
        self._input.start()
        self._select(self.geos)
        log.report("info", PROMPT)

    def stop(self):
        if self._input is not None:
            self._input.stop()
            self._input = None
        if self.copies is None:
            self._select([])
        if self._on_finish is not None:
            self._on_finish(self)

    def _qt_press(self, x, y, modifiers):
        pt = self.to_sketch(x, y)
        if pt is None:
            return
        try:
            dpr = self.view.graphicsView().viewport().devicePixelRatioF()
        except Exception:
            dpr = 1.0
        far = self.to_sketch(x + EDGE_PX * dpr, y)
        edge_tol = (far - pt).Length if far is not None else 1.0
        self.click(pt, edge_tol)

    def click(self, pt, edge_tol=1.0):
        pick = mirror_pick_at(self.sketch, pt, edge_tol * POINT_PX / EDGE_PX, edge_tol)
        if pick is None:
            log.report("info", PROMPT)
            return None
        return self.take(pick)

    def take(self, pick):
        sk = self.sketch
        r = safe.run_safely("Mirror", lambda: sketch_mirror.mirror(sk, self.geos, pick), sk.Document, only=[sk])
        if not r.ok:
            log.report("warning", "Mirror: %s" % r.error)  # the shapes stay picked: click another mirror line
            return None
        self.copies = r.value
        self._select(self.copies)
        log.report("info", "Mirrored %d: the copy follows its original (right-click it ▸ Break Mirror Link frees it)"
                   % len(self.copies))
        if self._on_done is not None:
            self._on_done(self.copies)
        self.stop()
        return self.copies

    def _select(self, geos):
        try:
            import FreeCADGui as Gui
            Gui.Selection.clearSelection()
            for g in geos:
                Gui.Selection.addSelection(self.sketch.Document.Name, self.sketch.Name, "Edge%d" % (g + 1))
        except Exception:
            pass
