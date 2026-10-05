"""Save, write and restore FreeCAD parameter values (InCad changes a few 'View' colors while active)."""
import FreeCAD as App


def _names(p):
    return {c[1] for c in (p.GetContents() or [])}


def snapshot(group, names_kinds):
    """{name: [kind, existed, value]} for each name in names_kinds ({name: kind})."""
    p = App.ParamGet(group)
    present = _names(p)
    return {name: [kind, name in present, getattr(p, "Get" + kind)(name) if name in present else None]
            for name, kind in names_kinds.items()}


def write(group, values):
    """values: {name: (kind, value)}"""
    p = App.ParamGet(group)
    for name, (kind, value) in values.items():
        getattr(p, "Set" + kind)(name, value)


def restore(group, snap):
    p = App.ParamGet(group)
    for name, (kind, existed, value) in snap.items():
        if existed:
            getattr(p, "Set" + kind)(name, value)
        else:
            getattr(p, "Rem" + kind)(name)
