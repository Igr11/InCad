"""Feature kinds: pure model modules (FIELDS, defaults, create, read, update) that the feature dialog drives."""
from incad.features import extrude, revolve

KINDS = [extrude, revolve]


def kind_for(feature):
    for kind in KINDS:
        if feature is not None and feature.TypeId in kind.TYPES:
            return kind
    return None
