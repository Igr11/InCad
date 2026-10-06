"""Part materials for printing: density (g/cm³) for Mass Properties and a display colour. Stored in doc.Meta."""
from incad.core import document

KEY = "InCadMaterial"
MATERIALS = {
    "PLA": (1.24, (0.85, 0.85, 0.80)), "PETG": (1.27, (0.55, 0.75, 0.90)), "ABS": (1.04, (0.92, 0.90, 0.85)),
    "ASA": (1.07, (0.80, 0.80, 0.78)), "TPU": (1.21, (0.30, 0.30, 0.32)), "Nylon": (1.14, (0.95, 0.94, 0.90)),
    "Resin": (1.18, (0.60, 0.62, 0.66)), "Aluminium": (2.70, (0.78, 0.80, 0.83)),
    "Steel": (7.85, (0.62, 0.64, 0.67)),
}


def names():
    return list(MATERIALS)


_PROP = "Material"


def _store(doc, create=False):
    """The material lives on the InCad model object, so a change is part of the undo history (doc.Meta isn't)."""
    from incad.core import model
    obj = model._model_obj(doc, create=create)
    if obj is not None and create and _PROP not in obj.PropertiesList:
        obj.addProperty("App::PropertyString", _PROP, "InCad", "Part material")
        obj.setPropertyStatus(_PROP, "Hidden")
    return obj


def material(doc):
    obj = _store(doc) if doc is not None else None
    name = getattr(obj, _PROP, None) if obj is not None else None
    if not name and doc is not None:
        name = doc.Meta.get(KEY)  # files from before materials were undoable
    return name if name in MATERIALS else "PLA"


def density(doc):
    return MATERIALS[material(doc)][0]


def set_material(doc, name):
    if name not in MATERIALS:
        raise ValueError("Unknown material %r (choose one of %s)" % (name, ", ".join(MATERIALS)))
    setattr(_store(doc, create=True), _PROP, name)
    color = MATERIALS[name][1]
    for body in document.bodies(doc):
        vo = getattr(body, "ViewObject", None)
        if vo is not None:
            try:
                vo.ShapeColor = color
            except Exception:
                pass
