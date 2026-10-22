"""Feature kinds: pure model modules (FIELDS, defaults, create, read, update) that the feature dialog drives.
Loaded on first use, so widget code can import incad.features.common without FreeCAD."""


def kinds():
    from incad.features import (asm_combine, combine, constraints, dressup, emboss, extrude, full_round, hole, move_face,
                                patterns, revolve, shapes, sketch_patterns, sketch_text, split, thread, work)
    return [extrude, revolve, hole, dressup.FILLET, dressup.CHAMFER, dressup.SHELL, patterns.RECT, patterns.CIRC,
            patterns.MIRROR, work.PLANE, work.AXIS, work.POINT, thread, combine, split, move_face, emboss,
            full_round] \
        + list(constraints.KINDS) \
        + [asm_combine] + list(shapes.KINDS) + list(sketch_patterns.KINDS) + [sketch_text.TEXT]


def kind_for(feature):
    if getattr(feature, "InCadHelperOf", None):
        return None  # a piece InCad made for another feature (a sweep's wall): edited from that feature
    for kind in kinds():
        if feature is not None and feature.TypeId in kind.TYPES and getattr(kind, "claims", lambda f: True)(feature):
            return kind
    return None


def __getattr__(name):
    if name == "KINDS":
        return kinds()
    raise AttributeError(name)
