# InCad — Stage 1 Design: Shell + Core Part Modeling

Date: 2026-10-05 · Status: draft for review · Target: FreeCAD 1.1.3 (Qt 6.8.3 / PySide6), macOS

## 1. Intent

InCad is a FreeCAD add-on: **one workbench** that gives FreeCAD the interface and the workflow logic of
Autodesk Inventor / Alibre Design. The user wants to model parts and assemblies, mostly for 3D printing,
without FreeCAD's native workflow (Body setup, Part vs PartDesign, task panels, unclear assembly steps).

What the user said (brainstorm 2026-10-05):

- Inventor/Alibre look **and logic**; "no stupid and not logical native FreeCAD workflow".
- Clear icons (as in the mockup), parametric fully-constrained sketches.
- Real modeled threads for 3D printing (all standards), Boolean Cut with clearance that keeps the tool.
- Parts and assemblies only; no drawings.
- Must not crash FreeCAD.
- Light and dark modes with a one-click toggle; ribbon size adjustable; a button back to native FreeCAD.
- New file asks mm or inch. English UI, Inventor default shortcuts.
- Standard mouse (no 3D mouse); **LMB+RMB drag = orbit**, no Shift. RMB = Inventor marking menu.

Assumptions (confirmed during the brainstorm unless noted): mainly for the user's own use; files stay
standard `.FCStd` and open in plain FreeCAD.

### Success criteria for Stage 1

1. With InCad active, the user never sees FreeCAD's menus/toolbars/task panel, and one click returns
   FreeCAD's UI exactly as it was.
2. The user can model a typical printable part (sketch → extrude/revolve → holes, fillets, chamfers,
   shell, patterns, mirror, work planes) using only InCad UI, the marking menu and Inventor shortcuts.
3. Sketching behaves like Inventor: auto-constraints, dynamic input, smart Dimension, DOF status.
4. No InCad action leaves a broken model; every failure rolls back with a readable message.
5. The resulting file opens and edits in plain FreeCAD 1.1.3.

## 2. Roadmap (each stage gets its own spec)

| Stage | Content |
|---|---|
| **1 (this spec)** | Shell (ribbon, browser, marking menu, navigation, themes, takeover) + sketch workflow + core part features |
| 2 | Threads: Thread feature + threaded Hole; ISO metric (coarse/fine), UNC/UNF, pipe (G/BSP, NPT), trapezoidal/ACME, custom, print-friendly profiles; real geometry + print clearance |
| 3 | Combine in a part: Cut/Join/Intersect between solid bodies with clearance (offset tool / target / split), tool body always kept |
| 4 | Assemblies: separate part/assembly files (App::Link), Place, first part auto-grounded, constraints (Mate, Flush, Angle, Tangent, Insert) + joints, create part in place |
| 5 | Combine with clearance between assembly parts (pocket written into the target part file, updates with the tool) |
| 6 | Polish: Sweep, Loft, Coil, Rib, Draft, Split, materials, section view |

## 3. Architecture

**Approach (chosen): an Inventor UI over native FreeCAD objects.** Sketches are `Sketcher::SketchObject`,
features are native PartDesign features in a hidden `PartDesign::Body`. InCad adds its own Python features
only where FreeCAD cannot do what is needed (stages 2, 3, 5). Rejected: a custom feature engine on the raw
kernel (would need its own topological naming solution, more crash risk, files dependent on InCad).

### 3.1 Install and layout

Repo `/Volumes/Docs/InCad` (git). A symlink `~/Library/Application Support/FreeCAD/v1-1/Mod/InCad →
/Volumes/Docs/InCad/InCad` installs it; a FreeCAD restart picks up code changes.

```
InCad/                      # the FreeCAD module (symlinked into Mod)
  Init.py, InitGui.py       # workbench registration only
  incad/
    core/document.py        # InCad Part setup, hidden Body, End of Part, units marker
    core/safe.py            # safe command guard (transaction, rollback, validity, logging)
    core/commands.py        # command registry: id, label, icon, shortcut, contexts, handler
    core/prefs.py           # InCad preferences (theme, ribbon size, units default, nav on/off)
    ui/shell.py             # takeover / restore of FreeCAD UI
    ui/ribbon.py            # ribbon widget, tabs per mode, size S/M/L
    ui/browser.py           # Model Browser + Parameters panel
    ui/statusbar.py         # prompt, units, DOF, part stats
    ui/marking_menu.py      # radial RMB menu + overflow list
    ui/theme.py             # light/dark palettes, Qt stylesheet, view colors
    ui/dialogs/base.py      # floating feature dialog base (preview, OK/Apply/Cancel, errors)
    ui/new_dialog.py        # New: Part/Assembly + mm/in
    nav/navigation.py       # mouse navigation event filter
    sketch/                 # start/finish sketch, tools, dimension, status coloring, dynamic input
    features/               # one module per feature (extrude, revolve, hole, fillet, ...)
    resources/icons/{light,dark}/*.svg
tests/                      # headless (freecadcmd) + GUI smoke tests
launchers/                  # Desktop InCad.app (Claude Code session launcher)
docs/
```

### 3.2 Unit responsibilities

- **core/document**: `make_part(doc, units)` creates a hidden Body (`AllowCompound` off), marks the
  document (`InCadType = "Part"`, `InCadUnits = "mm"|"in"`); `active_part()`; End of Part ⇄ Body `Tip`;
  `bodies()` for multi-body ("New Solid" creates another hidden Body). Pure model logic, no Qt.
- **core/safe**: `run_safely(label, fn)` → opens a document transaction, runs `fn`, recomputes, checks
  every touched shape (`isValid()`, not null, no error state); on any exception or invalid result aborts
  the transaction, restores the previous state, reports to status bar/dialog, logs to
  `~/Library/Logs/InCad.log`. `autosave_before(label)` hook (used by stages 2–5).
- **core/commands**: single registry consumed by ribbon, marking menu, shortcuts and tooltips; each
  command declares the contexts where it is available (part, sketch, face selected, browser feature, …).
- **ui/shell**: on activate, saves FreeCAD's UI state (`QMainWindow.saveState()`, visibility of menubar,
  toolbars, combo view, report view, Python console, status bar) and replaces it with InCad's widgets; on
  deactivate or "⇄ FreeCAD" restores the saved state. Any exception during activation triggers restore.
- **nav/navigation**: Qt event filter on the 3D view widget. LMB+RMB drag → orbit around the point under
  the cursor (fallback: scene center); MMB drag → pan; wheel → zoom at cursor; RMB press+release with no
  LMB and no movement → marking menu; LMB → select (passed through). Toggleable; when off or on error,
  FreeCAD's own navigation stays in effect.

### 3.3 Data flow

User action (ribbon / marking menu / shortcut) → command registry → `run_safely` → feature module creates
or edits a native object and opens its dialog → live preview by recompute → OK commits the transaction,
Cancel aborts it.

## 4. Interface shell

- **Title area**: quick-access (New, Open, Save, Undo, Redo), document name, **☾/☀︎ theme toggle**,
  **⇄ FreeCAD**, ⚙ settings.
- **Theme**: follows macOS appearance on first run; the toggle overrides and is remembered. Covers ribbon,
  browser, dialogs, marking menu, status bar, 3D background and sketch status colors. Icons have light and
  dark SVG variants.
- **Ribbon**: tabs by mode — Part: *3D Model · Sketch · Inspect · Tools · View*; in a sketch the *Sketch*
  tab (Draw · Constrain · Pattern · Modify · Insert · Format · ✓ Finish Sketch) is first. Sizes
  **Small 16 px (no labels) / Medium 24 px / Large 32 px (default)**, set by right-click on the ribbon or
  ⚙, applied instantly, remembered.
- **New dialog**: Part / Assembly (Assembly greyed until stage 4) and **Millimeters / Inches**, "Remember
  my choice". Units are stored in the document and applied whenever it is active.
- **Model Browser**: part node, Origin folder (planes, axes, center point), features with nested sketches,
  sketch status (✓ fully constrained / "n DOF"), **End of Part** marker draggable to roll back/forward,
  failed features red with the reason as tooltip, suppressed features grey, "Solid Bodies (n)" when more
  than one. A part with several Solids keeps ONE history, as Inventor does (2026-10-10): every Solid's
  features sit in the part's list in the order they were made (`document.history`), rows of a Solid other
  than the main one name it ("Extrude006    Solid2"), the Solid Bodies folder lists names only, and the one
  End of Part rolls every Solid back to the dropped row (`document.set_end_of_part_at`). Double-click = Edit Feature. Parameters panel below: name / expression / value, using
  FreeCAD's expression engine (stored as properties of one `App::VarSet` named "Parameters", hidden from the browser tree).
- **3D view**: ViewCube (FreeCAD's NaviCube restyled), navigation strip (pan, orbit, zoom, zoom all,
  visual style), triad.
- **Status bar**: next-step prompt, units, sketch DOF, solids/features count.
- **Document tabs** at the bottom (FreeCAD's MDI tabs restyled).
- **Marking menu (RMB)**: 8 radial slots + overflow list, filled from the command registry per context:
  empty space in Part, face, edge, browser feature, empty space in sketch, sketch entity. Flick gestures
  (press, move in a direction, release) execute without the menu fully drawing. Examples: Part empty —
  New Sketch (↑), Extrude, Revolve, Hole, Fillet, Repeat last, Home View, Zoom All; Sketch empty — Finish
  Sketch (↑), Line, Circle, Rectangle, Dimension (↓), Arc, Undo, Trim.
- **Shortcuts (Inventor defaults)**: S sketch, L line, C circle, R rectangle, A arc, D dimension,
  X trim, E extrude, H hole, F fillet, F6 home view, F7 slice graphics, F8/F9 show/hide constraints,
  Esc finish tool → finish sketch, ⌘Z/⌘⇧Z undo/redo.

## 5. Sketch workflow

- **Start**: Start 2D Sketch (S / ribbon / marking menu) → pick origin plane, planar face or work plane →
  view looks at the sketch; origin and (for face sketches) face edges available for projection; origin
  center point and axes always projected automatically. RMB on a face → New Sketch skips the pick.
- **Draw tools**: Line (with drag-back tangent arc), Circle, Rectangle (2-point, 3-point, center),
  Arc (3-point, center, tangent), Slot, Polygon, Spline, Point, Fillet, Chamfer, Trim, Extend, Offset,
  Project Geometry, Construction toggle, Mirror, Rectangular/Circular sketch pattern.
- **Auto-constraints** while drawing (reuse Sketcher's autoconstraint); holding Ctrl suppresses them.
- **Dynamic input**: value fields next to the cursor (length/angle, width/height, radius); Tab moves
  between fields; Enter creates **driving dimensions**; fields accept expressions and parameters.
  Implementation: drive and restyle Sketcher's on-view parameters; fallback is an InCad overlay.
  **This is the highest-risk item of Stage 1 and is prototyped first.**
- **Dimension (D)**: one smart tool (linear, aligned, radius, diameter, angle by what is clicked), edit box
  pops up immediately; an over-constraining dimension is offered as a reference (driven) dimension.
- **Status**: colors for under-constrained / fully constrained / conflicting (light and dark palettes);
  "DOF: n" in the status bar, click highlights free geometry.
- **Finish**: ✓ Finish Sketch, ↑ flick, or Esc with no active tool. If the sketch has exactly one closed
  profile, the next Extrude/Revolve picks it automatically.

## 5a. Named dimensions and click-to-insert (added 2026-10-05)

- Every driving sketch dimension and every feature value (extrude distance, fillet radius, …) gets an automatic
  name `d0`, `d1`, `d2`, … (Inventor model parameters). Under the hood: named Sketcher constraints and feature
  properties, linked with FreeCAD's expression engine, so links keep working in plain FreeCAD.
- The Parameters panel shows **Model parameters** (the `dN` names) above **User parameters**; any name can be
  renamed (`d3` → `WallThick`) and every reference follows.
- While any value box is open (new dimension, dimension edit, feature dialog field), clicking an existing
  dimension in the sketch or 3D view, or a row in the Parameters panel, inserts its name at the cursor. Enter keeps
  it as is; typing more builds a formula (`d3*2`, `d3/2 + 1 mm`, `Width - 2*d5`).
- A linked dimension shows an `fx:` prefix in the sketch. ⚙ → Dimension display: Value / Name / Expression.
- A formula that would create a loop, or that names something unknown, is refused on Enter: the box turns red,
  says why, and keeps the text for fixing.
- Plans: 1c (sketch dimensions, naming, click-to-insert, fx display, display modes, model/user split of the
  Parameters panel), 1d (click-to-insert in every feature dialog field). Plan 1a is unchanged.

## 6. Part features

Common dialog behavior: floating dialog in the 3D view + drag handles (arrows for distance, rings for
angle), live preview, values accept units/parameters/formulas, **OK / Apply (+) / Cancel**, invalid result
→ red preview + plain-language reason + OK disabled, Edit Feature reopens the dialog, last values
remembered per feature.

| Feature | Options | Native objects |
|---|---|---|
| Extrude (E) | profile (auto-pick), Join / Cut / Intersect / New Solid; extents Distance, To face, To Next, Through All, Between; one side / flip / symmetric / two sides; taper | `Pad` / `Pocket` (`Type`, `SideType`, `TaperAngle`); Intersect = new Body + `PartDesign::Boolean` Common; New Solid = new hidden Body |
| Revolve | profile, axis, same 4 operations, Angle / Full / To | `Revolution` / `Groove` |
| Hole (H) | placement: sketch points or on face (concentric / from edges); simple, counterbore, countersink; Distance / Through All / To; drill point angle | `Hole` (threaded option in stage 2) |
| Fillet (F) | several edge sets each with its radius, tangent chain, all edges / all fillets | one `Fillet` per set, shown as one browser node |
| Chamfer | distance, two distances, distance + angle, tangent chain | `Chamfer` |
| Shell | thickness, faces to remove, inside / outside / both | `Thickness` |
| Rectangular Pattern | two directions with count + spacing, features or solid | `LinearPattern` / `MultiTransform` |
| Circular Pattern | axis, count, angle, fit / incremental | `PolarPattern` |
| Mirror | features or solid, plane | `Mirrored` |
| Work Plane / Axis / Point | offset, angle, 3 points, midplane, tangent; axis through edge / 2 points; point at vertex / intersection | `DatumPlane` / `DatumLine` / `DatumPoint` |

Join vs Cut is pre-selected Inventor-style from the profile location and direction (user can override).

**Inspect tab (Stage 1)**: Measure (distance, angle, radius, area) and Mass Properties (volume, surface
area, mass from a density, bounding box).

**Out of Stage 1**: Sweep, Loft, Coil, Rib, Draft, Split, Emboss, Thread, Combine, materials beyond a
basic color.

## 7. Stability and error handling

1. **Safe command guard** (`core/safe`) around every InCad action: transaction, exception handling,
   rollback, readable message, log file.
2. **Validate before commit**: shapes checked before OK is allowed; invalid geometry is never committed.
3. **UI safety**: FreeCAD UI state saved before takeover and restored on exit or on any activation error;
   navigation filter can be disabled and falls back to FreeCAD navigation.
4. **Autosave hook** before heavy operations (used from stage 2 on).
5. Known limit: crashes inside FreeCAD's C++ code cannot be caught from Python; layers 2 and 4 reduce the
   risk and the damage.

## 8. Testing

- **Headless** (`/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd`): core/document (part
  setup, units, End of Part, multi-body), every feature module with its options, parameters/formulas,
  rollback on error, file opens without InCad.
- **GUI smoke tests** (FreeCAD launched by the test runner): activate InCad → takeover verified →
  ⇄ FreeCAD → UI restored identically; theme toggle; ribbon sizes; marking menu builds per context;
  navigation filter installs and removes cleanly.
- **Acceptance**: build one of the user's typical printable parts entirely through InCad; the user tries
  it hands-on. Stage 1 is done when the user accepts it.
- Claude may launch and restart FreeCAD for tests without asking (user permission 2026-10-05), and says
  when mouse/keyboard are off-limits and when they are free again.

## 9. Open risks

| Risk | Mitigation |
|---|---|
| Dynamic input / glyphs need hooks into Sketcher's C++ edit mode | prototype first; reuse on-view parameters; fallback overlay |
| Custom navigation conflicts with FreeCAD's navigation style | event filter consumes only its gestures; toggle; fallback |
| Takeover leaves FreeCAD UI in a bad state | save/restore via `saveState`, restore on any error, smoke test |
| FreeCAD internal API changes in later versions | pin 1.1.3, test suite run before upgrading |
| Live preview slow on heavy parts | preview throttling (recompute after typing pauses) |
