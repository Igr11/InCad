"""Feature kinds: pure model modules (FIELDS, defaults, create, read, update) that the feature dialog drives.
Loaded on first use, so widget code can import incad.features.common without FreeCAD."""


def kinds():
    from incad.features import combine, dressup, extrude, hole, patterns, revolve, thread, work
    return [extrude, revolve, hole, dressup.FILLET, dressup.CHAMFER, dressup.SHELL, patterns.RECT, patterns.CIRC,
            patterns.MIRROR, work.PLANE, work.AXIS, work.POINT, thread, combine]


def kind_for(feature):
    for kind in kinds():
        if feature is not None and feature.TypeId in kind.TYPES and getattr(kind, "claims", lambda f: True)(feature):
            return kind
    return None


def __getattr__(name):
    if name == "KINDS":
        return kinds()
    raise AttributeError(name)
