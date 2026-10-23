"""DOF handles (Inventor): the glyph of the assembly part the user clicked (selected) is a gizmo — drag its arc to turn
the part about that axis, its arrow to slide it along that direction. Easy to catch: InCad hit-tests in screen space
(the pointer's distance to each handle's projected line and arrow heads, HANDLE_PX), never Coin picking; the handle
under the pointer lights up. The drag is InCad's own (no FreeCAD edit): every other free part is held by a temporary
ground, the part is turned / slid by the mouse's amount from where it started, solved after each move (a step the
solver can't meet keeps the last good place), all in one undo step "Move part".

The screen math at the top is pure (no FreeCAD, no Qt): points are (x, y) in logical px, top-left origin."""
import math

from incad.core import gestures, log

HANDLE_PX = 12        # logical px around a handle's line or arrow head that catch it
MIN_SHAFT_PX = 2 * HANDLE_PX  # a slide arrow seen shorter (nearly end-on, a dot at the centre) is no handle
MIN_FORESHORTEN = 0.2  # a slide whose mm shows shorter than this share of the view's mm is refused (it would fling)
EDGE_ON = 0.1         # an arc seen flatter than this (minor / major axis) is followed along its line instead


def segment_distance(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    n = ax * ax + ay * ay
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / n))
    return math.hypot(p[0] - (a[0] + t * ax), p[1] - (a[1] + t * ay))


def polyline_distance(p, pts):
    if len(pts) == 1:
        return math.hypot(p[0] - pts[0][0], p[1] - pts[0][1])
    return min(segment_distance(p, pts[k], pts[k + 1]) for k in range(len(pts) - 1))


def polyline_length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def nearest(candidates, p, tol=HANDLE_PX):
    """candidates: [(key, [polyline, ...])] on screen -> the key of the nearest one within tol, else None."""
    best, best_d = None, tol
    for key, polylines in candidates:
        d = min((polyline_distance(p, pl) for pl in polylines if pl), default=None)
        if d is not None and d <= best_d:
            best, best_d = key, d
    return best


def segment_toward(p, polylines):
    """(distance, unit direction) of the screen segment of `polylines` nearest p."""
    best = (float("inf"), (0.0, 0.0))
    for pl in polylines:
        segs = list(zip(pl, pl[1:])) or [(pl[0], pl[0])]
        for a, b in segs:
            d = segment_distance(p, a, b)
            if d < best[0]:
                n = math.hypot(b[0] - a[0], b[1] - a[1])
                best = (d, ((b[0] - a[0]) / n, (b[1] - a[1]) / n) if n else (0.0, 0.0))
    return best


def by_direction(options, motion, close=0.1):
    """options: [(key, distance, direction)] of the handles near the press -> the one whose line runs the way the
    pointer moved (the nearest of those about as well aligned): where an arc crosses an arrow or another arc on
    screen, dragging along the one meant picks it."""
    n = math.hypot(*motion)
    if not options:
        return None
    if n == 0:
        return min(options, key=lambda o: o[1])[0]
    cos = [(abs(o[2][0] * motion[0] + o[2][1] * motion[1]) / n, o) for o in options]
    top = max(c for c, _ in cos)
    return min((o for c, o in cos if c >= top - close), key=lambda o: o[1])[0]


def wrap(deg):
    """An angle step in (-180, 180]."""
    deg = math.fmod(deg, 360.0)
    if deg > 180:
        deg -= 360
    elif deg <= -180:
        deg += 360
    return deg


def plane_angle(centre, pu, pw, p):
    """The arc's own angle (degrees, from u towards w) of the screen point p: its plane's u and w axes seen on screen
    as the vectors pu, pw from the projected centre (an ellipse; exact for FreeCAD's orthographic camera). None when
    the plane is seen edge-on or p is on the centre."""
    det = pu[0] * pw[1] - pw[0] * pu[1]
    sq = pu[0] ** 2 + pu[1] ** 2 + pw[0] ** 2 + pw[1] ** 2
    major2 = (sq + math.sqrt(max(sq * sq - 4 * det * det, 0.0))) / 2  # the ellipse's half-axes: s1 * s2 = |det|
    if det == 0 or abs(det) < EDGE_ON * major2:  # minor / major below EDGE_ON: seen (nearly) edge-on
        return None
    mx, my = p[0] - centre[0], p[1] - centre[1]
    a = (mx * pw[1] - pw[0] * my) / det
    b = (pu[0] * my - mx * pu[1]) / det
    if abs(a) < 1e-9 and abs(b) < 1e-9:
        return None
    return math.degrees(math.atan2(b, a))


def track_angle(centre, pu, pw, p, last=None, window=90.0):
    """The arc's own angle (degrees) of the point of its projected circle nearest the screen point p, searched within
    `window` of the last reading (None: anywhere) and the nearest to it on a tie: it follows the pointer along an arc
    seen edge-on (a line, where front and back points coincide)."""
    best, best_key = None, None
    for k in range(-360, 360):
        t = k * 0.5
        dt = abs(wrap(t - last)) if last is not None else 0.0
        if dt > window:
            continue
        r = math.radians(t)
        q = (centre[0] + pu[0] * math.cos(r) + pw[0] * math.sin(r), centre[1] + pu[1] * math.cos(r) + pw[1] * math.sin(r))
        key = (round(math.hypot(p[0] - q[0], p[1] - q[1]), 6), dt)
        if best_key is None or key < best_key:
            best, best_key = t, key
    return best


def end_on(per_mm, axes_px, minimum=MIN_FORESHORTEN):
    """True when a direction showing 1 mm as the screen vector per_mm is seen (nearly) end-on: shorter than
    `minimum` of the view's own scale (the longest of the screen vectors of 1 mm along X, Y and Z, axes_px)."""
    scale = max((math.hypot(*v) for v in axes_px), default=0)
    return scale <= 0 or math.hypot(*per_mm) < minimum * scale


def mm_along(delta, per_mm):
    """A screen delta -> mm along a direction that 1 mm of shows as the screen vector per_mm."""
    n = per_mm[0] ** 2 + per_mm[1] ** 2
    if n < 1e-9:
        return 0
    return (delta[0] * per_mm[0] + delta[1] * per_mm[1]) / n


# ----- FreeCAD side -----

def screen(view, viewport, v):
    """A 3D point -> its viewport position (logical px, top-left origin)."""
    from incad.ui.nav import from_coin
    x, y = view.getPointOnViewport(v)
    return from_coin(viewport, x, y)


def selected_component(doc):
    """The one assembly component the selection names (a 3D click on it gives the assembly + 'Link.Body.Face6', a
    browser row the link itself), else None (nothing, several parts, a joint or anything else)."""
    import FreeCADGui as Gui
    from incad.core import assembly
    comps = {c.Name for c in assembly.components(doc)}
    names = set()
    for sel in Gui.Selection.getSelectionEx(doc.Name, 0):
        o = sel.Object
        if o.Name in comps:
            names.add(o.Name)
        elif o.TypeId == "Assembly::AssemblyObject":
            for sub in sel.SubElementNames or ("",):
                first = sub.split(".")[0] if sub else ""
                names.add(first if first in comps else None)
        else:
            names.add(None)
    return names.pop() if len(names) == 1 and None not in names else None


class HandleDrag:
    """One drag of one handle: begun on the first move past DRAG_PX, finished on the release."""

    def __init__(self, owner, doc, link, handles, options, view, viewport, x, y):
        """options: [(index, distance, screen direction)] of the handles near the press; the one dragged is chosen
        by the first move (by_direction)."""
        self.owner, self.shell = owner, owner.shell
        self.doc_name, self.link_name, self.handles, self.options = doc.Name, link.Name, handles, options
        self.index = min(options, key=lambda o: o[1])[0]
        self.handle = handles[self.index]
        self.view, self.viewport, self.press = view, viewport, (x, y)
        self.started = False
        self.label = link.Label
        self.amount = 0.0
        self._held, self._start, self._good = [], None, None

    def _doc(self):
        import FreeCAD as App
        return App.getDocument(self.doc_name) if self.doc_name in App.listDocuments() else None

    def begin(self):
        """Open the step and hold every other free part: the solver then moves only this one."""
        import FreeCAD as App
        from incad.core import assembly
        doc = self._doc()
        link = doc.getObject(self.link_name) if doc is not None else None
        if link is None:
            raise RuntimeError("the part is gone")
        h = self.handle
        sc = lambda v: screen(self.view, self.viewport, v)
        if h.kind == "turn":
            c = sc(h.point)
            self._centre = c
            pu, pw = sc(h.point + h.u * h.radius), sc(h.point + h.w * h.radius)
            self._pu, self._pw = (pu[0] - c[0], pu[1] - c[1]), (pw[0] - c[0], pw[1] - c[1])
            self._last = None
            self._last = self._angle(*self.press)
        else:
            a, b = sc(h.point), sc(h.point + h.axis)
            self._per_mm = (b[0] - a[0], b[1] - a[1])
            axes = [sc(h.point + App.Vector(*e)) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            if end_on(self._per_mm, [(q[0] - a[0], q[1] - a[1]) for q in axes]):
                raise RuntimeError("that direction points at the viewer: turn the view")
        if doc.HasPendingTransaction:  # a stray change: its own step, apart from the drag
            doc.commitTransaction()
        if not doc.UndoMode:
            doc.UndoMode = 1
        self._start = App.Placement(link.Placement)
        self._good = App.Placement(link.Placement)
        doc.openTransaction("Move part")
        self.started = True
        self._held = [c.Name for c in assembly.components(doc) if c is not link
                      and not assembly.is_grounded(c) and not assembly.is_suppressed(c)]
        for name in self._held:
            assembly.ground(doc.getObject(name))

    def _angle(self, x, y):
        """The arc's own angle under the pointer: read through the projected ellipse, or, seen edge-on, tracked
        along it from the last reading."""
        a = plane_angle(self._centre, self._pu, self._pw, (x, y))
        if a is not None:
            return a
        return track_angle(self._centre, self._pu, self._pw, (x, y), self._last)

    def move(self, x, y):
        import FreeCAD as App
        from incad.core import assembly
        if not self.started:
            if math.hypot(x - self.press[0], y - self.press[1]) <= gestures.DRAG_PX:
                return
            self.index = by_direction(self.options, (x - self.press[0], y - self.press[1]))
            self.handle = self.handles[self.index]
            self.owner.lit = self.index
            self.begin()
        doc = self._doc()
        link = doc.getObject(self.link_name) if doc is not None else None
        if link is None:
            return
        h = self.handle
        if h.kind == "turn":
            a = self._angle(x, y)
            self.amount += wrap(a - self._last)
            self._last = a
            delta = App.Placement(App.Vector(), App.Rotation(h.axis, self.amount), h.pivot)
            text = "Turn %d°" % round(self.amount)
        else:
            self.amount = mm_along((x - self.press[0], y - self.press[1]), self._per_mm)
            delta = App.Placement(h.axis * self.amount, App.Rotation())
            text = "Slide %.1f mm" % self.amount
        link.Placement = delta.multiply(self._start)
        try:
            ok = assembly.assembly_of(doc).solve() == 0
        except Exception:
            ok = False
        if ok:
            self._good = App.Placement(link.Placement)
        else:
            link.Placement = self._good  # the solver can't meet this step: the last good place
        self._status(text)
        self.shell.dof_display_changed()

    def _status(self, text):
        status = getattr(self.shell, "status", None)
        if status is not None:
            status.show_message("info", text)

    def finish(self, moved_ok=True, closing=False):
        """Grounds off, the step committed when the part moved (else aborted). closing: the document is going."""
        from incad.core import assembly
        if not self.started:
            return False
        self.started = False
        doc = None if closing else self._doc()
        if doc is None:
            return False
        moved, done = False, False
        try:
            try:
                for name in self._held:
                    o = doc.getObject(name)
                    if o is not None:
                        assembly.unground(o)
                link = doc.getObject(self.link_name)
                moved = moved_ok and link is not None and not link.Placement.isSame(self._start, 1e-9)
                if moved:
                    doc.recompute()
                if doc.HasPendingTransaction:
                    doc.commitTransaction() if moved else doc.abortTransaction()
                done = True
            finally:
                if not done and doc.HasPendingTransaction:
                    moved = False
                    doc.abortTransaction()  # a failed clean-up: the step goes, the part and the grounds with it
        finally:
            self._held = []
        return moved


class Handles:
    """The navigator's handle hook and the gizmo state: which part's handles are drawn (where), which one is lit,
    the drag going on."""

    def __init__(self, shell):
        self.shell = shell
        self.drawn = None     # (doc name, part name, [Handle], size, view) of the gizmo on screen
        self.lit = None       # index into drawn's handles under the pointer
        self.drag = None      # HandleDrag
        self._cursor = None   # viewport we set a hand cursor on

    # --- state the shell reads ---
    def dragging(self):
        return self.drag is not None

    def wants_selection(self):
        """A selection change matters to the gizmo only in an assembly (or while one is drawn): a part document's
        clicks and menus run exactly as without it."""
        if self.drawn is not None or self.drag is not None:
            return True
        try:
            import FreeCAD as App
            from incad.core import assembly
            return assembly.is_assembly(App.ActiveDocument)
        except Exception:
            return False

    def gizmo_part(self, doc):
        """The part whose glyph gets handles: the one being dragged, else the selected free component while a
        handle could be grabbed."""
        if self.drag is not None:
            return self.drag.link_name if self.drag.doc_name == doc.Name else None
        if not self.can_grab():
            return None
        try:
            return selected_component(doc)
        except Exception:
            return None

    def set_drawn(self, doc_name, name, handles, size, view):
        if self.drawn is None or self.drawn[:2] != (doc_name, name):
            self.lit = None if self.drag is None else self.lit
        self.drawn = (doc_name, name, handles, size, view)

    def clear_drawn(self):
        self.drawn = None
        if self.drag is None:
            self.lit = None
        self._set_cursor(None)

    def can_grab(self):
        """The same guards as AssemblyDrag.begin: no dialog, tool, pick or FreeCAD edit owns the mouse."""
        import FreeCAD as App
        import FreeCADGui as Gui
        from incad.core import assembly
        sh = self.shell
        if sh.feature_session is not None or any(
                getattr(sh, a, None) is not None for a in ("_point_pick", "_region_pick", "_profile_pick")):
            return False
        drag = getattr(sh, "asm_drag", None)
        if drag is not None and drag.active():
            return False
        if Gui.editDocument() is not None or Gui.Control.activeDialog():
            return False
        return assembly.is_assembly(App.ActiveDocument)

    # --- hit-test ---
    def _candidates(self, view, viewport):
        import FreeCAD as App
        if self.drawn is None:
            return []
        doc_name, _, handles, size, drawn_view = self.drawn
        try:
            if drawn_view.graphicsView().viewport() != viewport:
                return []  # the gizmo is in another view
        except Exception:
            return []
        view = drawn_view
        if App.ActiveDocument is None or App.ActiveDocument.Name != doc_name:
            return []
        sc = lambda v: screen(view, viewport, v)
        h_len = size * 0.25
        out = []
        for k, h in enumerate(handles):
            polylines = [[sc(p) for p in h.line]]
            if h.kind == "slide" and polyline_length(polylines[0]) < MIN_SHAFT_PX:
                continue  # seen end-on: a dot at the part's centre, where the user aims to drag the part itself
            polylines += [[sc(tip), sc(tip - d * h_len)] for tip, d in h.heads]
            out.append((k, polylines))
        return out

    def hit(self, view, viewport, x, y):
        return nearest(self._candidates(view, viewport), (x, y))

    def at(self, view, viewport, x, y):
        return self.drawn is not None and self.can_grab() and self.hit(view, viewport, x, y) is not None

    # --- the navigator's hook ---
    def hover(self, view, viewport, x, y):
        if self.drag is not None or self.drawn is None and self.lit is None and self._cursor is None:
            return  # no gizmo (a part document, nothing selected): nothing to do
        k = self.hit(view, viewport, x, y) if self.drawn is not None and self.can_grab() else None
        self._set_cursor(viewport if k is not None else None)
        if k != self.lit:
            self.lit = k
            self.shell.dof_display_changed()

    def press(self, view, viewport, x, y):
        import FreeCAD as App
        if self.drag is not None:
            self.finish()
        if self.shell.axis_pressed(view, viewport, x, y):  # a part's axis taken by a constraint dialog
            return True
        if self.drawn is None or not self.can_grab():
            return False
        options = []
        for k, polylines in self._candidates(view, viewport):
            d, direction = segment_toward((x, y), polylines)
            if d <= HANDLE_PX:
                options.append((k, d, direction))
        if not options:
            return False
        doc_name, name, handles = self.drawn[:3]
        doc = App.ActiveDocument
        link = doc.getObject(name) if doc is not None and doc.Name == doc_name else None
        if link is None:
            return False
        self.drag = HandleDrag(self, doc, link, handles, options, view, viewport, x, y)
        self.lit = self.drag.index
        self._set_cursor(viewport, closed=True)
        return True

    def move(self, x, y):
        drag = self.drag
        if drag is None:
            return
        try:
            drag.move(x, y)
        except Exception as e:
            log.report("warning", "Can't move %s: %s" % (drag.label, e))
            self.finish(moved_ok=False)

    def release(self):
        """The press's release: True when it was a plain click (no drag) for FreeCAD to have — it selects or clears
        as usual — unless the gizmo's own part is under it (then nothing changes)."""
        drag = self.drag
        click = drag is not None and not drag.started
        self.finish()
        if not click:
            return False
        try:
            from incad.ui.asm_drag import component_in_hits
            from incad.ui.nav import to_coin
            import FreeCAD as App
            doc = App.getDocument(drag.doc_name)
            link = component_in_hits(doc, drag.view.getObjectsInfo(to_coin(drag.viewport, *drag.press)))
            return link is None or link.Name != drag.link_name
        except Exception:
            return False

    def finish(self, moved_ok=True, closing=False):
        """End the handle drag (its release, a command, a closing document or tab): the clean-up runs once."""
        drag, self.drag = self.drag, None
        if drag is None:
            return
        self._set_cursor(None)
        moved = False
        try:
            moved = drag.finish(moved_ok, closing)
        except Exception as e:
            log.report("warning", "Can't move %s: %s" % (drag.label, e))
        finally:
            if not closing:
                self.shell.schedule_refresh()
                self.shell.dof_display_changed()
        if moved:
            log.report("info", "Moved %s" % drag.label)
        elif not closing and drag.amount == 0:
            status = getattr(self.shell, "status", None)
            if status is not None and status.texts().get("message", "").startswith(("Turn ", "Slide ")):
                status.clear_message()

    def document_closing(self, doc_name):
        if self.drag is not None and self.drag.doc_name == doc_name:
            self.finish(moved_ok=False, closing=True)
        if self.drawn is not None and self.drawn[0] == doc_name:
            self.clear_drawn()

    def _set_cursor(self, viewport, closed=False):
        """Open hand over a handle, closed while dragging; FreeCAD's own cursor is never taken away."""
        from incad.qt import QtCore, QtGui
        ours = (QtCore.Qt.OpenHandCursor, QtCore.Qt.ClosedHandCursor)
        try:
            if self._cursor is not None and self._cursor is not viewport:
                if self._cursor.cursor().shape() in ours:
                    self._cursor.unsetCursor()
                self._cursor = None
            if viewport is not None:
                shape = viewport.cursor().shape()
                if shape == QtCore.Qt.BitmapCursor:
                    return  # a Sketcher tool's cursor
                viewport.setCursor(QtGui.QCursor(ours[1] if closed else ours[0]))
                self._cursor = viewport
        except RuntimeError:
            self._cursor = None
