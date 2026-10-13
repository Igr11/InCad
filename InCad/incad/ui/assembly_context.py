"""Edit a part from the assembly: the other parts drawn around it in the part's tab, semi-transparent grey — a
picture only (never document objects, never saved, never picked: an UNPICKABLE pick style first, so clicks,
preselection and getObjectInfo go through). Ordinary depth-tested geometry, not an SoAnnotation: the part hides
what is behind it and the context what is behind that."""
from incad.ui import theme as themes

NAME = "InCadAssemblyContext"
TRANSPARENCY = 0.7


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _mesh(shape):
    """The shape's faces as one SoCoordinate3 + SoIndexedFaceSet (no materials of its own)."""
    from pivy import coin
    tol = max(shape.BoundBox.DiagonalLength * 0.002, 0.01)
    points, triangles = shape.tessellate(tol)
    sep = coin.SoSeparator()
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
    faces = coin.SoIndexedFaceSet()
    index = []
    for a, b, c in triangles:
        index.extend((a, b, c, -1))
    faces.coordIndex.setValues(0, len(index), index)
    sep.addChild(coords)
    sep.addChild(faces)
    return sep


class AssemblyContext:
    def __init__(self, view, parts, theme="light", asm_name=None):
        """parts: assembly.context_of output [(name, shape, placement)]."""
        from pivy import coin
        self.view, self.asm_name, self.names = view, asm_name, [p[0] for p in parts]
        self.node = coin.SoSeparator()
        self.node.setName(NAME)
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE  # two-sided lighting
        hints.creaseAngle = 0.5
        self.material = coin.SoMaterial()
        for n in (pick, hints, self.material):
            self.node.addChild(n)
        for _, shape, placement in parts:
            one = coin.SoSeparator()
            t = coin.SoTransform()
            b, q = placement.Base, placement.Rotation.Q  # (x, y, z, w), as SbRotation takes it
            t.translation.setValue(b.x, b.y, b.z)
            t.rotation.setValue(coin.SbRotation(*q))
            one.addChild(t)
            one.addChild(_mesh(shape))
            self.node.addChild(one)
        self.set_theme(theme)
        self.shown = False
        self.set_visible(True)

    @property
    def count(self):
        return len(self.names)

    def set_theme(self, theme):
        p = themes.PALETTES.get(theme, themes.PALETTES["light"])
        self.material.diffuseColor.setValue(*_rgb(p["context"]))
        self.material.transparency.setValue(TRANSPARENCY)

    def set_visible(self, on):
        root = self.view.getSceneGraph()
        if on and not self.shown:
            root.addChild(self.node)
        elif not on and self.shown:
            i = root.findChild(self.node)
            if i >= 0:
                root.removeChild(i)
        self.shown = bool(on)

    def remove(self):
        try:
            self.set_visible(False)
        except Exception:
            pass
