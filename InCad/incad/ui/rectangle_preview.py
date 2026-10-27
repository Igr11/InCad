"""Live diagonals while a rectangle is drawn (the user: they help with orientation from the first click). FreeCAD's
rectangle tools draw their rubber band in the sketch's edit curve (EditCurvesCoordinate: the four sides first, two
points each, then a rounded rectangle's arcs); a sensor on it draws the two diagonals over it, dashed in the edit
curve's colour, corner to corner — a rounded rectangle's from arc centre to arc centre.
Armed by a rectangle command; hidden while no tool's cursor shows, off with any other Sketcher command and when
the sketch closes. A finished rectangle keeps only its centre point (shell._centres_for_new_rectangles)."""
from incad.core import log

TOOLS = ("Sketcher_CreateRectangle", "Sketcher_CreateRectangle_Center", "Sketcher_CreateOblong")
DASHES = 0xF0F0
_live = None


def _named(root, name):
    """(node, its parent) of the first node called `name` under root, or (None, None). Read while the search lives:
    its path goes with it (reading it afterwards crashed FreeCAD)."""
    from pivy import coin
    sa = coin.SoSearchAction()
    sa.setName(coin.SbName(name))
    sa.setInterest(coin.SoSearchAction.FIRST)
    sa.setSearchingAll(True)
    sa.apply(root)
    path = sa.getPath()
    if path is None or path.getLength() < 2:
        return None, None
    return path.getTail(), path.getNode(path.getLength() - 2)


def _meet(a0, a1, b0, b1):
    """Where the lines through a0-a1 and b0-b1 cross (x, y), or None when they are parallel."""
    dax, day, dbx, dby = a1[0] - a0[0], a1[1] - a0[1], b1[0] - b0[0], b1[1] - b0[1]
    den = dax * dby - day * dbx
    if abs(den) < 1e-12 * max(dax * dax + day * day, dbx * dbx + dby * dby, 1e-300):
        return None
    t = ((b0[0] - a0[0]) * dby - (b0[1] - a0[1]) * dbx) / den
    return a0[0] + t * dax, a0[1] + t * day


def corners(points, counts):
    """The 4 corners the diagonals join (a rounded rectangle: its arc centres) from an edit curve, or None when it
    holds no rectangle (no four two-point sides first)."""
    if len(counts) < 4 or list(counts[:4]) != [2, 2, 2, 2] or len(points) < 8:
        return None
    sides = [(points[2 * i], points[2 * i + 1]) for i in range(4)]
    out = []
    for i in range(4):
        (a0, a1), (b0, b1) = sides[i], sides[(i + 1) % 4]
        p = _meet(a0, a1, b0, b1)
        if p is None:
            return None
        # the corner arc's centre: the side's end and the next side's start, less the sharp corner (a plain
        # rectangle's sides meet there, so it is the corner itself)
        out.append((a1[0] + b0[0] - p[0], a1[1] + b0[1] - p[1], a1[2]))
    return out


class _Live:
    def __init__(self, view):
        from pivy import coin
        self.view = view
        self.viewport = view.graphicsView().viewport()
        root = view.getSceneGraph()
        self.coords, self.parent = _named(root, "EditCurvesCoordinate")
        self.lines = _named(root, "EditCurveLineSet")[0]
        if self.coords is None or self.lines is None:
            raise LookupError("no sketch edit curve in this view")
        self.switch = coin.SoSwitch()
        sep = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.color = coin.SoBaseColor()
        binding = coin.SoMaterialBinding()  # FreeCAD colours the edit curve per part: one colour for both lines
        binding.value = coin.SoMaterialBinding.OVERALL
        style = coin.SoDrawStyle()
        style.linePattern = DASHES
        width = _named(root, "EditCurvesDrawStyle")[0]
        style.lineWidth = width.lineWidth.getValue() if width is not None else 2
        mat = _named(root, "EditCurvesMaterials")[0]
        if mat is not None and mat.diffuseColor.getNum():
            self.color.rgb = mat.diffuseColor[0]
        self.points = coin.SoCoordinate3()
        self.set = coin.SoLineSet()
        for n in (pick, binding, self.color, style, self.points, self.set):
            sep.addChild(n)
        self.switch.addChild(sep)
        self.switch.whichChild = coin.SO_SWITCH_NONE
        self.parent.addChild(self.switch)
        self.sensors = []
        for field in (self.coords.point, self.lines.numVertices):
            s = coin.SoFieldSensor(self._changed, None)
            s.setPriority(0)  # at once, with the rubber band: never a redraw between the two
            s.attach(field)
            self.sensors.append(s)

    def _changed(self, _data, _sensor):
        from pivy import coin
        from incad.ui.nav import Navigator
        try:
            if not Navigator.tool_cursor(self.viewport):  # no tool now (hidden only: called at once, it also saw
                self._show(coin.SO_SWITCH_NONE)         # the moment a tool swaps its mode); the next Sketcher
                return                                  # command or the sketch closing ends this
            point, counts = self.coords.point, self.lines.numVertices
            c = None
            if point.getNum() >= 8 and counts.getNum() >= 4:  # the four sides only (a rounded one has 200 more)
                c = corners([point[i].getValue() for i in range(8)], [counts[i] for i in range(4)])
            if c is None:
                self._show(coin.SO_SWITCH_NONE)
                return
            self.points.point.setValues(0, 4, [c[0], c[2], c[1], c[3]])
            if self.set.numVertices.getNum() != 2:
                self.set.numVertices.setValues(0, 2, [2, 2])
            self._show(0)
        except Exception:
            log.logger().exception("rectangle preview diagonals")

    def _show(self, which):
        if self.switch.whichChild.getValue() != which:  # an equal write still redraws
            self.switch.whichChild = which

    def close(self):
        for s in self.sensors:
            s.detach()
        self.sensors = []
        try:
            if self.parent.findChild(self.switch) >= 0:
                self.parent.removeChild(self.switch)
        except RuntimeError:
            pass


def start(name):
    """After a Sketcher command `name` has started: diagonals over a rectangle tool's rubber band."""
    stop()
    if name not in TOOLS:
        return
    global _live
    try:
        import FreeCADGui as Gui
        _live = _Live(Gui.ActiveDocument.ActiveView)
    except Exception as e:
        log.logger().info("No live rectangle diagonals: %s", e)


def stop():
    global _live
    if _live is not None:
        live, _live = _live, None
        live.close()


def active():
    return _live is not None
