"""One piece of the part drawn on the view while the Make Assembly dialog hovers its row: its edges as lines over
the model (an SoAnnotation, never in the document)."""


class PieceMarker:
    def __init__(self, view):
        from pivy import coin
        self.view = view
        self.node = coin.SoAnnotation()
        self.node.setName("InCadPiece")
        view.getSceneGraph().addChild(self.node)

    def show(self, solid):
        from pivy import coin
        self.node.removeAllChildren()
        if solid is None:
            return
        color = coin.SoBaseColor()
        color.rgb.setValue(1.0, 0.55, 0.1)
        style = coin.SoDrawStyle()
        style.lineWidth = 3
        self.node.addChild(color)
        self.node.addChild(style)
        for e in solid.Edges:
            pts = e.discretize(Deflection=0.05)
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, len(pts), [(p.x, p.y, p.z) for p in pts])
            line = coin.SoLineSet()
            sep = coin.SoSeparator()
            sep.addChild(coords)
            sep.addChild(line)
            self.node.addChild(sep)

    def remove(self):
        self.node.removeAllChildren()
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass
