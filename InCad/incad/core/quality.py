"""⚙ ▸ Display Quality: how finely curved faces are drawn (the view's triangles, never the model). Normal is FreeCAD's
own; Fine keeps small round faces (an emboss on a ball, a fillet) smooth under a highlight, at some cost in drawing
time. New shapes take it from FreeCAD's Part settings (each view provider reads them when it is made); shapes in
open files are set to it, which does not mark a file as changed."""
import FreeCAD as App

from incad.core import prefs

PART = "User parameter:BaseApp/Preferences/Mod/Part"
VALUES = {"normal": (0.2, 28.65), "fine": (0.1, 12.0)}  # (deviation, % of the shape's size; angle, degrees)
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
    if not force and _applied.get(key) == q:
        return False
    _applied[key] = q
    deviation, angle = VALUES[q]
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


def apply_all(force=False):
    for doc in list(App.listDocuments().values()):
        apply(doc, force)
