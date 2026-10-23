"""Textures for Appearance (the user: "colour, and some textures maybe"): brushed metal, wood, carbon fibre, knurl,
sand — grey pictures made here once (tiling, numpy), laid over the Solid's own colours (the picture darkens them, so a
red Solid gets red wood) by Coin nodes at the top of its view: a cube mapping, sized so the pattern keeps its real
size (mm) whatever the part's size. View nodes only: the record says which texture, and it is put back whenever it
is missing (a file opened, a view made again)."""
import math
import os

import FreeCAD as App

NAMES = ("None", "Brushed", "Wood", "Carbon", "Knurl", "Sand")
PERIOD = {"Brushed": 30.0, "Wood": 90.0, "Carbon": 8.0, "Knurl": 6.0, "Sand": 12.0}  # mm one picture covers
NODE = "InCadTexture"
SIZE = 256


def _image(name):
    """A SIZE × SIZE grey picture (0..1, tiling) of the texture."""
    import numpy as np
    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:SIZE, 0:SIZE] / float(SIZE)

    def blur_x(a, k):
        out = a.copy()
        for s in range(1, k):
            out += np.roll(a, s, axis=1) + np.roll(a, -s, axis=1)
        return out / (2 * k - 1)

    if name == "Brushed":  # fine streaks along one way
        a = blur_x(rng.random((SIZE, SIZE)), 24)
        a = (a - a.min()) / (np.ptp(a) or 1)
        return 0.78 + 0.22 * a
    if name == "Wood":  # long grain lines, gently bent, unevenly spaced: a thin dark late-wood band in each year
        def smooth(n, k):  # periodic noise across, k waves
            phases = rng.random(k) * 2 * math.pi
            return sum(np.sin(2 * math.pi * (j + 1) * n + phases[j]) / (j + 1) for j in range(k))
        w = y + 0.01 * smooth(x, 3)
        t = 9 * (w + 0.035 * smooth(w, 3))  # years of uneven width
        f = t - np.floor(t)
        late = np.exp(-((f - 0.8) / 0.09) ** 2)
        grain = blur_x(rng.random((SIZE, SIZE)), 60)
        grain = (grain - grain.min()) / (np.ptp(grain) or 1)
        return 0.86 - 0.38 * late - 0.12 * f + 0.16 * (grain - 0.5)
    if name == "Carbon":  # a 2 × 2 twill: bundles across and along, each shaded along its length
        n = 4
        cx, cy = (x * n) % 1.0, (y * n) % 1.0
        ix, iy = np.floor(x * n).astype(int), np.floor(y * n).astype(int)
        across = ((ix + iy) // 2) % 2 == 0
        shade = np.where(across, np.sin(math.pi * cy), np.sin(math.pi * cx))
        return 0.45 + 0.5 * shade ** 0.7
    if name == "Knurl":  # diamonds: two crossing grooves
        n = 6
        a = np.abs(np.sin(math.pi * n * (x + y)))
        b = np.abs(np.sin(math.pi * n * (x - y)))
        return 0.55 + 0.45 * np.minimum(a, b) ** 0.6
    if name == "Sand":  # fine grains, a little blotchy
        a = rng.random((SIZE, SIZE))
        blot = blur_x(blur_x(rng.random((SIZE, SIZE)), 8).T, 8).T
        blot = (blot - blot.min()) / (np.ptp(blot) or 1)
        return 0.8 + 0.12 * a + 0.08 * blot
    return np.ones((SIZE, SIZE))


def path(name):
    """The texture's picture file (made the first time)."""
    folder = os.path.join(App.getUserAppDataDir(), "InCadTextures")
    p = os.path.join(folder, "%s_v2.png" % name.lower())
    if not os.path.isfile(p):
        import numpy as np
        from incad.qt import QtGui
        os.makedirs(folder, exist_ok=True)
        a = (np.clip(_image(name), 0, 1) * 255).astype(np.uint8)
        a = np.ascontiguousarray(a)
        img = QtGui.QImage(a.data, SIZE, SIZE, SIZE, QtGui.QImage.Format_Grayscale8)
        img.copy().save(p)
    return p


def _found(root):
    for i in range(root.getNumChildren()):
        c = root.getChild(i)
        if c.getName() == NODE:
            return i, c
    return None, None


def put(body, name):
    """The texture on the Solid's view (None / "None": taken off); only what changed."""
    from pivy import coin
    vo = getattr(body, "ViewObject", None)
    if vo is None:
        return
    root = vo.RootNode
    index, node = _found(root)
    if not name or name == "None":
        if node is not None:
            root.removeChild(index)
        return
    shape = body.Shape
    box = shape.BoundBox if not shape.isNull() else None
    size = round(max(box.XLength, box.YLength, box.ZLength), 3) if box is not None else 1.0
    if node is not None:
        if node.getChild(2).getName().getString() == NODE + "_" + name \
                and abs(node.getChild(0).scaleFactor.getValue()[0] - size / PERIOD[name]) < 1e-6:
            return
        root.removeChild(index)
    group = coin.SoGroup()
    group.setName(NODE)
    xf = coin.SoTexture2Transform()
    xf.scaleFactor.setValue(size / PERIOD[name], size / PERIOD[name])  # the pattern's real size on any part
    group.addChild(xf)
    group.addChild(coin.SoTextureCoordinateCube())
    tex = coin.SoTexture2()
    tex.setName(NODE + "_" + name)
    tex.filename = path(name)
    tex.model = coin.SoTexture2.MODULATE
    tex.wrapS = tex.wrapT = coin.SoTexture2.REPEAT
    group.addChild(tex)
    root.insertChild(group, 0)


def name_on(body):
    """The texture shown on the Solid's view now ('None' when there is none)."""
    vo = getattr(body, "ViewObject", None)
    if vo is None:
        return "None"
    _, node = _found(vo.RootNode)
    if node is None:
        return "None"
    return node.getChild(2).getName().getString()[len(NODE) + 1:]
