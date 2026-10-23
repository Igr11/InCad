"""The axes of the components' round faces in an assembly (the user: every turned body and hole has its axis, a
light dash-dot centre line on a dark rim, to constrain to; incad.core.axes): drawn over the parts, redrawn as parts
move (with the DOF glyphs), and hit-tested in screen space so a constraint dialog can take one."""
from incad.core import axes as core_axes
from incad.core import log

NAME = "InCadAxes"


class AxisLines:
    def __init__(self, view, theme, doc_name):
        self.view, self.theme, self.doc_name = view, theme, doc_name
        self.root = None
        self.items = []  # [(link name, start, end, face index, circle edge indices)]
        self._key = None

    def set(self, doc):
        """Every visible component's axes, as they stand now."""
        items = []
        for link in [o for o in doc.Objects if o.TypeId == "App::Link"]:
            if not getattr(link, "Visibility", True):
                continue
            for start, end, face, circles in core_axes.axes(link):
                items.append((link.Name, start, end, face, circles))
        key = (tuple((n, tuple(a), tuple(b)) for n, a, b, _, _ in items), self.theme)
        self.items = items
        if key == self._key and self.root is not None:
            return
        self._key = key
        self._draw()

    def _draw(self):
        from pivy import coin
        from incad.ui import theme as themes
        from incad.ui.move_face_arrow import _rgb
        self.remove(keep_items=True)
        if not self.items:
            return
        root = coin.SoAnnotation()
        root.setName(NAME)
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        coords = coin.SoCoordinate3()
        pts = [tuple(p) for _, a, b, _, _ in self.items for p in (a, b)]
        coords.point.setValues(0, len(pts), pts)
        root.addChild(coords)
        light = _rgb(themes.PALETTES[self.theme]["text"])
        try:
            dpr = self.view.graphicsView().viewport().devicePixelRatioF()  # line widths are device px
        except Exception:
            dpr = 1.0
        # a dark rim under a light dash-dot centre line: it reads on a light part and on the dark background alike
        # (the user: the axes a little brighter)
        for color, width in (((0.07, 0.07, 0.09), 3.6 * dpr), (tuple(0.85 * c + 0.15 for c in light), 1.8 * dpr)):
            sep = coin.SoSeparator()
            c = coin.SoBaseColor()
            c.rgb.setValue(*color)
            st = coin.SoDrawStyle()
            st.lineWidth = width
            st.linePattern = 0xFF18  # a long dash and a short one, as a centre line
            ls = coin.SoLineSet()
            ls.numVertices.setValues(0, len(self.items), [2] * len(self.items))
            for n in (c, st, ls):
                sep.addChild(n)
            root.addChild(sep)
        try:
            self.view.getSceneGraph().addChild(root)
            self.root = root
        except Exception:
            log.logger().exception("assembly axes")

    def hit(self, viewport, x, y):
        """The axis under (x, y) (logical px in the view): its item, else None."""
        from incad.ui import dof_handles as dh
        best = None
        for item in self.items:
            try:
                a, b = dh.screen(self.view, viewport, item[1]), dh.screen(self.view, viewport, item[2])
            except Exception:
                continue
            d = dh.segment_distance((x, y), a, b)
            if d <= dh.HANDLE_PX and (best is None or d < best[0]):
                best = (d, item)
        return best[1] if best is not None else None

    def remove(self, keep_items=False):
        if self.root is not None:
            try:
                self.view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass
        self.root = None
        if not keep_items:
            self.items, self._key = [], None
