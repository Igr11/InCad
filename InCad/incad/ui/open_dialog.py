"""Open / Place / Import file dialog with a picture of the file (the user: "a preview, to see the file's picture before
opening"; STL too). A FreeCAD file keeps the view it was saved with as thumbnails/Thumbnail.png inside its zip; an STL
is drawn here, shaded, from above at an angle. macOS dropped the old Quick Look plug-ins and Windows has no handler for
either, so the system dialogs show nothing: Qt's own dialog with a preview panel beside the list, the same on both
systems. No pictures in the list itself: Qt asks for file icons from a worker thread, where a picture can't be made
(InnCad hung opening a folder)."""
import datetime
import os
import zipfile

from incad.qt import QtCore, QtGui, QtWidgets

PREVIEW_PX = 256


def thumbnail(path):
    """The PNG bytes a FreeCAD file was saved with, or None (another type, no picture saved, not a zip)."""
    if not path or not path.lower().endswith(".fcstd") or not os.path.isfile(path):
        return None
    try:
        with zipfile.ZipFile(path) as z:
            return z.read("thumbnails/Thumbnail.png")
    except (KeyError, OSError, zipfile.BadZipFile):
        return None


STL_MOST = 600000  # triangles drawn at most (more are thinned: the preview stays about a second)
_STL_SEEN = {}  # (path, mtime, px) -> QImage


def _obj_triangles(path):
    """(N, 3, 3) corners of an OBJ's faces (polygons fanned into triangles), or None."""
    import numpy as np
    verts, faces = [], []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                parts = line.split()
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("f "):
                idx = [int(p.split("/")[0]) for p in line.split()[1:]]
                faces.extend((idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1))
    if not verts or not faces:
        return None
    v = np.array(verts, dtype=np.float32)
    f = np.array(faces, dtype=np.int64)
    f = np.where(f < 0, f + len(v), f - 1)  # 1-based, or negative from the end
    return v[f]


def _stl_triangles(path):
    """(N, 3, 3) float32 corners of an STL's triangles (binary or ASCII), or None."""
    import re
    import numpy as np
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(84)
        if len(head) == 84:
            n = int(np.frombuffer(head[80:84], dtype="<u4")[0])
            if 84 + 50 * n == size and n > 0:
                rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
                return np.fromfile(f, dtype=rec, count=n)["v"]
    with open(path, "r", errors="ignore") as f:
        text = f.read()
    nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    if len(nums) < 3:
        return None
    v = np.array(nums, dtype=np.float32)
    return v[: len(v) // 3 * 3].reshape(-1, 3, 3)


CAD_TYPES = (".step", ".stp", ".iges", ".igs", ".brep", ".brp")
PICTURES = (".jpg", ".jpeg", ".png", ".bmp")
CAD_MOST_MB = 40  # a larger STEP is not read for its picture (reading it takes too long for a preview)


def _cad_triangles(path):
    """(N, 3, 3) corners of a STEP / IGES / BREP file's faces, meshed coarsely, or None (no FreeCAD, too big,
    nothing in it)."""
    import numpy as np
    if os.path.getsize(path) > CAD_MOST_MB * 1024 * 1024:
        return None
    try:
        import Part
    except ImportError:
        return None
    shape = Part.Shape()
    shape.read(path)
    if shape.isNull() or not shape.Faces:
        return None
    pts, tris = shape.tessellate(max(shape.BoundBox.DiagonalLength / 250.0, 1e-3))
    if not tris:
        return None
    p = np.array([(v.x, v.y, v.z) for v in pts], dtype=np.float32)
    return p[np.array(tris, dtype=np.int64)]


def stl_picture(path, px=256, background=(43, 47, 54)):
    """A shaded picture of an STL — or a STEP, IGES or BREP file, meshed — (QImage), seen from the front-right and
    above, or None."""
    import numpy as np
    try:
        key = (path, os.path.getmtime(path), px)
    except OSError:
        return None
    if key in _STL_SEEN:
        return _STL_SEEN[key]
    try:
        low = path.lower()
        tri = _cad_triangles(path) if low.endswith(CAD_TYPES) else _obj_triangles(path) if low.endswith(".obj") \
            else _stl_triangles(path)
    except Exception:
        tri = None
    if tri is None or not len(tri):
        return None
    if len(tri) > STL_MOST:
        tri = tri[:: int(np.ceil(len(tri) / STL_MOST))]
    a, e = np.radians(-35.0), np.radians(30.0)  # the view: turned round Z, then tipped towards the eye
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    m = rx @ np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]]) @ rz  # Z up on the screen
    p = tri.reshape(-1, 3) @ m.T
    lo, hi = p.min(axis=0), p.max(axis=0)
    span = max(hi[0] - lo[0], hi[1] - lo[1], 1e-9)
    scale = (px - 16) / span
    sx = (p[:, 0] - (lo[0] + hi[0]) / 2) * scale + px / 2
    sy = px / 2 - (p[:, 1] - (lo[1] + hi[1]) / 2) * scale
    q = np.stack([sx, sy, p[:, 2]], axis=1).reshape(-1, 3, 3)
    v = p.reshape(-1, 3, 3)
    nrm = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    ok = ln > 0
    q, nrm, ln = q[ok], nrm[ok], ln[ok]
    nrm = nrm / ln[:, None]
    light = np.array([0.35, 0.55, 0.76])
    shade = 0.28 + 0.72 * np.abs(nrm @ light)
    # a depth buffer: each triangle sampled about every pixel along its longest side (a dense mesh by its
    # corners and middle, a long thin or a big triangle by a grid), the nearest sample of every pixel kept
    edges = np.stack([q[:, 1, :2] - q[:, 0, :2], q[:, 2, :2] - q[:, 1, :2], q[:, 0, :2] - q[:, 2, :2]], axis=1)
    longest = np.linalg.norm(edges, axis=2).max(axis=1)
    k = np.clip(np.ceil(1.25 * longest), 1, 128).astype(int)
    xs, ys, zs, cs = [], [], [], []
    for n in np.unique(k):
        sel = np.nonzero(k == n)[0]
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
        keep = i + j <= n
        w = np.stack([i[keep], j[keep], n - i[keep] - j[keep]], axis=1) / float(n)  # (m, 3) barycentric
        if n == 1:
            w = np.vstack([w, [[1 / 3.0, 1 / 3.0, 1 / 3.0]]])
        pts = np.einsum("mk,tkc->tmc", w, q[sel])  # (t, m, 3)
        xs.append(pts[:, :, 0].ravel())
        ys.append(pts[:, :, 1].ravel())
        zs.append(pts[:, :, 2].ravel())
        cs.append(np.repeat(shade[sel], len(w)))
    x, y, z, c = (np.concatenate(a) for a in (xs, ys, zs, cs))
    ix, iy = np.clip(x.astype(int), 0, px - 1), np.clip(y.astype(int), 0, px - 1)
    cell = iy * px + ix
    order = np.lexsort((-z, cell))  # by pixel, the nearest (largest z) first
    first = order[np.unique(cell[order], return_index=True)[1]]
    rgb = np.empty((px, px, 3), dtype=np.uint8)
    rgb[:] = background
    base = np.array([150, 175, 205], dtype=float)
    rgb[iy[first], ix[first]] = (base[None, :] * c[first, None]).astype(np.uint8)
    rgba = np.dstack([rgb, np.full((px, px), 255, np.uint8)])
    img = QtGui.QImage(rgba.tobytes(), px, px, px * 4, QtGui.QImage.Format_RGBA8888).copy()
    _STL_SEEN.clear()  # one at a time is enough: the file under the pointer
    _STL_SEEN[key] = img
    return img


def _size_text(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "bytes" else ("%.1f %s" % (n, unit))
        n /= 1024.0


class Preview(QtWidgets.QFrame):
    """The picture of the file under the cursor, its name, date and size."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InCadOpenPreview")
        self.setMinimumWidth(PREVIEW_PX + 16)
        col = QtWidgets.QVBoxLayout(self)
        self.picture = QtWidgets.QLabel()
        self.picture.setFixedSize(PREVIEW_PX, PREVIEW_PX)
        self.picture.setAlignment(QtCore.Qt.AlignCenter)
        self.picture.setStyleSheet("background: #2b2f36; color: #9aa3ad; border-radius: 6px;")
        self.name = QtWidgets.QLabel()
        self.name.setWordWrap(True)
        self.name.setStyleSheet("font-weight: 600;")
        self.details = QtWidgets.QLabel()
        self.details.setWordWrap(True)
        col.addWidget(self.picture)
        col.addWidget(self.name)
        col.addWidget(self.details)
        col.addStretch(1)
        self.show_file(None)

    def show_file(self, path):
        self.path = path if path and os.path.isfile(path) else None
        if self.path is None:
            self.picture.setPixmap(QtGui.QPixmap())
            self.picture.setText("Pick a file\nto see its picture")
            self.name.setText("")
            self.details.setText("")
            return
        data = thumbnail(self.path)
        pix = QtGui.QPixmap()
        if data:
            pix.loadFromData(data)
        elif self.path.lower().endswith(PICTURES):
            pix.load(self.path)
        elif self.path.lower().endswith((".stl", ".obj") + CAD_TYPES):
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                img = stl_picture(self.path, PREVIEW_PX)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            if img is not None:
                pix = QtGui.QPixmap.fromImage(img)
        if pix.isNull():
            self.picture.setPixmap(QtGui.QPixmap())
            self.picture.setText("No picture" if self.path.lower().endswith(".fcstd") else "No preview")
        else:
            self.picture.setText("")
            self.picture.setPixmap(pix.scaled(PREVIEW_PX, PREVIEW_PX, QtCore.Qt.KeepAspectRatio,
                                              QtCore.Qt.SmoothTransformation))
        st = os.stat(self.path)
        self.name.setText(os.path.basename(self.path))
        when = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        self.details.setText("%s\n%s" % (when, _size_text(st.st_size)))

    def has_picture(self):
        p = self.picture.pixmap()
        return p is not None and not p.isNull()


def places(recent=()):
    """The side panel: home, Desktop, Documents, Downloads, then the folders of the recent files."""
    home = os.path.expanduser("~")
    out = [home] + [os.path.join(home, n) for n in ("Desktop", "Documents", "Downloads")]
    for f in recent:
        d = os.path.dirname(f or "")
        if d and d not in out:
            out.append(d)
    return [QtCore.QUrl.fromLocalFile(d) for d in out if os.path.isdir(d)]


class OpenDialog(QtWidgets.QFileDialog):
    def __init__(self, parent=None, title="Open", folder="", filters="FreeCAD files (*.FCStd)", recent=()):
        super().__init__(parent, title, folder, filters)
        self.setObjectName("InCadOpenDialog")
        self.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)  # the system dialogs can't show the picture
        self.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        self.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        self.setViewMode(QtWidgets.QFileDialog.Detail)
        self.setSidebarUrls(places(recent))
        self.preview = Preview(self)
        grid = self.layout()
        if isinstance(grid, QtWidgets.QGridLayout):
            grid.addWidget(self.preview, 0, grid.columnCount(), grid.rowCount(), 1)
        self.currentChanged.connect(self.preview.show_file)
        self.resize(1000, 560)
        split = self.findChild(QtWidgets.QSplitter, "splitter")
        if split is not None and split.count() == 2:
            split.setSizes([170, 560])  # the side panel's names whole ("Downloads", not "Downl")

    def selectFile(self, name):
        super().selectFile(name)
        path = name if os.path.isabs(name) else os.path.join(self.directory().absolutePath(), name)
        self.preview.show_file(path)


def recent_files():
    """FreeCAD's Recent Files, newest first."""
    try:
        import FreeCAD as App
    except ImportError:
        return []
    p = App.ParamGet("User parameter:BaseApp/Preferences/RecentFiles")
    return [f for f in (p.GetString("MRU%d" % i, "") for i in range(p.GetInt("RecentFiles", 4) or 4)) if f]


def get_open_file(parent, title, folder, filters):
    """Like QFileDialog.getOpenFileName: (path, filter), path '' when cancelled."""
    dlg = OpenDialog(parent, title, folder, filters, recent_files())
    if not dlg.exec():
        return "", ""
    files = dlg.selectedFiles()
    return (files[0] if files else ""), dlg.selectedNameFilter()
