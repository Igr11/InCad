# InCad 1c — Sketch Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inventor-style sketching inside InCad: Start 2D Sketch (S) on a plane or flat face (or pick one), sketch
tools on the ribbon/marking menu/shortcuts, dynamic input while drawing, one smart Dimension (D) whose value is typed
in InCad's own value box, named dimensions `d0, d1…` usable in formulas, click-to-insert of names, DOF status and
theme colors, Finish Sketch — all without leaving InCad.

**Architecture:** FreeCAD's Sketcher does the drawing and solving; InCad configures and drives it. Probed facts
(see ledger): Sketcher's on-view parameters (`Mod/Sketcher/Tools/OnViewParameterVisibility = 1`) turn typed values
into real constraints; `Mod/Sketcher/ShowDialogOnDistanceConstraint = False` (root group) suppresses FreeCAD's modal
"Insert Length" dialog; `ViewObject.EditingWorkbench = ""` keeps the current workbench while editing; sketches expose
`DoF`, `FullyConstrained`, `ConflictingConstraints`; `renameConstraint` updates every formula that uses the name.
New: `incad.core.sketch` (model logic, headless-tested), `incad.ui.value_box`, `incad.ui.sketch_session`, browser /
status / navigator hooks, shell wiring.

**Tech Stack:** FreeCAD 1.1.3 Sketcher, PySide6, pivy.

**Spec:** `docs/superpowers/specs/2026-10-05-incad-stage1-design.md` §5 (sketch workflow) and §5a (named dimensions,
click-to-insert). Base: plans 1a + 1b (merged to `main`).

## Global Constraints

- Plan 1a/1b constraints hold (Qt via `incad.qt`, `run_safely`, throwaway `user.cfg`, English UI, announce GUI runs).
- Sketch editing never leaves InCad (EditingWorkbench cleared on every sketch InCad edits).
- Every Sketcher/View setting InCad writes is in the takeover snapshot and restored on exit and crash recovery.
- Dimension names: `d<N>`, unique in the document (also against user parameters); renamable to any valid
  parameter name that is not a unit symbol and not already used.
- A formula may use user parameter names and dimension names; InCad translates them to FreeCAD expression paths
  (`InCadParameters.Width`, `Sketch001.Constraints.d3`) and shows them back as plain names.
- Single-letter shortcuts work only in their mode (sketch tools in a sketch, S in a part) and never while typing
  in a text field.

## Review Focus

1. Values typed while drawing (on-view parameters) must not pop InCad's value box — only the Dimension tool does
   (Task 7 GUI test 3 vs. geometry-count rule in Task 7).
2. A formula that references a renamed dimension keeps working and shows the new name (Task 2 test, Task 7 test 6).
3. Clicking a dimension while the value box is open inserts its name and must not select or move anything in the
   sketch (Task 6 test, Task 7 test 4).
4. Leaving InCad mid-sketch or after sketching restores every Sketcher/View setting (Task 7 test 13).
5. Typing letters in the Parameters table or the value box never triggers sketch shortcuts (Task 7 test 9).

## File Map

```
InCad/incad/core/sketch.py          sketch model logic (supports, status, names, formulas)
InCad/incad/core/nodes.py           + Node.detail
InCad/incad/core/tree.py            + sketch DOF detail
InCad/incad/core/prefs.py           + dimension_display()
InCad/incad/core/safe.py            sketch editing is not "an open edit"
InCad/incad/actions.py              + sketch commands
InCad/incad/ui/theme.py             + sketch settings and colors
InCad/incad/ui/ribbon_layout.py     + sketch mode, 3D Model ▸ Sketch
InCad/incad/ui/marking_layout.py    + sketch context, New Sketch on part/face
InCad/incad/ui/value_box.py         floating value/formula box
InCad/incad/ui/browser.py           model + user parameters, rename, click, row detail
InCad/incad/ui/statusbar.py         + dofClicked
InCad/incad/ui/nav.py               + click/double-click hooks
InCad/incad/ui/sketch_session.py    start / pick / edit / finish
InCad/incad/ui/shell.py             sketch mode, shortcuts, value box, settings snapshot
tools/make_icons.py                 + 33 sketch icons
```

---

### Task 1: Sketch commands, icons, layouts, settings

**Files:**
- Modify: `tools/make_icons.py`, `InCad/incad/core/prefs.py`, `InCad/incad/ui/theme.py`, `InCad/incad/actions.py`,
  `InCad/incad/ui/ribbon_layout.py`, `InCad/incad/ui/marking_layout.py`, `tests/widgets/test_actions.py`,
  `tests/widgets/test_prefs.py`, `tests/widgets/test_theme.py`, `tests/widgets/test_marking_layout.py`

**Interfaces:**
- Produces: `prefs.DISPLAYS = ("value", "name", "expression")`, `prefs.dimension_display()` (default `"value"`),
  `prefs.set_dimension_display(v)`; `theme.SKETCH_ROOT`, `theme.SKETCH_TOOLS`, `theme.SKETCH_KEYS
  ({group: {name: kind}})`, `theme.sketch_params(theme, display) -> {group: {name: (kind, value)}}`;
  `actions.SKETCHER ({id: (label, icon, FreeCAD command, shortcut)})`; commands `sketch.start` (S, context part),
  `sketch.finish` and every `SKETCHER` id (context sketch); `ribbon_layout.LAYOUT["sketch"]`;
  `marking_layout.LAYOUT["sketch"]`; `actions.start_sketch/finish_sketch` call `shell.sketch_session()` (Task 7).

- [ ] **Step 1: Write the failing tests**

Append to `tests/widgets/test_prefs.py` (inside `PrefsMemoryTest`):
```python
    def test_dimension_display(self):
        self.assertEqual(prefs.dimension_display(), "value")
        prefs.set_dimension_display("expression")
        self.assertEqual(prefs.dimension_display(), "expression")
        with self.assertRaises(ValueError):
            prefs.set_dimension_display("fancy")
```

Append to `tests/widgets/test_theme.py` (inside `ThemeTest`):
```python
    def test_sketch_params(self):
        p = theme.sketch_params("dark", "expression")
        self.assertEqual(p[theme.SKETCH_ROOT]["ShowDialogOnDistanceConstraint"], ("Bool", False))
        self.assertEqual(p[theme.SKETCH_ROOT]["DimensionalStringFormat"], ("String", "%N = %V"))
        self.assertEqual(p[theme.SKETCH_TOOLS]["OnViewParameterVisibility"], ("Int", 1))
        self.assertEqual(p[theme.VIEW_GROUP]["EditedEdgeColor"], ("Unsigned", 0xF2F2F2FF))
        self.assertEqual(theme.sketch_params("light", "value")[theme.SKETCH_ROOT]["ShowDimensionalName"], ("Bool", False))
        for group, values in p.items():
            self.assertEqual(set(values), set(theme.SKETCH_KEYS[group]), group)
```

In `tests/widgets/test_actions.py` replace the line `"browser.move_end_of_part", "browser.suppress", "browser.rename",
"nav.orbit", "nav.pan"}` (end of `EXPECTED`) with:
```python
            "browser.move_end_of_part", "browser.suppress", "browser.rename", "nav.orbit", "nav.pan",
            "sketch.start", "sketch.finish"} | set(actions.SKETCHER)
```
and append to `ActionsTest`:
```python
    def test_sketch_shortcuts(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual(r.get("sketch.start").shortcut, "S")
        self.assertEqual({i: r.get(i).shortcut for i in ("sketch.line", "sketch.circle", "sketch.arc",
                          "sketch.rectangle", "sketch.dimension", "sketch.trim")},
                         {"sketch.line": "L", "sketch.circle": "C", "sketch.arc": "A", "sketch.rectangle": "R",
                          "sketch.dimension": "D", "sketch.trim": "X"})
        self.assertEqual(r.get("sketch.line").contexts, frozenset({"sketch"}))
```

In `tests/widgets/test_marking_layout.py` change the contexts test to:
```python
    def test_contexts(self):
        self.assertEqual(set(marking_layout.LAYOUT),
                         {"part", "face", "edge", "vertex", "empty", "browser", "sketch"})
        self.assertEqual(marking_layout.LAYOUT["sketch"]["N"], "sketch.finish")
        self.assertEqual(marking_layout.LAYOUT["sketch"]["S"], "sketch.dimension")
        self.assertEqual(marking_layout.LAYOUT["part"]["N"], "sketch.start")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_prefs.py`, `test_theme.py`, `test_actions.py`, `test_marking_layout.py`
Expected: AttributeErrors (`dimension_display`, `sketch_params`, `SKETCHER`) and the contexts assertion.

- [ ] **Step 3: Implement**

`tools/make_icons.py` — add to `ICONS`:
```python
    "line": ('<path d="M5 26 L27 6" stroke="{S}" stroke-width="2.4" stroke-linecap="round"/>'
             '<circle cx="5" cy="26" r="2.6" fill="{A}"/><circle cx="27" cy="6" r="2.6" fill="{A}"/>'),
    "circle": '<circle cx="16" cy="16" r="10" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="16" r="2.2" fill="{A}"/>',
    "arc": ('<path d="M5 24 A13 13 0 0 1 27 24" fill="none" stroke="{S}" stroke-width="2.4"/>'
            '<circle cx="5" cy="24" r="2.4" fill="{A}"/><circle cx="16" cy="11.5" r="2.4" fill="{A}"/>'
            '<circle cx="27" cy="24" r="2.4" fill="{A}"/>'),
    "rectangle": ('<rect x="5" y="8" width="22" height="16" fill="none" stroke="{S}" stroke-width="2.4"/>'
                  '<circle cx="5" cy="24" r="2.4" fill="{A}"/><circle cx="27" cy="8" r="2.4" fill="{A}"/>'),
    "slot": ('<rect x="4" y="10" width="24" height="12" rx="6" fill="none" stroke="{S}" stroke-width="2.4"/>'
             '<circle cx="10" cy="16" r="1.8" fill="{A}"/><circle cx="22" cy="16" r="1.8" fill="{A}"/>'),
    "polygon": ('<path d="M16 4 L26.4 10 L26.4 22 L16 28 L5.6 22 L5.6 10 Z" fill="none" stroke="{S}" stroke-width="2.4" '
                'stroke-linejoin="round"/><circle cx="16" cy="16" r="2" fill="{A}"/>'),
    "spline": ('<path d="M4 24 C10 4 18 30 28 8" fill="none" stroke="{S}" stroke-width="2.4"/>'
               '<circle cx="4" cy="24" r="2.2" fill="{A}"/><circle cx="16" cy="17" r="2.2" fill="{A}"/>'
               '<circle cx="28" cy="8" r="2.2" fill="{A}"/>'),
    "point": '<path d="M16 8 V24 M8 16 H24" stroke="{N}" stroke-width="1.4"/><circle cx="16" cy="16" r="4" fill="{A}"/>',
    "sk_fillet": ('<path d="M6 6 V18 A8 8 0 0 0 14 26 H26" fill="none" stroke="{S}" stroke-width="2.4"/>'
                  '<path d="M6 6 V26 H26" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "sk_chamfer": ('<path d="M6 6 V18 L14 26 H26" fill="none" stroke="{S}" stroke-width="2.4"/>'
                   '<path d="M6 18 V26 H14" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "trim": ('<path d="M4 16 H14" stroke="{S}" stroke-width="2.4"/><path d="M14 16 H28" stroke="{N}" stroke-width="1.6" '
             'stroke-dasharray="2 2"/><path d="M20 6 V26" stroke="{S}" stroke-width="2.4"/>'
             '<path d="M11 9 L17 15 M17 9 L11 15" stroke="{R}" stroke-width="2" stroke-linecap="round"/>'),
    "extend": ('<path d="M4 16 H14" stroke="{S}" stroke-width="2.4"/><path d="M14 16 H22" stroke="{A}" stroke-width="2.4" '
               'stroke-dasharray="3 2"/><path d="M24 6 V26" stroke="{S}" stroke-width="2.4"/>'),
    "offset": ('<path d="M6 26 V12 Q6 6 12 6 H26" fill="none" stroke="{S}" stroke-width="2.4"/>'
               '<path d="M12 26 V16 Q12 12 16 12 H26" fill="none" stroke="{A}" stroke-width="2" stroke-dasharray="3 2"/>'),
    "project": ('<path d="M4 20 L14 25 L28 18 L18 13 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M16 3 V15" stroke="{A}" stroke-width="2.2"/>'
                '<path d="M12 11 L16 16 L20 11" fill="none" stroke="{A}" stroke-width="2.2" stroke-linejoin="round"/>'),
    "construction": ('<path d="M5 26 L27 6" stroke="{S}" stroke-width="2.4" stroke-dasharray="4 3"/>'
                     '<circle cx="16" cy="16" r="9" fill="none" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 3"/>'),
    "mirror": ('<path d="M16 3 V29" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 2"/>'
               '<path d="M4 9 H12 V23 H4 Z" fill="{F}" stroke="{S}" stroke-width="1.8"/>'
               '<path d="M28 9 H20 V23 H28 Z" fill="none" stroke="{A}" stroke-width="1.8"/>'),
    "rect_pattern": ('<g fill="{F}" stroke="{S}" stroke-width="1.6"><rect x="4" y="4" width="9" height="9"/>'
                     '<rect x="19" y="4" width="9" height="9"/><rect x="4" y="19" width="9" height="9"/>'
                     '<rect x="19" y="19" width="9" height="9"/></g>'),
    "dimension": ('<path d="M5 22 H27" stroke="{S}" stroke-width="1.8"/><path d="M5 16 V28 M27 16 V28" stroke="{S}" '
                  'stroke-width="1.6"/><path d="M9 19 L5 22 L9 25 M23 19 L27 22 L23 25" fill="none" stroke="{S}" '
                  'stroke-width="1.8"/><text x="16" y="15" font-family="Helvetica" font-size="10" text-anchor="middle" '
                  'fill="{A}">40</text>'),
    "coincident": ('<path d="M4 26 L16 16 L28 22" fill="none" stroke="{S}" stroke-width="2.2"/>'
                   '<circle cx="16" cy="16" r="4" fill="{A}"/>'),
    "horizontal": ('<path d="M4 18 H28" stroke="{S}" stroke-width="2.6"/><text x="16" y="13" font-family="Helvetica" '
                   'font-size="10" font-weight="bold" text-anchor="middle" fill="{A}">H</text>'),
    "vertical": ('<path d="M14 4 V28" stroke="{S}" stroke-width="2.6"/><text x="19" y="19" font-family="Helvetica" '
                 'font-size="10" font-weight="bold" fill="{A}">V</text>'),
    "parallel": '<path d="M6 24 L20 6 M13 26 L27 8" stroke="{S}" stroke-width="2.4"/>',
    "perpendicular": ('<path d="M6 26 H26 M16 26 V6" stroke="{S}" stroke-width="2.4"/>'
                      '<path d="M16 20 H22 V26" fill="none" stroke="{A}" stroke-width="1.6"/>'),
    "tangent": '<circle cx="14" cy="18" r="8" fill="none" stroke="{S}" stroke-width="2.2"/><path d="M4 10 H28" stroke="{A}" stroke-width="2.2"/>',
    "equal": '<path d="M7 12 H25 M7 20 H25" stroke="{S}" stroke-width="2.6"/>',
    "symmetric": ('<path d="M16 4 V28" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 2"/>'
                  '<circle cx="7" cy="16" r="3" fill="{A}"/><circle cx="25" cy="16" r="3" fill="{A}"/>'
                  '<path d="M10 16 H13 M19 16 H22" stroke="{S}" stroke-width="1.6"/>'),
    "fix": ('<rect x="8" y="14" width="16" height="13" rx="2" fill="{F}" stroke="{S}" stroke-width="1.8"/>'
            '<path d="M11 14 V10 A5 5 0 0 1 21 10 V14" fill="none" stroke="{S}" stroke-width="2.2"/>'),
    "show_dof": ('<path d="M5 26 L16 10 L27 26" fill="none" stroke="{S}" stroke-width="2"/>'
                 '<circle cx="16" cy="10" r="3.5" fill="{R}"/><path d="M16 4 V1 M21 6 L23 4 M11 6 L9 4" stroke="{R}" '
                 'stroke-width="1.6"/>'),
    "stop": ('<circle cx="16" cy="16" r="11" fill="none" stroke="{N}" stroke-width="2"/>'
             '<path d="M11 11 L21 21 M21 11 L11 21" stroke="{N}" stroke-width="2.4" stroke-linecap="round"/>'),
    "finish": ('<circle cx="16" cy="16" r="12" fill="#2ea043"/><path d="M10 16.5 L14.5 21 L23 11.5" fill="none" '
               'stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "start_sketch": ('<rect x="4" y="9" width="18" height="15" fill="none" stroke="{S}" stroke-width="1.6"/>'
                     '<path d="M4 24 L22 9" stroke="{S}" stroke-width="1.2"/>'
                     '<path d="M25 4 V12 M21 8 H29" stroke="{A}" stroke-width="2.4" stroke-linecap="round"/>'),
    "slice": ('<path d="M4 21 L14 26 L28 18 L18 13 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<path d="M3 15 H29" stroke="{R}" stroke-width="2" stroke-dasharray="4 2"/>'),
```
Run `python3 tools/make_icons.py` → Expected `wrote 64 icons per theme …`.

`InCad/incad/core/prefs.py` — append:
```python
DISPLAYS = ("value", "name", "expression")


def dimension_display():
    return _choice("DimensionDisplay", DISPLAYS, "value")


def set_dimension_display(value):
    _set_choice("DimensionDisplay", DISPLAYS, value)
```

`InCad/incad/ui/theme.py` — append:
```python
SKETCH_ROOT = "User parameter:BaseApp/Preferences/Mod/Sketcher"
SKETCH_TOOLS = "User parameter:BaseApp/Preferences/Mod/Sketcher/Tools"
DISPLAY_FORMAT = {"value": (False, "%V"), "name": (True, "%N"), "expression": (True, "%N = %V")}
SKETCH_COLORS = {
    "light": dict(EditedEdgeColor="#1d1d1f", SketchEdgeColor="#1d1d1f", SketchVertexColor="#1d1d1f",
                  FullyConstrainedColor="#1a8a2e", ConstructionColor="#0a64d6", ConstrainedDimColor="#b00020",
                  ExprBasedConstrDimColor="#c75a00", NonDrivingConstrDimColor="#5b6b80", CursorTextColor="#1d1d1f",
                  CreateLineColor="#e67e22"),
    "dark": dict(EditedEdgeColor="#f2f2f2", SketchEdgeColor="#f2f2f2", SketchVertexColor="#f2f2f2",
                 FullyConstrainedColor="#5ad16b", ConstructionColor="#5aa2ff", ConstrainedDimColor="#ff8a80",
                 ExprBasedConstrDimColor="#f39c4a", NonDrivingConstrDimColor="#9aa7b8", CursorTextColor="#f2f2f2",
                 CreateLineColor="#f39c4a"),
}
SKETCH_KEYS = {
    SKETCH_ROOT: {"ShowDialogOnDistanceConstraint": "Bool", "ShowDimensionalName": "Bool",
                  "DimensionalStringFormat": "String", "LeaveSketchWithEscape": "Bool"},
    SKETCH_TOOLS: {"OnViewParameterVisibility": "Int", "ContinuousCreationMode": "Bool"},
    VIEW_GROUP: {k: "Unsigned" for k in SKETCH_COLORS["light"]},
}


def sketch_params(theme, display="value"):
    """Sketcher settings InCad uses: no modal dimension dialog (InCad's value box instead), dimensional on-view
    parameters (dynamic input), continuous tools, Esc leaves the sketch, names shown per display mode, colors."""
    show, fmt = DISPLAY_FORMAT[display]
    return {
        SKETCH_ROOT: {"ShowDialogOnDistanceConstraint": ("Bool", False), "ShowDimensionalName": ("Bool", show),
                      "DimensionalStringFormat": ("String", fmt), "LeaveSketchWithEscape": ("Bool", True)},
        SKETCH_TOOLS: {"OnViewParameterVisibility": ("Int", 1), "ContinuousCreationMode": ("Bool", True)},
        VIEW_GROUP: {k: ("Unsigned", _rgba(v)) for k, v in SKETCH_COLORS[theme].items()},
    }
```

`InCad/incad/actions.py` — add after `STD_INDEX`:
```python
SKETCHER = {  # InCad id: (label, icon, FreeCAD Sketcher command, shortcut)
    "sketch.line": ("Line", "line", "Sketcher_CreatePolyline", "L"),
    "sketch.circle": ("Circle", "circle", "Sketcher_CreateCircle", "C"),
    "sketch.arc": ("Arc", "arc", "Sketcher_Create3PointArc", "A"),
    "sketch.rectangle": ("Rectangle", "rectangle", "Sketcher_CreateRectangle", "R"),
    "sketch.slot": ("Slot", "slot", "Sketcher_CreateSlot", ""),
    "sketch.polygon": ("Polygon", "polygon", "Sketcher_CreateHexagon", ""),
    "sketch.spline": ("Spline", "spline", "Sketcher_CreateBSplineByInterpolation", ""),
    "sketch.point": ("Point", "point", "Sketcher_CreatePoint", ""),
    "sketch.fillet": ("Fillet", "sk_fillet", "Sketcher_CreateFillet", ""),
    "sketch.chamfer": ("Chamfer", "sk_chamfer", "Sketcher_CreateChamfer", ""),
    "sketch.trim": ("Trim", "trim", "Sketcher_Trimming", "X"),
    "sketch.extend": ("Extend", "extend", "Sketcher_Extend", ""),
    "sketch.offset": ("Offset", "offset", "Sketcher_Offset", ""),
    "sketch.project": ("Project Geometry", "project", "Sketcher_Projection", ""),
    "sketch.construction": ("Construction", "construction", "Sketcher_ToggleConstruction", ""),
    "sketch.mirror": ("Mirror", "mirror", "Sketcher_Symmetry", ""),
    "sketch.rect_pattern": ("Rectangular Pattern", "rect_pattern", "Sketcher_RectangularArray", ""),
    "sketch.dimension": ("Dimension", "dimension", "Sketcher_Dimension", "D"),
    "sketch.coincident": ("Coincident", "coincident", "Sketcher_ConstrainCoincidentUnified", ""),
    "sketch.horizontal": ("Horizontal", "horizontal", "Sketcher_ConstrainHorizontal", ""),
    "sketch.vertical": ("Vertical", "vertical", "Sketcher_ConstrainVertical", ""),
    "sketch.parallel": ("Parallel", "parallel", "Sketcher_ConstrainParallel", ""),
    "sketch.perpendicular": ("Perpendicular", "perpendicular", "Sketcher_ConstrainPerpendicular", ""),
    "sketch.tangent": ("Tangent", "tangent", "Sketcher_ConstrainTangent", ""),
    "sketch.equal": ("Equal", "equal", "Sketcher_ConstrainEqual", ""),
    "sketch.symmetric": ("Symmetric", "symmetric", "Sketcher_ConstrainSymmetric", ""),
    "sketch.fix": ("Fix", "fix", "Sketcher_ConstrainLock", ""),
    "sketch.show_dof": ("Show Free Geometry", "show_dof", "Sketcher_SelectElementsWithDoFs", ""),
    "sketch.stop": ("Stop Tool", "stop", "Sketcher_StopOperation", ""),
    "sketch.slice": ("Slice Graphics", "slice", "Sketcher_ViewSection", "F7"),
}
```
add before `def _std(`:
```python
def start_sketch():
    from incad.ui import shell
    return shell.sketch_session().start()


def finish_sketch():
    from incad.ui import shell
    shell.sketch_session().finish()
```
change `edit_feature` to:
```python
def edit_feature():
    from incad.core import log, sketch
    obj = _target_object()
    if sketch.is_sketch(obj):
        from incad.ui import shell
        shell.sketch_session().edit(obj)
    else:
        log.report("info", "Editing features arrives with the feature tools (plan 1d)")
```
and add at the end of the list in `commands()`:
```python
        Command(id="sketch.start", label="Start 2D Sketch", icon="start_sketch", handler=start_sketch, shortcut="S",
                contexts=frozenset({"part"}), tooltip="Pick a plane or a flat face to sketch on"),
        Command(id="sketch.finish", label="Finish Sketch", icon="finish", handler=finish_sketch,
                contexts=frozenset({"sketch"}), tooltip="Back to the 3D model (Esc)"),
    ] + [Command(id=i, label=lbl, icon=icon, handler=(lambda n=cmd: run_std(n)), shortcut=sc,
                 contexts=frozenset({"sketch"})) for i, (lbl, icon, cmd, sc) in SKETCHER.items()]
```
(replace the list's closing `]` accordingly so `commands()` returns the concatenation.)

`InCad/incad/ui/ribbon_layout.py` — in `"part"` replace `["3D Model", []],` with
`["3D Model", [["Sketch", ["sketch.start"]]]],` and add a `"sketch"` mode:
```python
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
```

`InCad/incad/ui/marking_layout.py` — replace `_GEOMETRY` and the `part`/`face` entries with:
```python
_EDGE = {"N": "view.look_at", "S": "view.zoom_selection", "E": "view.style_shaded", "W": "view.style_wireframe",
         "NW": "edit.undo", "NE": "edit.redo", "SW": "view.zoom_all", "SE": "view.home", "list": []}
```
```python
    "part": {"N": "sketch.start", "NE": "edit.redo", "E": "view.style_shaded", "SE": "view.parameters",
             "S": "view.zoom_all", "SW": "view.theme_toggle", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": ["view.home", "view.freecad"]},
    "face": {"N": "sketch.start", "NE": "view.look_at", "E": "view.style_shaded", "SE": "view.home",
             "S": "view.zoom_selection", "SW": "view.zoom_all", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": []},
    "edge": dict(_EDGE),
    "vertex": dict(_EDGE),
    "sketch": {"N": "sketch.finish", "NE": "sketch.line", "E": "sketch.circle", "SE": "sketch.rectangle",
               "S": "sketch.dimension", "SW": "sketch.arc", "W": "edit.undo", "NW": "sketch.trim",
               "list": ["sketch.construction", "sketch.project", "sketch.stop"]},
```

- [ ] **Step 4: Run to verify they pass**

Run the four widget runs from Step 2 plus `tests/run_widgets.sh test_icons.py` and `tests/run_fast.sh`
→ Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add tools InCad tests && git commit -m "InCad 1c: sketch commands, icons, layouts, Sketcher settings"
```

---

### Task 2: Sketch model logic

**Files:**
- Create: `InCad/incad/core/sketch.py`, `tests/headless/test_sketch.py`

**Interfaces:**
- Consumes: `document.list_parameters/PARAMS_NAME/primary_body/part_units/_format/_NAME_RE/_is_literal`.
- Produces (`incad.core.sketch`): `DIMENSIONAL`; `is_sketch(obj)`; `valid_support(obj, sub="") -> bool`;
  `make_sketch(body, support, sub="") -> sketch` (label `Sketch<n>`); `status(sk) -> {"dof", "fully",
  "conflicting", "redundant", "malformed"}`; `name_new_dimensions(doc) -> [names]`; `dimensions(doc) ->
  [(name, sketch, index)]`; `find_dimension(doc, name) -> (sketch, index)|(None, None)`;
  `model_parameters(doc) -> [(name, formula shown with plain names or "", value text)]`;
  `to_expression(doc, text)`; `to_display(doc, expr)`; `set_dimension(doc, name, text)` (call inside
  `run_safely`); `rename_dimension(doc, old, new)`. Errors are `ValueError` with readable text.

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_sketch.py`:
```python
import unittest

import FreeCAD as App
import Part
import Sketcher
from incad.core import document, safe, sketch
from headless import util


def plane(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


class SketchTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sk")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def line_sketch(self):
        sk = sketch.make_sketch(self.body, plane(self.body, "XY_Plane"))
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)))
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0)))
        sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10))
        self.doc.recompute()
        return sk

    def test_valid_support(self):
        self.assertTrue(sketch.valid_support(plane(self.body, "XY_Plane")))
        self.assertFalse(sketch.valid_support(plane(self.body, "X_Axis")))
        body, pad = util.padded_part(util.new_doc("P"), 10, incad=True)
        try:
            tops = [f"Face{i + 1}" for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6]
            self.assertTrue(sketch.valid_support(pad, tops[0]))
            self.assertFalse(sketch.valid_support(pad, "Edge1"))
            self.assertFalse(sketch.valid_support(None))
        finally:
            App.closeDocument(body.Document.Name)

    def test_cylindrical_face_is_not_flat(self):
        cyl = self.doc.addObject("Part::Cylinder", "Cyl")
        self.doc.recompute()
        side = [f"Face{i + 1}" for i, f in enumerate(cyl.Shape.Faces) if f.Surface.TypeId != "Part::GeomPlane"][0]
        self.assertFalse(sketch.valid_support(cyl, side))

    def test_make_sketch(self):
        a = sketch.make_sketch(self.body, plane(self.body, "XY_Plane"))
        b = sketch.make_sketch(self.body, plane(self.body, "XZ_Plane"))
        self.assertEqual((a.Label, b.Label), ("Sketch1", "Sketch2"))
        self.assertIn(a, self.body.Group)
        self.assertEqual(a.MapMode, "FlatFace")
        with self.assertRaises(ValueError):
            sketch.make_sketch(self.body, plane(self.body, "X_Axis"))

    def test_names_are_unique_across_sketches_and_parameters(self):
        document.set_parameter(self.doc, "d5", "1 mm")
        sk = self.line_sketch()
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d6", "d7"])
        sk2 = self.line_sketch()
        sk2.renameConstraint(0, "Len")
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d8"])
        self.assertEqual(sketch.name_new_dimensions(self.doc), [])
        self.assertEqual(sorted(n for n, _, _ in sketch.dimensions(self.doc)), ["Len", "d6", "d7", "d8"])

    def test_status(self):
        sk = self.line_sketch()
        st = sketch.status(sk)
        self.assertEqual(st["dof"], sk.DoF)
        self.assertFalse(st["fully"])
        self.assertEqual(st["conflicting"], [])

    def test_set_dimension_value_and_formulas(self):
        sk = self.line_sketch()
        sketch.name_new_dimensions(self.doc)  # d0 (X 20), d1 (Y 10)
        document.set_parameter(self.doc, "Width", "60 mm")
        sketch.set_dimension(self.doc, "d0", "40 mm")
        self.assertAlmostEqual(sk.getDatum("d0").Value, 40)
        sketch.set_dimension(self.doc, "d1", "d0 / 2")
        self.assertAlmostEqual(sk.getDatum("d1").Value, 20)
        sketch.set_dimension(self.doc, "d0", "Width / 2")
        self.assertAlmostEqual(sk.getDatum("d1").Value, 15)
        rows = {n: (f, v) for n, f, v in sketch.model_parameters(self.doc)}
        self.assertEqual(rows["d0"], ("Width / 2", "30 mm"))
        self.assertEqual(rows["d1"], ("d0 / 2", "15 mm"))
        sketch.set_dimension(self.doc, "d1", "12")  # a plain number uses the part's units
        self.assertEqual({n: (f, v) for n, f, v in sketch.model_parameters(self.doc)}["d1"], ("", "12 mm"))

    def test_bad_input(self):
        self.line_sketch()
        sketch.name_new_dimensions(self.doc)
        with self.assertRaises(ValueError):
            sketch.set_dimension(self.doc, "nope", "1")
        with self.assertRaises(ValueError):
            sketch.set_dimension(self.doc, "d0", " ")
        r = safe.run_safely("bad", lambda: sketch.set_dimension(self.doc, "d0", "Missing * 2"), self.doc)
        self.assertFalse(r.ok)

    def test_rename_keeps_formulas(self):
        self.line_sketch()
        sketch.name_new_dimensions(self.doc)
        sketch.set_dimension(self.doc, "d1", "d0 / 2")
        sketch.rename_dimension(self.doc, "d0", "Len")
        rows = {n: f for n, f, _ in sketch.model_parameters(self.doc)}
        self.assertEqual(rows["d1"], "Len / 2")
        document.set_parameter(self.doc, "Width", "1 mm")
        for bad in ("mm", "Width", "2x", "d1"):
            with self.assertRaises(ValueError, msg=bad):
                sketch.rename_dimension(self.doc, "Len", bad)

    def test_translation_roundtrip(self):
        sk = self.line_sketch()
        sketch.name_new_dimensions(self.doc)
        document.set_parameter(self.doc, "Width", "1 mm")
        expr = sketch.to_expression(self.doc, "Width + d0*2 + sin(30)")
        self.assertEqual(expr, "InCadParameters.Width + %s.Constraints.d0*2 + sin(30)" % sk.Name)
        self.assertEqual(sketch.to_display(self.doc, expr), "Width + d0*2 + sin(30)")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_sketch.py` → Expected: `cannot import name 'sketch'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/sketch.py`:
```python
"""InCad sketches: create on a plane or a flat face, status, named dimensions (d0, d1, …) and formulas that use
parameter and dimension names. Pure model logic: no Qt, no GUI."""
import re

import FreeCAD as App

from incad.core import document

DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")
_DNAME = re.compile(r"^d(\d+)$")
_TOKEN = re.compile(r"(?<![\w.<>])([A-Za-z_][A-Za-z0-9_]*)(?![\w(.])")


def is_sketch(obj):
    return obj is not None and getattr(obj, "TypeId", "") == "Sketcher::SketchObject"


def valid_support(obj, sub=""):
    """True for an origin plane, a datum plane or a flat face."""
    if obj is None:
        return False
    if obj.TypeId in ("App::Plane", "PartDesign::Plane"):
        return True
    if sub.startswith("Face"):
        try:
            face = obj.getSubObject(sub)
        except Exception:
            return False
        return face is not None and face.Surface.TypeId == "Part::GeomPlane"
    return False


def _next_label(doc, stem):
    used = {o.Label for o in doc.Objects}
    n = 1
    while "%s%d" % (stem, n) in used:
        n += 1
    return "%s%d" % (stem, n)


def make_sketch(body, support, sub=""):
    """A sketch in `body`, attached to `support` (+ face name), placed after End of Part."""
    if not valid_support(support, sub):
        raise ValueError("Pick a plane or a flat face to sketch on")
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    sk.AttachmentSupport = [(support, sub)]
    sk.MapMode = "FlatFace"
    sk.Label = _next_label(body.Document, "Sketch")
    body.Document.recompute()
    return sk


def status(sk):
    return {"dof": sk.DoF, "fully": bool(sk.FullyConstrained), "conflicting": list(sk.ConflictingConstraints),
            "redundant": list(sk.RedundantConstraints), "malformed": list(sk.MalformedConstraints)}


def _sketches(doc):
    return [o for o in doc.Objects if is_sketch(o)]


def dimensions(doc):
    """[(name, sketch, index)] for every named dimension, in document order."""
    out = []
    for sk in _sketches(doc):
        for i, c in enumerate(sk.Constraints):
            if c.Type in DIMENSIONAL and c.Name:
                out.append((c.Name, sk, i))
    return out


def find_dimension(doc, name):
    for n, sk, i in dimensions(doc):
        if n == name:
            return sk, i
    return None, None


def _used_names(doc):
    names = {c.Name for sk in _sketches(doc) for c in sk.Constraints if c.Name}
    return names | {n for n, _, _ in document.list_parameters(doc)}


def name_new_dimensions(doc):
    """Give every unnamed driving dimension the next free dN name; returns the names given."""
    numbers = [int(m.group(1)) for m in (_DNAME.match(n) for n in _used_names(doc)) if m]
    nxt = max(numbers) + 1 if numbers else 0
    added = []
    for sk in _sketches(doc):
        for i, c in enumerate(sk.Constraints):
            if c.Type in DIMENSIONAL and not c.Name and c.Driving:
                name = "d%d" % nxt
                nxt += 1
                sk.renameConstraint(i, name)
                added.append(name)
    return added


def _refs(doc):
    """plain name -> FreeCAD expression path, for user parameters and named dimensions."""
    refs = {n: "%s.%s" % (document.PARAMS_NAME, n) for n, _, _ in document.list_parameters(doc)}
    for name, sk, _ in dimensions(doc):
        refs[name] = "%s.Constraints.%s" % (sk.Name, name)
    return refs


def to_expression(doc, text):
    refs = _refs(doc)
    return _TOKEN.sub(lambda m: refs.get(m.group(1), m.group(1)), text)


def to_display(doc, expr):
    for path, name in sorted(((p, n) for n, p in _refs(doc).items()), key=lambda pn: -len(pn[0])):
        expr = expr.replace(path, name)
    return re.sub(r"(?<![\w])\.Constraints\.([A-Za-z_]\w*)", r"\1", expr)


def _expression_of(obj, path):
    for p, e in obj.ExpressionEngine:
        if p.lstrip(".") == path:
            return e
    return ""


def model_parameters(doc):
    """[(name, formula with plain names or '', value text)] for every named dimension."""
    rows = []
    for name, sk, _ in dimensions(doc):
        expr = _expression_of(sk, "Constraints." + name)
        rows.append((name, to_display(doc, expr) if expr else "", document._format(sk.getDatum(name))))
    return rows


def set_dimension(doc, name, text):
    """Set a named dimension to a value ('40 mm', '12') or a formula ('d3*2', 'Width/2').
    Call inside safe.run_safely: a failing formula raises and must be rolled back."""
    sk, index = find_dimension(doc, name)
    if sk is None:
        raise ValueError("No dimension named %r" % name)
    text = (text or "").strip()
    if not text:
        raise ValueError("%s needs a value" % name)
    path = "Constraints." + name
    try:
        quantity = App.Units.Quantity(text)
    except Exception:
        quantity = None
    if quantity is not None:
        if quantity.Unit == App.Units.Quantity("1").Unit:  # a plain number: the part's length unit or degrees
            unit = "deg" if sk.Constraints[index].Type == "Angle" else (document.part_units(doc) or "mm")
            quantity = App.Units.Quantity("%s %s" % (quantity.Value, unit))
        sk.setExpression(path, None)
        try:
            sk.setDatum(name, quantity)
        except Exception as e:
            raise ValueError("%s cannot be %s: %s" % (name, text, e))
    else:
        try:
            sk.setExpression(path, to_expression(doc, text))
        except Exception as e:
            raise ValueError("Invalid formula for %s: %s" % (name, e))
    doc.recompute()
    if "Invalid" in sk.State or status(sk)["conflicting"]:
        raise ValueError("%s = %s cannot be satisfied: %s" % (name, text, sk.getStatusString()))


def rename_dimension(doc, old, new):
    sk, index = find_dimension(doc, old)
    if sk is None:
        raise ValueError("No dimension named %r" % old)
    if not document._NAME_RE.match(new or ""):
        raise ValueError("A name starts with a letter or _ and has only letters, digits and _ (got %r)" % new)
    if document._is_literal(new):
        raise ValueError("%r is a unit symbol; choose another name" % new)
    if new != old and new in _used_names(doc):
        raise ValueError("%r is already used" % new)
    sk.renameConstraint(index, new)
    doc.recompute()
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_sketch.py` → Expected: 9 tests `OK`. If `to_display` misses FreeCAD's own
normalisation of a path (e.g. `<<Sketch>>` labels), print the raw `ExpressionEngine` entry and extend `to_display`
with that form; the tests stay.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/sketch.py tests/headless/test_sketch.py && git commit -m "InCad 1c: sketch model logic, named dimensions, formulas with plain names"
```

---

### Task 3: Value box

**Files:**
- Create: `InCad/incad/ui/value_box.py`, `tests/widgets/test_value_box.py`

**Interfaces:**
- Produces: `ValueBox(name, text, theme="light", parent=None)` (a frameless tool window): signals
  `applied(str name, str text)`, `closed()`; attributes `name`, `edit` (QLineEdit, initial text selected);
  `insert(name)` (replaces the selection / inserts at the cursor), `show_near(global_pos)`. Enter applies and closes;
  Esc closes without applying.

- [ ] **Step 1: Write the failing test**

`tests/widgets/test_value_box.py`:
```python
import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.ui.value_box import ValueBox


class ValueBoxTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.box = ValueBox("d1", "20 mm", "light")
        self.seen = []
        self.box.applied.connect(lambda n, t: self.seen.append((n, t)))
        self.box.show_near(QtCore.QPoint(300, 300))

    def tearDown(self):
        self.box.close()

    def test_enter_applies_and_closes(self):
        from PySide6.QtTest import QTest
        self.box.edit.setText("25 mm")
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Return)
        self.assertEqual(self.seen, [("d1", "25 mm")])
        self.assertFalse(self.box.isVisible())

    def test_escape_cancels(self):
        from PySide6.QtTest import QTest
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Escape)
        self.assertEqual(self.seen, [])
        self.assertFalse(self.box.isVisible())

    def test_insert_replaces_selection_then_typing_builds_a_formula(self):
        from PySide6.QtTest import QTest
        self.box.insert("d0")
        QTest.keyClicks(self.box.edit, "*2")
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Return)
        self.assertEqual(self.seen, [("d1", "d0*2")])

    def test_empty_text_applies_nothing(self):
        from PySide6.QtTest import QTest
        self.box.edit.setText("  ")
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Return)
        self.assertEqual(self.seen, [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_widgets.sh test_value_box.py` → Expected: `No module named 'incad.ui.value_box'`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/value_box.py`:
```python
"""Floating box to type a dimension's value or formula (Inventor's edit-dimension box). Enter applies, Esc cancels.
While it is open, clicking a dimension or a parameter inserts that name at the cursor."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class ValueBox(QtWidgets.QFrame):
    applied = Signal(str, str)
    closed = Signal()

    def __init__(self, name, text, theme="light", parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setObjectName("InCadValueBox")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.name = name
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.addWidget(QtWidgets.QLabel(name + " ="))
        self.edit = QtWidgets.QLineEdit(text)
        self.edit.setMinimumWidth(170)
        self.edit.selectAll()
        self.edit.returnPressed.connect(self._apply)
        self.edit.installEventFilter(self)
        row.addWidget(self.edit)
        hint = QtWidgets.QLabel("Enter ✓  Esc ✕")
        hint.setObjectName("InCadValueHint")
        row.addWidget(hint)
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadValueBox {{ background: {panel}; border: 1px solid {accent}; border-radius: 8px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadValueHint {{ color: {text_dim}; font-size: 10px; }}"
            " QLineEdit {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 4px;"
            " padding: 2px 4px; }}".format(**p))

    def show_near(self, global_pos):
        self.adjustSize()
        self.move(global_pos + QtCore.QPoint(16, 16))
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def insert(self, name):
        self.edit.insert(name)
        self.edit.setFocus()

    def _apply(self):
        text = self.edit.text().strip()
        self.close()
        if text:
            self.applied.emit(self.name, text)

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self.close()
            return True
        return False

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_widgets.sh test_value_box.py` → Expected: 4 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/value_box.py tests/widgets/test_value_box.py && git commit -m "InCad 1c: value box for dimensions"
```

---

### Task 4: Browser parameters (model + user), row detail, status DOF click

**Files:**
- Modify: `InCad/incad/core/nodes.py`, `InCad/incad/core/tree.py`, `InCad/incad/ui/browser.py`,
  `InCad/incad/ui/statusbar.py`, `tests/widgets/test_browser.py`, `tests/widgets/test_titlebar_status.py`,
  `tests/headless/test_tree.py`

**Interfaces:**
- Produces: `Node.detail: str = ""`; sketch nodes get detail `"✓"` (fully constrained) or `"<n> DOF"`;
  `ModelBrowser.set_parameters(rows, model_rows=())` (model rows first, Name editable for renaming),
  signals `parameterRenamed(str old, str new)` and `parameterClicked(str name)` (click on a Name cell);
  `tree_rows()`/`item_by_label()` use the node label (not the shown detail); `StatusBar.dofClicked` signal.

- [ ] **Step 1: Write the failing tests**

Append to `tests/headless/test_tree.py` (inside `TreeTest`):
```python
    def test_sketch_detail(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        sk = self.doc.getObject("Sketch")
        node = [n for d, n in nodes.flatten(tree.build(self.doc)) if n.label == "Sketch"][0]
        self.assertEqual(node.detail, "✓" if sk.FullyConstrained else "%d DOF" % sk.DoF)
```

Append to `tests/widgets/test_browser.py`:
```python
class ModelParametersTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.b = ModelBrowser("light")
        self.b.set_parameters([("Width", "", "80 mm")], [("d0", "", "40 mm"), ("d1", "d0 * 2", "80 mm")])
        self.events = []
        self.b.parameterSet.connect(lambda n, t: self.events.append(("set", n, t)))
        self.b.parameterRenamed.connect(lambda o, n: self.events.append(("rename", o, n)))
        self.b.parameterClicked.connect(lambda n: self.events.append(("click", n)))
        self.b.parameterRemoved.connect(lambda n: self.events.append(("remove", n)))

    def test_model_rows_first(self):
        self.assertEqual(self.b.parameter_rows(),
                         [("d0", "40 mm", "40 mm"), ("d1", "d0 * 2", "80 mm"), ("Width", "80 mm", "80 mm")])

    def test_rename_model_parameter(self):
        self.b.params.item(0, 0).setText("Len")
        self.assertEqual(self.events, [("rename", "d0", "Len")])

    def test_edit_model_value(self):
        self.b.params.item(1, 1).setText("d0 * 3")
        self.assertEqual(self.events, [("set", "d1", "d0 * 3")])

    def test_model_rows_cannot_be_removed(self):
        self.b.params.setCurrentCell(0, 0)
        self.b.remove_selected_parameter()
        self.assertEqual(self.events, [])

    def test_click_on_name_reports_it(self):
        self.b.params.cellClicked.emit(2, 0)
        self.b.params.cellClicked.emit(2, 1)
        self.assertEqual(self.events, [("click", "Width")])


class DetailTest(unittest.TestCase):
    def test_detail_is_shown_but_label_stays(self):
        qtapp.app()
        b = ModelBrowser("light")
        b.set_nodes([Node("part", "P", children=[Node("sketch", "Sketch1", "Sketch", detail="3 DOF")])])
        item = b.item_by_label("Sketch1")
        self.assertIn("3 DOF", item.text(0))
        self.assertEqual([r[1] for r in b.tree_rows()], ["P", "Sketch1"])
```

Append to `tests/widgets/test_titlebar_status.py` (inside `StatusBarTest`):
```python
    def test_dof_click(self):
        from PySide6.QtTest import QTest
        from incad.qt import QtCore
        seen = []
        self.sb.dofClicked.connect(lambda: seen.append(1))
        self.sb.set_dof(3)
        self.sb.show()
        QTest.mouseClick(self.sb._dof, QtCore.Qt.LeftButton)
        self.sb.hide()
        self.assertEqual(seen, [1])
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_tree.py`, `tests/run_widgets.sh test_browser.py`, `tests/run_widgets.sh test_titlebar_status.py`
Expected: `Node` has no `detail`, `set_parameters` takes no `model_rows`, no `dofClicked`.

- [ ] **Step 3: Implement**

`InCad/incad/core/nodes.py` — add the field `detail: str = ""  # shown after the label (e.g. a sketch's DOF)` after
`tooltip`.

`InCad/incad/core/tree.py` — in `_obj_node` replace the return with:
```python
    node = Node(kind, obj.Label, obj.Name, state, _tooltip(obj, state))
    if kind == "sketch":
        try:
            node.detail = "✓" if obj.FullyConstrained else "%d DOF" % obj.DoF
        except Exception:
            node.detail = ""
    return node
```

`InCad/incad/ui/browser.py`:
1. Below `STATE_ROLE` add `LABEL_ROLE = QtCore.Qt.UserRole + 3` and `PARAM_KIND_ROLE = QtCore.Qt.UserRole + 4`.
2. Signals: add `parameterRenamed = Signal(str, str)` and `parameterClicked = Signal(str)`.
3. In `__init__` after `self.params.itemChanged.connect(self._on_param_changed)` add
   `self.params.cellClicked.connect(self._on_param_clicked)`.
4. In `_item`, replace `item = QtWidgets.QTreeWidgetItem([node.label])` with:
```python
        item = QtWidgets.QTreeWidgetItem([node.label + ("    " + node.detail if node.detail else "")])
        item.setData(0, LABEL_ROLE, node.label)
```
5. In `tree_rows` use `i.data(0, LABEL_ROLE)` instead of `i.text(0)`; in `item_by_label` compare
   `item.data(0, LABEL_ROLE) == label`.
6. Replace `set_parameters` with:
```python
    def set_parameters(self, rows, model_rows=()):
        """Model parameters (named sketch dimensions; renamable) first, then user parameters."""
        accent = QtGui.QColor(themes.PALETTES[self._theme]["accent"])
        self._loading = True
        try:
            self.params.setRowCount(0)
            for kind, entries in (("model", model_rows), ("user", rows)):
                for name, formula, value in entries:
                    r = self.params.rowCount()
                    self.params.insertRow(r)
                    name_item = QtWidgets.QTableWidgetItem(name) if kind == "model" else self._readonly(name)
                    name_item.setData(PARAM_KIND_ROLE, kind)
                    name_item.setData(NAME_ROLE, name)
                    if kind == "model":
                        name_item.setForeground(QtGui.QBrush(accent))
                        name_item.setToolTip("Model parameter (a sketch dimension) — type a new name to rename it")
                    self.params.setItem(r, 0, name_item)
                    self.params.setItem(r, 1, QtWidgets.QTableWidgetItem(formula or value))
                    self.params.setItem(r, 2, self._readonly(value))
        finally:
            self._loading = False
```
7. Replace `_on_param_changed` with:
```python
    def _on_param_changed(self, item):
        if self._loading or not self._params_enabled:
            return
        r = item.row()
        name_item, value_item = self.params.item(r, 0), self.params.item(r, 1)
        if name_item is not None and name_item.data(PARAM_KIND_ROLE) == "model" and item.column() == 0:
            old, new = name_item.data(NAME_ROLE), name_item.text().strip()
            if new and new != old:
                self.parameterRenamed.emit(old, new)
            return
        name = name_item.data(NAME_ROLE) or name_item.text().strip() if name_item else ""
        value = value_item.text().strip() if value_item else ""
        if name and value:
            self.parameterSet.emit(name, value)
```
8. In `remove_selected_parameter`, after `item = self.params.item(r, 0)` add:
```python
        if item is not None and item.data(PARAM_KIND_ROLE) == "model":
            return  # dimensions live in their sketch
```
9. Add:
```python
    def _on_param_clicked(self, row, column):
        item = self.params.item(row, 0)
        if column == 0 and item is not None and (item.data(NAME_ROLE) or item.text()):
            self.parameterClicked.emit(item.data(NAME_ROLE) or item.text())
```

`InCad/incad/ui/statusbar.py` — import `Signal` from `incad.qt`; add the class attribute `dofClicked = Signal()`;
at the end of `__init__` add `self._dof.installEventFilter(self)` and
`self._dof.setCursor(QtCore.Qt.PointingHandCursor)` and `self._dof.setToolTip("Show the geometry that is still free")`;
add:
```python
    def eventFilter(self, obj, event):
        if obj is self._dof and event.type() == QtCore.QEvent.MouseButtonPress:
            self.dofClicked.emit()
            return True
        return False
```

- [ ] **Step 4: Run to verify they pass**

Run: the three commands from Step 2 and `tests/run_fast.sh` → Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add InCad tests && git commit -m "InCad 1c: model parameters in the browser, sketch DOF detail, DOF click"
```

---

### Task 5: Navigator click hooks

**Files:**
- Modify: `InCad/incad/ui/nav.py`
- Create: `tests/widgets/test_nav_hooks.py`

**Interfaces:**
- Produces: `Navigator.click_hook` and `Navigator.dblclick_hook`: `callable(view, viewport, x, y) -> bool`; True
  takes a left click (press and its release are consumed, nothing reaches FreeCAD) or a double-click.

- [ ] **Step 1: Write the failing test**

`tests/widgets/test_nav_hooks.py`:
```python
import unittest

from widgets import qtapp
from incad.qt import QtCore, QtGui, QtWidgets
from incad.core import gestures
from incad.ui.nav import Navigator


def ev(kind, button, buttons):
    t = {"press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease,
         "dbl": QtCore.QEvent.MouseButtonDblClick}[kind]
    return QtGui.QMouseEvent(t, QtCore.QPointF(10, 10), QtCore.QPointF(10, 10), button, buttons, QtCore.Qt.NoModifier)


class HooksTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.nav = Navigator(lambda *a: None)
        self.w = QtWidgets.QWidget()
        self.nav._attached[self.w] = [None, gestures.Gestures(), QtCore.Qt.NoModifier]
        self.calls = []

    def test_click_hook_takes_press_and_release(self):
        self.nav.click_hook = lambda *a: (self.calls.append(a[2:]), True)[1]
        L = QtCore.Qt.LeftButton
        self.assertTrue(self.nav.eventFilter(self.w, ev("press", L, L)))
        self.assertTrue(self.nav.eventFilter(self.w, ev("release", L, QtCore.Qt.NoButton)))
        self.assertEqual(self.calls, [(10.0, 10.0)])
        self.assertEqual(self.nav._attached[self.w][1].state, "idle")

    def test_declined_click_goes_through_gestures(self):
        self.nav.click_hook = lambda *a: False
        L = QtCore.Qt.LeftButton
        self.assertTrue(self.nav.eventFilter(self.w, ev("press", L, L)))  # held back by the gesture rules
        self.assertEqual(self.nav._attached[self.w][1].state, "left_held")

    def test_dblclick_hook(self):
        self.nav.dblclick_hook = lambda *a: True
        L = QtCore.Qt.LeftButton
        self.assertTrue(self.nav.eventFilter(self.w, ev("dbl", L, L)))
        self.nav.dblclick_hook = lambda *a: False
        self.assertFalse(self.nav.eventFilter(self.w, ev("dbl", L, L)))
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_widgets.sh test_nav_hooks.py` → Expected: `test_click_hook_takes_press_and_release` and
`test_dblclick_hook` fail (hooks are ignored).

- [ ] **Step 3: Implement**

In `InCad/incad/ui/nav.py` `Navigator.__init__` add:
```python
        self.click_hook = None      # callable(view, viewport, x, y) -> True takes the left click
        self.dblclick_hook = None   # same for left double-clicks
        self._swallow_release = False
```
and in `eventFilter`, right after `pos = event.position()`, add:
```python
            if event.button() == QtCore.Qt.LeftButton:
                if kind == "press" and machine.state == "idle" and self.click_hook is not None \
                        and self.click_hook(view, obj, pos.x(), pos.y()):
                    self._swallow_release = True
                    return True
                if kind == "release" and self._swallow_release:
                    self._swallow_release = False
                    return True
                if kind == "dblclick" and self.dblclick_hook is not None \
                        and self.dblclick_hook(view, obj, pos.x(), pos.y()):
                    return True
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_widgets.sh test_nav_hooks.py` → Expected: 3 tests `OK`; `tests/run_widgets.sh test_gestures.py` OK.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/nav.py tests/widgets/test_nav_hooks.py && git commit -m "InCad 1c: navigator click and double-click hooks"
```

---

### Task 6: Sketch session (start, pick, edit, finish)

**Files:**
- Create: `InCad/incad/ui/sketch_session.py`
- Modify: `InCad/incad/core/safe.py`

**Interfaces:**
- Produces: `SketchSession(on_change=None)`: `picking`, `start()` (selected support → new sketch in edit; else
  pick mode with origin shown), `cancel_pick()`, `edit(sk)`, `finish()`, `editing() -> sketch|None` (static),
  selection-observer method `addSelection(doc, obj, sub, pnt)`; `safe.edit_open()` is False while a sketch is
  being edited (Sketcher commits each tool step itself). Tested through the GUI tests of Task 7.

- [ ] **Step 1: Implement**

`InCad/incad/core/safe.py` — in `edit_open()` replace the `return bool(Gui.Control.activeDialog()) or …` line with:
```python
        vp = gdoc.getInEdit() if gdoc is not None else None
        if vp is not None and getattr(getattr(vp, "Object", None), "TypeId", "") == "Sketcher::SketchObject":
            return False  # InCad's own sketch editing: Sketcher commits each tool step itself
        return bool(Gui.Control.activeDialog()) or vp is not None
```

`InCad/incad/ui/sketch_session.py`:
```python
"""Starting, editing and finishing sketches the Inventor way (GUI side of incad.core.sketch)."""
from incad.core import document, log, safe, sketch
from incad.qt import QtCore


class SketchSession:
    def __init__(self, on_change=None):
        self.picking = False
        self._on_change = on_change
        self._origin = None  # (view object, was visible) while picking

    def _changed(self):
        if self._on_change is not None:
            self._on_change()

    @staticmethod
    def _resolve(obj, sub):
        """A pick on a Body means its Tip feature; 'Pad.Face6' style paths name the feature and the face."""
        if "." in sub:
            parts = sub.split(".")
            child = obj.Document.getObject(parts[-2]) if len(parts) > 1 else None
            return (child or obj), parts[-1]
        if obj is not None and obj.TypeId == "PartDesign::Body" and sub.startswith("Face") and obj.Tip is not None:
            return obj.Tip, sub
        return obj, sub

    def start(self):
        import FreeCAD as App
        import FreeCADGui as Gui
        doc = App.ActiveDocument
        if not document.is_incad_part(doc):
            raise ValueError("Create or open an InCad part first")
        for sel in Gui.Selection.getSelectionEx(doc.Name):
            for sub in (sel.SubElementNames or ("",)):
                support, face = self._resolve(sel.Object, sub)
                if sketch.valid_support(support, face):
                    Gui.Selection.clearSelection()
                    return self._create(support, face)
        self._begin_pick(doc)
        return None

    def _begin_pick(self, doc):
        import FreeCADGui as Gui
        self.cancel_pick()
        body = document.primary_body(doc)
        if body is not None:
            vo = body.Origin.ViewObject
            self._origin = (vo, vo.Visibility)
            vo.Visibility = True
        self.picking = True
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        log.report("info", "Pick a plane or a flat face for the new sketch (Esc cancels)")
        self._changed()

    def cancel_pick(self):
        import FreeCADGui as Gui
        if not self.picking:
            return
        self.picking = False
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        if self._origin is not None:
            vo, was = self._origin
            try:
                vo.Visibility = was
            except Exception:
                pass
            self._origin = None
        self._changed()

    def addSelection(self, doc_name, obj_name, sub, pnt):
        import FreeCAD as App
        if not self.picking:
            return
        obj = App.getDocument(doc_name).getObject(obj_name)
        support, face = self._resolve(obj, sub)
        if sketch.valid_support(support, face):
            QtCore.QTimer.singleShot(0, lambda: self._picked(support, face))
        else:
            log.report("warning", "That is not flat: pick a plane or a flat face")

    def _picked(self, support, face):
        import FreeCADGui as Gui
        self.cancel_pick()
        Gui.Selection.clearSelection()
        self._create(support, face)

    def _create(self, support, face):
        import FreeCAD as App
        doc = App.ActiveDocument
        body = document.primary_body(doc)
        r = safe.run_safely("New Sketch", lambda: sketch.make_sketch(body, support, face), doc)
        if r.ok:
            self.edit(r.value)
            return r.value
        return None

    def edit(self, sk):
        import FreeCADGui as Gui
        vo = sk.ViewObject
        vo.EditingWorkbench = ""  # stay in InCad while sketching
        if "Autoconstraints" in vo.PropertiesList:
            vo.Autoconstraints = True
        Gui.getDocument(sk.Document.Name).setEdit(sk.Name)
        self._changed()

    def finish(self):
        import FreeCAD as App
        import FreeCADGui as Gui
        gdoc = Gui.ActiveDocument
        if gdoc is not None and gdoc.getInEdit() is not None:
            gdoc.resetEdit()
        if App.ActiveDocument is not None:
            App.ActiveDocument.recompute()
        self._changed()

    @staticmethod
    def editing():
        """The sketch being edited, or None."""
        import FreeCADGui as Gui
        gdoc = Gui.ActiveDocument
        vp = gdoc.getInEdit() if gdoc is not None else None
        obj = getattr(vp, "Object", None)
        return obj if sketch.is_sketch(obj) else None
```

- [ ] **Step 2: Syntax check and fast suite**

Run: `/Applications/FreeCAD.app/Contents/Resources/bin/python -c "import ast; ast.parse(open('InCad/incad/ui/sketch_session.py').read())"`
and `tests/run_fast.sh` → Expected: no output / `FAST SUITES PASSED`. (Behaviour is tested in Task 7.)

- [ ] **Step 3: Commit**

```bash
git add InCad/incad/ui/sketch_session.py InCad/incad/core/safe.py && git commit -m "InCad 1c: sketch session (start, pick, edit, finish)"
```

---

### Task 7: Shell wiring and GUI tests

**Files:**
- Modify: `InCad/incad/ui/shell.py`, `tests/gui/test_nav.py`
- Create: `tests/gui/test_sketch.py`

**Interfaces:**
- Produces (`incad.ui.shell`): `Shell.sketches` (SketchSession), `Shell.value_box`, `Shell.shortcut_action(cmd_id)`,
  `Shell.open_value_box(sk, name)`; module `sketch_session()` (raises `ValueError` when InCad is not active).

- [ ] **Step 1: Write the failing GUI tests**

In `tests/gui/test_nav.py` change `test_6_flick_north_runs_home_view`: rename it to
`test_6_flick_north_starts_a_sketch`, assert `ran == ["sketch.start"]`, and add after the assertion
`shell.sketch_session().cancel_pick()`; update the name in the `harness.run([...])` list.

`tests/gui/test_sketch.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad import actions  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, document, params, prefs, sketch  # noqa: E402
from incad.ui import shell, theme  # noqa: E402

mw = Gui.getMainWindow()
L = QtCore.Qt.LeftButton
BASE = {}
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def sk():
    return s().sketches.editing()


def sketch_settings():
    return {g: params.snapshot(g, keys) for g, keys in theme.SKETCH_KEYS.items()}


def plane(role):
    body = document.primary_body(doc())
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def click_view():
    v = Gui.ActiveDocument.ActiveView
    vp = v.graphicsView().viewport()
    p = QtCore.QPointF(vp.width() * 0.5, vp.height() * 0.5)
    for t, bs in ((QtCore.QEvent.MouseButtonPress, L), (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
        QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(t, p, QtCore.QPointF(vp.mapToGlobal(p.toPoint())),
                                                                L, bs, QtCore.Qt.NoModifier))
        harness.pump(60)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    BASE["sketch"] = sketch_settings()
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)


def test_1_sketcher_commands_exist():
    missing = [c for _, _, c, _ in actions.SKETCHER.values() if c not in Gui.listCommands()]
    assert not missing, missing


def test_2_start_on_selected_plane_stays_in_incad():
    Gui.Selection.addSelection(doc().Name, plane("XY_Plane").Name)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    assert sk() is not None and sk().Label == "Sketch1"
    assert Gui.activeWorkbench().name() == "InCadWorkbench", Gui.activeWorkbench().name()
    assert s().active
    assert s().ribbon.tab_names()[0] == "Sketch", s().ribbon.tab_names()
    assert s().status.texts()["dof"] != ""
    ST["sk"] = sk().Name


def test_3_settings_applied_while_active():
    p = App.ParamGet(theme.SKETCH_TOOLS)
    assert p.GetInt("OnViewParameterVisibility", 0) == 1
    assert not App.ParamGet(theme.SKETCH_ROOT).GetBool("ShowDialogOnDistanceConstraint", True)


def test_4_dimension_names_and_value_box():
    k = sk()
    k.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)))
    k.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0)))
    harness.pump(400)
    assert s().value_box is None, "drawing must not open the value box"
    k.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
    harness.pump(600)
    assert k.Constraints[-1].Name == "d0", [c.Name for c in k.Constraints]
    box = s().value_box
    assert box is not None and box.isVisible() and box.name == "d0"
    box.edit.setText("40")
    QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
    harness.pump(600)
    assert abs(k.getDatum("d0").Value - 40) < 1e-6, k.getDatum("d0")


def test_5_click_a_dimension_inserts_its_name():
    k = sk()
    k.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10))
    harness.pump(600)
    box = s().value_box
    assert box is not None and box.name == "d1"
    index = [c.Name for c in k.Constraints].index("d0")
    Gui.Selection.setPreselection(k, "Constraint%d" % (index + 1))
    click_view()
    assert box.edit.text() == "d0", box.edit.text()
    QTest.keyClicks(box.edit, "/2")
    QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
    harness.pump(600)
    rows = {n: (f, v) for n, f, v in sketch.model_parameters(doc())}
    assert rows["d1"] == ("d0 / 2", "20 mm"), rows
    assert ("d1", "d0 / 2", "20 mm") in s().browser.parameter_rows(), s().browser.parameter_rows()


def test_6_parameter_click_and_rename():
    document.set_parameter(doc(), "Width", "100 mm")
    s().open_value_box(sk(), "d0")
    harness.pump(200)
    s().browser.parameterClicked.emit("Width")
    box = s().value_box
    assert box.edit.text() == "Width", box.edit.text()
    QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
    harness.pump(600)
    s().browser.parameterRenamed.emit("d0", "Len")
    harness.pump(600)
    rows = {n: (f, v) for n, f, v in sketch.model_parameters(doc())}
    assert rows["Len"] == ("Width", "100 mm") and rows["d1"][0] == "Len / 2", rows


def test_7_shortcuts_follow_the_mode():
    assert s().shortcut_action("sketch.line").isEnabled()
    assert not s().shortcut_action("sketch.start").isEnabled()


def test_8_right_click_in_a_sketch():
    v = Gui.ActiveDocument.ActiveView
    vp = v.graphicsView().viewport()
    p = QtCore.QPointF(vp.width() * 0.2, vp.height() * 0.8)
    R = QtCore.Qt.RightButton
    for t, bs in ((QtCore.QEvent.MouseButtonPress, R), (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
        QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(t, p, QtCore.QPointF(vp.mapToGlobal(p.toPoint())),
                                                                R, bs, QtCore.Qt.NoModifier))
        harness.pump(80)
    assert s().menu_kind == "sketch", s().menu_kind
    s().marking_menu.close()
    harness.pump(100)


def test_9_typing_never_triggers_sketch_shortcuts():
    ran = []
    original = commands.REGISTRY.run
    commands.REGISTRY.run = lambda i: (ran.append(i), original(i))[1]
    try:
        b = s().browser
        r = b.add_parameter_row()
        editor = b.params.findChild(QtWidgets.QLineEdit)
        QTest.keyClicks(editor, "Lcdrax")
        QTest.keyClick(editor, QtCore.Qt.Key_Escape)
        b.params.removeRow(r)
    finally:
        commands.REGISTRY.run = original
    assert not [i for i in ran if i.startswith("sketch.")], ran


def test_10_finish():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    assert sk() is None
    assert "Sketch" not in s().ribbon.tab_names()[:1] or s().ribbon.tab_names()[0] == "3D Model", s().ribbon.tab_names()
    assert s().shortcut_action("sketch.start").isEnabled()
    row = [r for r in s().browser.tree_rows() if r[1] == "Sketch1"]
    assert row, s().browser.tree_rows()


def test_11_pick_mode():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.start")
    harness.pump(500)
    assert s().sketches.picking
    Gui.Selection.addSelection(doc().Name, plane("XZ_Plane").Name)
    harness.pump(1000)
    assert not s().sketches.picking and sk() is not None and sk().Label == "Sketch2"
    commands.REGISTRY.run("sketch.finish")
    harness.pump(600)


def test_12_sketch_on_a_face():
    import headless.util as util
    body = document.primary_body(doc())
    base = util.add_rect_sketch(body, name="Base")
    pad = util.add_pad(body, base, 10)
    doc().recompute()
    top = [i + 1 for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    Gui.Selection.addSelection(doc().Name, pad.Name, "Face%d" % top)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1000)
    assert sk() is not None
    support = sk().AttachmentSupport[0]
    assert support[0].Name == pad.Name and support[1][0] == "Face%d" % top, support
    commands.REGISTRY.run("sketch.finish")
    harness.pump(600)


def test_13_leaving_incad_restores_sketch_settings():
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert sketch_settings() == BASE["sketch"], (sketch_settings(), BASE["sketch"])


harness.run([test_0_setup, test_1_sketcher_commands_exist, test_2_start_on_selected_plane_stays_in_incad,
             test_3_settings_applied_while_active, test_4_dimension_names_and_value_box,
             test_5_click_a_dimension_inserts_its_name, test_6_parameter_click_and_rename,
             test_7_shortcuts_follow_the_mode, test_8_right_click_in_a_sketch,
             test_9_typing_never_triggers_sketch_shortcuts, test_10_finish, test_11_pick_mode,
             test_12_sketch_on_a_face, test_13_leaving_incad_restores_sketch_settings])
```

- [ ] **Step 2: Run to verify they fail**

Announce the FreeCAD window. Run: `tests/run_gui.sh tests/gui/test_sketch.py` → Expected: failures from test_2 on
(`shell.sketch_session` missing).

- [ ] **Step 3: Implement the shell wiring**

In `InCad/incad/ui/shell.py`:

1. Imports: `from incad.ui.sketch_session import SketchSession` and `from incad.ui.value_box import ValueBox`.
2. `__init__`: add `self.sketches = SketchSession(on_change=self.schedule_refresh)`, `self.value_box = None`,
   `self._shortcuts = {}`, `self._geometry_counts = {}`.
3. `_capture()`: add `"sketch": {g: params.snapshot(g, keys) for g, keys in themes.SKETCH_KEYS.items()},`.
4. `_restore()`: add a step after "ViewCube colors":
```python
            ("Sketcher settings", lambda: [params.restore(g, v) for g, v in snap.get("sketch", {}).items()]),
```
5. `apply_theme()`: before `params.write(themes.VIEW_GROUP, themes.view_params(self.theme))` add:
```python
        for group, values in themes.sketch_params(self.theme, prefs.dimension_display()).items():
            params.write(group, values)
```
6. End of `_build()`: add
```python
        self.browser.parameterRenamed.connect(self._on_parameter_renamed)
        self.browser.parameterClicked.connect(self._on_parameter_clicked)
        self.status.dofClicked.connect(lambda: self.registry.run("sketch.show_dof"))
        self.navigator.click_hook = self._click_hook
        self.navigator.dblclick_hook = self._dblclick_hook
        self._build_shortcuts()
```
7. `_teardown()`: at the start add
```python
        self.sketches.cancel_pick()
        self._close_value_box()
        for act in self._shortcuts.values():
            try:
                self.mw.removeAction(act)
                act.deleteLater()
            except RuntimeError:
                pass
        self._shortcuts = {}
```
8. `_DocObserver.slotChangedObject` — replace with:
```python
    def slotChangedObject(self, obj, prop):
        self.callback()
        if prop in ("Constraints", "Geometry") and getattr(obj, "TypeId", "") == "Sketcher::SketchObject" \
                and self.sketch_callback is not None:
            self.sketch_callback(obj)
```
and give `_DocObserver.__init__` a second parameter `sketch_callback=None` stored as `self.sketch_callback`; in
`_install_hooks` create it as `_DocObserver(self.schedule_refresh, self._sketch_changed)`.
9. In `_refresh()` replace the block from `is_part = …` to the end of the `if is_part:/else:` with:
```python
        is_part = document.is_incad_part(doc)
        editing = self.sketches.editing() if is_part else None
        mode = "sketch" if editing is not None else "part" if is_part else "empty"
        self.ribbon.set_mode(mode)
        self.title.set_document_name(doc.Label if doc is not None else "")
        self.browser.set_nodes(tree.build(doc))
        from incad.core import sketch as sketches
        self.browser.set_parameters(document.list_parameters(doc) if is_part else [],
                                    sketches.model_parameters(doc) if is_part else [])
        self.browser.set_parameters_enabled(is_part)
        self.status.set_units(document.part_units(doc) if is_part else None)
        self.status.set_dof(editing.DoF if editing is not None else None)
        if is_part:
            bodies = document.bodies(doc)
            features = sum(1 for b in bodies for o in b.Group if o.TypeId != "Sketcher::SketchObject")
            self.status.set_stats(len(bodies), features)
            if editing is not None:
                self.status.set_prompt("Sketch: draw and dimension, then Finish Sketch (Esc)")
            elif self.sketches.picking:
                self.status.set_prompt("Pick a plane or a flat face for the new sketch (Esc cancels)")
            else:
                self.status.set_prompt("Ready")
        else:
            self.status.set_stats(None, None)
            self.status.set_prompt("Create or open a part" if doc is None else "This file was not made in InCad")
        for cmd_id, act in self._shortcuts.items():
            if cmd_id == "_esc":
                act.setEnabled(self.sketches.picking)
                continue
            ctx = self.registry.get(cmd_id).contexts
            act.setEnabled(commands.ANY in ctx or mode in ctx)
```
10. `_open_marking_menu()`: at the start (after imports) add
```python
        if self.sketches.editing() is not None:
            return self._show_marking_menu("sketch", global_pos, flick)
```
11. `_on_feature_activated(name)`: replace the body with
```python
        from incad.core import context
        context.set_target(name)
        self.registry.run("browser.edit")
```
12. `_on_parameter_set(name, text)`: replace the body with
```python
        from incad.core import document, safe
        from incad.core import sketch as sketches
        doc = self._doc()
        if doc is not None:
            if sketches.find_dimension(doc, name)[0] is not None:
                safe.run_safely("Set %s" % name, lambda: sketches.set_dimension(doc, name, text), doc)
            else:
                safe.run_safely("Set %s" % name, lambda: document.set_parameter(doc, name, text), doc)
        self.schedule_refresh()
```
13. New methods in `Shell`:
```python
    # ----- sketching -----
    def _build_shortcuts(self):
        """Single-key shortcuts (Inventor defaults) for registry commands; enabled per mode in _refresh."""
        menu_owned = {"file.new"}
        for cmd_id in self.registry.ids():
            cmd = self.registry.get(cmd_id)
            if not cmd.shortcut or cmd_id in menu_owned:
                continue
            act = QAction(cmd.label, self.mw)
            act.setShortcut(QtGui.QKeySequence(cmd.shortcut))
            act.setShortcutContext(QtCore.Qt.WindowShortcut)
            act.triggered.connect(lambda _=False, i=cmd_id: self.registry.run(i))
            self.mw.addAction(act)
            self._shortcuts[cmd_id] = act
        self._esc = QAction("Cancel", self.mw)
        self._esc.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape))
        self._esc.setEnabled(False)
        self._esc.triggered.connect(self.sketches.cancel_pick)
        self.mw.addAction(self._esc)
        self._shortcuts["_esc"] = self._esc

    def shortcut_action(self, cmd_id):
        return self._shortcuts.get(cmd_id)

    def _sketch_changed(self, sk):
        """New dimensions get dN names; one added by the Dimension tool (no new geometry) opens the value box."""
        QtCore.QTimer.singleShot(0, lambda: self._name_dimensions(sk))

    def _name_dimensions(self, sk):
        from incad.core import document
        from incad.core import sketch as sketches
        try:
            doc = sk.Document
            if not document.is_incad_part(doc):
                return
            count = sk.GeometryCount
            drawn = count != self._geometry_counts.get(sk.Name, count)
            self._geometry_counts[sk.Name] = count
            added = sketches.name_new_dimensions(doc)
        except Exception as e:
            log.report("warning", "Could not name new dimensions: %s" % e, traceback.format_exc())
            return
        if len(added) == 1 and not drawn and self.sketches.editing() is sk:
            self.open_value_box(sk, added[0])

    def open_value_box(self, sk, name):
        from incad.core import sketch as sketches
        self._close_value_box()
        expr = sketches._expression_of(sk, "Constraints." + name)
        text = sketches.to_display(sk.Document, expr) if expr else \
            sketches.document._format(sk.getDatum(name))
        box = ValueBox(name, text, self.theme, self.mw)
        box.applied.connect(self._on_value_applied)
        box.closed.connect(lambda: self._value_box_closed(box))
        self.value_box = box
        box.show_near(QtGui.QCursor.pos())

    def _close_value_box(self):
        if self.value_box is not None:
            try:
                self.value_box.close()
            except RuntimeError:
                pass
            self.value_box = None

    def _value_box_closed(self, box):
        if self.value_box is box:
            self.value_box = None

    def _on_value_applied(self, name, text):
        self._on_parameter_set(name, text)

    def _on_parameter_renamed(self, old, new):
        from incad.core import safe
        from incad.core import sketch as sketches
        doc = self._doc()
        if doc is not None:
            safe.run_safely("Rename %s" % old, lambda: sketches.rename_dimension(doc, old, new), doc)
        self.schedule_refresh()

    def _on_parameter_clicked(self, name):
        if self.value_box is not None:
            self.value_box.insert(name)

    @staticmethod
    def _preselected_dimension():
        """(sketch, name) of the dimension under the cursor, or (None, None)."""
        import FreeCADGui as Gui
        pre = Gui.Selection.getPreselection()
        obj = getattr(pre, "Object", None)
        subs = getattr(pre, "SubElementNames", ()) or ()
        if obj is None or obj.TypeId != "Sketcher::SketchObject":
            return None, None
        for sub in subs:
            if sub.startswith("Constraint"):
                try:
                    c = obj.Constraints[int(sub[len("Constraint"):]) - 1]
                except (ValueError, IndexError):
                    continue
                if c.Name:
                    return obj, c.Name
        return None, None

    def _click_hook(self, view, viewport, x, y):
        if self.value_box is None:
            return False
        sk, name = self._preselected_dimension()
        if name is None:
            return False
        self.value_box.insert(name)
        return True

    def _dblclick_hook(self, view, viewport, x, y):
        sk, name = self._preselected_dimension()
        if name is None or self.sketches.editing() is None:
            return False
        self.open_value_box(sk, name)
        return True
```
(add `from incad.qt import QAction` to the Qt import line of shell.py.)
14. `_settings_menu()`: before the navigation action add:
```python
        dims = menu.addMenu("Dimension Display")
        for value, label in (("value", "Value (40)"), ("name", "Name (d3)"), ("expression", "Expression (d3 = 40)")):
            act = dims.addAction(label)
            act.setCheckable(True)
            act.setChecked(prefs.dimension_display() == value)
            act.triggered.connect(lambda _=False, v=value: (prefs.set_dimension_display(v), self.apply_theme()))
```
15. Module function at the end:
```python
def sketch_session():
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    return _shell.sketches
```

- [ ] **Step 4: Run the GUI tests until they pass**

Announce the FreeCAD window. Run: `tests/run_gui.sh tests/gui/test_sketch.py tests/gui/test_nav.py`
→ Expected: `14 passed` and `15 passed`. If test_5 fails because the Sketcher does not report constraint
preselection via `Gui.Selection.getPreselection()`, probe `getPreselection()` while hovering a constraint in a
throwaway FreeCAD and adapt `_preselected_dimension` (the test stays).

- [ ] **Step 5: Run every suite and commit**

Run: `tests/run_all.sh` → Expected: `ALL SUITES PASSED`.
```bash
git add InCad tests && git commit -m "InCad 1c: sketch mode in the shell — start/pick/finish, value box, click-to-insert, shortcuts, Sketcher settings"
```

---

### Task 8: Look check and docs

- [ ] **Step 1:** In a throwaway FreeCAD (probe script, not committed) sketch a rectangle with two dimensions in an
InCad part in light and dark, open the value box, grab the window and `View.saveImage`; look at them. Fix what
looks wrong (sketch lines invisible against the background, unreadable dimension text, value box placement) with a
test first where a test can express it.

- [ ] **Step 2:** README — add:
```markdown
## Sketching
- S (or right-click → New Sketch) on a plane or a flat face; with nothing selected InCad shows the origin planes
  to pick from. Esc or ✓ Finish Sketch returns to the model.
- L line (M switches to arc while drawing), C circle, A arc, R rectangle, X trim, D dimension.
- While drawing, type lengths and angles directly (Tab moves between fields).
- Every dimension gets a name (d0, d1 …) shown under Parameters; rename it there. In a value box, click another
  dimension or a parameter to use its name in a formula (d0/2, Width - 2*d3).
```
- [ ] **Step 3:** `tests/run_all.sh` → `ALL SUITES PASSED`; commit
`git add README.md && git commit -m "InCad 1c: README sketching section"`.
