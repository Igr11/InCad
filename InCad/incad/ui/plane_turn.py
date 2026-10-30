"""Work Plane ▸ Turn rings (the user: loft planes turned with a gizmo about their axes): three circles round the
plane's point, about X (red), Y (green) and Z (blue) of what Turn measures from (the previous plane or the global
axes), each with a knob at its angle; dragging a knob sets that angle (5° steps, ⌘ / Ctrl for any value), previewed
live. Move Face's arrow does the rest (hit-testing hook, cursor, zoom watcher)."""
import math

import FreeCAD as App

from incad import host
from incad.ui.move_face_arrow import FaceArrow

ANGLE_STEP, ANGLE_FINE = 5.0, 0.1  # a drag snaps to 5°; with ⌘ (Ctrl) held, to 0.1°
FREE_KEY = "⌘" if host.MAC else "Ctrl"


def snapped_angle(value):
    from incad.qt import QtCore, QtWidgets
    fine = bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier)
    step = ANGLE_FINE if fine else ANGLE_STEP
    return round(round(value / step) * step, 4) + 0.0


def viewport_of(view):
    return view.graphicsView().viewport()


def log_drag():
    from incad.core import log
    log.logger().exception("Work Plane turn drag")

AXES = ("turn_x", "turn_y", "turn_z")
COLORS = ((0.90, 0.25, 0.25), (0.25, 0.75, 0.30), (0.25, 0.50, 0.95))
SEGMENTS = 72


def _start_and_side(frame, i):
    """The circle about axis i: (where 0° is, the way an angle turns) in global directions (right-handed)."""
    x, y, z = frame
    return ((y, z), (z, x), (x, y))[i]


class PlaneTurn(FaceArrow):
    FIELD = "turn_x"

    def __init__(self, shell, session):
        self.HINT = "Drag a knob to turn the plane about that axis (5° steps; hold %s for any value)" % FREE_KEY
        self._frame = None  # (centre, (x, y, z) axes, radius)
        self._axis = None   # the knob under the pointer or dragged: 0, 1, 2
        FaceArrow.__init__(self, shell, session)

    def _usable(self):
        return (self._values().get("mode") or "offset") == "offset"

    def _value(self, f):
        return 0.0

    def _angle(self, i):
        from incad.features.work import _deg
        try:
            return _deg(self._values().get(AXES[i]) or "0")
        except ValueError:
            return 0.0

    def _turn_frame(self, f):
        from incad.features import work
        values = self._values()
        body = f.getParentGeoFeatureGroup()
        g = body.getGlobalPlacement() if body is not None else App.Placement()
        centre = g.multVec(f.Placement.Base)
        own = work._global_rotation(f)
        base_rot = own.multiply(App.Rotation(f.AttachmentOffset.Rotation).inverted())
        ref = work._reference(self.session.doc, f, values.get("turn_ref") or "previous", base_rot)
        return centre, tuple(ref.multVec(App.Vector(*v)) for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))

    def _at(self, i, degrees, frame=None):
        centre, axes, radius = frame or self._frame
        u, v = _start_and_side(axes, i)
        t = math.radians(degrees)
        return centre + (u * math.cos(t) + v * math.sin(t)) * (radius * (1.0, 0.9, 0.8)[i])

    def refresh(self):
        from incad.ui.move_face_arrow import _screen_size
        self._remove_node()
        f, view = self.session.feature, self._active_view()
        try:
            if f is None or view is None or not self._usable() or f.TypeId != "PartDesign::Plane":
                return
        except ReferenceError:  # the plane was deleted while its dialog closed
            return
        try:
            centre, axes = self._turn_frame(f)
        except Exception:
            return
        try:
            vp = viewport_of(view)
            size = _screen_size(view, vp, centre) or 10.0
            dpr = vp.devicePixelRatioF()
        except Exception:
            size, dpr = 10.0, 1.0
        self._frame = (centre, axes, size)
        self._watch_zoom(view)
        self._nodes = self._rings(dpr)
        self.root = self._nodes["root"]
        view.getSceneGraph().addChild(self.root)
        self._geom, self._view = (centre, None, size), view

    def _rings(self, dpr):
        from pivy import coin
        from incad.ui import theme as themes
        from incad.ui.move_face_arrow import NAME, _rgb
        root = coin.SoAnnotation()
        root.setName(NAME)
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        nodes = dict(root=root, styles=[], balls=[], size=self._frame[2])
        for i in range(3):
            sep = coin.SoSeparator()
            color = coin.SoBaseColor()
            color.rgb.setValue(*COLORS[i])
            style = coin.SoDrawStyle()
            sep.addChild(color)
            sep.addChild(style)
            pts = [self._at(i, 360.0 * k / SEGMENTS) for k in range(SEGMENTS + 1)]
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, len(pts), [(p.x, p.y, p.z) for p in pts])
            sep.addChild(coords)
            sep.addChild(coin.SoLineSet())
            knob = self._at(i, self._angle(i))
            ks = coin.SoSeparator()
            move = coin.SoTranslation()
            move.translation.setValue(knob.x, knob.y, knob.z)
            ball = coin.SoSphere()
            ks.addChild(move)
            ks.addChild(ball)
            sep.addChild(ks)
            root.addChild(sep)
            nodes["styles"].append(style)
            nodes["balls"].append(ball)
        if self._label and self._axis is not None:
            knob = self._at(self._axis, self._angle(self._axis))
            out = knob - self._frame[0]
            at = knob + out * (0.3 / max(out.Length, 1e-9)) * self._frame[2]
            lab = coin.SoSeparator()
            c = coin.SoBaseColor()
            c.rgb.setValue(*_rgb(themes.PALETTES[self.shell.theme]["text"]))
            t = coin.SoTranslation()
            t.translation.setValue(at.x, at.y, at.z)
            font = coin.SoFont()
            font.size = 14 * dpr
            text = coin.SoText2()
            text.string = self._label.replace(" °", "°")
            for n in (c, t, font, text):
                lab.addChild(n)
            root.addChild(lab)
        self._paint(nodes)
        return nodes

    def _paint(self, nodes):
        for i in range(3):
            lit = self.lit and self._axis == i
            nodes["styles"][i].lineWidth = 4 if lit else 2
            nodes["balls"][i].radius = nodes["size"] * (0.10 if lit else 0.07)

    def _set_lit(self, lit):
        if lit != self.lit or (self._nodes is not None):
            self.lit = lit
            if self._nodes is not None:
                self._paint(self._nodes)

    def _hit(self, viewport, x, y):
        from incad.ui import dof_handles as dh
        session = self.session
        if self.root is None or self._frame is None or session.dialog is None or getattr(session, "_closed", False):
            return None
        if not self._usable():
            return None
        try:
            if viewport_of(self._view) != viewport:
                return None
        except Exception:
            return None
        best = None
        for i in range(3):
            kx, ky = dh.screen(self._view, viewport, self._at(i, self._angle(i)))
            d = math.hypot(kx - x, ky - y)
            if d <= dh.HANDLE_PX + 4 and (best is None or d < best[1]):
                best = (i, d)
        return best

    def hover(self, view, viewport, x, y):
        if self._drag is None and self._other is None and self._own(viewport):
            hit = self._hit(viewport, x, y)
            self._axis = hit[0] if hit is not None else None
        return FaceArrow.hover(self, view, viewport, x, y)

    def press(self, view, viewport, x, y):
        if not self._own(viewport):
            return FaceArrow.press(self, view, viewport, x, y)  # another view: the DOF gizmo's
        hit = self._hit(viewport, x, y)
        if hit is None:
            return False
        self._axis = hit[0]
        start = self._angle(self._axis)
        self._drag = [x, y, start, start, False, start]  # press, start, now, moved past DRAG_PX, unsnapped
        self._set_lit(True)
        self._set_cursor(viewport, closed=True)
        return True

    def _nearest(self, viewport, x, y, around):
        from incad.ui import dof_handles as dh
        best, best_d = around, None
        for k in range(-180, 181):
            a = around + k * 0.5
            sx, sy = dh.screen(self._view, viewport, self._at(self._axis, a))
            d = math.hypot(sx - x, sy - y)
            if best_d is None or d < best_d:
                best, best_d = a, d
        return best

    def move(self, x, y):
        from incad.core import gestures
        if self._other is not None:
            self._other.move(x, y)
            return
        drag = self._drag
        if drag is None or self._frame is None or self._axis is None:
            return
        if not drag[4]:
            if math.hypot(x - drag[0], y - drag[1]) <= gestures.DRAG_PX:
                return
            drag[4] = True
        try:
            raw = self._nearest(viewport_of(self._view), x, y, drag[5])
        except Exception:
            return
        drag[5] = raw
        angle = snapped_angle(((raw + 180.0) % 360.0) - 180.0)
        if abs(angle) < ANGLE_FINE / 2:
            angle = 0.0
        if angle == drag[3] and self._label:
            return
        drag[3] = angle
        self._label = "%g °" % angle
        dialog = self.session.dialog
        if dialog is None:
            return
        dialog.set_values({AXES[self._axis]: self._label})
        self.refresh()  # the knob at the new angle at once, ahead of the preview
        try:
            self.session._changed(dialog.values(), throttle=True)
        except Exception:
            log_drag()


    def _end(self):
        FaceArrow._end(self)
        self._label, self._axis = "", None
        self.refresh()


def plane_overlay(shell, session):
    return PlaneTurn(shell, session)
