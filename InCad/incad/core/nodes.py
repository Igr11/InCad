"""Model Browser tree nodes: plain data built by incad.core.tree and drawn by incad.ui.browser."""
from dataclasses import dataclass, field


@dataclass
class Node:
    kind: str          # part | origin | origin_item | solids | body | feature | sketch | end_of_part | message | action
    label: str
    name: str = ""     # FreeCAD object name; for 'action' nodes the action id
    state: str = ""    # '' | 'error' | 'suppressed' | 'rolled_back'
    tooltip: str = ""
    children: list = field(default_factory=list)


def flatten(nodes, depth=0):
    """[(depth, node)] depth-first."""
    out = []
    for n in nodes:
        out.append((depth, n))
        out.extend(flatten(n.children, depth + 1))
    return out
