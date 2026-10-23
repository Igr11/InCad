"""Assembly constraints and joints (Inventor) on FreeCAD's native Assembly joints.

Mate = Distance (faces opposed), Flush = Distance (faces aligned), Angle, Parallel, Perpendicular (each on flat faces
or straight edges in any mix), Tangent = Distance on a cylinder, Insert = Revolute on round edges; joints Rigid
(Fixed), Rotational (Revolute), Slider, Cylindrical, Ball.
FreeCAD's Parallel / Perpendicular / Angle compare the picks' axes: a face's normal, an edge's direction. For a face
against an edge the user means the edge against the FACE, so InCad gives FreeCAD the other meaning (Parallel <->
Perpendicular, Angle a <-> 90 deg - a; the model parameter keeps what the user typed).
Picks are 'Link:Element'. Offsets/angles are model parameters. A constraint that can't be met is refused with the
previous placements restored.
Flip (the hidden bool InCadFlip on the joint) picks the other solution: Mate's faces face the same way, Flush's each
other; Tangent's round face sits outside the flat face's part (its outward normal's side, whichever way FreeCAD's
frame points: the frame is turned over by its Offset where they disagree) and Flip puts it inside; on two round faces
it touches outside, Flip inside the other (the Distance bound as -(offset + 2 r)); Insert and the Rotational /
Slider / Cylindrical joints turn the free part over about the joint frame's X (the solver keeps either way, so
InCadFlip says which one is applied: re-applying the same choice turns nothing)."""
import math
import re
from types import SimpleNamespace

import FreeCAD as App

from incad.features.common import Field, parse_picks, value_param
from incad.core import safe

_STORE = "InCadConstraint"
_FLIP = "InCadFlip"
_OVER = App.Rotation(App.Vector(1, 0, 0), 180)  # a joint frame turned over: Z the other way


def _flipped(j):
    return bool(getattr(j, _FLIP, False))


def _add_flip(j):
    j.addProperty("App::PropertyBool", _FLIP, "InCad", "InCad: the constraint's other solution (Flip)")
    j.setPropertyStatus(_FLIP, "Hidden")


def _store_flip(j, on):
    """Keep the Flip that is applied (a joint from before Flip gets the property when first flipped)."""
    if _FLIP not in j.PropertiesList:
        if not on:
            return
        _add_flip(j)
    if getattr(j, _FLIP) != bool(on):
        setattr(j, _FLIP, bool(on))


def _facing(spec, values):
    """Mate's / Flush's wanted facing; Flip swaps it."""
    if spec.facing is None or not values.get("flip"):
        return spec.facing
    return "aligned" if spec.facing == "opposed" else "opposed"


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


_DIRECTIONS = ("Parallel", "Perpendicular", "Angle")  # kinds that compare two directions (rotation only)
_SWAP = {"Parallel": "Perpendicular", "Perpendicular": "Parallel"}


def _axis(link, el):
    """(point, unit direction) of a direction pick in the assembly: a flat face's (centre, normal), a straight edge's
    (middle, direction); None for anything else."""
    try:
        sh = link.Shape.getElement(el)
    except Exception:
        return None
    if sh.ShapeType == "Face" and sh.Surface.TypeId == "Part::GeomPlane":
        n = _normal(link, el)
        return (sh.CenterOfMass, App.Vector(n).normalize()) if n is not None else None
    if sh.ShapeType == "Face" and sh.Surface.TypeId in ("Part::GeomCylinder", "Part::GeomCone"):
        return sh.CenterOfMass, App.Vector(sh.Surface.Axis).normalize()  # a round face: its axis, as an edge
    if sh.ShapeType == "Edge" and safe.curve_type(sh) == "Part::GeomLine":
        return sh.CenterOfMass, App.Vector(sh.Curve.Direction).normalize()
    return None


def _mixed(doc, values):
    """A face against an edge: FreeCAD compares the face's NORMAL with the edge, the user the face itself."""
    kinds = []
    for link, el in _moving_refs(doc, values):
        try:
            sh = link.Shape.getElement(el)
            round_face = sh.ShapeType == "Face" and sh.Surface.TypeId in ("Part::GeomCylinder", "Part::GeomCone")
            kinds.append("Edge" if round_face else sh.ShapeType)  # a round face stands for its axis: an edge
        except Exception:
            kinds.append(None)
    return set(kinds) == {"Face", "Edge"}


_ROUND = ("Part::GeomCylinder", "Part::GeomCone")


def _both_round(doc, values):
    """Two round faces (or two parts' axes clicked): Mate and Flush put their axes in line (the user, as Inventor)."""
    try:
        for link, el in _moving_refs(doc, values):
            sh = link.Shape.getElement(el)
            if sh.ShapeType != "Face" or sh.Surface.TypeId not in _ROUND:
                return False
        return True
    except Exception:
        return False


def _joint_type(doc, spec, values, j=None):
    """FreeCAD's joint type for these picks: Parallel and Perpendicular swap for a face against an edge; an Angle of
    90 deg there (FreeCAD's Angle 0, which its solver handles badly) is FreeCAD's Parallel: the edge stands up; Mate
    or Flush on two round faces (two axes) is FreeCAD's Cylindrical: the axes in line."""
    if spec.key in ("mate", "flush") and _both_round(doc, values):
        return "Cylindrical"
    if spec.joint in _SWAP and _mixed(doc, values):
        return _SWAP[spec.joint]
    if spec.joint == "Angle" and j is not None and _mixed(doc, values) and abs(j.Angle.Value) < 1e-9:
        return "Parallel"
    return spec.joint


def _set_type(j, joint):
    """Set FreeCAD's joint type, keeping the label: FreeCAD renames 'Parallel' to 'Perpendicular' in it."""
    if j.JointType != joint:
        label = j.Label
        j.JointType = joint
        if j.Label != label:
            j.Label = label


_COMPLEMENT = "90 deg - "


def _angle_param(j):
    """The model parameter holding an Angle's value as the user typed it: bound plainly, or as 90 deg - it (a face
    against an edge)."""
    from incad.core import model
    name = model.bound_parameter(j, "Angle")
    if name is not None:
        return name
    m = re.match(r"^%s%s\.([A-Za-z_]\w*)$" % (re.escape(_COMPLEMENT), model.MODEL_NAME), model._expression(j, "Angle"))
    return m.group(1) if m else None


def _bind_angle(doc, j, spec, text, complement):
    """Bind the joint's Angle to the model parameter holding `text` (made '<Title>N' when there is none):
    plainly, or as its complement for a face against an edge; an Edit switching between the two rebinds it."""
    from incad.core import model
    name = _angle_param(j)
    if name is None:
        name = model.new_feature_parameter(doc, text, "angle", spec.TITLE)
    elif model.parameter_text(doc, name) != text:
        model.set_model_parameter(doc, name, text)
    expr = "%s%s.%s" % (_COMPLEMENT if complement else "", model.MODEL_NAME, name)
    if model._expression(j, "Angle") != expr:
        j.setExpression("Angle", expr)
    return name


def _wanted(j):
    """|cos| of the angle FreeCAD's joint asks between the two axes (edges have no side, so either way round)."""
    if j.JointType == "Parallel":
        return 1.0
    if j.JointType == "Perpendicular":
        return 0.0
    return abs(math.cos(math.radians(j.Angle.Value)))


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


def _frame(link, el):
    """(point, direction) of a picked element in the assembly: a flat face (centre, normal), a circle (centre,
    axis); None for anything else."""
    import Part
    try:
        sh = link.Shape.getElement(el)
    except Exception:
        return None
    if sh.ShapeType == "Face" and sh.Surface.TypeId == "Part::GeomPlane":
        return sh.CenterOfMass, App.Vector(_normal(link, el)).normalize()
    if sh.ShapeType == "Edge" and safe.curve_type(sh) in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
        return App.Vector(sh.Curve.Center), App.Vector(sh.Curve.Axis).normalize()
    return None


def _turn_to(nm, nf, cos_wanted):
    """The smallest turn of direction nm that leaves it at the wanted angle to nf (either way round)."""
    a = math.degrees(nm.getAngle(nf))
    phi = math.degrees(math.acos(max(-1.0, min(1.0, cos_wanted))))
    target = phi if abs(a - phi) <= abs(a - (180 - phi)) else 180 - phi
    axis = nm.cross(nf)
    if axis.Length < 1e-9:
        axis = nm.cross(App.Vector(1, 0, 0))
        if axis.Length < 1e-6:
            axis = nm.cross(App.Vector(0, 1, 0))
    return App.Rotation(axis.normalize(), a - target)


def _pre_align_direction(doc, j, moving, fixed):
    """Parallel / Perpendicular / Angle: turn the free part about its pick (smallest turn) until the two axes are at
    the angle FreeCAD's joint asks; where it is stays free."""
    am, af = _axis(*moving), _axis(*fixed)
    if am is None or af is None:
        return
    (pm, nm), (_, nf) = am, af
    turn = _turn_to(nm, nf, _wanted(j))
    if abs(turn.Angle) < 1e-12:
        return
    link = moving[0]
    link.Placement = App.Placement(pm, App.Rotation()).multiply(App.Placement(App.Vector(), turn)) \
        .multiply(App.Placement(-pm, App.Rotation())).multiply(link.Placement)
    doc.recompute()


def _pre_align(doc, spec, values, j=None):
    """Put the free part near the answer first: from a start far off (faces at a large angle) FreeCAD's solver
    diverges and the constraint 'can't be met'. Only the part that is not grounded moves: its picked face turns to
    the other one (towards it for Mate, the same way for Flush; a circle's axis onto the other's) and its centre
    goes onto the other's; the solver does the rest."""
    from incad.core import assembly
    (l1, e1), (l2, e2) = _moving_refs(doc, values)
    if assembly.is_grounded(l1) and assembly.is_grounded(l2):
        return
    # the grounded side stays; with nothing grounded _solve holds the first part still: the second one moves
    first_moves = assembly.is_grounded(l2) and not assembly.is_grounded(l1)
    moving, fixed = ((l1, e1), (l2, e2)) if first_moves else ((l2, e2), (l1, e1))
    if spec.joint in _DIRECTIONS:
        return _pre_align_direction(doc, j, moving, fixed)
    fm, ff = _frame(*moving), _frame(*fixed)
    if fm is None or ff is None:
        return
    (pm, nm), (pf, nf) = fm, ff
    facing = _facing(spec, values)
    if facing == "opposed":
        want = -nf
    elif facing == "aligned":
        want = nf
    elif spec.joint == "Revolute":  # Insert: axes in line, whichever way is nearer
        want = nf if nm.dot(nf) >= 0 else -nf
    else:
        return
    turn = App.Rotation(nm, want)
    link = moving[0]
    link.Placement = App.Placement(pf, App.Rotation()).multiply(App.Placement(App.Vector(), turn)) \
        .multiply(App.Placement(-pm, App.Rotation())).multiply(link.Placement)
    doc.recompute()


def _apply(doc, j, spec, values):
    import JointObject
    (l1, e1), (l2, e2) = _moving_refs(doc, values)
    _set_type(j, _joint_type(doc, spec, values))
    flip = bool(values.get("flip"))
    if spec.flip == "tangent":
        _bind_distance(doc, j, spec, values.get("offset") or "0 mm", _inside(doc, values) if flip else None)
    elif spec.value == "offset":
        value_param(doc, j, "Distance", values.get("offset") or "0 mm", "length", base=spec.TITLE)
    elif spec.value == "angle":
        global _APPLYING
        _APPLYING += 1
        try:
            _bind_angle(doc, j, spec, values.get("angle") or "90 °", _mixed(doc, values))
        finally:
            _APPLYING -= 1
        doc.recompute()  # the joint's Angle follows its formula before the pre-align and the type read it
        _set_type(j, _joint_type(doc, spec, values, j))
    _pre_align(doc, spec, values, j)
    held = _placements(doc)
    j.Proxy.setJointConnectors(j, [[l1, [e1, e1]], [l2, [e2, e2]]])
    for name, plc in held.items():  # FreeCAD's own pre-solve (Revolute: Insert) can move the grounded part
        o = doc.getObject(name)
        if not o.Placement.isSame(plc, 1e-12):
            o.Placement = plc
    if spec.flip == "tangent":
        _tangent_side(j, flip)
    doc.recompute()
    result = _solve(doc, l1)
    facing = _facing(spec, values)
    if facing is not None:
        n1, n2 = _normal(l1, e1), _normal(l2, e2)
        if n1 is not None and n2 is not None and (n1.dot(n2) < 0) != (facing == "opposed"):
            j.Proxy.flipOnePart(j)
            result = _solve(doc, l1)
    if spec.flip == "tangent" and _tangent_side(j, flip):  # the solve swapped the references
        result = _solve(doc, l1)
    if spec.flip == "turn" and flip != _flipped(j) and result == 0:
        if _turn_over(doc, j, values):
            result = _solve(doc, l1)
    if spec.flip is not None:
        _store_flip(j, flip)
    return result


def _round(link, el):
    """A round face's radius, None for anything else."""
    try:
        sh = link.Shape.getElement(el)
        return sh.Surface.Radius if sh.ShapeType == "Face" and sh.Surface.TypeId == "Part::GeomCylinder" else None
    except Exception:
        return None


def _inside(doc, values):
    """Tangent on two round faces, flipped: the smaller one touches the other inside. FreeCAD's Distance there is
    the gap outside (axes r1 + r2 + d apart), so inside (axes r1 - r2 - d apart) is a Distance of -(d + 2 r2);
    None for a round face on a flat one (flipped by its frame instead)."""
    radii = [_round(link, el) for link, el in _moving_refs(doc, values)]
    return 2 * min(radii) if None not in radii else None


def _distance_param(j):
    """The model parameter holding a Distance as the user typed it: bound plainly, or as -(it + 2 r) (Tangent
    inside)."""
    from incad.core import model
    name = model.bound_parameter(j, "Distance")
    if name is not None:
        return name
    m = re.match(r"^-\(%s\.([A-Za-z_]\w*) \+ [-+0-9.e]+ mm\)$" % model.MODEL_NAME, model._expression(j, "Distance"))
    return m.group(1) if m else None


def _bind_distance(doc, j, spec, text, inside):
    """Bind the joint's Distance to the parameter holding `text` ('<Title>N' when there is none): plainly, or for a
    Tangent inside as -(it + inside)."""
    from incad.core import model
    name = _distance_param(j)
    if name is None:
        name = model.new_feature_parameter(doc, text, "length", spec.TITLE)
    elif model.parameter_text(doc, name) != text:
        model.set_model_parameter(doc, name, text)
    expr = "%s.%s" % (model.MODEL_NAME, name)
    if inside is not None:
        expr = "-(%s + %s mm)" % (expr, ("%.12g" % inside))
    if model._expression(j, "Distance") != expr:
        j.setExpression("Distance", expr)
    return name


def _tangent_side(j, flip):
    """A round face on a flat one sits outside the flat face's part (the side its outward normal points to), Flip
    inside. FreeCAD keeps the round face on the side the flat face's joint frame Z points to, and that frame follows
    the face's surface, not its outward normal (reversed on some faces: Train_1's hex), so the frame is turned over
    (its Offset) where the two disagree. FreeCAD's solve may swap the references (not the Offsets): the flat one is
    found each time. True when an Offset changed."""
    import UtilsAssembly
    changed = False
    for i in (1, 2):
        ref = getattr(j, "Reference%d" % i, None)
        prop = "Offset%d" % i
        want = False
        try:
            sh = ref[0].Shape.getElement(ref[1][0])
            if sh.ShapeType == "Face" and sh.Surface.TypeId == "Part::GeomPlane":
                z = UtilsAssembly.getJcsGlobalPlc(UtilsAssembly.findPlacement(ref, True), ref) \
                    .Rotation.multVec(App.Vector(0, 0, 1))  # FreeCAD's own frame, without any offset
                want = (z.dot(_normal(ref[0], ref[1][0])) < 0) != bool(flip)
        except Exception:
            pass
        now = getattr(j, prop)
        turned = now.Rotation.isSame(_OVER, 1e-9) and now.Base.Length < 1e-12
        if want != turned:
            setattr(j, prop, App.Placement(App.Vector(), _OVER) if want else App.Placement())
            changed = True
    return changed


def _turn_over(doc, j, values):
    """Insert / Rotational / Slider / Cylindrical: turn the free part 180 deg about the X axis of its joint frame
    (the axis the other way, the frame's origin and X kept); the solver keeps either way. False when nothing can
    move (both parts grounded)."""
    import UtilsAssembly
    from incad.core import assembly
    (l1, _), (l2, _) = _moving_refs(doc, values)
    if assembly.is_grounded(l1) and assembly.is_grounded(l2):
        return False
    link = l1 if assembly.is_grounded(l2) and not assembly.is_grounded(l1) else l2
    i = 1 if getattr(j, "Reference1")[0] is link else 2
    jcs = UtilsAssembly.getJcsGlobalPlc(getattr(j, "Placement%d" % i), getattr(j, "Reference%d" % i))
    axis, c = jcs.Rotation.multVec(App.Vector(1, 0, 0)), jcs.Base
    link.Placement = App.Placement(c, App.Rotation(axis, 180)).multiply(App.Placement(-c, App.Rotation())) \
        .multiply(link.Placement)
    doc.recompute()
    return True


def _turn_around(doc, j, spec, values):
    """FreeCAD's pre-solve picks the nearest orientation; from an awkward start that can end with the faces
    across each other. Turn the moving component 180° about an axis lying in its picked face, then solve again."""
    from incad.core import assembly
    (l1, e1), (l2, e2) = _moving_refs(doc, values)
    link, el = (l1, e1) if assembly.is_grounded(l2) else (l2, e2)
    face = link.Shape.getElement(el)
    n = _normal(link, el)
    if n is None:
        return 1
    axis = n.cross(App.Vector(1, 0, 0))
    if axis.Length < 1e-6:
        axis = n.cross(App.Vector(0, 1, 0))
    axis.normalize()
    c = face.CenterOfMass
    turn = App.Placement(c, App.Rotation(axis, 180)) * App.Placement(-c, App.Rotation())
    link.Placement = turn * link.Placement
    doc.recompute()
    return _apply(doc, j, spec, values)


def _settle(doc, j, spec, values):
    """Solve; while the result doesn't meet the constraint, flip the moving part's side (FreeCAD's pre-solve
    picks the nearest orientation, which from an awkward start can take two flips), then turn it around."""
    (l1, _), _ = _moving_refs(doc, values)
    result = _apply(doc, j, spec, values)
    for _ in range(3):
        if result != 0 or _met(doc, j, spec, values):
            return result
        j.Proxy.flipOnePart(j)
        result = _solve(doc, l1)
    if result == 0 and not _met(doc, j, spec, values):
        result = _turn_around(doc, j, spec, values)
    return result


def _placements(doc):
    from incad.core import assembly
    return {c.Name: App.Placement(c.Placement) for c in assembly.components(doc)}


def _met(doc, j, spec, values):
    """Did the solver satisfy the constraint? (checks the planar distance for Mate/Flush, the angle between the two
    axes for Parallel / Perpendicular / Angle: FreeCAD drops one of two conflicting joints without a word)."""
    if spec.joint in _DIRECTIONS:
        (l1, e1), (l2, e2) = _moving_refs(doc, values)
        a1, a2 = _axis(l1, e1), _axis(l2, e2)
        if a1 is None or a2 is None:  # an older Angle on a curved face: FreeCAD's own axis, not checked here
            return True
        return abs(abs(a1[1].dot(a2[1])) - _wanted(j)) < 1e-6
    if spec.key in ("mate", "flush") and _both_round(doc, values):  # two axes: in line
        (l1, e1), (l2, e2) = _moving_refs(doc, values)
        (p1, d1), (p2, d2) = _axis(l1, e1), _axis(l2, e2)
        off = (p2 - p1) - d1 * (p2 - p1).dot(d1)
        return abs(abs(d1.dot(d2)) - 1) < 1e-6 and off.Length < 1e-4
    facing = _facing(spec, values)
    if spec.value != "offset" or facing is None:
        return True
    (l1, e1), (l2, e2) = _moving_refs(doc, values)
    f1, f2 = l1.Shape.getElement(e1), l2.Shape.getElement(e2)
    n1 = _normal(l1, e1)
    if n1 is None:
        return True
    gap = abs((f2.CenterOfMass - f1.CenterOfMass).dot(n1))
    want = abs(j.Distance.Value)
    n2 = _normal(l2, e2)
    if n2 is None:
        return abs(gap - want) < 1e-3
    faces = (n1.dot(n2) < 0) == (facing == "opposed")
    return abs(gap - want) < 1e-3 and abs(abs(n1.dot(n2)) - 1) < 1e-6 and faces


def kind_of(j):
    """The InCad constraint kind of a joint, None for anything else (a grounding, say)."""
    return next((k for k in KINDS if k.claims(j)), None) if j is not None else None


def _unmet(doc, but=None):
    """Names of the active constraints the parts don't meet now (`but` left out)."""
    from incad.core import assembly
    out = set()
    for o in assembly.joints(doc):
        spec = kind_of(o)
        if o is but or spec is None or getattr(o, "Suppressed", False):
            continue
        try:
            if not _met(doc, o, spec, spec.read(doc, o)):
                out.add(o.Name)
        except Exception:  # unreadable (a pick that is gone, a face index past the end): not this constraint's doing
            pass
    return out


_APPLYING = 0  # an Angle being bound by _apply: follow_parameters leaves it to _apply


def follow_parameters(doc):
    """After a parameter change (model.set_model_parameter): an Angle on a face and an edge switches between
    FreeCAD's Parallel (at 90 deg) and Angle, then solves; refused (ValueError) when it can't be met."""
    from incad.core import assembly
    if _APPLYING or not assembly.is_assembly(doc):
        return
    for j in assembly.joints(doc):
        if kind_of(j) is not ANGLE or getattr(j, "Suppressed", False):
            continue
        try:
            values = ANGLE.read(doc, j)
            want = _joint_type(doc, ANGLE, values, j)
        except Exception:
            continue
        if want == j.JointType:
            continue
        unmet = _unmet(doc, j)
        result = _settle(doc, j, ANGLE, values)
        if result != 0 or not _met(doc, j, ANGLE, values) or _unmet(doc, j) - unmet:
            raise ValueError("%s conflicts with the other constraints (it can't be met)" % j.Label)


def toggle_suppressed(j):
    """Suppress (Inventor) a constraint: the solver ignores it, the parts stay where they are; again to bring it back,
    solved to meet it — refused (it stays suppressed, the parts back) when it can't be met any more. Returns True when
    it is suppressed now."""
    from incad.core import assembly
    spec = kind_of(j)
    if spec is None or "Suppressed" not in j.PropertiesList:
        raise ValueError("%s can't be suppressed" % getattr(j, "Label", j))
    doc = j.Document
    if not j.Suppressed:
        j.Suppressed = True
        doc.recompute()
        return True
    refs = [(getattr(j, p, None) or (None,))[0] for p in ("Reference1", "Reference2")]
    off = [c for c in assembly.components(doc) if c in refs and assembly.is_suppressed(c)]
    if off:
        raise ValueError("%s is suppressed: unsuppress the part first" % off[0].Label)
    before = _placements(doc)
    unmet = _unmet(doc, j)
    j.Suppressed = False
    values = spec.read(doc, j)
    try:
        result = _settle(doc, j, spec, values)
        met = result == 0 and _met(doc, j, spec, values) and not _unmet(doc, j) - unmet
    except ValueError:  # a pick that is gone (its part deleted): the same refusal
        met = False
    if not met:
        j.Suppressed = True
        for name, plc in before.items():
            doc.getObject(name).Placement = plc
        _solve(doc)
        raise ValueError("%s can't be met any more: it stays suppressed" % j.Label)
    doc.recompute()
    return False


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
        unmet = _unmet(doc)
        j = assembly.joint_group(doc).newObject("App::FeaturePython", spec.joint_name)
        JointObject.Joint(j, JointObject.JointTypes.index(spec.joint))
        if App.GuiUp:
            JointObject.ViewProviderJoint(j.ViewObject)
        j.addProperty("App::PropertyString", _STORE, "InCad", "InCad constraint kind")
        j.setPropertyStatus(_STORE, "Hidden")
        setattr(j, _STORE, spec.key)
        if spec.flip is not None:
            _add_flip(j)
        j.Label = spec.TITLE
        try:
            result = _settle(doc, j, spec, values)
            # FreeCAD drops one of two conflicting joints without a word: another one no longer met is a conflict too
            if result != 0 or not _met(doc, j, spec, values) or _unmet(doc, j) - unmet:
                raise ValueError("%s conflicts with the other constraints (it can't be met)" % spec.TITLE)
        except Exception:
            doc.removeObject(j.Name)
            for name, plc in before.items():
                doc.getObject(name).Placement = plc
            _solve(doc)
            raise
        return j

    def read(doc, j):
        from incad.core import model
        values = defaults(doc, None)
        refs = []
        for prop in ("Reference1", "Reference2"):
            ref = getattr(j, prop, None)
            refs.append("%s:%s" % (ref[0].Name, ref[1][0]) if ref and ref[0] is not None and ref[1] else "")
        values.update(first=refs[0], second=refs[1])
        if spec.value == "offset":
            name = _distance_param(j)
            values["offset"] = (model.parameter_text(doc, name) if name else "") or "0 mm"
        elif spec.value == "angle":
            name = _angle_param(j)
            values["angle"] = (model.parameter_text(doc, name) if name else "") or "90°"
        if spec.flip is not None:
            values["flip"] = _flipped(j)
        return values

    def update(doc, j, values):
        before = _placements(doc)
        unmet = _unmet(doc, j)
        was = dict(read(doc, j)) if spec.flip is not None else None
        result = _settle(doc, j, spec, values)
        if result != 0 or not _met(doc, j, spec, values) or _unmet(doc, j) - unmet:
            if was is not None and bool(values.get("flip")) != was["flip"]:  # the flip goes back with the parts
                _store_flip(j, was["flip"])
                if spec.flip == "tangent":
                    _tangent_side(j, was["flip"])
                    _bind_distance(doc, j, spec, was["offset"], _inside(doc, was) if was["flip"] else None)
            for name, plc in before.items():
                doc.getObject(name).Placement = plc
            raise ValueError("%s conflicts with the other constraints (it can't be met)" % spec.TITLE)
        return j

    def param_names(j):  # an Angle on a face and an edge is bound as 90 deg - its parameter, a Tangent inside as
        if spec.value == "angle":  # -(it + 2 r): still its parameter
            return {"angle": _angle_param(j)}
        return {"offset": _distance_param(j)} if spec.value == "offset" else {}

    spec.defaults, spec.create, spec.read, spec.update = defaults, create, read, update
    spec.param_names = param_names
    spec.claims = lambda j: getattr(j, _STORE, None) == spec.key
    spec._pad_of = lambda j: j
    return spec


def _kind(key, title, icon, joint, pick1, pick2, value=None, facing=None, flip=None):
    fields = [Field("first", "First", "pick", pick=pick1), Field("second", "Second", "pick", pick=pick2)]
    props = {}
    if value == "offset":
        fields.append(Field("offset", "Offset", "value_length", default="0 mm"))
        props = {"offset": "Distance"}
    elif value == "angle":
        fields.append(Field("angle", "Angle", "value_angle", default="90 °"))
        props = {"angle": "Angle"}
    if flip is not None:
        fields.append(Field("flip", "Flip", "bool", default=False))
    return _make(SimpleNamespace(
        __name__="incad.features." + key, key=key, TITLE=title, ICON=icon, TYPES=("App::FeaturePython",),
        NEEDS_PROFILE=False, ASSEMBLY=True, PROPS=props, FIELDS=tuple(fields), joint=joint,
        joint_name=title.replace(" ", ""), value=value, facing=facing, flip=flip))


MATE = _kind("mate", "Mate", "mate", "Distance", "face", "face", "offset", "opposed", flip="facing")
FLUSH = _kind("flush", "Flush", "flush", "Distance", "face", "face", "offset", "aligned", flip="facing")
ANGLE = _kind("angle_c", "Angle", "angle_c", "Angle", "direction", "direction", "angle")
PARALLEL = _kind("parallel", "Parallel", "parallel_c", "Parallel", "direction", "direction")
PERPENDICULAR = _kind("perpendicular", "Perpendicular", "perpendicular_c", "Perpendicular", "direction", "direction")
TANGENT = _kind("tangent", "Tangent", "tangent", "Distance", "face", "face", "offset", flip="tangent")
INSERT = _kind("insert", "Insert", "insert", "Revolute", "circular_edge", "circular_edge", flip="turn")
RIGID = _kind("rigid", "Rigid", "rigid", "Fixed", "element", "element")
ROTATIONAL = _kind("rotational", "Rotational", "rotational", "Revolute", "element", "element", flip="turn")
SLIDER = _kind("slider", "Slider", "slider", "Slider", "element", "element", flip="turn")
CYLINDRICAL = _kind("cylindrical", "Cylindrical", "cylindrical", "Cylindrical", "element", "element", flip="turn")
BALL = _kind("ball", "Ball", "ball", "Ball", "element", "element")

KINDS = [MATE, FLUSH, ANGLE, PARALLEL, PERPENDICULAR, TANGENT, INSERT, RIGID, ROTATIONAL, SLIDER, CYLINDRICAL, BALL]
