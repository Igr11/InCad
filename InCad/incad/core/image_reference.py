"""File ▸ Import of a picture (the user: JPG for reference): an Image plane on the XY plane, centred on the origin, its
longer side SIZE mm and the picture's proportions kept, to sketch over. Data to look at, not part of the model: a
row of its own in the browser (Hide / Show, Rename, Delete), as an STL Reference."""
import os

MARK = "InCadPicture"  # on the Image plane: the file it shows
IMAGES = (".jpg", ".jpeg", ".png", ".bmp")
SIZE = 100.0


def is_picture(obj):
    return obj is not None and obj.TypeId == "Image::ImagePlane" and hasattr(obj, MARK)


def pictures(doc):
    return [o for o in doc.Objects if is_picture(o)] if doc is not None else []


PLANES = {"xy": ((1, 0, 0), (0, 1, 0)), "xz": ((1, 0, 0), (0, 0, 1)), "yz": ((0, 1, 0), (0, 0, 1))}


def put_on(obj, plane):
    """The picture onto an origin plane (its right along the plane's first axis, its up along the second), about its
    middle."""
    import FreeCAD as App
    x, y = (App.Vector(*v) for v in PLANES[plane])
    obj.Placement = App.Placement(obj.Placement.Base, App.Rotation(x, y, x.cross(y), "ZXY"))


def turn(obj, degrees):
    """Turned about its own middle, in its plane."""
    import FreeCAD as App
    p = App.Placement(obj.Placement)
    p.Rotation = p.Rotation.multiply(App.Rotation(App.Vector(0, 0, 1), degrees))
    obj.Placement = p


def mirror(obj):
    """Mirrored left to right (turned over about its up axis: the same picture seen from behind)."""
    import FreeCAD as App
    p = App.Placement(obj.Placement)
    p.Rotation = p.Rotation.multiply(App.Rotation(App.Vector(0, 1, 0), 180))
    obj.Placement = p


def _pixels(path):
    """(width, height) of the picture in pixels, or None."""
    try:
        from incad.qt import QtGui
        size = QtGui.QImageReader(path).size()
        if size.width() > 0 and size.height() > 0:
            return size.width(), size.height()
    except Exception:
        pass
    return None


def add(doc, path):
    """The picture in the part as an Image plane; returns it."""
    name = os.path.basename(path)
    if os.path.splitext(path)[1].lower() not in IMAGES:
        raise ValueError("An image (JPG, PNG, BMP) is imported for reference, not %s" % name)
    if not os.path.isfile(path):
        raise ValueError("%s is not there" % name)
    w, h = _pixels(path) or (1, 1)
    scale = SIZE / max(w, h)
    obj = doc.addObject("Image::ImagePlane", "Picture")
    obj.ImageFile = path
    obj.XSize, obj.YSize = w * scale, h * scale
    obj.Label = "%s (image)" % os.path.splitext(name)[0]
    obj.addProperty("App::PropertyString", MARK, "InCad", "The picture this Image plane shows")
    obj.setPropertyStatus(MARK, "Hidden")
    setattr(obj, MARK, name)
    doc.recompute()
    return obj
