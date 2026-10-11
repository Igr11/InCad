"""The constraints of a sketch as the Constraints window lists them: what each one is, what it ties (in the
user's words), its value; filtered by picked lines and points; refused or deleted. Pure model logic: no Qt."""
import dataclasses
import math
import re

from incad.core import sketch as sketches, sketch_patterns as sp

UNDEF = -2000  # Sketcher's GeoUndef
_TYPES = {"PointOnObject": "Point on Object", "Block": "Fix", "DistanceX": "Horizontal Distance",
          "DistanceY": "Vertical Distance", "InternalAlignment": "Internal"}
_KINDS = (("Part::GeomLineSegment", "Line"), ("Part::GeomArcOfCircle", "Arc"), ("Part::GeomCircle", "Circle"),
          ("Part::GeomArcOfEllipse", "Arc"), ("Part::GeomEllipse", "Ellipse"), ("Part::GeomBSplineCurve", "Spline"),
          ("Part::GeomPoint", "Point"))
_POS = {1: "start", 2: "end", 3: "centre"}


@dataclasses.dataclass
class Row:
    index: int
    name: str
    type: str
    ties: list
    text: str
    value: str
    owner: str


def element_name(sk, geo, pos=0):
    if geo == -1:
        return "Origin" if pos == 1 else "X axis"
    if geo == -2:
        return "Y axis"
    if geo <= -3:
        return "Projected edge %d" % (-geo - 2)
    g = sk.Geometry[geo]
    kind = next((k for t, k in _KINDS if g.TypeId == t), "Curve")
    name = "%s %d" % (kind, geo + 1)
    if pos in _POS and kind != "Point":
        name += " " + _POS[pos]
    if sk.getConstruction(geo):
        name += " (construction)"
    return name


def _ties(c):
    out = []
    for geo, pos in ((c.First, int(c.FirstPos)), (c.Second, int(c.SecondPos)), (c.Third, int(c.ThirdPos))):
        if geo != UNDEF:
            out.append((geo, pos))
    return out


def _value(sk, c):
    if c.Type not in sketches.DIMENSIONAL:
        return ""
    if c.Name:
        for path, expr in sk.ExpressionEngine or []:
            if path.lstrip(".") == "Constraints." + c.Name:
                from incad.core import model
                return model.to_display(sk.Document, expr)
    if c.Type == "Angle":
        return "%g°" % round(math.degrees(c.Value), 6)
    return "%g mm" % round(c.Value, 6)


def _owner(c):
    if sketches.is_pattern_name(c.Name):
        return "Pattern" + c.Name[len(sketches.PATTERN_PREFIX):].split("_")[0]
    return ""


def rows(sk):
    out = []
    for i, c in enumerate(sk.Constraints):
        ties = _ties(c)
        out.append(Row(i, c.Name or "", _TYPES.get(c.Type, c.Type), ties,
                       " ↔ ".join(element_name(sk, g, p) for g, p in ties), _value(sk, c), _owner(c)))
    return out


def for_elements(sk, subs):
    """Rows that touch any picked element: an edge matches its geometry at any point, a vertex only that point."""
    picks = []
    for sub in subs or ():
        try:
            picks.append(sp.element(sk, sub) + (sub.startswith(("Edge", "ExternalEdge", "H_Axis", "V_Axis")),))
        except (ValueError, IndexError):
            continue
    all_rows = rows(sk)
    if not picks:
        return all_rows
    def hit(r):
        return any(g == pg and (whole or p == pp) for g, p in r.ties for pg, pp, whole in picks)
    return [r for r in all_rows if hit(r)]


def _users(sk, name):
    """Who uses dimension `name` of this sketch in a formula: other dimensions of it by name, other objects by
    label (feature values in the Model Parameters by their own name)."""
    from incad.core import model
    own = "Constraints." + name
    here = re.compile(r"(?:(?<![\w.])|%s\.)\.?Constraints\.%s(?!\w)" % (re.escape(sk.Name), re.escape(name)))
    there = re.compile(r"(?<![\w.])%s\.Constraints\.%s(?!\w)" % (re.escape(sk.Name), re.escape(name)))
    model_obj = sk.Document.getObject(model.MODEL_NAME)
    out = []
    for obj in sk.Document.Objects:
        for path, expr in getattr(obj, "ExpressionEngine", []) or []:
            if obj is sk:
                if path.lstrip(".") != own and here.search(expr):
                    out.append(path.lstrip(".").split(".", 1)[-1])
            elif there.search(expr):
                out.append(path.lstrip(".") if obj is model_obj else obj.Label)
                if obj is not model_obj:
                    break
    return list(dict.fromkeys(out))


def refusal(sk, indices):
    """Why these constraints can't be deleted (the first reason found), or None."""
    cs = sk.Constraints
    for i in sorted(set(indices)):
        c = cs[i]
        owner = _owner(c)
        if owner:
            return "Part of %s: edit or delete the pattern" % owner
        if c.Name and c.Type in sketches.DIMENSIONAL:
            users = _users(sk, c.Name)
            if users:
                return "%s is used by %s: change %s first" % (c.Name, ", ".join(users),
                                                              "that" if len(users) == 1 else "those")
    return None


def delete(sk, indices):
    """Delete these constraints (highest index first, so the others keep theirs). Refused as a whole when any
    of them is a pattern tie or a dimension a formula uses."""
    why = refusal(sk, indices)
    if why:
        raise ValueError(why)
    done = 0
    for i in sorted(set(indices), reverse=True):
        sk.delConstraint(i)
        done += 1
    return done
