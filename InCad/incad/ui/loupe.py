"""A magnifying glass beside the pointer (the user: when putting a point on an image, so it lands on the spot): a round
window ZOOM times the view under the pointer, a thin cross at its middle. FreeCAD's view is an OpenGL widget that
Python only sees as a plain QWidget (its grab() gives no picture), so the view is rendered once (saveImage, ~0.15 s)
and the glass crops that picture as the pointer moves; it is rendered again when the camera moves or a point is
set (forget())."""
import os
import tempfile
import time

from incad.qt import QtCore, QtGui, QtWidgets

SIZE = 140      # px across
ZOOM = 4.0
OFFSET = 28     # px from the pointer, up and to the right
INTERVAL = 0.03


def _camera_key(view):
    try:
        from pivy import coin  # noqa: F401  (getCameraNode needs it loaded)
        cam = view.getCameraNode()
        h = cam.height.getValue() if hasattr(cam, "height") else cam.heightAngle.getValue()
        return (tuple(cam.position.getValue().getValue()), tuple(cam.orientation.getValue().getValue()), h)
    except Exception:
        return None


def view_picture(view, viewport, hide=None):
    """The 3D view as it is drawn now (device px), or None. hide(True / False): what to leave out of it (the tool's
    own marks, which the glass draws itself at their real size)."""
    dpr = viewport.devicePixelRatioF()
    path = os.path.join(tempfile.gettempdir(), "incad_loupe_%d.png" % os.getpid())
    try:
        if hide is not None:
            hide(True)
        view.saveImage(path, int(round(viewport.width() * dpr)), int(round(viewport.height() * dpr)), "Current")
        img = QtGui.QImage(path)
    except Exception:
        return None
    finally:
        if hide is not None:
            hide(False)
        try:
            os.remove(path)
        except OSError:
            pass
    return img if not img.isNull() else None


class Loupe(QtWidgets.QWidget):
    def __init__(self, parent=None):
        flags = QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowTransparentForInput
        super().__init__(parent, flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setFixedSize(SIZE, SIZE)
        self._image = None
        self._last = 0.0
        self._frame, self._frame_key = None, None  # the view's picture, and the camera it was taken with

    def forget(self):
        """The view changed (a point set): render it again on the next move."""
        self._frame = None

    def follow(self, view, viewport, x, y, marks=(), hide=None):
        """marks: points (logical px in the view) drawn in the glass small, as they are — not magnified (the user)."""
        """Show what is around (x, y) of `viewport` (logical px), magnified, beside the pointer."""
        now = time.monotonic()
        if now - self._last < INTERVAL and self.isVisible():
            self.move(viewport.mapToGlobal(QtCore.QPoint(int(x) + OFFSET, int(y) - OFFSET - SIZE)))
            return
        self._last = now
        key = _camera_key(view)
        if self._frame is None or key != self._frame_key:
            self._frame, self._frame_key = view_picture(view, viewport, hide), key
        frame = self._frame
        if frame is None or frame.isNull():
            return
        dpr = frame.width() / max(1, viewport.width())
        side = SIZE / ZOOM * dpr  # device px taken
        src = QtCore.QRectF(x * dpr - side / 2, y * dpr - side / 2, side, side)
        img = QtGui.QImage(SIZE * 2, SIZE * 2, QtGui.QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(2.0)
        img.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        clip = QtGui.QPainterPath()
        clip.addEllipse(QtCore.QRectF(1, 1, SIZE - 2, SIZE - 2))
        p.setClipPath(clip)
        p.fillRect(QtCore.QRectF(0, 0, SIZE, SIZE), QtGui.QColor(30, 33, 38))
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, False)  # the pixels as they are, larger
        p.drawImage(QtCore.QRectF(0, 0, SIZE, SIZE), frame, src)
        if marks:  # the points and the line between them, at their real size where the glass shows them
            pts = [QtCore.QPointF(SIZE / 2.0 + (mx - x) * ZOOM, SIZE / 2.0 + (my - y) * ZOOM) for mx, my in marks]
            if len(pts) > 1:
                p.setPen(QtGui.QPen(QtGui.QColor(90, 160, 255), 1.5))
                p.drawLine(pts[0], pts[1])
            for q in pts:  # a small cross, not a dot (the user): a dark one under a bright one
                for pen in (QtGui.QPen(QtGui.QColor(20, 20, 26), 3), QtGui.QPen(QtGui.QColor(255, 220, 40), 1.2)):
                    p.setPen(pen)
                    p.drawLine(QtCore.QPointF(q.x() - 4, q.y()), QtCore.QPointF(q.x() + 4, q.y()))
                    p.drawLine(QtCore.QPointF(q.x(), q.y() - 4), QtCore.QPointF(q.x(), q.y() + 4))
        p.setClipping(False)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 210, 40), 1))
        c = SIZE / 2.0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):  # a cross with a gap at its middle: the spot stays seen
            p.drawLine(QtCore.QPointF(c + 3 * dx, c + 3 * dy), QtCore.QPointF(c + 10 * dx, c + 10 * dy))
        p.setPen(QtGui.QPen(QtGui.QColor(200, 205, 215), 2))
        p.drawEllipse(QtCore.QRectF(1, 1, SIZE - 2, SIZE - 2))
        p.end()
        self._image = img
        self.move(viewport.mapToGlobal(QtCore.QPoint(int(x) + OFFSET, int(y) - OFFSET - SIZE)))
        if not self.isVisible():
            self.show()
        self.update()

    def paintEvent(self, _event):
        if self._image is not None:
            p = QtGui.QPainter(self)
            p.drawImage(0, 0, self._image)
            p.end()
