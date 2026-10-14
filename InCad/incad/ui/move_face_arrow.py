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


def _arrow_node(point, normal, size, text, theme, dpr=1.0):
    """The arrow (a line and a cone, as dof_glyphs draws a slide arrow) from `point` along `normal`, and the label
    beyond its tip: an SoAnnotation that is never picked. Returns (root, shift, label): `shift` moves it all along
    the normal during a drag, `label` is the SoText2."""
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
    return root, shift, label


def _set_label(label, text):
    label.string = text


class FaceArrow:
    def __init__(self, shell, session):
        self.shell, self.session = shell, session
        self.root, self._drag, self._label = None, None, ""
        self._geom, self._view, self._shift, self._text = None, None, None, None
        self._built = 0.0   # the feature's distance the arrow was drawn at
        self._offset = 0.0  # mm along the normal it is shown moved by (the drag ahead of the preview)
        self.refresh()

    def _active_view(self):
        import FreeCADGui as Gui
        gdoc = Gui.getDocument(self.session.doc_name)
        return gdoc.ActiveView if gdoc is not None else None

    def _place(self):
        from incad.features import move_face
        f = self.session.feature
        return move_face.arrow(f) if f is not None else None

    def _values(self):
        dialog = self.session.dialog
        return dialog.values() if dialog is not None else {}

    def label_text(self):
        return self._label

    def dragging(self):
        return self._drag is not None

    def _label_for(self, f):
        """The Distance as typed; a formula as its value; nothing with Extent = To."""
        values = self._values()
        if values.get("extent", "distance") != "distance":
            return ""
        text = values.get("distance", "")
        if _mm(text) is not None:
            return text
        return "%g mm" % round(f.Distance.Value, 4)

    def refresh(self):
        """Redraw at the feature's current place (after every preview) with the dialog's distance."""
        self._remove_node()
        f = self.session.feature
        place, view = self._place(), self._active_view()
        if place is None or view is None:
            return
        point, normal = place
        base = getattr(f, "BaseFeature", None)
        shape = base.Shape if base is not None and not base.Shape.isNull() else f.Shape
        size = dof.glyph_size(shape.BoundBox.DiagonalLength)
        self._built = f.Distance.Value
        if self._drag is None:
            self._label = self._label_for(f)
            self._offset = 0.0
        else:
            self._offset = self._drag[4] - self._built  # a preview landed mid-drag: the arrow stays at the pointer
        try:
            dpr = view.graphicsView().viewport().devicePixelRatioF()
        except Exception:
            dpr = 1.0
        self.root, self._shift, self._text = _arrow_node(point, normal, size, self._label, self.shell.theme, dpr)
        off = normal * self._offset
        self._shift.translation.setValue(off.x, off.y, off.z)
        view.getSceneGraph().addChild(self.root)
        self._geom, self._view = (point, normal, size), view

    def _remove_node(self):
        if self.root is not None and self._view is not None:
            try:
                self._view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass  # the view is gone with its document
        self.root = self._shift = self._text = self._view = None

    def _ends_px(self, view, viewport):
        point, normal, size = self._geom
        base = point + normal * self._offset
        return dh.screen(view, viewport, base), dh.screen(view, viewport, base + normal * size)

    def hover(self, view, viewport, x, y):
        return False

    def press(self, view, viewport, x, y):
        session = self.session
        if self.root is None or session.dialog is None or getattr(session, "_closed", False):
            return False
        if self._values().get("extent") != "distance":
            return False  # To: the arrow shows where the face goes, nothing to drag
        try:
            if self._view.graphicsView().viewport() != viewport:
                return False  # the arrow is in another view
        except Exception:
            return False
        a, b = self._ends_px(self._view, viewport)
        if math.hypot(b[0] - a[0], b[1] - a[1]) < dh.MIN_SHAFT_PX:
            return False  # seen end-on: a dot on the face, where the user means the face itself
        if dh.segment_distance((x, y), a, b) > dh.HANDLE_PX:
            return False
        size = self._geom[2]
        per_mm = ((b[0] - a[0]) / size, (b[1] - a[1]) / size)  # screen px per mm along the arrow
        start = _mm(self._values().get("distance"))
        if start is None:
            start = self._built + self._offset  # a formula: from its value
        self._drag = [x, y, per_mm, start, start, False]  # press, px per mm, start, now, moved past DRAG_PX
        return True

    def move(self, x, y):
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
        self._label = text
        if self._text is not None:
            _set_label(self._text, text)
            self._offset = d - self._built
            off = self._geom[1] * self._offset
            self._shift.translation.setValue(off.x, off.y, off.z)
        dialog = self.session.dialog
        if dialog is None:
            return
        dialog.set_values({"distance": text})
        try:
            self.session._changed(dialog.values())  # the throttled preview, as typing does
        except Exception:
            log.logger().exception("Move Face drag")

    def release(self):
        """True when the press was a plain click (no drag): FreeCAD gets it as a click (it picks or selects)."""
        drag, self._drag = self._drag, None
        return drag is not None and not drag[5]

    def finish(self, moved_ok=True, closing=False):
        """A command, another tab or a closing document ends the drag: the distance stays where it got to."""
        self._drag = None

    def remove(self):
        self._drag = None
        self._remove_node()
