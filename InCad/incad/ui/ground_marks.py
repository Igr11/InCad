"""Which part of an assembly is grounded, said on the part itself (the user: "two parts come into the assembly and it is
not clear what the padlock belongs to" — FreeCAD draws it at the part's origin, often off the part): the word Grounded
over the middle of the part's top, in the theme's accent. A view node only, never picked, nothing in the document."""
from pivy import coin

NAME = "InCadGroundMarks"


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class GroundMarks:
    def __init__(self, view):
        self.view = view
        self.root = None
        self.key = None

    def set(self, points, colour):
        """points: [(x, y, z)] where the words go (one for each grounded part); colour '#rrggbb'."""
        key = (tuple(tuple(round(c, 3) for c in p) for p in points), colour)
        if key == self.key:
            return
        self.remove()
        self.key = key
        if not points:
            return
        root = coin.SoAnnotation()  # over the parts: the word is never hidden behind them
        root.setName(NAME)
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        root.addChild(pick)
        mat = coin.SoBaseColor()
        mat.rgb.setValue(*_rgb(colour))
        root.addChild(mat)
        font = coin.SoFont()
        font.size = 22
        root.addChild(font)
        for p in points:
            sep = coin.SoSeparator()
            t = coin.SoTranslation()
            t.translation.setValue(*p)
            text = coin.SoText2()
            text.string = "Grounded"
            text.justification = coin.SoText2.CENTER
            sep.addChild(t)
            sep.addChild(text)
            root.addChild(sep)
        self.view.getSceneGraph().addChild(root)
        self.root = root

    def remove(self):
        if self.root is not None:
            try:
                self.view.getSceneGraph().removeChild(self.root)
            except Exception:
                pass
        self.root, self.key = None, None


def points(doc):
    """Where the words go: above the middle of each grounded component's top."""
    from incad.core import assembly
    out = []
    for c in assembly.components(doc):
        if not assembly.is_grounded(c) or assembly.is_suppressed(c):
            continue
        try:
            bb = c.Shape.BoundBox
        except Exception:
            continue
        if not bb.isValid():
            continue
        out.append((bb.Center.x, bb.Center.y, bb.ZMax + 0.04 * bb.DiagonalLength))
    return out
