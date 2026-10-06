"""Feature kinds: pure model modules (FIELDS, defaults, create, read, update) that the feature dialog drives.
Loaded on first use, so widget code can import incad.features.common without FreeCAD."""


def kinds():
    from incad.features import dressup, extrude, hole, revolve
    return [extrude, revolve, hole, dressup.FILLET, dressup.CHAMFER, dressup.SHELL]


def kind_for(feature):
    for kind in kinds():
        if feature is not None and feature.TypeId in kind.TYPES:
            return kind
    return None


def __getattr__(name):
    if name == "KINDS":
        return kinds()
    raise AttributeError(name)
