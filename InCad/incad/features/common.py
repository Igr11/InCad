"""Helpers shared by feature kinds."""
from dataclasses import dataclass



@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str                # value_length | value_angle | choice | bool | pick
    choices: tuple = ()      # ((value, label), …) for choice
    default: object = None
    show_if: tuple = None    # (other key, (values…)): shown only when that field has one of the values


def closed_profile(sk):
    try:
        return any(w.isClosed() for w in sk.Shape.Wires)
    except Exception:
        return False


def consumers(sk):
    return [o for o in sk.InList if getattr(o, "Profile", None) is not None and _profile(o) is sk]


def _profile(feature):
    prof = getattr(feature, "Profile", None)
    if isinstance(prof, (tuple, list)):
        prof = prof[0] if prof else None
    return prof


def unconsumed_closed_sketches(body):
    from incad.core import sketch
    return [o for o in body.Group if sketch.is_sketch(o) and closed_profile(o) and not consumers(o)]


def value_param(doc, feature, prop, text, unit_kind):
    """Bind feature.prop to a model parameter holding `text` (create one if the property has none yet)."""
    from incad.core import model
    name = model.bound_parameter(feature, prop)
    if name is None:
        name = model.new_feature_parameter(doc, text, unit_kind)
        model.bind(feature, prop, name)
    elif model.parameter_text(doc, name) != text:
        model.set_model_parameter(doc, name, text)
    return name


def value_text(doc, feature, prop):
    from incad.core import model
    name = model.bound_parameter(feature, prop)
    return model.parameter_text(doc, name) if name else ""


def profile_of(feature):
    return _profile(feature)
