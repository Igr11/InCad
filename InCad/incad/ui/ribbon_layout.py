"""Which commands sit on which ribbon tab and group, per mode. Later plans add groups with add_group().
Modes: 'part' (an InCad Part is active), 'empty' (no document, or a file not made in InCad);
'sketch' and 'assembly' arrive with later plans."""

LAYOUT = {
    "part": [
        ["3D Model", [["Sketch", ["sketch.start"]],
                      ["Create", ["feature.extrude", "feature.revolve", "feature.hole",
                                  ["feature.sweep", "feature.loft", "feature.coil"]]],
                      ["Modify", [["feature.fillet", "feature.chamfer"], ["feature.shell", "feature.draft"],
                                  "feature.thread", "feature.combine"]],
                      ["Pattern", [["feature.rect_pattern", "feature.circ_pattern", "feature.mirror"]]],
                      ["Work Features", [["work.plane", "work.axis", "work.point"]]]]],
        ["Sketch", []],
        ["Inspect", [["Measure", ["inspect.measure", "inspect.mass"]]]],
        ["Tools", [["Material", ["tools.material"]], ["Options", ["view.freecad"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "view.look_at", "view.zoom_selection", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe", "view.section"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "sketch": [
        ["Sketch", [["Create", [["sketch.line", "sketch.line_single"],
                                ["sketch.circle", "sketch.circle_3pt", "sketch.ellipse", "sketch.ellipse_3pt"],
                                ["sketch.arc", "sketch.arc_center", "sketch.arc_ellipse"],
                                ["sketch.rectangle", "sketch.rectangle_center", "sketch.rectangle_3pt",
                                 "sketch.rectangle_center_3pt", "sketch.rectangle_rounded"],
                                ["sketch.slot", "sketch.slot_arc", "sketch.slot_arc_flat"],
                                ["sketch.polygon", "sketch.triangle", "sketch.square", "sketch.pentagon",
                                 "sketch.octagon", "sketch.polygon_n"],
                                ["sketch.spline", "sketch.spline_cv"], "sketch.point"]],
                    ["Modify", ["sketch.fillet", "sketch.chamfer", "sketch.trim", "sketch.extend", "sketch.offset"]],
                    ["Pattern", ["sketch.mirror", "sketch.rect_pattern"]],
                    ["Constrain", ["sketch.dimension", "sketch.coincident", "sketch.horizontal", "sketch.vertical",
                                   "sketch.parallel", "sketch.perpendicular", "sketch.tangent", "sketch.equal",
                                   "sketch.symmetric", "sketch.fix"]],
                    ["Insert", ["sketch.project"]],
                    ["Format", ["sketch.construction", "sketch.constraints_toggle", "sketch.show_dof", "sketch.slice"]],
                    ["Exit", ["sketch.finish"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe", "view.section"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "assembly": [
        ["Assemble", [["Component", ["assembly.place", "assembly.create", "assembly.ground", "assembly.combine"]],
                      ["Constrain", ["constrain.mate", "constrain.flush", "constrain.angle", "constrain.tangent",
                                     "constrain.insert"]],
                      ["Joint", ["joint.rigid", "joint.rotational", "joint.slider", "joint.cylindrical",
                                 "joint.ball"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "view.look_at", "view.zoom_selection", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe", "view.section"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "empty": [
        ["Get Started", [["New", ["file.new", "file.new_assembly", "file.open"]]]],
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
