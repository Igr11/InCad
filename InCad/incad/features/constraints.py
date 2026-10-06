"""Assembly constraints and joints (Inventor) on FreeCAD's native Assembly joints.

Mate = Distance (faces opposed), Flush = Distance (faces aligned), Angle, Tangent = Distance on a cylinder,
Insert = Revolute on round edges; joints Rigid (Fixed), Rotational (Revolute), Slider, Cylindrical, Ball.
Picks are 'Link:Element'. Offsets/angles are model parameters. A constraint that can't be met is refused with the
previous placements restored."""
from types import SimpleNamespace

import FreeCAD as App

from incad.features.common import Field, parse_picks, value_param, value_text

_STORE = "InCadConstraint"


def claims(j):
    return hasattr(j, _STORE)


def _moving_refs(doc, values):
    out = []
    for key in ("first", "second"):
        picks = parse_picks(doc, values.get(key))
        if not picks:
            raise ValueError("Pick the %s item on a component" % ("first" if key == "first" else "second"))
        link, el = picks[0]
        if link.TypeId != "App::Link":
            raise ValueError("Pick on a placed component")
        out.append((link, el))
    if out[0][0] is out[1][0]:
        raise ValueError("Pick items on two different components")
    return out


def _normal(link, el):
    sh = link.Shape.getElement(el) if hasattr(link.Shape, "getElement") else None
    if sh is None or sh.ShapeType != "Face":
        return None
    try:
        return sh.normalAt(*sh.Surface.parameter(sh.CenterOfMass)) if sh.Surface.TypeId == "Part::GeomPlane" \
            else None
    except Exception:
        return None


def _solve(doc, anchor=None):
    """Solve; with nothing grounded, hold `anchor` still for this solve (FreeCAD needs one fixed part)."""
    from incad.core import assembly
    asm = assembly.assembly_of(doc)
    temporary = anchor is not None and not any(assembly.is_grounded(c) for c in assembly.components(doc))
    if temporary:
        assembly.ground(anchor)
    try:
        result = asm.solve()
    finally:
        if temporary:
            assembly.unground(anchor)
    doc.recompute()
    return result


def _apply(doc, j, spec, values):
    import JointObject
    (l1, e1), (l2, e2) = _moving_refs(doc, values)
    if j.JointType != spec.joint:
        j.JointType = spec.joint
    if spec.value == "offset":
        value_param(doc, j, "Distance", values.get("offset") or "0 mm", "length")
    elif spec.value == "angle":
        value_param(doc, j, "Angle", values.get("angle") or "90 °", "angle")
    j.Proxy.setJointConnectors(j, [[l1, [e1, e1]], [l2, [e2, e2]]])
    result = _solve(doc, l1)
    if spec.facing is not None:
        n1, n2 = _normal(l1, e1), _normal(l2, e2)
        if n1 is not None and n2 is not None and (n1.dot(n2) < 0) != (spec.facing == "opposed"):
            j.Proxy.flipOnePart(j)
            result = _solve(doc, l1)
    return result


def _placements(doc):
    from incad.core import assembly
    return {c.Name: App.Placement(c.Placement) for c in assembly.components(doc)}


def _met(doc, j, spec, values):
    """Did the solver satisfy the constraint? (checks the planar distance for Mate/Flush)."""
    if spec.value != "offset" or spec.facing is None:
        return True
    (l1, e1), (l2, e2) = _moving_refs(doc, values)
    f1, f2 = l1.Shape.getElement(e1), l2.Shape.getElement(e2)
    n1 = _normal(l1, e1)
    if n1 is None:
        return True
    gap = abs((f2.CenterOfMass - f1.CenterOfMass).dot(n1))
    want = abs(j.Distance.Value)
    n2 = _normal(l2, e2)
    return abs(gap - want) < 1e-3 and (n2 is None or abs(abs(n1.dot(n2)) - 1) < 1e-6)


def _make(spec):
    def defaults(doc, body, profile=None):
        values = {f.key: f.default for f in spec.FIELDS}
        values.update(first="", second="")
        return values

    def create(doc, body, profile, values):
        import JointObject
        from incad.core import assembly
        _moving_refs(doc, values)
        before = _placements(doc)
        j = assembly.joint_group(doc).newObject("App::FeaturePython", spec.joint_name)
        JointObject.Joint(j, JointObject.JointTypes.index(spec.joint))
        if App.GuiUp:
            JointObject.ViewProviderJoint(j.ViewObject)
        j.addProperty("App::PropertyString", _STORE, "InCad", "InCad constraint kind")
        j.setPropertyStatus(_STORE, "Hidden")
        setattr(j, _STORE, spec.key)
        j.Label = spec.TITLE
        try:
            result = _apply(doc, j, spec, values)
            if result != 0 or not _met(doc, j, spec, values):
                raise ValueError("%s conflicts with the other constraints (it can't be met)" % spec.TITLE)
        except Exception:
            doc.removeObject(j.Name)
            for name, plc in before.items():
                doc.getObject(name).Placement = plc
            _solve(doc)
            raise
        return j

    def read(doc, j):
        values = defaults(doc, None)
        refs = []
        for prop in ("Reference1", "Reference2"):
            ref = getattr(j, prop, None)
            refs.append("%s:%s" % (ref[0].Name, ref[1][0]) if ref and ref[0] is not None and ref[1] else "")
        values.update(first=refs[0], second=refs[1])
        if spec.value == "offset":
            values["offset"] = value_text(doc, j, "Distance") or "0 mm"
        elif spec.value == "angle":
            values["angle"] = value_text(doc, j, "Angle") or "90°"
        return values

    def update(doc, j, values):
        before = _placements(doc)
        result = _apply(doc, j, spec, values)
        if result != 0 or not _met(doc, j, spec, values):
            for name, plc in before.items():
                doc.getObject(name).Placement = plc
            raise ValueError("%s conflicts with the other constraints (it can't be met)" % spec.TITLE)
        return j

    spec.defaults, spec.create, spec.read, spec.update = defaults, create, read, update
    spec.claims = lambda j: getattr(j, _STORE, None) == spec.key
    spec._pad_of = lambda j: j
    return spec


def _kind(key, title, icon, joint, pick1, pick2, value=None, facing=None):
    fields = [Field("first", "First", "pick", pick=pick1), Field("second", "Second", "pick", pick=pick2)]
    props = {}
    if value == "offset":
        fields.append(Field("offset", "Offset", "value_length", default="0 mm"))
        props = {"offset": "Distance"}
    elif value == "angle":
        fields.append(Field("angle", "Angle", "value_angle", default="90 °"))
        props = {"angle": "Angle"}
    return _make(SimpleNamespace(
        __name__="incad.features." + key, key=key, TITLE=title, ICON=icon, TYPES=("App::FeaturePython",),
        NEEDS_PROFILE=False, ASSEMBLY=True, PROPS=props, FIELDS=tuple(fields), joint=joint,
        joint_name=title.replace(" ", ""), value=value, facing=facing))


MATE = _kind("mate", "Mate", "mate", "Distance", "face", "face", "offset", "opposed")
FLUSH = _kind("flush", "Flush", "flush", "Distance", "face", "face", "offset", "aligned")
ANGLE = _kind("angle_c", "Angle", "angle_c", "Angle", "face", "face", "angle")
TANGENT = _kind("tangent", "Tangent", "tangent", "Distance", "face", "face", "offset")
INSERT = _kind("insert", "Insert", "insert", "Revolute", "circular_edge", "circular_edge")
RIGID = _kind("rigid", "Rigid", "rigid", "Fixed", "element", "element")
ROTATIONAL = _kind("rotational", "Rotational", "rotational", "Revolute", "element", "element")
SLIDER = _kind("slider", "Slider", "slider", "Slider", "element", "element")
CYLINDRICAL = _kind("cylindrical", "Cylindrical", "cylindrical", "Cylindrical", "element", "element")
BALL = _kind("ball", "Ball", "ball", "Ball", "element", "element")

KINDS = [MATE, FLUSH, ANGLE, TANGENT, INSERT, RIGID, ROTATIONAL, SLIDER, CYLINDRICAL, BALL]
