"""Small points drawn on the 3D view (never in the document) at a sketch's key points: spline poles, segment
ends, circle centres. Not clickable: an SoAnnotation outside the document, so FreeCAD never picks them."""
from incad.ui import theme as themes

SIZE = 9
KIND_COLOR = {"pole": "accent", "centre": "accent", "end": "marker_end"}


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class PointMarkers:
    def __init__(self, view, theme="light"):
        from pivy import coin
        self.view, self.theme, self.count = view, theme, 0
        self.node = coin.SoAnnotation()
        self.node.setName("InCadSketchPoints")
        view.getSceneGraph().addChild(self.node)

    def set(self, points):
        """Draw `points` ([(kind, Vector)]) instead of whatever was drawn before."""
        from pivy import coin
        self.clear()
        palette = themes.PALETTES[self.theme]
        for kind in ("end", "pole", "centre"):
            pts = [v for k, v in points if k == kind]
            if not pts:
                continue
            sep = coin.SoSeparator()
            color = coin.SoBaseColor()
            color.rgb.setValue(*_rgb(palette[KIND_COLOR[kind]]))
            style = coin.SoDrawStyle()
            style.pointSize = SIZE
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, len(pts), [(v.x, v.y, v.z) for v in pts])
            for n in (color, style, coords, coin.SoPointSet()):
                sep.addChild(n)
            self.node.addChild(sep)
        self.count = len(points)

    def clear(self):
        self.node.removeAllChildren()
        self.count = 0

    def remove(self):
        self.clear()
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass
