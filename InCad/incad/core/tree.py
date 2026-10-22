"""Builds the Model Browser tree from a document (Inventor-style: one history for the part with every Solid's
features in the order made, sketches under the feature that uses them, one End of Part marker)."""
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


def _history(doc, primary):
    """The part's feature rows: every Solid's features in the one list, in the order made (Inventor's one
    history), rows of other Solids than the main one naming theirs; one End of Part, after the latest Tip."""
    from incad.core import regions
    hist = document.history(doc)
    objs = [o for _, o in hist]
    groups = {b.Name: list(b.Group) for b in document.bodies(doc)}
    tips = {name: (group.index(b.Tip) if b.Tip in group else -1)
            for name, group, b in ((b.Name, groups[b.Name], b) for b in document.bodies(doc))}
    consumed = {p.Name for p in (_profile(o) for o in objs) if p is not None}
    for o in objs:
        if regions.is_profile(o) and o.Name in consumed:  # an orphan profile (its feature gone) hides nothing
            src = regions.source_of(o)
            if src is not None:
                consumed.add(src.Name)
    helpers = {}  # owner name -> objects InCad made for it (a thread's chamfer): shown under the owner
    for o in objs:
        owner = getattr(o, "InCadHelperOf", None)
        if owner:
            helpers.setdefault(owner, []).append(o)
    from incad.features import combine
    used = combine.used_up_names(doc)  # tools a Boolean used up: under it
    tip_positions = [i for i, (b, o) in enumerate(hist) if b.Tip is not None and o is b.Tip and b.Name not in used]
    latest = hist[max(tip_positions)][1] if tip_positions else None  # the marker goes right after it
    marked = document.end_marker(doc)  # End of Part put before sketches / Texts / work features: right there
    if marked is not None:
        latest = marked[0]
    out = []
    if latest is None:
        out.append(Node("end_of_part", "End of Part"))

    def rolled(b, o):
        return groups[b.Name].index(o) > tips[b.Name]

    def row(b, obj):
        """The row of obj with its sketch and helpers under it, and those objects; None for a row not shown."""
        if (obj.TypeId == "Sketcher::SketchObject" or getattr(obj, "InCadText", None) is not None) \
                and obj.Name in consumed:  # a used sketch or Text shows under its feature
            return None, []
        if getattr(obj, "InCadHelperOf", None) or regions.is_profile(obj):
            return None, []
        node = _obj_node(obj, rolled(b, obj))
        if b is not primary and b.Name not in used:
            node.detail = (node.detail + "  ·  " + b.Label) if node.detail else b.Label
        under = []
        prof = _profile(obj)
        if prof is not None and regions.is_profile(prof):
            under.append(prof)
            prof = regions.source_of(prof)  # the user's sketch, not the area copy
        if prof is not None and prof in groups[b.Name]:
            node.children.append(_obj_node(prof, rolled(b, prof)))
            under.append(prof)
        for h in helpers.get(obj.Name, []):
            node.children.append(_obj_node(h, rolled(b, h)))
            under.append(h)
        return node, under

    tool_rows = {}  # a used-up tool's rows, built first: they may come later in the history than its Boolean
    for b, obj in hist:
        if b.Name in used:
            node, _ = row(b, obj)
            if node is not None:
                tool_rows.setdefault(b.Name, []).append((obj, node))

    def tools_under(node, obj, seen):
        """A Boolean's used-up tools under its row, theirs under theirs (a pin cut into a plug cut into the part)."""
        if not combine.claims(obj):
            return
        for t in combine.used_up_tools(obj):
            if t.Name in seen:
                continue
            child = Node("body", t.Label, t.Name)
            for sub_obj, sub_node in tool_rows.get(t.Name, []):
                tools_under(sub_node, sub_obj, seen | {t.Name})
                child.children.append(sub_node)
            node.children.append(child)

    for b, obj in hist:
        if b.Name in used:
            continue
        node, under = row(b, obj)
        if node is None:
            continue
        tools_under(node, obj, frozenset())
        out.append(node)
        if latest is not None and (obj is latest or latest in under):
            out.append(Node("end_of_part", "End of Part"))
    return _work_in_progress_above_end(out, doc, set(marked[1]) if marked is not None else None)


def _work_in_progress_above_end(nodes, doc=None, rolled=None):
    """What follows End of Part and is no solid feature — sketches, work planes / axes / points, Text — is work in
    progress: Inventor shows it above the marker (FreeCAD never makes any of them the Tip). Only the solid features
    after it are rolled back. (A work plane between them stopped this, leaving a sketch and a Text below.)
    rolled: the names End of Part was put above on purpose (document.end_marker): they stay below it, rolled back;
    only work made since goes above it."""
    marker = next((i for i, n in enumerate(nodes) if n.kind == "end_of_part"), None)
    if marker is None:
        return nodes
    if rolled is not None:
        for n in nodes[:marker]:  # above it: applied (a sketch after the Tip still counts as rolled back by it)
            if n.state == "rolled_back":
                n.state = ""
        above, below = [], []
        for n in nodes[marker + 1:]:
            if n.name in rolled or n.kind not in ("sketch", "feature"):
                if n.name in rolled and n.state in ("", "hidden"):
                    n.state = "rolled_back"
                below.append(n)
            elif n.kind == "sketch" or (doc is not None and n.name and doc.getObject(n.name) is not None
                                        and not doc.getObject(n.name).isDerivedFrom("PartDesign::Feature")):
                if n.state == "rolled_back":
                    n.state = ""
                above.append(n)  # made since End of Part went up: work in progress, above it
            else:
                below.append(n)
        return nodes[:marker] + above + [nodes[marker]] + below

    def in_progress(n):
        if n.kind == "sketch":
            return True
        obj = doc.getObject(n.name) if doc is not None and n.kind == "feature" and n.name else None
        return obj is not None and not obj.isDerivedFrom("PartDesign::Feature")

    j = marker + 1
    while j < len(nodes) and in_progress(nodes[j]) and nodes[j].state in ("", "rolled_back", "hidden"):
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


def _component_rows(link):
    """The component's part history under its row (Inventor): its sketches and features as in the part, each row
    standing for the component itself (a click selects it, a double-click opens the part file)."""
    target = link.LinkedObject
    part = target.Document if target is not None else None
    primary = document.primary_body(part) if part is not None and document.is_incad_part(part) else None
    if primary is None:
        return []

    def recast(n):
        if n.kind == "end_of_part":
            return None
        kids = [k for k in (recast(c) for c in n.children) if k is not None]
        return Node(n.kind, n.label, link.Name, n.state, n.tooltip, n.detail, kids)

    return [r for r in (recast(n) for n in _history(part, primary)) if r is not None]


def _assembly(doc):
    from incad.core import assembly
    from incad.features import constraints
    root = Node("assembly", doc.Label, detail="⚡ Needs update" if assembly.needs_update(doc) else "",
                tooltip="Parts changed: Refresh updates the assembly" if assembly.needs_update(doc) else "")
    from incad.core import dof
    counts = dof.last(doc) or {}
    for c in assembly.components(doc):
        f = counts.get(c.Name)
        detail = "grounded" if assembly.is_grounded(c) else "" if assembly.is_suppressed(c) or f is None else \
            "DOF ?" if f.n is None else "DOF %d" % f.n
        tip = f.error if f is not None and f.n is None else (c.LinkedObject.Document.FileName if c.LinkedObject else "")
        root.children.append(Node("component", c.Label, c.Name,
                                  state="suppressed" if assembly.is_suppressed(c) else
                                  ("" if document.is_shown(c) else "hidden"),
                                  detail=detail, tooltip=tip, children=_component_rows(c)))
    from incad.core import asm_cut
    rel = [j for j in assembly.joints(doc) if constraints.claims(j)] + asm_cut.records(doc)
    root.children.append(Node("relationships", "Relationships (%d)" % len(rel),
                              children=[Node("joint", j.Label, j.Name,
                                             state="suppressed" if getattr(j, "Suppressed", False) else "")
                                        for j in rel]))
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
    from incad.features import combine
    used = combine.used_up_names(doc)
    listed = [b for b in all_bodies if b.Name not in used]  # a used-up tool sits under its Boolean
    if len(listed) > 1:
        root.children.append(Node("solids", "Solid Bodies (%d)" % len(listed),
                                  children=[Node("body", b.Label, b.Name, "" if document.is_shown(b) else "hidden",
                                                 "" if document.is_shown(b) else "Hidden (Hide / Show brings it back)")
                                            for b in listed]))
    if primary is not None:
        root.children.extend(_history(doc, primary))
    return [root]
