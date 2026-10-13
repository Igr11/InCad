"""Inventor's DOF glyphs on the 3D view (never in the document): a double arrow per direction a part can slide, an
arc per axis it can turn about; the handle under the pointer (ui/dof_handles) lit. Never picked (an UNPICKABLE pick style first under the SoAnnotation, outside the
document): a click or a drag on a glyph reaches the part under it. HoverWatch tells which assembly
part the pointer rests on (FreeCAD's preselection), for the tip."""
from incad.ui import theme as themes


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class DofGlyphs:
    def __init__(self, view, theme="light", doc_name=None):
        from pivy import coin
        self.view, self.theme, self.doc_name = view, theme, doc_name
        self.count, self.parts, self.highlighted, self.lit = 0, {}, [], None
        self.node = coin.SoAnnotation()
        self.node.setName("InCadDOF")
        self._pick = coin.SoPickStyle()
        self._pick.style = coin.SoPickStyle.UNPICKABLE
        self.node.addChild(self._pick)
        view.getSceneGraph().addChild(self.node)

    def set(self, items):
        """items: [(name, handles, size, highlight, lit)] — dof.handles output per part, its size, the tip colour
        (accent) and the index of the handle under the pointer (accent and thicker; None: none)."""
        from pivy import coin
        self.clear()
        palette = themes.PALETTES[self.theme]
        for name, handles, size, highlight, lit in items:
            sep = coin.SoSeparator()
            color = coin.SoBaseColor()
            color.rgb.setValue(*_rgb(palette["accent" if highlight else "marker_end"]))
            style = coin.SoDrawStyle()
            style.lineWidth = 3
            sep.addChild(color)
            sep.addChild(style)
            h = size * 0.25
            for k, handle in enumerate(handles):
                one = coin.SoSeparator()
                if k == lit:
                    c = coin.SoBaseColor()
                    c.rgb.setValue(*_rgb(palette["accent"]))
                    st = coin.SoDrawStyle()
                    st.lineWidth = 6
                    one.addChild(c)
                    one.addChild(st)
                pts = handle.line
                coords = coin.SoCoordinate3()
                coords.point.setValues(0, len(pts), [(p.x, p.y, p.z) for p in pts])
                one.addChild(coords)
                one.addChild(coin.SoLineSet())
                for tip, d in handle.heads:
                    head = coin.SoSeparator()
                    t = coin.SoTransform()
                    base = tip - d * (h / 2)
                    t.translation.setValue(base.x, base.y, base.z)
                    t.rotation.setValue(coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(d.x, d.y, d.z)))
                    cone = coin.SoCone()
                    cone.height, cone.bottomRadius = h, size * (0.14 if k == lit else 0.1)
                    head.addChild(t)
                    head.addChild(cone)
                    one.addChild(head)
                sep.addChild(one)
            self.node.addChild(sep)
            self.parts[name] = (len(handles), sum(len(x.heads) for x in handles))
            if highlight:
                self.highlighted.append(name)
            if lit is not None and 0 <= lit < len(handles):
                self.lit = (name, lit)
        self.count = len(items)

    def clear(self):
        self.node.removeAllChildren()
        self.node.addChild(self._pick)
        self.count, self.parts, self.highlighted, self.lit = 0, {}, [], None

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
