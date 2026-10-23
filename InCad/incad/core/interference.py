"""Interference in an assembly (the user: "where parts of an assembly go into each other must show in a bright
colour"; Inventor: Analyze Interference): the solid two shown components share, for every pair whose boxes meet.
Faces that only touch (a shaft in its hole, a part standing on another) share no volume and are not interference."""

MIN_VOLUME = 1e-3  # mm³: less is the kernel's rounding where faces touch
_cache = {}  # document name -> (signature, result)


def _items(doc):
    """The shown components with solids: InCad's links, or the Bodies and shapes of an assembly from elsewhere."""
    from incad.core import section
    return [(o, shape) for o, shape, _ in section.shown_shapes(doc) if shape.Solids]


def signature(doc):
    """What the result depends on: every shown component, where it is and what it is."""
    return tuple((link.Name, str(link.Placement), shape.hashCode()) for link, shape in _items(doc))


def overlaps(doc):
    """[(link a, link b, shared solid, volume mm³)] for every pair of shown components that go into each other."""
    sig = signature(doc)
    seen = _cache.get(doc.Name)
    if seen is not None and seen[0] == sig:
        return seen[1]
    items = _items(doc)
    out = []
    for i, (a, sa) in enumerate(items):
        for b, sb in items[i + 1:]:
            if not sa.BoundBox.intersect(sb.BoundBox):
                continue
            try:
                common = sa.common(sb)
            except Exception:
                continue
            volume = sum(s.Volume for s in common.Solids)
            if volume > max(MIN_VOLUME, 1e-9 * min(sa.Volume, sb.Volume)):
                out.append((a, b, common, volume))
    _cache[doc.Name] = (sig, out)
    return out


def forget(doc_name=None):
    if doc_name is None:
        _cache.clear()
    else:
        _cache.pop(doc_name, None)
