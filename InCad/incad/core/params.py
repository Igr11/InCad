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


_KINDS = {"Boolean": "Bool", "Unsigned Long": "Unsigned", "Integer": "Int", "Float": "Float", "String": "String"}


def snapshot_group(group):
    """Every value currently in `group`, in the same form as snapshot()."""
    out = {}
    for kind, name, value in App.ParamGet(group).GetContents() or []:
        if kind in _KINDS:
            out[name] = [_KINDS[kind], True, value]
    return out
