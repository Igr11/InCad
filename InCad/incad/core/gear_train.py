"""Gears turning together in an assembly (the user: after Make Assembly a gear should turn about its own axis, and the
one in mesh with it too). Make Assembly gives each gear a Rotational joint to "Gear Axes", a hidden grounded object
holding a copy of each gear's bore circle, and records the gears in mesh and their ratios on it. Turning a gear with
the gizmo's arc then turns the gears in mesh by their ratio (followers): FreeCAD's own Gears joint couples them only
inside FreeCAD's drag, never in a solve."""
import json

import FreeCAD as App

KEY = "InCadGearTrain"
LABEL = "Gear Axes"
V = App.Vector


def _vec(v):
    return [v.x, v.y, v.z]


def _bore_edge(link, origin, axis, radius):
    """The name of a circle of the gear's bore: its radius, its centre on the gear's axis."""
    if radius <= 1e-9:
        return None
    for i, e in enumerate(link.Shape.Edges):
        c = getattr(e, "Curve", None)
        if c is None or c.TypeId != "Part::GeomCircle" or abs(c.Radius - radius) > 1e-6:
            continue
        off = c.Center - origin
        if (off - axis * off.dot(axis)).Length < 1e-5 and abs(abs(V(c.Axis).normalize().dot(axis)) - 1) < 1e-6:
            return "Edge%d" % (i + 1)
    return None


def build(doc, links, where, pairs):
    """Gear Axes, a Rotational joint per gear (gears are not grounded: they turn), the train recorded. links: the
    components in the order of Make Assembly's pieces; where, pairs: gear.train_of. Returns the axes object or None."""
    import JointObject
    import Part
    from incad.core import assembly
    from incad.features import constraints
    found = {}
    for i, (origin, axis, radius) in sorted(where.items()):
        edge = _bore_edge(links[i], origin, axis, radius) if i < len(links) else None
        if edge is not None:  # a gear without a bore has no circle to turn on: it stays as it is
            found[i] = (edge, len(found))
    if not found:
        return None
    asm = assembly.assembly_of(doc)
    axes = asm.newObject("Part::Feature", "GearAxes")
    axes.Label = LABEL
    axes.Shape = Part.Compound([links[i].Shape.getElement(e).copy() for i, (e, _k) in sorted(found.items(),
                                                                                           key=lambda t: t[1][1])])
    axes.Visibility = False
    axes.addProperty("App::PropertyString", KEY, "InCad", "Gears in mesh: their axes and ratios")
    axes.setPropertyStatus(KEY, "Hidden")
    doc.recompute()
    assembly.ground(axes)
    for i, (edge, k) in sorted(found.items()):
        link = links[i]
        if assembly.is_grounded(link):
            assembly.unground(link)
        j = assembly.joint_group(doc).newObject("App::FeaturePython", "Rotational")
        JointObject.Joint(j, JointObject.JointTypes.index("Revolute"))
        if App.GuiUp:
            JointObject.ViewProviderJoint(j.ViewObject)
        j.addProperty("App::PropertyString", constraints._STORE, "InCad", "InCad constraint kind")
        j.setPropertyStatus(constraints._STORE, "Hidden")
        setattr(j, constraints._STORE, "rotational")
        j.Label = "Rotational"
        j.Proxy.setJointConnectors(j, [[axes, ["Edge%d" % (k + 1)] * 2], [link, [edge, edge]]])
    data = {"gears": {links[i].Name: {"point": _vec(where[i][0]), "axis": _vec(where[i][1])} for i in found},
            "pairs": [[links[a].Name, links[b].Name, r] for a, b, r in pairs if a in found and b in found]}
    setattr(axes, KEY, json.dumps(data))
    doc.recompute()
    return axes


def _train(doc):
    for o in doc.Objects:
        if KEY in getattr(o, "PropertiesList", ()):
            try:
                return json.loads(getattr(o, KEY) or "{}")
            except ValueError:
                return {}
    return {}


def axis_of(doc, name):
    """(point, direction) of a gear's axis in the assembly, or None for a part that is no gear of a train."""
    g = _train(doc).get("gears", {}).get(name)
    return (V(*g["point"]), V(*g["axis"]).normalize()) if g else None


def followers(doc, name):
    """[(name, point, axis, ratio)]: every gear turning with gear `name`, ratio its degrees per degree of `name`
    about the recorded axes (through gears in mesh with gears in mesh)."""
    t = _train(doc)
    links = {}
    for a, b, r in t.get("pairs", []):
        if r:
            links.setdefault(a, []).append((b, r))
            links.setdefault(b, []).append((a, 1.0 / r))
    ratio, todo = {name: 1.0}, [name]
    while todo:
        here = todo.pop()
        for other, r in links.get(here, []):
            if other not in ratio:
                ratio[other] = ratio[here] * r
                todo.append(other)
    out = []
    for other, r in ratio.items():
        ax = axis_of(doc, other) if other != name else None
        if ax is not None and doc.getObject(other) is not None:
            out.append((other, ax[0], ax[1], r))
    return out
