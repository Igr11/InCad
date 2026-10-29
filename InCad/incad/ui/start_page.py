"""The start page (the user: "every program shows recent files when it opens, and we have room for it — with
previews"): while no file is open, the empty window holds the recent files as tiles, each with the picture the file
was saved with (incad.ui.open_dialog.thumbnail), its name, folder and date; a click opens it as File ▸ Open does."""
import datetime
import os

from incad.qt import QtCore, QtGui, QtWidgets
from incad.ui import theme as themes

MOST = 12       # recent files kept and shown
TILE = 168      # px: a tile's picture
OPEN = None     # tests: OPEN(path) instead of opening the file


def recent():
    """The recent files that are still there, newest first (at most MOST)."""
    from incad.ui import open_dialog
    return [p for p in open_dialog.recent_files() if os.path.isfile(p)][:MOST]


class _Tile(QtWidgets.QToolButton):
    def __init__(self, path, palette, parent=None):
        super().__init__(parent)
        from incad.ui import open_dialog
        self.path = path
        self.setObjectName("InCadStartTile")
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QtCore.QSize(TILE, TILE))
        self.setFixedSize(TILE + 24, TILE + 62)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        pix = QtGui.QPixmap()
        data = open_dialog.thumbnail(path)
        if data:
            pix.loadFromData(data)
        if pix.isNull():  # no picture saved (or not a FreeCAD file): the file's first letter on a plain square
            pix = QtGui.QPixmap(TILE, TILE)
            pix.fill(QtGui.QColor(palette["panel_alt"]))
            p = QtGui.QPainter(pix)
            p.setPen(QtGui.QColor(palette["text_dim"]))
            f = p.font()
            f.setPointSize(48)
            p.setFont(f)
            p.drawText(pix.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, os.path.basename(path)[:1].upper())
            p.end()
        self.setIcon(QtGui.QIcon(pix.scaled(TILE, TILE, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                            QtCore.Qt.TransformationMode.SmoothTransformation)))
        name = os.path.splitext(os.path.basename(path))[0]
        when = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d %b %Y")
        metrics = self.fontMetrics()
        self.setText("%s\n%s" % (metrics.elidedText(name, QtCore.Qt.TextElideMode.ElideMiddle, TILE + 16), when))
        self.setToolTip(path)


class StartPage(QtWidgets.QFrame):
    """The recent files over the empty window; shown only while no file is open."""

    def __init__(self, parent, theme="light"):
        super().__init__(parent)
        self.setObjectName("InCadStartPage")
        self.theme = theme
        self._paths = None
        parent.installEventFilter(self)
        self.outer = QtWidgets.QVBoxLayout(self)
        self.outer.setContentsMargins(40, 32, 40, 32)
        self.title = QtWidgets.QLabel("Recent")
        self.title.setObjectName("InCadStartTitle")
        self.outer.addWidget(self.title)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.outer.addWidget(self.scroll, 1)
        self.hint = QtWidgets.QLabel("")
        self.hint.setObjectName("InCadStartHint")
        self.outer.addWidget(self.hint)
        self.fill()

    def fill(self):
        """The tiles again when the list changed (a file opened, saved or closed since)."""
        paths = recent()
        if paths == self._paths:
            return
        self._paths = paths
        p = themes.PALETTES.get(self.theme, themes.PALETTES["light"])
        box = QtWidgets.QWidget()
        box.setObjectName("InCadStartTiles")
        grid = QtWidgets.QGridLayout(box)
        grid.setSpacing(14)
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        cols = max(1, (self.width() - 80) // (TILE + 38)) if self.width() > 0 else 4
        self.tiles = []
        for i, path in enumerate(paths):
            t = _Tile(path, p)
            t.clicked.connect(lambda _=False, q=path: self._open(q))
            grid.addWidget(t, i // cols, i % cols)
            self.tiles.append(t)
        self.scroll.setWidget(box)
        self.hint.setText("" if paths else "No recent files yet: Start 2D Sketch begins a new part, Open opens a file")
        self._cols = cols
        self.setStyleSheet(
            "QFrame#InCadStartPage, QWidget#InCadStartTiles, QScrollArea, QScrollArea > QWidget > QWidget"
            " {{ background: {window}; }}"
            " QLabel#InCadStartTitle {{ color: {text}; font-size: 20px; font-weight: 600; }}"
            " QLabel#InCadStartHint {{ color: {text_dim}; }}"
            " QToolButton#InCadStartTile {{ background: {panel}; color: {text}; border: 1px solid {border};"
            " border-radius: 10px; padding: 6px; }}"
            " QToolButton#InCadStartTile:hover {{ border: 1px solid {accent}; }}".format(**p))

    def set_theme(self, theme):
        if theme != self.theme:
            self.theme, self._paths = theme, None
            self.fill()

    def _open(self, path):
        if OPEN is not None:
            return OPEN(path)
        from incad import actions
        from incad.core import log
        try:
            actions.open_path(path)
        except Exception as e:
            log.report("warning", "Could not open %s: %s" % (os.path.basename(path), e))

    def show_now(self, on):
        if on:
            self.setGeometry(self.parentWidget().rect())
            self.fill()
            if getattr(self, "_cols", None) != max(1, (self.width() - 80) // (TILE + 38)):
                self._paths = None
                self.fill()
            self.show()
            self.raise_()
        else:
            self.hide()

    def eventFilter(self, obj, ev):
        if obj is self.parentWidget() and ev.type() == QtCore.QEvent.Type.Resize and self.isVisible():
            self.setGeometry(obj.rect())
            if getattr(self, "_cols", None) != max(1, (self.width() - 80) // (TILE + 38)):
                self._paths = None
                self.fill()
        return False
