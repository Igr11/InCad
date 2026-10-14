"""Move Face's drag arrow: drawn on the first face along its normal (the assembly gizmo's look and size), hit in
screen space (dof_handles.HANDLE_PX), dragged by InCad itself through Navigator.handle_hook; a label at the tip
shows the distance live (like Fusion). The dialog's Distance field follows the drag; a typed value moves it."""
import math

from incad.core import dof, gestures, log
from incad.ui import dof_handles as dh
from incad.ui import theme as themes

NAME = "InCadMoveFaceArrow"


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _mm(text):
    """A distance as typed ("5 mm", "0.5 in", "2*3 mm") in mm; None when it is no plain quantity (a formula)."""
    import FreeCAD as App
    text = str(text or "").strip()
    if not text:
        return None
    try:
        q = App.Units.Quantity(text)
        return float(q.Value) if q.Unit == App.Units.Unit() else float(q.getValueAs("mm"))
    except Exception:  # no quantity, or not a length
        return None


def _shown(text):
    """A distance as the label shows it: a plain "-" (the view's text drops the typographic minus U+2212, so
    −3 mm showed as "3 mm")."""
    return str(text or "").strip()


def _arrow_node(point, normal, size, text, theme, dpr=1.0):
    """The arrow (a line and a cone, as dof_glyphs draws a slide arrow) from `point` along `normal`, and the label
    beyond its tip: an SoAnnotation that is never picked. Returns a dict of the nodes: root, shift (moves it all
    along the normal during a drag), label (the SoText2), and color / style / cone (lit by _light)."""
    from pivy import coin
    palette = themes.PALETTES[theme]
    root = coin.SoAnnotation()
    root.setName(NAME)
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    root.addChild(pick)
    shift = coin.SoTransform()
    root.addChild(shift)
    sep = coin.SoSeparator()
    color = coin.SoBaseColor()
    color.rgb.setValue(*_rgb(palette["marker_end"]))
    style = coin.SoDrawStyle()
    style.lineWidth = 3
    sep.addChild(color)
    sep.addChild(style)
    tip = point + normal * size
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, 2, [(point.x, point.y, point.z), (tip.x, tip.y, tip.z)])
    sep.addChild(coords)
    sep.addChild(coin.SoLineSet())
    h = size * 0.25
    head = coin.SoSeparator()
    t = coin.SoTransform()
    base = tip - normal * (h / 2)
    t.translation.setValue(base.x, base.y, base.z)
    t.rotation.setValue(coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(normal.x, normal.y, normal.z)))
    cone = coin.SoCone()
    cone.height, cone.bottomRadius = h, size * 0.1
    head.addChild(t)
    head.addChild(cone)
    sep.addChild(head)
    root.addChild(sep)
    lab = coin.SoSeparator()
    c = coin.SoBaseColor()
    c.rgb.setValue(*_rgb(palette["text"]))
    at = point + normal * (size * 1.15)
    move = coin.SoTranslation()
    move.translation.setValue(at.x, at.y, at.z)
    font = coin.SoFont()
    font.size = 14 * dpr  # SoText2 draws in device px
    label = coin.SoText2()
    label.string = text
    for n in (c, move, font, label):
        lab.addChild(n)
    root.addChild(lab)
    return dict(root=root, shift=shift, label=label, color=color, style=style, cone=cone, size=size)


def _set_label(label, text):
    label.string = text


def _light(nodes, lit, theme):
    """The arrow under the pointer (or dragged) in the accent colour and thicker, as the gizmo lights a handle."""
    palette = themes.PALETTES[theme]
    nodes["color"].rgb.setValue(*_rgb(palette["accent" if lit else "marker_end"]))
    nodes["style"].lineWidth = 6 if lit else 3
    nodes["cone"].bottomRadius = nodes["size"] * (0.14 if lit else 0.1)


class FaceArrow:
    def __init__(self, shell, session):
        self.shell, self.session = shell, session
        self.root, self._drag, self._label = None, None, ""
        self._geom, self._view, self._nodes = None, None, None
        self._built = 0.0   # the feature's distance the arrow was drawn at
        self._good = None   # the last distance a preview worked with (a refused one leaves the arrow there)
        self._offset = 0.0  # mm along the normal it is shown moved by (the drag ahead of the preview)
        self.lit = False    # the pointer is over it (or it is dragged)
        self._cursor = None  # viewport we set a hand cursor on
        self._other = None   # the DOF gizmo, while a press in another view is its drag
        self.refresh()

    def _active_view(self):
        import FreeCADGui as Gui
        gdoc = Gui.getDocument(self.session.doc_name)
        return gdoc.ActiveView if gdoc is not None else None

    def _place(self, distance=None):
        from incad.features import move_face
        f = self.session.feature
        return move_face.arrow(f, distance) if f is not None else None

    def _values(self):
        dialog = self.session.dialog
        return dialog.values() if dialog is not None else {}

    def label_text(self):
        return self._label

    def dragging(self):
        return self._drag is not None or self._other is not None and self._other.dragging()

    def _label_for(self, f, refused=False):
        """The Distance as typed; a formula as its value; nothing with Extent = To; after a refused preview the
        distance the arrow stays at."""
        values = self._values()
        if values.get("extent", "distance") != "distance":
            return ""
        text = values.get("distance", "")
        if refused:
            return _shown("%g mm" % round(self._built, 4))
        if _mm(text) is not None:
            return _shown(text)
        return _shown("%g mm" % round(f.Distance.Value, 4))

    def refresh(self):
        """Redraw at the feature's current place (after every preview, a theme switch) with the dialog's distance."""
        self._remove_node()
        f = self.session.feature
        refused = f is not None and "Invalid" in f.State and self._good is not None
        if f is not None and not refused:
            self._good = f.Distance.Value
        place, view = self._place(self._good if refused else None), self._active_view()
        if place is None or view is None:
            return
        point, normal = place
        base = getattr(f, "BaseFeature", None)
        shape = base.Shape if base is not None and not base.Shape.isNull() else f.Shape
        size = dof.glyph_size(shape.BoundBox.DiagonalLength)
        self._built = self._good if refused else f.Distance.Value
        if self._drag is None:
            self._label = self._label_for(f, refused)
            self._offset = 0.0
        else:
            self._offset = self._drag[4] - self._built  # a preview landed mid-drag: the arrow stays at the pointer
        try:
            dpr = view.graphicsView().viewport().devicePixelRatioF()
        except Exception:
            dpr = 1.0
        self._nodes = _arrow_node(point, normal, size, self._label, self.shell.theme, dpr)
        self.root = self._nodes["root"]
        _light(self._nodes, self.lit, self.shell.theme)
        off = normal * self._offset
        self._nodes["shift"].translation.setValue(off.x, off.y, off.z)
        view.getSceneGraph().addChild(self.root)
        self._geom, self._view = (point, normal, size), view

    def _remove_node(self):
        if self.root is not None and self._view is not None:
            try:
                self._view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass  # the view is gone with its document
        self.root = self._nodes = self._view = None

    def _ends_px(self, view, viewport):
        point, normal, size = self._geom
        base = point + normal * self._offset
        return dh.screen(view, viewport, base), dh.screen(view, viewport, base + normal * size)

    def _hit(self, viewport, x, y):
        """The arrow's screen ends (base, tip) when (x, y) catches it and it can be dragged, else None."""
        session = self.session
        if self.root is None or session.dialog is None or getattr(session, "_closed", False):
            return None
        if self._values().get("extent") != "distance":
            return None  # To: the arrow shows where the face goes, nothing to drag
        try:
            if self._view.graphicsView().viewport() != viewport:
                return None  # the arrow is in another view
        except Exception:
            return None
        a, b = self._ends_px(self._view, viewport)
        if math.hypot(b[0] - a[0], b[1] - a[1]) < dh.MIN_SHAFT_PX:
            return None  # seen end-on: a dot on the face, where the user means the face itself
        if dh.segment_distance((x, y), a, b) > dh.HANDLE_PX:
            return None
        return a, b

    def _own(self, viewport):
        """The viewport the arrow is (or would be) drawn in: the dialog's document's view."""
        view = self._view or self._active_view()
        try:
            return view is not None and view.graphicsView().viewport() == viewport
        except Exception:
            return False

    def _gizmo(self):
        """The shell's DOF gizmo hook, which gets what happens in other views (an assembly in another tab)."""
        return getattr(self.shell, "dof_handles", None)

    def _set_lit(self, lit):
        if lit != self.lit:
            self.lit = lit
            if self._nodes is not None:
                _light(self._nodes, lit, self.shell.theme)

    def hover(self, view, viewport, x, y):
        if self._drag is not None or self._other is not None:
            return False
        if not self._own(viewport):
            self._set_lit(False)
            gizmo = self._gizmo()
            return gizmo.hover(view, viewport, x, y) if gizmo is not None else False
        on = self._hit(viewport, x, y) is not None
        self._set_lit(on)
        self._set_cursor(viewport if on else None)
        return False

    def press(self, view, viewport, x, y):
        if not self._own(viewport):
            gizmo = self._gizmo()
            if gizmo is None or not gizmo.press(view, viewport, x, y):
                return False
            self._other = gizmo  # its moves and release go there too
            return True
        ends = self._hit(viewport, x, y)
        if ends is None:
            return False
        a, b = ends
        size = self._geom[2]
        per_mm = ((b[0] - a[0]) / size, (b[1] - a[1]) / size)  # screen px per mm along the arrow
        start = self._built + self._offset  # from where the arrow is drawn (a failed preview never makes it jump)
        typed = _mm(self._values().get("distance"))
        if typed is not None and abs(typed - start) < 1e-6:
            start = typed
        self._drag = [x, y, per_mm, start, start, False]  # press, px per mm, start, now, moved past DRAG_PX
        self._set_lit(True)
        self._set_cursor(viewport, closed=True)
        return True

    def move(self, x, y):
        if self._other is not None:
            self._other.move(x, y)
            return
        drag = self._drag
        if drag is None:
            return
        x0, y0, per_mm, start = drag[:4]
        if not drag[5]:
            if math.hypot(x - x0, y - y0) <= gestures.DRAG_PX:
                return
            drag[5] = True
        d = round(start + dh.mm_along((x - x0, y - y0), per_mm), 1) + 0.0  # + 0.0: never "-0 mm"
        if d == drag[4] and self._label:
            return
        drag[4] = d
        text = "%g mm" % d
        self._label = _shown(text)
        if self._nodes is not None:
            _set_label(self._nodes["label"], self._label)
            self._offset = d - self._built
            off = self._geom[1] * self._offset
            self._nodes["shift"].translation.setValue(off.x, off.y, off.z)
        dialog = self.session.dialog
        if dialog is None:
            return
        dialog.set_values({"distance": text})
        try:
            self.session._changed(dialog.values(), throttle=True)  # a preview every interval while it moves
        except Exception:
            log.logger().exception("Move Face drag")

    def release(self):
        """The press's release. Never handed to FreeCAD as a click, even without a drag: a click there would pick
        the face under the arrow into the Faces field. A press in another view: the gizmo's release."""
        if self._other is not None:
            gizmo, self._other = self._other, None
            return gizmo.release()
        self._end()
        return False

    def _end(self):
        self._drag = None
        self._set_lit(False)
        self._set_cursor(None)

    def finish(self, moved_ok=True, closing=False):
        """A command, another tab or a closing document ends the drag: the distance stays where it got to."""
        if self._other is not None:
            gizmo, self._other = self._other, None
            gizmo.finish(moved_ok, closing)
        self._end()

    def remove(self):
        self.finish()
        self._remove_node()

    def _set_cursor(self, viewport, closed=False):
        """Open hand over the arrow, closed while dragging; FreeCAD's own cursor is never taken away."""
        from incad.qt import QtCore, QtGui
        ours = (QtCore.Qt.OpenHandCursor, QtCore.Qt.ClosedHandCursor)
        try:
            if self._cursor is not None and self._cursor is not viewport:
                if self._cursor.cursor().shape() in ours:
                    self._cursor.unsetCursor()
                self._cursor = None
            if viewport is not None:
                if viewport.cursor().shape() == QtCore.Qt.BitmapCursor:
                    return  # a Sketcher tool's cursor
                viewport.setCursor(QtGui.QCursor(ours[1] if closed else ours[0]))
                self._cursor = viewport
        except RuntimeError:
            self._cursor = None
