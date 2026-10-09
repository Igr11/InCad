"""Rectangular and Circular patterns inside a sketch: the part's pattern dialogs, on sketch geometry. The
'feature' these kinds hand the session is the sketch itself; the pattern being made or edited is named in
sketch.InCadEditing (the shell sets it for an edit; create sets it for the new one)."""
import math
from types import SimpleNamespace

from incad.core import sketch_patterns as sp
from incad.features.common import Field, parse_picks

EDITING_PROP = "InCadEditing"


def _editing(sk):
    return getattr(sk, EDITING_PROP, "") or ""


def _record(sk, kind):
    """The record of the pattern open in the dialog, if it is of this kind (a stale InCadEditing may name a
    pattern of the other kind: then there is none to read)."""
    rec = sp.find(sk, _editing(sk))
    return rec if rec is not None and rec.get("kind") == kind else None


def _set_editing(sk, name):
    if EDITING_PROP not in sk.PropertiesList:
        sk.addProperty("App::PropertyString", EDITING_PROP, "InCad", "Pattern open in the dialog")
    setattr(sk, EDITING_PROP, name)


def _picks(doc, sk, text):
    out = []
    for o, s in parse_picks(doc, text):
        if o is sk and s:
            out.append(sp.element(sk, s))
    return out


PICK_KEYS = ("geometry", "dir1", "dir2", "from1", "to1", "axis")


def _geometry(doc, sk, text):
    picks = _picks(doc, sk, text)
    if not picks:
        raise ValueError("Click the geometry to repeat")
    geos = []
    for geo, _ in picks:
        if geo < 0:
            continue
        if sp.is_copy(sk, geo):
            raise ValueError("Pattern the original, not a copy")
        sp.ref_points(sk, geo)  # raises for splines/ellipses
        if geo not in geos:
            geos.append(geo)
    if not geos:
        raise ValueError("Click the geometry to repeat")
    return geos


def _direction(doc, sk, text):
    """(angle in degrees, ref) of a direction pick: a sketch line's angle now, or the X/Y axis."""
    picks = _picks(doc, sk, text)
    if not picks:
        return 0.0, [-1, 0]
    geo, pos = picks[0]
    if geo == -1:
        return 0.0, [-1, 0]
    if geo == -2:
        return 90.0, [-2, 0]
    a, b = sp.point_of(sk, geo, 1), sp.point_of(sk, geo, 2)
    return math.degrees(math.atan2(b.y - a.y, b.x - a.x)), sp.ref_of(sk, geo, 0)


def _text(sk, ref, fallback=""):
    """The pick text of a stored ref as the sketch is now ('Sketch:Edge3'), or `fallback` when it is gone."""
    if not ref:
        return fallback
    at = sp.deref(sk, ref)
    if at is None:
        return fallback
    try:
        return "%s:%s" % (sk.Name, sp.sub_of(sk, at[0], at[1]))
    except ValueError:
        return fallback


def _geometry_text(sk, rec):
    subs = []
    for gid in rec.get("originals", []):
        i = sp.index_of(sk, gid)
        if i is not None:
            subs.append("%s:Edge%d" % (sk.Name, i + 1))
    return ",".join(subs)


def _stored_values(values):
    return {k: v for k, v in values.items() if k not in PICK_KEYS}


def _count(text):
    t = (text or "").strip()
    if not t.isdigit() or int(t) < 1:
        raise ValueError("Count must be a whole number of 1 or more")
    return int(t)


def _param(doc, old, key, text, unit_kind, pending):
    """The pattern's model parameter for `key` (spacing_param / angle_param): made once with its value; an
    existing one is NOT set here but noted in `pending`: its value is written by the build, after the old copies
    are gone (changing a live tie's value lets the solver move the original toward the copies)."""
    from incad.core import model
    name = old.get(key)
    if name and model.is_model_parameter(doc, name):
        pending[name] = text
        return name
    return model.new_feature_parameter(doc, text, unit_kind)


# ----- rectangular -----
RECT_FIELDS = (
    Field("geometry", "Geometry", "picks", pick="sketch_geometry"),
    Field("fit1", "Distribution", "choice", (("spacing", "By spacing"), ("faces", "Equal spacing")), default="spacing"),
    Field("dir1", "Direction 1", "pick", pick="sketch_direction", show_if=("fit1", ("spacing",))),
    Field("flip1", "Flip direction", "bool", default=False),
    Field("count1", "Count", "value_length", default="2"),
    Field("spacing1", "Spacing", "value_length", default="10 mm", show_if=("fit1", ("spacing",))),
    Field("from1", "From", "pick", pick="sketch_limit", show_if=("fit1", ("faces",))),
    Field("to1", "To", "pick", pick="sketch_limit", show_if=("fit1", ("faces",))),
    Field("two_directions", "Two directions", "bool", default=False, show_if=("fit1", ("spacing",))),
    Field("dir2", "Direction 2", "pick", pick="sketch_direction", show_if=(("two_directions", (True,)), ("fit1", ("spacing",)))),
    Field("count2", "Count 2", "value_length", default="2", show_if=(("two_directions", (True,)), ("fit1", ("spacing",)))),
    Field("spacing2", "Spacing 2", "value_length", default="10 mm", show_if=(("two_directions", (True,)), ("fit1", ("spacing",)))),
)


def _rect_defaults(doc, body, sk):
    return {"geometry": "", "fit1": "spacing", "dir1": "%s:H_Axis" % sk.Name if sk is not None else "", "flip1": False,
            "count1": "2", "spacing1": "10 mm", "from1": "", "to1": "", "two_directions": False,
            "dir2": "%s:V_Axis" % sk.Name if sk is not None else "", "count2": "2", "spacing2": "10 mm"}


def _rect_record(doc, sk, name, old, values):
    geos = _geometry(doc, sk, values.get("geometry"))
    count = _count(values.get("count1"))
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    old = sp.live_params(doc, sk, dict(old)) if old else {}
    pending = {}
    rec = {"name": name, "kind": "rect", "values": _stored_values(values), "param_values": pending,
           "originals": [sp.ensure_id(sk, g) for g in geos], "count": count, "flip": bool(values.get("flip1"))}
    if values.get("fit1") == "faces":
        start = _picks(doc, sk, values.get("from1"))
        end = _picks(doc, sk, values.get("to1"))
        if not start or not end:
            raise ValueError("Pick the From and To limits: where the first and last copies are spaced from")
        spacing, angle = sp.equal_spacing(sk, geos, start[0], end[0], count)
        rec["spacing_param"] = _param(doc, old, "spacing_param", "%.6g mm" % spacing, "length", pending)
        rec["angle"] = angle
        rec["from_ref"], rec["to_ref"] = sp.ref_of(sk, *start[0]), sp.ref_of(sk, *end[0])
        rec["values"]["spacing1"] = "%.6g mm" % spacing
    else:
        rec["spacing_param"] = _param(doc, old, "spacing_param", (values.get("spacing1") or "10 mm").strip(), "length",
                                      pending)
        rec["angle"], rec["dir1_ref"] = _direction(doc, sk, values.get("dir1"))
        if values.get("two_directions"):
            rec["count2"] = _count(values.get("count2"))
            rec["spacing_param2"] = _param(doc, old, "spacing_param2", (values.get("spacing2") or "10 mm").strip(),
                                           "length", pending)
            rec["angle2"], rec["dir2_ref"] = _direction(doc, sk, values.get("dir2"))
    return rec


def _rect_create(doc, body, sk, values):
    if sk is None:
        raise ValueError("Open a sketch first")
    name = sp.next_name(sk)
    _set_editing(sk, name)
    rec = _rect_record(doc, sk, name, {}, values)
    sp.build_rect(doc, sk, rec)
    return sk


def _rect_update(doc, sk, values):
    name = _editing(sk)
    old = _record(sk, "rect") or {}
    rec = _rect_record(doc, sk, name, old, values)
    sp.rebuild(doc, sk, rec)
    return sk


def _rect_read(doc, sk):
    rec = _record(sk, "rect")
    if rec is None:
        return _rect_defaults(doc, None, sk)
    from incad.core import model
    rec = sp.live_params(doc, sk, dict(rec))
    defaults = _rect_defaults(doc, None, sk)
    values = dict(defaults, **_stored_values(rec.get("values", {})))
    values["geometry"] = _geometry_text(sk, rec)
    values["dir1"] = _text(sk, rec.get("dir1_ref"), defaults["dir1"])
    values["dir2"] = _text(sk, rec.get("dir2_ref"), defaults["dir2"])
    values["from1"] = _text(sk, rec.get("from_ref"))
    values["to1"] = _text(sk, rec.get("to_ref"))
    values["spacing1"] = model.parameter_text(doc, rec["spacing_param"])
    if rec.get("spacing_param2"):
        values["spacing2"] = model.parameter_text(doc, rec["spacing_param2"])
    values["count1"] = str(rec["count"])
    return values


def _rect_params(sk):
    rec = _record(sk, "rect") if sk is not None else None
    if rec is None:
        return {}
    rec = sp.live_params(sk.Document, sk, dict(rec))
    out = {"spacing1": rec.get("spacing_param")}
    if rec.get("spacing_param2"):
        out["spacing2"] = rec["spacing_param2"]
    return out


SKETCH_RECT = SimpleNamespace(
    __name__="incad.features.sketch_rect", TITLE="Rectangular Pattern", ICON="rect_pattern", TYPES=(),
    IN_SKETCH=True, NEEDS_PROFILE=False, FIELDS=RECT_FIELDS, PRESELECT={"geometry": "sketch_geometry"},
    defaults=_rect_defaults, create=_rect_create, read=_rect_read, update=_rect_update, param_names=_rect_params)


# ----- circular -----
CIRC_FIELDS = (
    Field("geometry", "Geometry", "picks", pick="sketch_geometry"),
    Field("axis", "Axis", "pick", pick="sketch_point"),
    Field("count", "Count", "value_length", default="4"),
    Field("angle", "Angle", "value_angle", default="360 °"),
    Field("fit", "Distribution", "choice", (("fitted", "Fitted"), ("between", "Between copies")), default="fitted"),
    Field("flip", "Flip", "bool", default=False),
)


def _circ_defaults(doc, body, sk):
    return {"geometry": "", "axis": "%s:RootPoint" % sk.Name if sk is not None else "", "count": "4",
            "angle": "360 °", "fit": "fitted", "flip": False}


def _angle_deg(text):
    import FreeCAD as App
    try:
        return float(App.Units.Quantity((text or "360 °").replace("°", "deg")).getValueAs("deg"))
    except Exception:
        raise ValueError("Angle must be a number of degrees")


def _circ_record(doc, sk, name, old, values):
    geos = _geometry(doc, sk, values.get("geometry"))
    count = _count(values.get("count"))
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    axis = _picks(doc, sk, values.get("axis"))
    if not axis:
        raise ValueError("Pick the axis point")
    total = _angle_deg(values.get("angle"))
    fitted = values.get("fit", "fitted") == "fitted"
    step = sp.step_angle(total, count, fitted)
    if abs(step) < 1e-9:
        raise ValueError("The copies would land on the original: give the pattern an angle")
    old = sp.live_params(doc, sk, dict(old)) if old else {}
    pending = {}
    return {"name": name, "kind": "circ", "values": _stored_values(values), "param_values": pending,
            "originals": [sp.ensure_id(sk, g) for g in geos], "count": count, "axis_ref": sp.ref_of(sk, *axis[0]),
            "flip": bool(values.get("flip")), "divisor": total / step,  # the parameter is the dialog's Angle
            "angle_param": _param(doc, old, "angle_param", "%.6g deg" % total, "angle", pending)}


def _circ_create(doc, body, sk, values):
    if sk is None:
        raise ValueError("Open a sketch first")
    name = sp.next_name(sk)
    _set_editing(sk, name)
    sp.build_circ(doc, sk, _circ_record(doc, sk, name, {}, values))
    return sk


def _circ_update(doc, sk, values):
    name = _editing(sk)
    old = _record(sk, "circ") or {}
    sp.rebuild(doc, sk, _circ_record(doc, sk, name, old, values))
    return sk


def _circ_read(doc, sk):
    rec = _record(sk, "circ")
    if rec is None:
        return _circ_defaults(doc, None, sk)
    from incad.core import model
    rec = sp.live_params(doc, sk, dict(rec))
    defaults = _circ_defaults(doc, None, sk)
    values = dict(defaults, **_stored_values(rec.get("values", {})))
    values["geometry"] = _geometry_text(sk, rec)
    values["axis"] = _text(sk, rec.get("axis_ref"), defaults["axis"])
    values["angle"] = model.parameter_text(doc, rec["angle_param"])
    values["count"] = str(rec["count"])
    return values


def _circ_params(sk):
    rec = _record(sk, "circ") if sk is not None else None
    if rec is None:
        return {}
    rec = sp.live_params(sk.Document, sk, dict(rec))
    return {"angle": rec["angle_param"]}


SKETCH_CIRC = SimpleNamespace(
    __name__="incad.features.sketch_circ", TITLE="Circular Pattern", ICON="circ_pattern", TYPES=(),
    IN_SKETCH=True, NEEDS_PROFILE=False, FIELDS=CIRC_FIELDS, PRESELECT={"geometry": "sketch_geometry"},
    defaults=_circ_defaults, create=_circ_create, read=_circ_read, update=_circ_update, param_names=_circ_params)

KINDS = (SKETCH_RECT, SKETCH_CIRC)
