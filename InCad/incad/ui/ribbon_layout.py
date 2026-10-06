"""Which commands sit on which ribbon tab and group, per mode. Later plans add groups with add_group().
Modes: 'part' (an InCad Part is active), 'empty' (no document, or a file not made in InCad);
'sketch' and 'assembly' arrive with later plans."""

LAYOUT = {
    "part": [
        ["3D Model", [["Sketch", ["sketch.start"]],
                      ["Create", ["feature.extrude", "feature.revolve", "feature.hole"]],
                      ["Modify", ["feature.fillet", "feature.chamfer", "feature.shell", "feature.thread", "feature.combine"]],
                      ["Pattern", ["feature.rect_pattern", "feature.circ_pattern", "feature.mirror"]],
                      ["Work Features", ["work.plane", "work.axis", "work.point"]]]],
        ["Sketch", []],
        ["Inspect", [["Measure", ["inspect.measure", "inspect.mass"]]]],
        ["Tools", [["Options", ["view.freecad"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "view.look_at", "view.zoom_selection", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "sketch": [
        ["Sketch", [["Create", ["sketch.line", "sketch.circle", "sketch.arc", "sketch.rectangle", "sketch.slot",
                                "sketch.polygon", "sketch.spline", "sketch.point"]],
                    ["Modify", ["sketch.fillet", "sketch.chamfer", "sketch.trim", "sketch.extend", "sketch.offset"]],
                    ["Pattern", ["sketch.mirror", "sketch.rect_pattern"]],
                    ["Constrain", ["sketch.dimension", "sketch.coincident", "sketch.horizontal", "sketch.vertical",
                                   "sketch.parallel", "sketch.perpendicular", "sketch.tangent", "sketch.equal",
                                   "sketch.symmetric", "sketch.fix"]],
                    ["Insert", ["sketch.project"]],
                    ["Format", ["sketch.construction", "sketch.show_dof", "sketch.slice"]],
                    ["Exit", ["sketch.finish"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home", "nav.orbit", "nav.pan"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "empty": [
        ["Get Started", [["New", ["file.new", "file.open"]]]],
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
