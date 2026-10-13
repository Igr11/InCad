"""Inventor's DOF glyphs on the 3D view (never in the document): a double arrow per direction a part can slide, an
arc per axis it can turn about. Not clickable (SoAnnotation outside the document). HoverWatch tells which assembly
part the pointer rests on (FreeCAD's preselection), for the tip."""
from incad.ui import theme as themes


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class DofGlyphs:
    def __init__(self, view, theme="light"):
        from pivy import coin
        self.view, self.theme = view, theme
        self.count, self.parts, self.highlighted = 0, {}, []
        self.node = coin.SoAnnotation()
        self.node.setName("InCadDOF")
        view.getSceneGraph().addChild(self.node)

    def set(self, items):
        """items: [(name, lines, heads, size, highlight)] — dof.glyph output per part, its size, the tip colour."""
        from pivy import coin
        self.clear()
        palette = themes.PALETTES[self.theme]
        for name, lines, heads, size, highlight in items:
            sep = coin.SoSeparator()
            color = coin.SoBaseColor()
            color.rgb.setValue(*_rgb(palette["accent" if highlight else "marker_end"]))
            style = coin.SoDrawStyle()
            style.lineWidth = 3
            sep.addChild(color)
            sep.addChild(style)
            for pts in lines:
                coords = coin.SoCoordinate3()
                coords.point.setValues(0, len(pts), [(p.x, p.y, p.z) for p in pts])
                sep.addChild(coords)
                sep.addChild(coin.SoLineSet())
            h = size * 0.25
            for tip, d in heads:
                head = coin.SoSeparator()
                t = coin.SoTransform()
                base = tip - d * (h / 2)
                t.translation.setValue(base.x, base.y, base.z)
                t.rotation.setValue(coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(d.x, d.y, d.z)))
                cone = coin.SoCone()
                cone.height, cone.bottomRadius = h, size * 0.1
                head.addChild(t)
                head.addChild(cone)
                sep.addChild(head)
            self.node.addChild(sep)
            self.parts[name] = (len(lines), len(heads))
            if highlight:
                self.highlighted.append(name)
        self.count = len(items)

    def clear(self):
        self.node.removeAllChildren()
        self.count, self.parts, self.highlighted = 0, {}, []

    def remove(self):
        self.clear()
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass


class HoverWatch:
    """Selection observer: callback(component name | None) when FreeCAD's preselection enters or leaves an
    assembly part. A preselection in an assembly names the part directly ('Link.Body.Face6'), but joint markers are
    drawn on top and win the pick ('Mate.'), so then the part is found by picking through them at the same spot."""

    def __init__(self, callback):
        self.callback = callback
        self.current = None

    def _set(self, name):
        if name != self.current:
            self.current = name
            self.callback(name)

    @staticmethod
    def _through_markers(doc, point):
        import FreeCADGui as Gui
        from incad.ui.asm_drag import component_in_hits
        view = Gui.ActiveDocument.ActiveView
        x, y = view.getPointOnViewport(point)
        link = component_in_hits(doc, view.getObjectsInfo((int(x), int(y))))
        return link.Name if link is not None else None

    def setPreselection(self, doc, obj, sub):
        import FreeCAD as App
        import FreeCADGui as Gui
        from incad.core import assembly
        active = App.ActiveDocument
        if not assembly.is_assembly(active):
            return self._set(None)
        asm = assembly.assembly_of(active)
        if doc == active.Name and obj == asm.Name and sub:
            link = active.getObject(sub.split(".")[0])
            if link is not None and link in assembly.components(active):
                return self._set(link.Name)
        try:
            points = Gui.Selection.getPreselection().PickedPoints
            self._set(self._through_markers(active, points[0]) if points else None)
        except Exception:
            self._set(None)

    def removePreselection(self, doc, obj, sub):
        self._set(None)
