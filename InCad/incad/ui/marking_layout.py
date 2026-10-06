"""Which commands the right-click marking menu shows, per context. Slots N…NW sit around the cursor (flick
directions); 'list' is the short list below the ring. Later plans move sketch/feature commands into the slots."""
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

_EDGE = {"N": "view.look_at", "S": "view.zoom_selection", "E": "view.style_shaded", "W": "view.style_wireframe",
         "NW": "edit.undo", "NE": "edit.redo", "SW": "view.zoom_all", "SE": "view.home", "list": []}

LAYOUT = {
    "part": {"N": "sketch.start", "NE": "edit.redo", "E": "view.style_shaded", "SE": "view.parameters",
             "S": "feature.extrude", "SW": "view.theme_toggle", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": ["view.zoom_all", "view.home", "view.freecad"]},
    "face": {"N": "sketch.start", "NE": "view.look_at", "E": "view.style_shaded", "SE": "view.home",
             "S": "feature.extrude", "SW": "view.zoom_all", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": ["view.zoom_selection", "feature.hole", "feature.fillet", "feature.thread"]},
    "edge": dict(_EDGE, E="feature.fillet", W="feature.chamfer", list=["view.style_shaded", "view.style_wireframe"]),
    "vertex": dict(_EDGE),
    "sketch": {"N": "sketch.finish", "NE": "sketch.line", "E": "sketch.circle", "SE": "sketch.rectangle",
               "S": "sketch.dimension", "SW": "sketch.arc", "W": "edit.undo", "NW": "sketch.trim",
               "list": ["sketch.constraints_toggle", "view.look_at", "sketch.construction", "sketch.project",
                        "sketch.stop"]},
    "assembly": {"N": "assembly.place", "S": "constrain.mate", "E": "joint.rigid", "W": "assembly.create",
                 "NE": "view.zoom_all", "NW": "edit.undo", "SE": "view.home", "SW": "assembly.ground",
                 "list": ["constrain.flush", "constrain.insert", "view.freecad"]},
    "asm_face": {"N": "constrain.mate", "S": "constrain.flush", "E": "constrain.angle", "W": "constrain.tangent",
                 "NE": "view.look_at", "SW": "assembly.ground", "list": ["joint.rigid", "view.zoom_selection"]},
    "asm_edge": {"N": "constrain.insert", "S": "joint.rotational", "E": "joint.cylindrical", "W": "joint.slider",
                 "SW": "assembly.ground", "list": ["joint.rigid", "view.zoom_selection"]},
    "empty": {"N": "file.new", "S": "file.open", "E": "view.theme_toggle", "W": "view.freecad", "list": []},
    "browser": {"N": "browser.edit", "S": "browser.move_end_of_part", "E": "browser.suppress",
                "W": "browser.rename", "list": ["sketch.start", "browser.delete"]},
}


def resolve(context, registry, layout=None):
    """([(direction, Command)] in N…NW order, [Command] for the list); unknown command ids are skipped."""
    spec = (LAYOUT if layout is None else layout).get(context, {})
    slots = [(d, registry.get(spec[d])) for d in DIRECTIONS if spec.get(d) and registry.has(spec[d])]
    items = [registry.get(i) for i in spec.get("list", []) if registry.has(i)]
    return slots, items
