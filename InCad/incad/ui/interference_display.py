"""Interference drawn on the assembly's view (incad.core.interference): each shared solid in bright red, on top of
the parts (it lies inside both of them, where nothing else would show it), a little see-through, outlined. View
nodes only: nothing is added to the document."""
from pivy import coin

COLOR = (1.0, 0.12, 0.25)
OUTLINE = (1.0, 0.85, 0.1)


class InterferenceDisplay:
    def __init__(self, view):
        self.view = view
        self.root = None

    def set(self, shapes):
        self.remove()
        if not shapes:
            return
        root = coin.SoAnnotation()  # over the parts that hold it
        root.setName("InCadInterference")
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        root.addChild(hints)
        mat = coin.SoMaterial()
        mat.diffuseColor.setValue(*COLOR)
        mat.emissiveColor.setValue(COLOR[0] * 0.45, COLOR[1] * 0.45, COLOR[2] * 0.45)
        mat.transparency.setValue(0.25)
        root.addChild(mat)
        pts, idx, lines, counts = [], [], [], []
        for shape in shapes:
            tol = max(0.01, shape.BoundBox.DiagonalLength / 300.0)
            vs, tris = shape.tessellate(tol)
            base = len(pts)
            pts += [(v.x, v.y, v.z) for v in vs]
            for a, b, c in tris:
                idx += [base + a, base + b, base + c, -1]
            for e in shape.Edges:
                ep = e.discretize(Deflection=tol)
                lines += [(p.x, p.y, p.z) for p in ep]
                counts.append(len(ep))
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(pts), pts)
        faces = coin.SoIndexedFaceSet()
        faces.coordIndex.setValues(0, len(idx), idx)
        root.addChild(coords)
        root.addChild(faces)
        if lines:
            sep = coin.SoSeparator()
            c = coin.SoBaseColor()
            c.rgb.setValue(*OUTLINE)
            st = coin.SoDrawStyle()
            st.lineWidth = 2.0
            lc = coin.SoCoordinate3()
            lc.point.setValues(0, len(lines), lines)
            ls = coin.SoLineSet()
            ls.numVertices.setValues(0, len(counts), counts)
            for n in (c, st, lc, ls):
                sep.addChild(n)
            root.addChild(sep)
        self.view.getSceneGraph().addChild(root)
        self.root = root

    def remove(self):
        if self.root is not None:
            try:
                self.view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass
        self.root = None
