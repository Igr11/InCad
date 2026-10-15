"""Which commands sit on which ribbon tab and group, per mode. Later plans add groups with add_group().
Modes: 'part' (an InCad Part is active), 'empty' (no document, or a file not made in InCad);
'sketch' and 'assembly' arrive with later plans."""

LAYOUT = {
    "part": [
        ["3D Model", [["Sketch", ["sketch.start"]],
                      ["Create", ["feature.extrude", "feature.revolve", "feature.hole",
                                  ["feature.sweep", "feature.loft", "feature.coil"], "feature.emboss"]],
                      ["Modify", [["feature.fillet", "feature.chamfer"], ["feature.shell", "feature.draft"],
                                  "feature.thread", "feature.threads_toggle", "feature.combine", "feature.split",
                                  "feature.move_face"]],
                      ["Pattern", [["feature.rect_pattern", "feature.circ_pattern", "feature.mirror"]]],
                      ["Work Features", [["work.plane", "work.axis", "work.point"]]],
                      ["Assemble", ["file.make_assembly"]]]],
        ["Sketch", []],
        ["Inspect", [["Measure", [["inspect.measure", "inspect.distance", "inspect.angle", "inspect.length",
                                   "inspect.area"], "inspect.mass"]]]],
        ["Tools", [["Material", ["tools.material"]], ["Options", ["view.freecad", "tools.ask_on_new"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "view.look_at", "view.zoom_selection", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe", ["view.section", "view.section_points"],
                                    ["view.toggle_visibility", "view.origin_show_all", "view.origin_hide_all"],
                                    "view.assembly_context"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "sketch": [
        ["Sketch", [["Create", [["sketch.line", "sketch.line_single"], ["sketch.spline", "sketch.spline_cv"],
                                ["sketch.circle", "sketch.circle_3pt", "sketch.ellipse", "sketch.ellipse_3pt"],
                                ["sketch.arc", "sketch.arc_center", "sketch.arc_ellipse"],
                                ["sketch.rectangle", "sketch.rectangle_center", "sketch.rectangle_3pt",
                                 "sketch.rectangle_center_3pt", "sketch.rectangle_rounded"],
                                ["sketch.slot", "sketch.slot_overall", "sketch.slot_center", "sketch.slot_arc",
                                 "sketch.slot_arc_flat"],
                                ["sketch.polygon", "sketch.triangle", "sketch.square", "sketch.pentagon",
                                 "sketch.octagon", "sketch.polygon_n"],
                                "sketch.point", "sketch.text"]],
                    ["Modify", [["sketch.fillet", "sketch.chamfer"], "sketch.trim", "sketch.extend", "sketch.offset"]],
                    ["Pattern", [["sketch.rect_pattern", "sketch.circ_pattern", "sketch.path_pattern"], "sketch.mirror"]],
                    ["Dimension", ["sketch.dimension"]],
                    ["Constrain", ["sketch.coincident", "sketch.concentric", "sketch.horizontal", "sketch.vertical", "sketch.parallel",
                                   "sketch.perpendicular", "sketch.tangent", "sketch.equal", "sketch.symmetric",
                                   "sketch.fix", "sketch.constraints_window"], "stacked"],
                    ["Insert", ["sketch.project"]],
                    ["Format", ["sketch.construction", "sketch.constraints_toggle", "sketch.show_dof", "sketch.slice"],
                     "stacked"],
                    ["Exit", ["sketch.finish"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe", ["view.section", "view.section_points"]]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "assembly": [
        ["Assemble", [["Component", ["assembly.place", "assembly.create", "assembly.ground", "assembly.combine",
                                     "assembly.threads_toggle"]],
                      ["Constrain", ["constrain.mate", "constrain.flush", "constrain.angle", "constrain.parallel",
                                     "constrain.perpendicular", "constrain.tangent", "constrain.insert"]],
                      ["Joint", ["joint.rigid", "joint.rotational", "joint.slider", "joint.cylindrical",
                                 "joint.ball"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "view.look_at", "view.zoom_selection", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe", ["view.section", "view.section_points"],
                                    "view.toggle_visibility", "view.dof"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "empty": [
        # New is in the title bar: the first button starts the sketch (a new part comes with it)
        ["Get Started", [["Start", ["sketch.start", "file.new_assembly", "file.open"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]]]],
    ],
}


def add_group(mode, tab, group, cmd_ids, layout=None):
    """Append a group of commands to a tab (the tab is created at the end if missing)."""
    layout = LAYOUT if layout is None else layout
    tabs = layout.setdefault(mode, [])
    for name, groups in tabs:
        if name == tab:
            groups.append([group, list(cmd_ids)])
            return
    tabs.append([tab, [[group, list(cmd_ids)]]])
