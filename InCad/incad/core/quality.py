"""⚙ ▸ Display Quality: how finely curved faces are drawn (the view's triangles, never the model). Normal is FreeCAD's
own; Fine keeps small round faces (an emboss on a ball, a fillet) smooth under a highlight, at some cost in drawing
time. New shapes take it from FreeCAD's Part settings (each view provider reads them when it is made); shapes in
open files are set to it, which does not mark a file as changed."""
import FreeCAD as App

from incad.core import prefs

PART = "User parameter:BaseApp/Preferences/Mod/Part"
VALUES = {"normal": (0.2, 28.65), "fine": (0.1, 12.0)}  # (deviation, % of the shape's size; angle, degrees)
# a Solid holding a gear or a worm, at most this fine (the user: redrawing took a second a mouse move — a worm's
# thread is one face winding round many times: 99 000 triangles at Fine, 12 000 here, and as smooth to the eye)
GEARS = (0.5, 28.65)
_applied = {}  # document (its Uid: a file closed and opened again is new) -> the quality its shapes were set to


def values():
    return VALUES[prefs.display_quality()]


def set_defaults():
    """FreeCAD's settings that every shape made from now on reads."""
    deviation, angle = values()
    p = App.ParamGet(PART)
    if abs(p.GetFloat("MeshDeviation", 0.2) - deviation) > 1e-9:
        p.SetFloat("MeshDeviation", deviation)
    if abs(p.GetFloat("MeshAngularDeflection", 28.65) - angle) > 1e-9:
        p.SetFloat("MeshAngularDeflection", angle)


def apply(doc, force=False):
    """The document's shapes drawn at the chosen quality (once per document and quality); True when it set any."""
    if getattr(doc, "Restoring", False):
        return False  # its shapes are not all there yet: the next activation sets them
    q = prefs.display_quality()
    key = str(getattr(doc, "Uid", doc.Name))
    stamp = (q, len(doc.Objects))  # a new object since: set it too (a gear's Solid draws coarser)
    if not force and _applied.get(key) == stamp:
        return False
    _applied[key] = stamp
    coarse = _gear_bodies(doc)
    try:
        import FreeCADGui as Gui
        gdoc = Gui.getDocument(doc.Name)
    except Exception:
        return False
    if gdoc is None:
        return False
    modified = gdoc.Modified
    changed = False
    for o in doc.Objects:
        vo = getattr(o, "ViewObject", None)
        props = getattr(vo, "PropertiesList", ()) if vo is not None else ()
        if "Deviation" not in props or "AngularDeflection" not in props:
            continue
        deviation, angle = drawn_at(o, q, coarse)
        try:
            if abs(vo.Deviation - deviation) > 1e-6:
                vo.Deviation = deviation
                changed = True
            if abs(float(getattr(vo.AngularDeflection, "Value", vo.AngularDeflection)) - angle) > 1e-3:
                vo.AngularDeflection = angle
                changed = True
        except Exception:
            continue
    if changed and not modified:
        gdoc.Modified = False  # only how it is drawn changed: nothing to save
    return changed


def _gear_bodies(doc):
    from incad.features import gear
    return {o.getParentGeoFeatureGroup().Name for o in doc.Objects
            if gear.is_gear(o) and o.getParentGeoFeatureGroup() is not None}


def drawn_at(obj, q=None, coarse=None):
    """(deviation, angle) an object is drawn at: the chosen quality, no finer than GEARS in a gear's Solid."""
    deviation, angle = VALUES[q or prefs.display_quality()]
    body = obj if obj.TypeId == "PartDesign::Body" else (
        obj.getParentGeoFeatureGroup() if hasattr(obj, "getParentGeoFeatureGroup") else None)
    if body is not None and body.Name in (coarse if coarse is not None else _gear_bodies(obj.Document)):
        deviation, angle = max(deviation, GEARS[0]), max(angle, GEARS[1])
    return deviation, angle


def draw_as_gear(obj):
    """A gear or worm just made: drawn at GEARS before its first recompute (never tessellated finely first)."""
    vo = getattr(obj, "ViewObject", None)
    if vo is None or "Deviation" not in getattr(vo, "PropertiesList", ()):
        return
    try:
        vo.Deviation = max(vo.Deviation, GEARS[0])
        vo.AngularDeflection = max(float(getattr(vo.AngularDeflection, "Value", vo.AngularDeflection)), GEARS[1])
    except Exception:
        pass


def apply_all(force=False):
    for doc in list(App.listDocuments().values()):
        apply(doc, force)
