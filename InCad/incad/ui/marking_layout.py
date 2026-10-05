"""Which commands the right-click marking menu shows, per context. Slots N…NW sit around the cursor (flick
directions); 'list' is the short list below the ring. Later plans move sketch/feature commands into the slots."""
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

_GEOMETRY = {"N": "view.look_at", "S": "view.zoom_selection", "E": "view.style_shaded", "W": "view.style_wireframe",
             "NW": "edit.undo", "NE": "edit.redo", "SW": "view.zoom_all", "SE": "view.home", "list": []}

LAYOUT = {
    "part": {"N": "view.home", "NE": "edit.redo", "E": "view.style_shaded", "SE": "view.parameters",
             "S": "view.zoom_all", "SW": "view.theme_toggle", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": ["view.freecad"]},
    "face": dict(_GEOMETRY),
    "edge": dict(_GEOMETRY),
    "vertex": dict(_GEOMETRY),
    "empty": {"N": "file.new", "S": "file.open", "E": "view.theme_toggle", "W": "view.freecad", "list": []},
    "browser": {"N": "browser.edit", "S": "browser.move_end_of_part", "E": "browser.suppress",
                "W": "browser.rename", "list": []},
}


def resolve(context, registry, layout=None):
    """([(direction, Command)] in N…NW order, [Command] for the list); unknown command ids are skipped."""
    spec = (LAYOUT if layout is None else layout).get(context, {})
    slots = [(d, registry.get(spec[d])) for d in DIRECTIONS if spec.get(d) and registry.has(spec[d])]
    items = [registry.get(i) for i in spec.get("list", []) if registry.has(i)]
    return slots, items
