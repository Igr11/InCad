"""The assembly's DOF gizmo on a Gear or Worm (the user: arrows as in the assembly, moving with dimensions; smaller;
turning too; there after the gears are placed): a double arrow along each of the gear's own X, Y and Z and an arc
round each of them — Offset X / Y / Z (whole mm; ⌘ / Ctrl held: 0.01 mm), Turn round its axis and Rotate X / Y
(5°; ⌘: 0.1°). The value shows at the pointer.

Two places: in a gear set's dialog (a drag writes the dialog's fields and previews), and on a gear selected in the
part with no dialog open (a drag writes the set's own parameters, recomputes as it goes, one undo step "Move Gear").
A set's second gear is placed by its first: the gizmo is the first's.

Drawn by DofGlyphs, hit-tested in screen space like the assembly's handles (ui/dof_handles), the drag never reaching
FreeCAD (the navigator's handle hook)."""
import math
import time

from incad.core import gestures, log
from incad.qt import viewport_of
from incad.ui import dof_handles as dh

SLIDES = ("offset_x", "offset_y", "offset_z")
TURNS = ("turn", "rotate_x", "rotate_y")      # round the gear's Z (its axis), X, Y
NAMES = {"offset_x": "X", "offset_y": "Y", "offset_z": "Z", "turn": "Turn", "rotate_x": "Rotate X",
         "rotate_y": "Rotate Y"}
PROPS = {"offset_x": ("OffsetX", "length"), "offset_y": ("OffsetY", "length"), "offset_z": ("OffsetZ", "length"),
         "turn": ("Turn", "angle"), "rotate_x": ("RotateX", "angle"), "rotate_y": ("RotateY", "angle")}
STEP, FINE = 1.0, 0.01        # mm
ANGLE_STEP, ANGLE_FINE = 5.0, 0.1
SIZE = 0.38                   # × the gear's width: arrows across three quarters of it (the user: too small to hold;
                              # still inside the gear, as asked before)
GRAB_PX = 18                  # logical px around a handle that catch it (the assembly's: 12; the user: hard to hold)
AXIS_RGB = ((0.90, 0.25, 0.25), (0.25, 0.75, 0.30), (0.25, 0.50, 0.95))  # X red, Y green, Z blue (as Turn rings)
TURN_AXIS = (2, 0, 1)          # TURNS round the gear's Z, X, Y: their colours
DIRECT_EVERY = 0.12           # s between recomputes while a selected gear is dragged


def _fine():
    from incad.qt import QtCore, QtWidgets
    return bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier)


def snapped(value, step):
    return round(round(value / step) * step, 4) + 0.0  # + 0.0: never "-0"


def _number(text):
    import FreeCAD as App
    try:
        return float(App.Units.Quantity((text or "0").strip()).Value)
    except Exception:
        return None


class GearGizmo:
    def __init__(self, shell, session=None, feature=None):
        """session: a dialog's gizmo; feature: a selected gear's, no dialog."""
        self.shell, self.session, self.target = shell, session, feature
        self.handles, self.size, self.view = [], 0.0, None
        self.lit = None
        self._glyphs, self._drag, self._cursor = None, None, None
        self.refresh()

    # --- what it is drawn on ---
    def _feature(self):
        from incad.features import gear
        f = self.session.feature if self.session is not None else self.target
        try:
            return gear.lead_of(f) if f is not None and f.Document is not None else None
        except Exception:
            return None

    def _doc_name(self):
        if self.session is not None:
            return self.session.doc_name
        f = self._feature()
        return f.Document.Name if f is not None else None

    def _active_view(self):
        import FreeCADGui as Gui
        name = self._doc_name()
        gdoc = Gui.getDocument(name) if name else None
        return gdoc.ActiveView if gdoc is not None else None

    def refresh(self):
        """Draw the gizmo where the gear now stands (after each preview or recompute)."""
        from types import SimpleNamespace
        import FreeCAD as App
        from incad.core import dof
        from incad.features import gear
        f = self._feature()
        frame = None
        try:
            frame = gear.gizmo_frame(f) if f is not None else None
        except Exception:
            frame = None
        view = self._active_view()
        if frame is None or view is None:
            self.handles = []
            self._draw()
            return
        try:
            shape = f.AddSubShape if not f.AddSubShape.isNull() else f.Shape
            bb = shape.BoundBox
            width = max(bb.XLength, bb.YLength, bb.ZLength)  # its diameter (a gear is thinner than it is wide)
        except Exception:
            width = 40.0
        self.size = max(width * SIZE, 3.0)
        V = App.Vector
        freedom = SimpleNamespace(slides=[V(1, 0, 0), V(0, 1, 0), V(0, 0, 1)],
                                  turns=[(V(0, 0, 0), V(0, 0, 1)), (V(0, 0, 0), V(1, 0, 0)), (V(0, 0, 0), V(0, 1, 0))])
        self.handles = dof.handles(freedom, frame, frame.Base, self.size)
        self.view = view
        self._draw()

    def _draw(self):
        from incad.ui.dof_glyphs import DofGlyphs
        if not self.handles:
            if self._glyphs is not None:
                self._glyphs.clear()
            return
        try:
            if self._glyphs is None or self._glyphs.view is not self.view:
                if self._glyphs is not None:
                    self._glyphs.remove()
                self._glyphs = DofGlyphs(self.view, getattr(self.shell, "theme", "light"))
            self._glyphs.set([("gear", self.handles, self.size, True, self.lit, self.colours())])
        except Exception:
            log.logger().exception("gear gizmo")

    def colours(self):
        """Each handle in its axis's colour (the user: all one colour, hard to tell apart): a slide along X and the
        turn round X red, Y green, Z (the gear's own Turn) blue."""
        return [AXIS_RGB[h.index if h.kind == "slide" else TURN_AXIS[h.index]] for h in self.handles]

    def key_of(self, handle):
        return (TURNS if handle.kind == "turn" else SLIDES)[handle.index]

    # --- hit-test (the assembly's rules) ---
    def _candidates(self, viewport):
        if not self.handles or self.view is None:
            return []
        try:
            if viewport_of(self.view) != viewport:
                return []
        except Exception:
            return []
        sc = lambda v: dh.screen(self.view, viewport, v)
        from incad.ui.dof_glyphs import HEAD
        h_len = self.size * HEAD
        out = []
        for k, h in enumerate(self.handles):
            polylines = [[sc(p) for p in h.line]]
            if h.kind == "slide" and dh.polyline_length(polylines[0]) < dh.MIN_SHAFT_PX:
                continue
            polylines += [[sc(tip), sc(tip - d * h_len)] for tip, d in h.heads]
            out.append((k, polylines))
        return out

    def hit(self, viewport, x, y):
        return dh.nearest(self._candidates(viewport), (x, y), GRAB_PX)

    def dragging(self):
        return self._drag is not None

    def label_text(self):
        return self._drag["text"] if self._drag is not None else ""

    # --- the navigator's hook ---
    def hover(self, view, viewport, x, y):
        if self._drag is not None:
            return False
        k = self.hit(viewport, x, y)
        self._set_cursor(viewport if k is not None else None)
        if k != self.lit:
            self.lit = k
            self._draw()
            key = "⌘" if __import__("incad.host", fromlist=["MAC"]).MAC else "Ctrl"
            self._tip(viewport, x, y, ("Drag to move (whole mm), an arc to turn (5°); hold %s for any value" % key)
                      if k is not None else "")
        return False

    def _values(self):
        """The current values of the six, as the dialog's texts (a dialog) or the gear's own (no dialog)."""
        if self.session is not None:
            return self.session.dialog.values() if self.session.dialog is not None else {}
        f = self._feature()
        out = {}
        for key, (prop, unit) in PROPS.items():
            v = getattr(f, prop).Value if f is not None and hasattr(f, prop) else 0.0
            out[key] = "%g %s" % (v, "mm" if unit == "length" else "°")
        return out

    def press(self, view, viewport, x, y):
        options = []
        for k, polylines in self._candidates(viewport):
            d, direction = dh.segment_toward((x, y), polylines)
            if d <= GRAB_PX:
                options.append((k, d, direction))
        if not options or (self.session is not None and self.session.dialog is None):
            return False
        self._drag = {"press": (x, y), "options": options, "index": min(options, key=lambda o: o[1])[0],
                      "started": False, "viewport": viewport, "values": self._values(), "text": "",
                      "applied": 0.0, "pending": None}
        self.lit = self._drag["index"]
        self._draw()
        self._set_cursor(viewport, closed=True)
        return True

    def _begin(self, x, y):
        import FreeCAD as App
        drag = self._drag
        drag["index"] = dh.by_direction(drag["options"], (x - drag["press"][0], y - drag["press"][1]))
        h = self.handles[drag["index"]]
        drag["key"] = self.key_of(h)
        drag["start"] = _number(drag["values"].get(drag["key"])) or 0.0
        sc = lambda v: dh.screen(self.view, drag["viewport"], v)
        if h.kind == "turn":
            c = sc(h.point)
            pu, pw = sc(h.point + h.u * h.radius), sc(h.point + h.w * h.radius)
            drag["turn"] = (c, (pu[0] - c[0], pu[1] - c[1]), (pw[0] - c[0], pw[1] - c[1]))
            drag["last"] = None
            drag["last"] = self._angle(*drag["press"])
            drag["amount"] = 0.0
        else:
            a, b = sc(h.point), sc(h.point + h.axis)
            drag["per_mm"] = (b[0] - a[0], b[1] - a[1])
            axes = [sc(h.point + App.Vector(*e)) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            if dh.end_on(drag["per_mm"], [(q[0] - a[0], q[1] - a[1]) for q in axes]):
                raise ValueError("that direction points at the viewer: turn the view")
        if self.session is None:  # a selected gear: one undo step for the whole drag
            doc = self._feature().Document
            if doc.HasPendingTransaction:
                doc.commitTransaction()
            if not doc.UndoMode:
                doc.UndoMode = 1
            doc.openTransaction("Move Gear")
        drag["started"] = True
        self.lit = drag["index"]

    def _angle(self, x, y):
        c, pu, pw = self._drag["turn"]
        a = dh.plane_angle(c, pu, pw, (x, y))
        return a if a is not None else dh.track_angle(c, pu, pw, (x, y), self._drag["last"])

    def move(self, x, y):
        drag = self._drag
        if drag is None:
            return
        try:
            if not drag["started"]:
                if math.hypot(x - drag["press"][0], y - drag["press"][1]) <= gestures.DRAG_PX:
                    return
                self._begin(x, y)
            fine = _fine()
            key = drag["key"]
            if key in TURNS:
                a = self._angle(x, y)
                drag["amount"] += dh.wrap(a - drag["last"])
                drag["last"] = a
                value = snapped(drag["start"] + drag["amount"], ANGLE_FINE if fine else ANGLE_STEP)
                text, shown = "%g °" % value, "%s %g°" % (NAMES[key], value)
            else:
                amount = dh.mm_along((x - drag["press"][0], y - drag["press"][1]), drag["per_mm"])
                value = snapped(drag["start"] + amount, FINE if fine else STEP)
                text, shown = "%g mm" % value, "%s %g mm" % (NAMES[key], value)
            if shown == drag["text"]:
                return
            drag["text"] = shown
            self._tip(drag["viewport"], x, y, shown)
            status = getattr(self.shell, "status", None)
            if status is not None:
                status.show_message("info", shown)
            if self.session is not None:
                dialog = self.session.dialog
                if dialog is None:
                    return
                dialog.set_values({key: text})
                self.session._changed(dialog.values(), throttle=True)  # a preview every interval while it moves
            else:
                drag["pending"] = (key, text)
                if time.monotonic() - drag["applied"] >= DIRECT_EVERY:
                    self._apply_pending()
        except ValueError as e:
            log.report("warning", str(e))
            self.finish()
        except Exception:
            log.logger().exception("gear gizmo drag")
            self.finish()

    def _apply_pending(self):
        """A selected gear's drag: the value into its parameter and the part recomputed."""
        from incad.features.common import value_param
        drag = self._drag
        if drag is None or drag["pending"] is None:
            return
        key, text = drag["pending"]
        drag["pending"] = None
        f = self._feature()
        prop, unit = PROPS[key]
        value_param(f.Document, f, prop, text, unit)
        f.Document.recompute()
        drag["applied"] = time.monotonic()
        self.refresh()

    def release(self):
        """Never handed to FreeCAD as a click (it would pick what is under the gizmo)."""
        self.finish()
        return False

    def finish(self, moved_ok=True, closing=False):
        drag, self._drag = self._drag, None
        if drag is not None and drag["started"] and self.session is None and not closing:
            f = self._feature()
            doc = f.Document if f is not None else None
            try:
                if moved_ok and drag["pending"] is not None:
                    self._drag = drag
                    self._apply_pending()
                    self._drag = None
                if doc is not None and doc.HasPendingTransaction:
                    doc.commitTransaction() if moved_ok and drag["text"] else doc.abortTransaction()
            except Exception:
                log.logger().exception("gear gizmo finish")
                if doc is not None and doc.HasPendingTransaction:
                    doc.abortTransaction()
            if self.shell is not None and hasattr(self.shell, "schedule_refresh"):
                self.shell.schedule_refresh()
        self._set_cursor(None)
        self._tip(None, 0, 0, "")
        if not closing:
            self.refresh() if self.session is None else self._draw()

    def remove(self):
        self.finish(closing=True)
        if self._glyphs is not None:
            self._glyphs.remove()
            self._glyphs = None

    # --- looks ---
    def _tip(self, viewport, x, y, text):
        from incad.qt import QtCore, QtWidgets
        try:
            if text and viewport is not None:
                QtWidgets.QToolTip.showText(viewport.mapToGlobal(QtCore.QPoint(int(x) + 14, int(y) + 18)), text,
                                            viewport)
            else:
                QtWidgets.QToolTip.hideText()
        except RuntimeError:
            pass

    def _set_cursor(self, viewport, closed=False):
        from incad.qt import QtCore, QtGui
        ours = (QtCore.Qt.OpenHandCursor, QtCore.Qt.ClosedHandCursor)
        try:
            if self._cursor is not None and self._cursor is not viewport:
                if self._cursor.cursor().shape() in ours:
                    self._cursor.unsetCursor()
                self._cursor = None
            if viewport is not None:
                if viewport.cursor().shape() == QtCore.Qt.BitmapCursor:
                    return
                viewport.setCursor(QtGui.QCursor(ours[1] if closed else ours[0]))
                self._cursor = viewport
        except RuntimeError:
            self._cursor = None
