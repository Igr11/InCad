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
        bar = getattr(self, "bar", None)
        if bar is not None:
            try:
                bar.set_theme(theme)
            except RuntimeError:
                pass

    def add_bar(self, part_label, on_return):
        """The bar on the part's view (the user: "no option to close the editing and return to the assembly"):
        what is edited, and Return to Assembly."""
        try:
            from incad.qt import viewport_of
            vp = viewport_of(self.view)
        except Exception:
            self.bar = None
            return None
        self.bar = ReturnBar(part_label, self.asm_label(), on_return, vp)
        return self.bar

    def asm_label(self):
        import FreeCAD as App
        try:
            return App.getDocument(self.asm_name).Label
        except Exception:
            return self.asm_name or "the assembly"

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
        bar, self.bar = getattr(self, "bar", None), None
        if bar is not None:
            try:
                bar.hide()
                bar.deleteLater()
            except RuntimeError:
                pass


class ReturnBar:
    """A small floating bar at the top of the part's view: "Editing <part> in <assembly>" and Return to Assembly."""

    def __new__(cls, part_label, asm_label, on_return, viewport, theme=None):
        from incad.qt import QtCore, QtWidgets

        class _Bar(QtWidgets.QFrame):
            def __init__(self):
                super().__init__(viewport)
                self.setObjectName("InCadReturnBar")
                row = QtWidgets.QHBoxLayout(self)
                row.setContentsMargins(12, 6, 6, 6)
                self.label = QtWidgets.QLabel("Editing %s in %s" % (part_label, asm_label))
                row.addWidget(self.label)
                self.button = QtWidgets.QPushButton("Return to Assembly")
                self.button.setObjectName("InCadReturnToAssembly")
                self.button.setDefault(True)
                self.button.clicked.connect(lambda: on_return())
                row.addWidget(self.button)
                viewport.installEventFilter(self)
                self.set_theme(theme or themes.current())
                self.adjustSize()
                self._place()
                self.show()
                self.raise_()

            def set_theme(self, name):
                p = themes.PALETTES.get(name, themes.PALETTES["light"])
                self.setStyleSheet(
                    "QFrame#InCadReturnBar {{ background: {panel}; border: 1px solid {border}; border-radius: 9px; }}"
                    " QLabel {{ color: {text}; }} QPushButton {{ background: {accent}; color: {selection_text};"
                    " border: none; border-radius: 6px; padding: 4px 12px; font-weight: 600; }}".format(**p))

            def _place(self):
                self.move(max(8, (viewport.width() - self.width()) // 2), 10)

            def eventFilter(self, obj, ev):
                if ev.type() == QtCore.QEvent.Type.Resize:
                    self._place()
                return False

        return _Bar()
