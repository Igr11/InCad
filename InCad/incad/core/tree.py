"""Builds the Model Browser tree from a document (Inventor-style: sketches under the feature that uses them,
an End of Part marker after the Tip)."""
from incad.core import document
from incad.core.nodes import Node

ROLE_LABELS = {"X_Axis": "X Axis", "Y_Axis": "Y Axis", "Z_Axis": "Z Axis", "XY_Plane": "XY Plane",
               "XZ_Plane": "XZ Plane", "YZ_Plane": "YZ Plane", "Origin": "Center Point"}


def _profile(feature):
    prof = getattr(feature, "Profile", None)
    if isinstance(prof, (tuple, list)):
        prof = prof[0] if prof else None
    return prof


def _state(obj, rolled_back):
    st = obj.State
    if "Invalid" in st or "Error" in st:
        return "error"
    if getattr(obj, "Suppressed", False):
        return "suppressed"
    return "rolled_back" if rolled_back else ""


def _tooltip(obj, state):
    if state != "error":
        return ""
    try:
        return obj.getStatusString()
    except Exception:
        return "Failed to compute"


def _obj_node(obj, rolled_back):
    state = _state(obj, rolled_back)
    kind = "sketch" if obj.TypeId == "Sketcher::SketchObject" else "feature"
    node = Node(kind, obj.Label, obj.Name, state, _tooltip(obj, state))
    if kind == "sketch":
        try:
            node.detail = "✓" if obj.FullyConstrained else "%d DOF" % obj.DoF
        except Exception:
            node.detail = ""
    return node


def _features(body):
    group = list(body.Group)
    tip = body.Tip
    tip_index = group.index(tip) if tip in group else -1
    consumed = {p.Name for p in (_profile(o) for o in group) if p is not None}
    out = []
    if tip_index == -1:
        out.append(Node("end_of_part", "End of Part"))
    for i, obj in enumerate(group):
        if obj.TypeId == "Sketcher::SketchObject" and obj.Name in consumed:
            continue
        node = _obj_node(obj, i > tip_index)
        prof = _profile(obj)
        if prof is not None and prof in group:
            node.children.append(_obj_node(prof, group.index(prof) > tip_index))
        out.append(node)
        if obj is tip or (prof is not None and prof is tip):
            out.append(Node("end_of_part", "End of Part"))
    return out


def _origin(body):
    origin = body.Origin
    items = [Node("origin_item", ROLE_LABELS.get(getattr(f, "Role", ""), f.Label), f.Name)
             for f in origin.OriginFeatures]
    return Node("origin", "Origin", origin.Name, children=items)


def build(doc):
    if doc is None:
        return []
    if not document.is_incad_part(doc):
        out = [Node("message", "Not an InCad part", tooltip="This file was made outside InCad.")]
        if len(document.bodies(doc)) == 1:
            out.append(Node("action", "Convert to InCad Part", "convert"))
        out.append(Node("action", "Open in FreeCAD", "freecad"))
        return out
    primary = document.primary_body(doc)
    all_bodies = document.bodies(doc)
    root = Node("part", doc.Label)
    if primary is not None:
        root.children.append(_origin(primary))
    if len(all_bodies) > 1:
        root.children.append(Node("solids", "Solid Bodies (%d)" % len(all_bodies), children=[
            Node("body", b.Label, b.Name, children=[] if b is primary else _features(b)) for b in all_bodies]))
    if primary is not None:
        root.children.extend(_features(primary))
    return [root]
