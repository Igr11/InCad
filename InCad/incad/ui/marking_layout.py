"""Which commands the right-click marking menu shows, per context. Slots N…NW sit around the cursor (flick
directions); 'list' is the short list below the ring. Later plans move sketch/feature commands into the slots."""
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

_EDGE = {"N": "view.look_at", "S": "view.zoom_selection", "E": "view.style_shaded", "W": "view.style_wireframe",
         "NW": "edit.undo", "NE": "edit.redo", "SW": "view.zoom_all", "SE": "view.home", "list": []}

LAYOUT = {
    "part": {"N": "sketch.start", "NE": "edit.redo", "E": "view.style_shaded", "SE": "view.parameters",
             "S": "feature.extrude", "SW": "view.theme_toggle", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": ["view.zoom_all", "view.home", "view.freecad", "view.toggle_visibility", "view.origin_show_all",
                      "view.origin_hide_all", "file.make_assembly"]},
    "face": {"N": "sketch.start", "NE": "view.look_at", "E": "view.style_shaded", "SE": "view.home",
             "S": "feature.extrude", "SW": "view.zoom_all", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": ["view.show_in_browser", "view.zoom_selection", "feature.hole", "feature.fillet", "feature.thread",
                      "view.toggle_visibility"]},
    "edge": dict(_EDGE, E="feature.fillet", W="feature.chamfer",
                 list=["view.show_in_browser", "view.style_shaded", "view.style_wireframe", "view.toggle_visibility"]),
    "vertex": dict(_EDGE, list=["view.show_in_browser", "view.toggle_visibility"]),
    "sketch": {"N": "sketch.finish", "NE": "sketch.line", "E": "sketch.circle", "SE": "sketch.rectangle",
               "S": "sketch.dimension", "SW": "sketch.arc", "W": "edit.undo", "NW": "sketch.trim",
               "list": ["sketch.stop", "edit.delete", "sketch.constraints_toggle", "sketch.constraints_window", "view.look_at",
                        "sketch.construction", "sketch.project", "sketch.edit_pattern", "sketch.delete_pattern"]},
    "assembly": {"N": "assembly.place", "S": "constrain.mate", "E": "joint.rigid", "W": "assembly.create",
                 "NE": "view.zoom_all", "NW": "edit.undo", "SE": "view.home", "SW": "assembly.ground",
                 "list": ["assembly.edit", "view.toggle_visibility", "assembly.suppress", "assembly.remove",
                          "constrain.flush", "constrain.insert", "view.freecad"]},
    "asm_face": {"N": "constrain.mate", "S": "constrain.flush", "E": "constrain.angle", "W": "constrain.tangent",
                 "NE": "view.look_at", "SW": "assembly.ground",
                 "list": ["assembly.edit", "view.toggle_visibility", "assembly.suppress", "assembly.remove",
                          "joint.rigid", "view.zoom_selection"]},
    "asm_edge": {"N": "constrain.insert", "S": "joint.rotational", "E": "joint.cylindrical", "W": "joint.slider",
                 "SW": "assembly.ground", "list": ["assembly.edit", "view.toggle_visibility", "assembly.suppress",
                                                   "assembly.remove", "joint.rigid", "view.zoom_selection"]},
    "empty": {"N": "file.new", "S": "file.open", "E": "view.theme_toggle", "W": "view.freecad", "list": []},
    "origin": {"N": "sketch.start", "S": "view.toggle_visibility", "list": ["sketch.start", "view.toggle_visibility"]},
    "solid": {"N": "view.toggle_visibility", "S": "browser.rename", "E": "browser.show_in_window",
              "W": "browser.delete", "list": ["view.toggle_visibility", "browser.show_in_window", "browser.rename",
                                              "browser.delete"]},
    "browser": {"N": "browser.edit", "S": "browser.move_end_of_part", "E": "browser.suppress",
                "W": "browser.rename", "list": ["browser.edit", "browser.show_in_window", "sketch.start", "browser.delete",
                         "view.toggle_visibility"]},
}


def resolve(context, registry, layout=None):
    """([(direction, Command)] in N…NW order, [Command] for the list); unknown command ids are skipped."""
    spec = (LAYOUT if layout is None else layout).get(context, {})
    slots = [(d, registry.get(spec[d])) for d in DIRECTIONS if spec.get(d) and registry.has(spec[d])]
    items = [registry.get(i) for i in spec.get("list", []) if registry.has(i)]
    return slots, items
