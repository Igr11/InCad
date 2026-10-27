"""Sketch ▸ Symmetric, InCad's own tool (incad.core.sketch_symmetric; the user: choosing the points was hard, and a click
sometimes took a dimension's point). Two clicks pick what to mirror — a point near the click (an end, a centre, the
origin) wins over the line or curve under it — the third the mirror line, an axis or a point; each pick shows
selected. One undo step, and the tool ends: the pair can be dragged at once (the user: after Symmetric the lines
could not be moved — the tool, waiting for a next pair, took every click). Clicks reach only the sketch's geometry: dimensions
and constraint symbols can't be caught. What was selected before the command is taken first (three: done at once)."""
from incad.core import log, safe, sketch_symmetric as sym
from incad.ui.overall_dim_tool import OverallDimTool

EDGE_PX = 8    # logical px around the pointer that count as a click on a line or curve
POINT_PX = 12  # a point this close wins over the line under the pointer
PROMPTS = ("Symmetric: click the first point, line, circle or arc to mirror (Esc ends)",
           "Symmetric: click the second one (Esc ends)",
           "Symmetric: click the mirror line, an axis or a point (Esc ends)")


class SymmetricTool:
    to_sketch = OverallDimTool.to_sketch  # a view position -> the sketch plane, as Overall Dimension does it

    def __init__(self, view, sketch, on_finish=None):
        self.view, self.sketch = view, sketch
        self.picked = []
        self._on_finish = on_finish
        self._input = None

    def start(self, preselected=()):
        from incad.ui.view_clicks import ViewClicks
        self._input = ViewClicks(self.view, self._qt_press, lambda x, y: None)
        self._input.start()
        for pick in preselected:
            self.take(pick)
        if self._input is not None:  # three picked beforehand made the pair and ended the tool: nothing to ask
            self._prompt()

    def stop(self):
        if self._input is not None:
            self._input.stop()
            self._input = None
        self.picked = []
        self._highlight()
        if self._on_finish is not None:
            self._on_finish(self)

    def _prompt(self):
        log.report("info", PROMPTS[min(len(self.picked), 2)])

    # ----- input -----
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
        pick = sym.pick_at(self.sketch, pt, edge_tol * POINT_PX / EDGE_PX, edge_tol)
        if pick is None:
            self._prompt()
            return None
        return self.take(pick)

    def take(self, pick):
        """Take a pick; with two taken, the third is the mirror and the pair is made. Returns the number of ties
        added once a pair is made, else None."""
        sk = self.sketch
        if len(self.picked) < 2:
            if pick in self.picked:
                return None
            if self.picked and sym.kind(sk, pick) != sym.kind(sk, self.picked[0]):
                log.report("warning", "Pick the same kind as the first: two points, two lines, or two circles / arcs")
                return None
            if sym.kind(sk, pick) == "other":
                log.report("warning", "Splines can't be mirrored here: pick points, lines, circles or arcs")
                return None
            self.picked.append(pick)
            self._highlight()
            self._prompt()
            return None
        a, b = self.picked
        r = safe.run_safely("Symmetric", lambda: sym.constrain(sk, a, b, pick), sk.Document, only=[sk])
        if not r.ok:
            log.report("warning", "Symmetric: %s" % r.error)  # the two stay picked: click another mirror
            return None
        log.report("info", "Symmetric: done — drag them freely; Symmetric again for another pair")
        self.stop()
        return r.value

    def _highlight(self):
        """What is picked shows selected while the rest is awaited."""
        try:
            import FreeCADGui as Gui
            Gui.Selection.clearSelection()
            for pick in self.picked:
                sub = sym.subname(self.sketch, pick)
                if sub:
                    Gui.Selection.addSelection(self.sketch.Document.Name, self.sketch.Name, sub)
        except Exception:
            pass
