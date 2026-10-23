"""Scale / Transparency's clicks on the picture: the place under the pointer on its plane, the two points and the line between
them with its length grey (as the gizmos' labels); a click sets a point (a third starts over). The points go into the
dialog as fractions of the picture (incad.features.picture_scale). The navigator's handle hook, as 3D Line's cube."""
import FreeCAD as App

from incad.core import line3d, log
from incad.ui.line3d_tool import _rgb, viewport_of


class PicturePoints:
    def __init__(self, shell, session):
        self.shell, self.session = shell, session
        self.root = self._view = None
        self._hover = None  # (u, v) under the pointer
        self._glass = None  # the magnifying glass beside the pointer (incad.ui.loupe)
        self.refresh()

    def _values(self):
        d = self.session.dialog
        return d.values() if d is not None else {}

    def _picture(self):
        f = self.session.feature
        return f if f is not None and f.TypeId == "Image::ImagePlane" else None

    def _active_view(self):
        import FreeCADGui as Gui
        gdoc = Gui.getDocument(self.session.doc_name)
        return gdoc.ActiveView if gdoc is not None else None

    def _world(self, f, u, v):
        from incad.features.picture_scale import local
        return f.Placement.multVec(local(f, u, v))

    # ----- drawing -----
    def refresh(self):
        self._remove_node()
        f, view = self._picture(), self._active_view()
        if f is None or view is None:
            return
        try:
            self.root = self._draw(f, view)
            view.getSceneGraph().addChild(self.root)
            self._view = view
        except Exception:
            log.logger().exception("Scale / Transparency points")
            self.root = None

    def _draw(self, f, view):
        from pivy import coin
        from incad.ui import theme as themes
        palette = themes.PALETTES[self.shell.theme]
        try:
            dpr = viewport_of(view).devicePixelRatioF()
        except Exception:
            dpr = 1.0
        root = coin.SoAnnotation()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        pts = [(u, v) for u, v, _ in line3d.parse_points(self._values().get("points"))][:2]
        if len(pts) == 1 and self._hover is not None:
            pts_line = pts + [self._hover]
        else:
            pts_line = pts
        world = [self._world(f, u, v) for u, v in pts_line]
        accent = _rgb(palette["accent"])
        if len(world) == 2:
            sep = coin.SoSeparator()
            c = coin.SoBaseColor()
            c.rgb.setValue(*accent)
            st = coin.SoDrawStyle()
            st.lineWidth = 1.5
            if len(pts) < 2:
                st.linePattern = 0x0F0F  # still the rubber line to the pointer
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, 2, [tuple(p) for p in world])
            for n in (c, st, coords, coin.SoLineSet()):
                sep.addChild(n)
            root.addChild(sep)
            mid = (world[0] + world[1]) * 0.5
            lab = coin.SoSeparator()
            c = coin.SoBaseColor()
            c.rgb.setValue(*_rgb(palette["text_dim"]))
            t = coin.SoTranslation()
            t.translation.setValue(mid.x, mid.y, mid.z)
            font = coin.SoFont()
            font.size = 13 * dpr
            text = coin.SoText2()
            text.string = "%g mm" % round((world[1] - world[0]).Length, 2)
            for n in (c, t, font, text):
                lab.addChild(n)
            root.addChild(lab)
        dots = [self._world(f, u, v) for u, v in pts] + ([self._world(f, *self._hover)] if self._hover else [])
        for size, color in ((7, (0.08, 0.08, 0.1)), (4, (1.0, 0.86, 0.15))):  # small: a dark rim, a bright core
            if not dots:
                break
            sep = coin.SoSeparator()
            c = coin.SoBaseColor()
            c.rgb.setValue(*color)
            st = coin.SoDrawStyle()
            st.pointSize = size * dpr
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, len(dots), [tuple(p) for p in dots])
            for n in (c, st, coords, coin.SoPointSet()):
                sep.addChild(n)
            root.addChild(sep)
        return root

    def _hide_marks(self, hide):
        """The points left out of the picture the glass magnifies (it draws them itself, small)."""
        if self.root is None or self._view is None:
            return
        sg = self._view.getSceneGraph()
        try:
            if hide:
                sg.removeChild(self.root)
            elif sg.findChild(self.root) < 0:
                sg.addChild(self.root)
        except Exception:
            pass

    def _remove_node(self):
        if self.root is not None and self._view is not None:
            try:
                self._view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass
        self.root = self._view = None

    # ----- the pointer -----
    def _uv(self, view, viewport, x, y):
        """(u, v) of the picture under the pointer, or None off it."""
        from pivy import coin  # noqa: F401  (getCameraNode needs it loaded)
        from incad.ui import nav
        f = self._picture()
        if f is None or self.session.dialog is None:
            return None
        try:
            if viewport_of(view) != viewport:
                return None
            cx, cy = nav.to_coin(viewport, x, y)
            p = App.Vector(view.getPoint(cx, cy))
            cam = view.getCameraNode()
            if cam.getTypeId().getName() == "PerspectiveCamera":
                d = p - App.Vector(*cam.position.getValue().getValue())
            else:
                d = App.Vector(*view.getViewDirection())
            inv = f.Placement.inverse()
            o, d = inv.multVec(p), inv.Rotation.multVec(d)
            if abs(d.z) < 1e-9:
                return None  # the picture seen edge-on
            q = o + d * (-o.z / d.z)
            u, v = q.x / f.XSize.Value + 0.5, q.y / f.YSize.Value + 0.5
            return (u, v) if -1e-6 <= u <= 1 + 1e-6 and -1e-6 <= v <= 1 + 1e-6 else None
        except Exception:
            log.logger().exception("Scale / Transparency pointer")
            return None

    def hover(self, view, viewport, x, y):
        uv = self._uv(view, viewport, x, y)
        if uv != self._hover:
            self._hover = uv
            self.refresh()
        self._magnify(view, viewport, x, y, uv is not None)
        return False

    def _magnify(self, view, viewport, x, y, on):
        """The magnifying glass beside the pointer while it is over the image (the user: points land on the spot)."""
        try:
            if on:
                if self._glass is None:
                    from incad.ui.loupe import Loupe
                    self._glass = Loupe(viewport.window())
                from incad.ui import dof_handles as dh
                f = self._picture()
                pts = [(u, v) for u, v, _ in line3d.parse_points(self._values().get("points"))][:2]
                marks = [dh.screen(view, viewport, self._world(f, u, v)) for u, v in pts] if f is not None else []
                self._glass.follow(view, viewport, x, y, marks, self._hide_marks)
            elif self._glass is not None:
                self._glass.hide()
        except Exception:
            log.logger().exception("Scale / Transparency magnifier")

    def press(self, view, viewport, x, y):
        uv = self._uv(view, viewport, x, y)
        dialog = self.session.dialog
        if uv is None or dialog is None or "points" not in dialog._widgets:
            return False
        field = dialog.field("points")
        items = line3d.parse_points(field.text())
        item = "%.9g %.9g 0" % uv
        if len(items) >= 2:  # a third click starts over
            field.set_text(item)
            field.changed.emit()
        else:
            field.add(item)
        self._hover = None
        self.refresh()
        if self._glass is not None:
            self._glass.forget()  # the new point shows in the glass too
        return True

    def move(self, x, y):
        pass

    def release(self):
        return False  # the click set a point: never FreeCAD's too

    def dragging(self):
        return False

    def finish(self, moved_ok=True, closing=False):
        pass

    def remove(self):
        if self._glass is not None:
            self._glass.hide()
            self._glass.deleteLater()
            self._glass = None
        self._remove_node()
