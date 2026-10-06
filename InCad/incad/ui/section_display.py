"""The sectioned part drawn on the view: the cut solid (with its cut faces) as a Coin mesh, while the part
itself is hidden. FreeCAD's clipping plane would leave the inside hollow."""
from pivy import coin


class SectionDisplay:
    def __init__(self, view, color=(0.8, 0.8, 0.8)):
        self.view = view
        self.node = coin.SoSeparator()
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.SOLID
        hints.creaseAngle = 0.5
        self.node.addChild(hints)
        self._material = coin.SoMaterial()
        self._material.diffuseColor.setValue(*color)
        self.node.addChild(self._material)
        self._coords = coin.SoCoordinate3()
        self._faces = coin.SoIndexedFaceSet()
        self.node.addChild(self._coords)
        self.node.addChild(self._faces)
        edges = coin.SoSeparator()
        ec = coin.SoBaseColor()
        ec.rgb.setValue(0.1, 0.1, 0.1)
        style = coin.SoDrawStyle()
        style.lineWidth = 1.5
        self._edge_coords = coin.SoCoordinate3()
        self._edges = coin.SoLineSet()
        for n in (ec, style, self._edge_coords, self._edges):
            edges.addChild(n)
        self.node.addChild(edges)
        view.getSceneGraph().addChild(self.node)

    def set_shape(self, shape, deflection=None):
        if shape.isNull() or not shape.Faces:
            for f in (self._coords.point, self._faces.coordIndex, self._edge_coords.point, self._edges.numVertices):
                f.setNum(0)
            return
        d = deflection or max(0.02, shape.BoundBox.DiagonalLength / 400.0)
        pts, tris = shape.tessellate(d)
        self._coords.point.setValues(0, len(pts), [(p.x, p.y, p.z) for p in pts])
        self._coords.point.setNum(len(pts))
        idx = []
        for a, b, c in tris:
            idx += [a, b, c, -1]
        self._faces.coordIndex.setValues(0, len(idx), idx)
        self._faces.coordIndex.setNum(len(idx))
        epts, counts = [], []
        for e in shape.Edges:
            try:
                poly = e.discretize(Deflection=d)
            except Exception:
                continue
            epts += [(p.x, p.y, p.z) for p in poly]
            counts.append(len(poly))
        self._edge_coords.point.setValues(0, len(epts), epts)
        self._edge_coords.point.setNum(len(epts))
        self._edges.numVertices.setValues(0, len(counts), counts)
        self._edges.numVertices.setNum(len(counts))

    def remove(self):
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass
