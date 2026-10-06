"""The material on the section plane, drawn on the view: FreeCAD's clipping plane removes one side of the
part (fast, on the GPU) but leaves it hollow; this draws the cut face(s) at the plane, so the part looks solid."""
from pivy import coin


class SectionDisplay:
    def __init__(self, view, color=(0.8, 0.8, 0.8)):
        self.view = view
        self.node = coin.SoSeparator()
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE  # both sides lit
        hints.faceType = coin.SoShapeHints.UNKNOWN_FACE_TYPE  # concave polygons are tessellated
        self.node.addChild(hints)
        self._material = coin.SoMaterial()
        r, g, b = color
        self._material.diffuseColor.setValue(r * 0.85, g * 0.85, b * 0.85)  # a little darker: cut material
        self.node.addChild(self._material)
        self._coords = coin.SoCoordinate3()
        self._faces = coin.SoIndexedFaceSet()
        self.node.addChild(self._coords)
        self.node.addChild(self._faces)
        outline = coin.SoSeparator()
        ec = coin.SoBaseColor()
        ec.rgb.setValue(0.1, 0.1, 0.1)
        style = coin.SoDrawStyle()
        style.lineWidth = 1.5
        self._edge_coords = coin.SoCoordinate3()
        self._edges = coin.SoLineSet()
        for n in (ec, style, self._edge_coords, self._edges):
            outline.addChild(n)
        self.node.addChild(outline)
        view.getSceneGraph().addChild(self.node)

    def set_faces(self, faces, shift, polygons=()):
        """faces: the cap faces; polygons: loops drawn as they are (no face could be made of them);
        shift: a small vector toward the kept side so the clipping plane doesn't eat it."""
        pts, idx, epts, counts = [], [], [], []
        for loop in polygons:
            base = len(pts)
            pts += [(p.x + shift.x, p.y + shift.y, p.z + shift.z) for p in loop]
            idx += list(range(base, base + len(loop))) + [-1]  # Coin triangulates a concave polygon itself
            epts += [(p.x + shift.x, p.y + shift.y, p.z + shift.z) for p in loop] + [(loop[0].x + shift.x, loop[0].y + shift.y, loop[0].z + shift.z)]
            counts.append(len(loop) + 1)
        for face in faces:
            d = max(0.02, face.BoundBox.DiagonalLength / 300.0)
            base = len(pts)
            fp, tris = face.tessellate(d)
            pts += [(p.x + shift.x, p.y + shift.y, p.z + shift.z) for p in fp]
            for a, b, c in tris:
                idx += [base + a, base + b, base + c, -1]
            for e in face.Edges:
                try:
                    poly = e.discretize(Deflection=d)
                except Exception:
                    continue
                epts += [(p.x + shift.x, p.y + shift.y, p.z + shift.z) for p in poly]
                counts.append(len(poly))
        self._coords.point.setValues(0, len(pts), pts)
        self._coords.point.setNum(len(pts))
        self._faces.coordIndex.setValues(0, len(idx), idx)
        self._faces.coordIndex.setNum(len(idx))
        self._edge_coords.point.setValues(0, len(epts), epts)
        self._edge_coords.point.setNum(len(epts))
        self._edges.numVertices.setValues(0, len(counts), counts)
        self._edges.numVertices.setNum(len(counts))

    def remove(self):
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass
