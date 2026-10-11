"""The constraints of a sketch as the Constraints window lists them: what each one is, what it ties (in the
user's words), its value; filtered by picked lines and points; refused or deleted. Pure model logic: no Qt."""
import dataclasses
import math

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
