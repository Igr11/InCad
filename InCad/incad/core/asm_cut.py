"""Combine between assembly parts: the cut is written into the base part's file.

Per tool, the base file gets a hidden link to the tool's solid ("proxy"), placed relative to the base as in the
assembly; a stage-3 Combine (Cut, with clearance helpers) in the base solid uses the proxies as tools. Positions
are re-synced by `sync` (a cross-document expression would make a dependency cycle). The assembly keeps a hidden
record object per cut."""
import json

import FreeCAD as App

from incad.core import document

_PROXY = "InCadAssemblyCut"
_RECORD = "InCadAsmCut"


def _load(obj, prop):
    try:
        return json.loads(getattr(obj, prop, "") or "{}")
    except ValueError:
        return {}


def _save(obj, prop, data, doc_text):
    if not hasattr(obj, prop):
        obj.addProperty("App::PropertyString", prop, "InCad", doc_text)
        obj.setPropertyStatus(prop, "Hidden")
    setattr(obj, prop, json.dumps(data, sort_keys=True))


def records(asm_doc):
    return [o for o in asm_doc.Objects if hasattr(o, _RECORD)]


def is_record(obj):
    return hasattr(obj, _RECORD)


def _relative(base_link, tool_link):
    """Placement of the tool's solid in the base solid's file coordinates."""
    # links replace their solid's own placement (LinkTransform off): a tool point p sits at TL·p in the
    # assembly, the base file shows base points at BB·p while the assembly shows them at BL·p
    base_body = base_link.LinkedObject
    return base_body.Placement * base_link.Placement.inverse() * tool_link.Placement


def _target(base_link):
    body = base_link.LinkedObject
    doc = body.Document if body is not None else None
    if doc is None or not document.is_incad_part(doc) or body.TypeId != "PartDesign::Body":
        raise ValueError("The base must be an InCad part (open it in InCad and convert it first)")
    return doc, body


def _proxy(target_doc, asm_doc, base_link, tool_link, name=None):
    p = target_doc.getObject(name) if name else None
    if p is None:
        p = target_doc.addObject("App::Link", "AsmTool")
        p.Visibility = False
    p.LinkedObject = tool_link.LinkedObject
    p.Label = "%s in %s" % (tool_link.Label, asm_doc.Label)
    p.Placement = _relative(base_link, tool_link)
    _save(p, _PROXY, {"assembly": asm_doc.FileName, "base": base_link.Name, "tool": tool_link.Name},
          "InCad assembly cut tool")
    return p


def documents(asm_doc, base_link):
    """Documents a cut changes besides the assembly (for one undo step in each)."""
    try:
        return [_target(base_link)[0]]
    except ValueError:
        return []


def create(asm_doc, base_link, tool_links, values):
    from incad.features import combine
    target_doc, body = _target(base_link)
    tools = [t for t in tool_links if t is not base_link]
    if not tools:
        raise ValueError("Pick at least one other component as a tool")
    proxies = [_proxy(target_doc, asm_doc, base_link, t) for t in tools]
    target_doc.recompute()
    try:
        f = combine.create(target_doc, body, None, {
            "base": body.Name, "tools": ",".join(p.Name for p in proxies), "operation": "cut",
            "clearance": values.get("clearance") or "0.2 mm", "apply_to": values.get("apply_to") or "cavity"})
    except Exception:
        for p in proxies:  # a refused cut leaves nothing in the part file
            if target_doc.getObject(p.Name) is not None:
                target_doc.removeObject(p.Name)
        raise
    target_doc.recompute()
    rec = asm_doc.addObject("App::FeaturePython", "AssemblyCut")
    rec.Label = "Cut %s" % base_link.Label
    _save(rec, _RECORD, {"target": target_doc.FileName, "boolean": f.Name, "base": base_link.Name,
                         "tools": [t.Name for t in tools], "proxies": {t.Name: p.Name for t, p in zip(tools, proxies)},
                         "clearance": values.get("clearance") or "0.2 mm",
                         "apply_to": values.get("apply_to") or "cavity"}, "InCad assembly cut")
    return rec


def _target_of(rec):
    """The base part's document: through the base component's link (survives a moved project folder), else the
    stored path; None when neither is available."""
    data = _load(rec, _RECORD)
    base = rec.Document.getObject(data.get("base", ""))
    linked = getattr(base, "LinkedObject", None) if base is not None else None
    if linked is not None:
        return data, linked.Document
    doc = next((d for d in App.listDocuments().values() if d.FileName == data.get("target")), None)
    if doc is None and data.get("target"):
        try:
            doc = App.openDocument(data["target"], hidden=True)
        except Exception:
            doc = None
    return data, doc


def read(rec):
    from incad.features import combine
    data, doc = _target_of(rec)
    f = doc.getObject(data.get("boolean", "")) if doc is not None else None
    values = combine.read(doc, f) if f is not None else {}
    return {"base": data.get("base", ""), "tools": ",".join(data.get("tools", [])),
            "clearance": values.get("clearance", data.get("clearance", "0.2 mm")),
            "apply_to": values.get("apply_to", data.get("apply_to", "cavity"))}


def update(rec, base_link, tool_links, values):
    from incad.features import combine
    asm_doc = rec.Document
    data, target_doc = _target_of(rec)
    f = target_doc.getObject(data["boolean"])
    if base_link.Name != data.get("base"):
        raise ValueError("To cut another base, delete this cut and make a new one")
    old = dict(data.get("proxies", {}))
    proxies, made = {}, []
    try:
        for t in tool_links:
            if t is not base_link:
                p = _proxy(target_doc, asm_doc, base_link, t, old.get(t.Name))
                proxies[t.Name] = p.Name
                if p.Name not in old.values():
                    made.append(p.Name)
        if not proxies:
            raise ValueError("Pick at least one other component as a tool")
        target_doc.recompute()
        combine.update(target_doc, f, {"tools": ",".join(proxies.values()), "operation": "cut",
                                       "clearance": values.get("clearance") or "0.2 mm",
                                       "apply_to": values.get("apply_to") or "cavity"})
    except Exception:
        for name in made:  # a refused tool leaves no proxy behind
            if target_doc.getObject(name) is not None:
                target_doc.removeObject(name)
        raise
    for tool, name in old.items():
        if tool not in proxies and target_doc.getObject(name) is not None:
            target_doc.removeObject(name)
    target_doc.recompute()
    data.update(tools=list(proxies), proxies=proxies, clearance=values.get("clearance") or "0.2 mm",
                apply_to=values.get("apply_to") or "cavity")
    _save(rec, _RECORD, data, "InCad assembly cut")
    return rec


def sync(asm_doc):
    """Re-place every proxy of this assembly's cuts; returns the part documents that changed."""
    changed = []
    for rec in records(asm_doc):
        data, target_doc = _target_of(rec)
        base = asm_doc.getObject(data.get("base", ""))
        if target_doc is None or base is None:
            continue
        moved = False
        for tool_name, proxy_name in data.get("proxies", {}).items():
            tool, proxy = asm_doc.getObject(tool_name), target_doc.getObject(proxy_name)
            if tool is None or proxy is None or tool.LinkedObject is None:
                continue  # a deleted tool leaves the pocket where it was
            want = _relative(base, tool)
            if not proxy.Placement.isSame(want, 1e-9):
                proxy.Placement = want
                moved = True
        if moved:
            target_doc.recompute()
            if target_doc not in changed:
                changed.append(target_doc)
    return changed


def remove(rec):
    """Delete the cut: the Boolean, its helpers and fit copies, the proxies and the record."""
    from incad.features import combine
    data, target_doc = _target_of(rec)
    f = target_doc.getObject(data.get("boolean", "")) if target_doc is not None else None
    if f is not None:
        combine.delete(target_doc, f)
    for name in data.get("proxies", {}).values():
        if target_doc is not None and target_doc.getObject(name) is not None:
            target_doc.removeObject(name)
    if target_doc is not None:
        target_doc.recompute()
    rec.Document.removeObject(rec.Name)
