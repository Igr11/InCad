"""Which commands sit on which ribbon tab and group, per mode. Later plans add groups with add_group().
Modes: 'part' (an InCad Part is active), 'empty' (no document, or a file not made in InCad);
'sketch' and 'assembly' arrive with later plans."""

LAYOUT = {
    "part": [
        ["3D Model", []],
        ["Sketch", []],
        ["Inspect", []],
        ["Tools", [["Options", ["view.freecad"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home"]],
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
