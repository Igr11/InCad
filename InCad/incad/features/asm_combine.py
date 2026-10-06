"""Combine in an assembly (Inventor): cut a component by others, written into the base part's file
(see incad.core.asm_cut). Cut only; clearance on the cavity, a fit copy, or split."""
from incad.core import asm_cut
from incad.features.common import Field, parse_picks

TITLE = "Combine"
ICON = "combine"
TYPES = ("App::FeaturePython",)
NEEDS_PROFILE = False
ASSEMBLY = True
PROPS = {}
RECREATE_ON = ("base",)  # another base means a cut in another part file

FIELDS = (
    Field("base", "Cut this", "pick", pick="component"),
    Field("tools", "With", "picks", pick="component"),
    Field("clearance", "Clearance", "value_length", default="0.2 mm"),
    Field("apply_to", "Clearance on", "choice", (("cavity", "Cavity"), ("tool", "Tool"), ("split", "Split")),
          "cavity"),
)


def claims(obj):
    return asm_cut.is_record(obj)


def defaults(doc, body=None, profile=None):
    from incad.core import prefs
    return {"base": "", "tools": "", "clearance": "%g mm" % prefs.thread_clearance(), "apply_to": "cavity"}


def preselect(pairs):
    links = []
    for obj, _ in pairs:
        if obj.TypeId == "App::Link" and obj not in links:
            links.append(obj)
    out = {"base": links[0].Name} if links else {}
    if len(links) > 1:
        out["tools"] = ",".join(l.Name for l in links[1:])
    return out


def _links(doc, text):
    out = []
    for obj, _ in parse_picks(doc, text):
        if obj.TypeId == "App::Link" and obj not in out:
            out.append(obj)
    return out


def _base(doc, values):
    links = _links(doc, values.get("base"))
    if not links:
        raise ValueError("Pick the component to cut")
    return links[0]


def documents(doc, values):
    try:
        return asm_cut.documents(doc, _base(doc, values))
    except ValueError:
        return []


def create(doc, body, profile, values):
    base = _base(doc, values)
    tools = [t for t in _links(doc, values.get("tools")) if t is not base]
    if not tools:
        raise ValueError("Pick the component(s) to cut with")
    return asm_cut.create(doc, base, tools, values)


def read(doc, rec):
    return asm_cut.read(rec)


def update(doc, rec, values):
    return asm_cut.update(rec, _base(doc, values), _links(doc, values.get("tools")), values)


def _pad_of(rec):
    return rec
