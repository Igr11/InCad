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
    if kind == "sketch" and state in ("", "rolled_back") and not obj.Visibility \
            and (document.SHOWN_PROP in obj.PropertiesList or document.is_unused_sketch(obj)):
        node.state = "hidden"  # hidden by the user's choice (a feature's sketch is hidden by design otherwise)
    if kind == "feature" and obj.TypeId in document.DATUM_TYPES and state in ("", "rolled_back") and not obj.Visibility:
        node.state = "hidden"  # a work plane, axis or point the user hid
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
    from incad.core import regions
    consumed = {p.Name for p in (_profile(o) for o in group) if p is not None}
    for o in group:
        if regions.is_profile(o):
            src = regions.source_of(o)
            if src is not None:
                consumed.add(src.Name)
    helpers = {}  # owner name -> objects InCad made for it (a thread's chamfer): shown under the owner
    for o in group:
        owner = getattr(o, "InCadHelperOf", None)
        if owner:
            helpers.setdefault(owner, []).append(o)
    tip_owner = getattr(tip, "InCadHelperOf", None) if tip is not None else None
    out = []
    if tip_index == -1:
        out.append(Node("end_of_part", "End of Part"))
    for i, obj in enumerate(group):
        if obj.TypeId == "Sketcher::SketchObject" and obj.Name in consumed:
            continue
        if getattr(obj, "InCadHelperOf", None) or regions.is_profile(obj):
            continue
        node = _obj_node(obj, i > tip_index)
        prof = _profile(obj)
        if prof is not None and regions.is_profile(prof):
            prof = regions.source_of(prof)  # the user's sketch, not the area copy
        if prof is not None and prof in group:
            node.children.append(_obj_node(prof, group.index(prof) > tip_index))
        for h in helpers.get(obj.Name, []):
            node.children.append(_obj_node(h, group.index(h) > tip_index))
        out.append(node)
        if obj is tip or (prof is not None and prof is tip) or (tip_owner and obj.Name == tip_owner) or \
                (regions.is_profile(tip) if tip is not None else False) and _profile(obj) is tip:
            out.append(Node("end_of_part", "End of Part"))
    return _work_in_progress_above_end(out)


def _work_in_progress_above_end(nodes):
    """Sketches right after End of Part that no feature uses yet are work in progress: Inventor shows them above
    the marker (FreeCAD never makes a sketch the Tip)."""
    marker = next((i for i, n in enumerate(nodes) if n.kind == "end_of_part"), None)
    if marker is None:
        return nodes
    j = marker + 1
    while j < len(nodes) and nodes[j].kind == "sketch" and nodes[j].state in ("", "rolled_back", "hidden"):
        if nodes[j].state == "rolled_back":
            nodes[j].state = ""
        j += 1
    return nodes[:marker] + nodes[marker + 1:j] + [nodes[marker]] + nodes[j:]


def _origin(body):
    origin = body.Origin
    items = [Node("origin_item", ROLE_LABELS.get(getattr(f, "Role", ""), f.Label), f.Name,
                  "" if document.is_shown(f) else "hidden")
             for f in origin.OriginFeatures]
    return Node("origin", "Origin", origin.Name, children=items)


def _assembly(doc):
    from incad.core import assembly
    from incad.features import constraints
    root = Node("assembly", doc.Label)
    for c in assembly.components(doc):
        root.children.append(Node("component", c.Label, c.Name,
                                  detail="grounded" if assembly.is_grounded(c) else "",
                                  tooltip=(c.LinkedObject.Document.FileName if c.LinkedObject else "")))
    from incad.core import asm_cut
    rel = [j for j in assembly.joints(doc) if constraints.claims(j)] + asm_cut.records(doc)
    root.children.append(Node("relationships", "Relationships (%d)" % len(rel),
                              children=[Node("joint", j.Label, j.Name) for j in rel]))
    return [root]


def build(doc):
    if doc is None:
        return []
    from incad.core import assembly
    if assembly.is_assembly(doc):
        return _assembly(doc)
    if not document.is_incad_part(doc):
        out = [Node("message", "Not an InCad part", tooltip="This file was made outside InCad.")]
        if len(document.bodies(doc)) == 1:
            out.append(Node("action", "Convert to InCad Part", "convert"))
        out.append(Node("action", "Open in FreeCAD", "freecad"))
        return out
    primary = document.primary_body(doc)
    all_bodies = document.bodies(doc)
    root = Node("part", doc.Label, primary.Name if primary is not None else "")  # a click on it: the solid
    if primary is not None:
        root.children.append(_origin(primary))
    if len(all_bodies) > 1:
        root.children.append(Node("solids", "Solid Bodies (%d)" % len(all_bodies), children=[
            Node("body", b.Label, b.Name, children=[] if b is primary else _features(b)) for b in all_bodies]))
    if primary is not None:
        root.children.extend(_features(primary))
    return [root]
