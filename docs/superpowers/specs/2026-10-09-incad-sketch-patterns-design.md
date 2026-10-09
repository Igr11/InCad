# InCad — Sketch Patterns (design)

Base: stage-1 spec `2026-10-05-incad-stage1-design.md` (sketch tab, Pattern group: "Mirror, Rectangular/Circular
sketch pattern"). Agreed with the user on 2026-10-09 after the FreeCAD route was ruled out: FreeCAD's sketch
array tools keep their parameters in the Tasks panel that InCad hides, and the Sketcher has no circular array.

## 1. Intent

Rectangular and Circular patterns **inside a sketch**, looking and behaving like InCad's pattern dialogs for the
part (same dialog, same fields, same errors), with results that stay editable the way Inventor's sketch
patterns do: the copies follow the original when it changes, spacing/angle/count can be changed afterwards,
and the pattern can be reopened or deleted as a whole. A third mode, copies along a path, comes second on the
same foundation. Mirror stays FreeCAD's `Sketcher_Symmetry` for now (it needs no panel) and will be redone
later on this pattern's model.

Who it is for: the user modelling parts for printing, who draws a hole or a slot once and wants N of them in a
row, on a circle, or along a curve, and wants to change N or the spacing later without redrawing.

Success: on the user's real part (`/Volumes/Docs/Plasticity_projects/p2_test_reordered.FCStd`), a hole drawn
in a sketch is patterned 4× along the block in the dialog, the pattern is reopened and set to 5, the sketch is
extruded as a cut, and the five holes appear in the solid. All of it drives the dialog in a real window.

## 2. Probed facts (FreeCAD 1.1.3)

- `sk.setGeometryId(i, id)` / `sk.getGeometryId(i)` give a geometry a permanent id that survives
  `delGeometry` of earlier geometry and a save/reload (`GeometryFacadeList[i].Id`). Ids not set are `None`.
- `sk.renameConstraint(i, name)` names survive reload; `sk.addProperty("App::PropertyString", …)` on a sketch
  is saved with the file.
- Sketch expressions may reference a constraint's value by name (`.Constraints.name`), driving or reference.
- In sketch edit mode `Gui.Selection` reports sketch sub-elements as `EdgeN`, `VertexN`, `H_Axis`, `V_Axis`,
  `RootPoint` on the sketch object.
- `FeatureSession` drives any kind with `create(doc, body, profile, values)`, `update(doc, f, values)`,
  `read(doc, f)`, `defaults`, `FIELDS`, inside one open undo step; `NEEDS_PROFILE=False` already exists for
  kinds that make no feature at start.

## 3. Dialogs

Both live in the sketch tab's Pattern group (`sketch.rect_pattern`, `sketch.circ_pattern`, then
`sketch.mirror`) and in the sketch marking menu where the 3D ones sit in the part's. Icons: the existing
`rect_pattern` and `circ_pattern`.

**Rectangular Pattern** (the part's dialog, with sketch picks):

| Field | Kind | Notes |
|---|---|---|
| Geometry | picks, `sketch_geometry` | lines, arcs, circles, points of this sketch; starts empty unless geometry was selected before the command (then seeded) |
| Distribution | choice | By spacing · Equal spacing · Along path (phase 2) |
| Direction 1 | pick, `sketch_direction` | a sketch line or the X/Y axis; default X; shown for By spacing |
| Flip direction | bool | both modes; mirrors the copies to the other side of the original (same spacing) |
| Count | value | whole number ≥ 2 |
| Spacing | value length | By spacing; a named model parameter |
| From / To | pick, `sketch_limit` | Equal spacing: a sketch line or point each; From is the start, copies run toward To; equal margins |
| Two directions | bool | Direction 2, Count 2, Spacing 2 (By spacing only) |
| Path, Orientation | phase 2 | see §7 |

Equal spacing follows the part's rules exactly: the direction is the normal from From toward To (a line limit)
or the vector between two point limits; margin = distance from the start to the original's near edge; a
negative margin says "pick the other end as From"; copies that would overlap say "no room" with the sizes.

**Circular Pattern**:

| Field | Kind | Notes |
|---|---|---|
| Geometry | picks, `sketch_geometry` | as above |
| Axis | pick, `sketch_point` | a sketch point, a circle/arc centre, a line end, or the origin (default: origin) |
| Count | value | whole number ≥ 2 |
| Angle | value angle | default 360° |
| Distribution | choice | Fitted (copies spread within Angle; 360° closes the ring with no double) · Between copies (Angle is the step) |
| Flip | bool | the other way round |

Errors shown in the dialog: nothing picked ("Click the geometry to repeat"); a spline or ellipse picked
("Pattern repeats lines, arcs, circles and points"); the axis point lies on the geometry; From and To coincide;
no room; a copy would land on the original (step 0); the solver fails or the sketch becomes over-constrained
after the copies are added (the preview is rolled back and the message names the cause).

## 4. What is created in the sketch

The copies are ordinary sketch geometry of the same types, placed exactly, then **tied to the original by
hidden constraints** so that a change to the original, the spacing, the angle or the direction moves them:

- For every point of the original (line ends, arc ends, circle centres, points) and every copy k, two driving
  constraints `DistanceX` and `DistanceY` from the original point to the copy's point, with expressions:
  - rectangular: `k * S * cos(D)` and `k * S * sin(D)`, where `S` is the pattern's spacing parameter and `D`
    is a **reference** (non-driving) `Angle` constraint between the H axis and the direction line (0° or 90°
    constants for the axes); Flip negates k; direction 2 adds its own terms; Equal spacing stores the computed
    spacing in `S` and re-solves it on edit from the limits.
  - circular: `dx*cos(kA) - dy*sin(kA) - dx` and `dx*sin(kA) + dy*cos(kA) - dy`, where `A` is the step
    angle (Angle, or Angle/(Count-1), or Angle/Count for a closed 360° ring) and `dx`, `dy` are **reference**
    `DistanceX`/`DistanceY` constraints from the axis point to the original point; the axis point is any sketch
    point, the origin uses `RootPoint`.
- Circles and arcs get an `Equal` to the original (radius). An arc ties its two ends and the radius (5 DOF),
  never its centre as well; a line ties both ends (4); a circle its centre and radius (3); a point its position
  (2). This keeps every copy exactly constrained.
- Construction geometry in the selection is copied as construction.
- Every constraint the pattern adds is named `<pattern>_<n>` (e.g. `Pattern1_17`) and put in virtual space, so
  the Constraints toggle never shows them and the user never sees or edits them. Dimensions on the original are
  not copied: the copies have no dimensions of their own.
- Spacing, Angle and Count are InCad model parameters named after the pattern (`Pattern1_spacing`,
  `Pattern1_angle`, `Pattern1_count`), shown in Parameters. Spacing and Angle drive the expressions directly;
  Count is read back by the dialog and cannot rebuild the copies from Parameters alone (a change there is applied
  on the next Edit Pattern, and the dialog says so).

## 5. The pattern record, editing, deleting

- The sketch gets `InCadPatterns` (`App::PropertyString`, JSON list). One entry per pattern: `name`, `kind`
  (`rect` | `circ` | `path`), the dialog `values`, `originals` (geometry ids), `copies` (list per copy of
  geometry ids), `constraints` (names), `params` (model parameter names).
- Geometry ids: the original's geometry gets ids on first use (`setGeometryId`); copies get ids at creation.
  Picks are stored by id, never by index, so deleting other geometry does not break the record.
- **Edit Pattern**: a double-click on a copy in the view (via `_dblclick_hook`, which already catches
  double-clicks in sketch mode for dimensions) or the marking menu / right-click "Edit Pattern" on a selected
  copy opens the same dialog with `read()` values. `update()` deletes the pattern's copies and constraints,
  then creates them afresh from the new values. The whole edit is one undo step.
- **Delete Pattern** (right-click on a copy; Delete key on a selected copy asks "Delete the whole pattern?"):
  removes copies, constraints and parameters; the original stays.
- A pattern whose copies were partly deleted by hand is *broken*: the record is kept; Edit Pattern warns
  "Some copies were deleted; the pattern will be rebuilt" and rebuilds; Delete Pattern removes what is left.
  The sketch's own tools stay usable on copies (the user can drag them: the constraints bring them back).
- Two patterns may share an original; a pattern of a copy is refused ("Pattern the original, not a copy").

## 6. Session and picks (`FeatureSession`)

- New module `incad/features/sketch_patterns.py`: kinds `SKETCH_RECT`, `SKETCH_CIRC` (phase 2 adds the path
  mode to `SKETCH_RECT`), `IN_SKETCH = True`, `NEEDS_PROFILE = False`. `create(doc, body, profile, values)`
  takes the sketch being edited as `profile`; the "feature" the session holds is the sketch itself; `read`
  takes the sketch and the pattern name (stored on the session as the feature's sub-identity).
- `FeatureSession` gets an `IN_SKETCH` path: no base feature, no visibility toggling of the feature or its
  base, no "on the current shape" check; `_selection()` keeps sketch sub-elements and `_as_picks()` turns them
  into `(sketch, "EdgeN")` pairs resolved to geometry ids; the dialog is parented like the dimension value box
  (over the 3D view, not the model browser).
- New pick kinds in `common.accepts`: `sketch_geometry` (Edge of a line/arc/circle, Vertex of a point;
  rejects splines/ellipses with the message above), `sketch_direction` (Edge of a line, `H_Axis`, `V_Axis`),
  `sketch_point` (any Vertex, `RootPoint`), `sketch_limit` (Edge of a line, any Vertex). `pick_label` shows
  "Line 3", "Circle 2 centre", "X axis", "Origin".
- Preview: every change rebuilds the copies inside the open undo step and recomputes the sketch; Cancel aborts
  the step (the sketch is as before); OK commits. Apply is not offered (one pattern per dialog).
- Starting the dialog while another sketch tool runs stops that tool (as the slot tool does); finishing the
  sketch with the dialog open cancels the dialog.

## 7. Phase 2 — Along path

- Rectangular's Distribution gains "Along path": Path (`sketch_path`: one curve or a connected chain of
  lines/arcs of this sketch), Count, Spacing or "Fit to path" (equal steps over the whole length, first copy at
  the start, last at the end), Orientation: Identical / Follow path (each copy rotated by the tangent angle at
  its station), Flip (start from the other end).
- Associativity: along lines and arcs the station is a translation (line) or a rotation about the arc centre
  (arc), expressed with the same `DistanceX`/`DistanceY` expression scheme, with the station's segment and
  parameter fixed at creation (a copy stays on its segment; if the chain's lengths change, stations shift
  within their segment but do not cross into the next segment until the pattern is edited). Splines and
  ellipses in the path are placed exactly at creation and re-placed on edit only; the dialog says
  "Copies on a spline follow it when the pattern is edited, not live".
- Everything else (record, edit, delete, broken patterns) is shared with the two first modes.

## 8. Testing

- Headless (`tests/headless/test_sketch_patterns.py`): create rect/circ on lines, arcs, circles, points;
  exact placement; moving the original moves the copies; changing `Pattern1_spacing` / `_angle` in
  Parameters moves the copies; Equal spacing margins and its errors; Flip; two directions; edit (count 3 → 5
  rebuilds; the record is updated); delete (original kept, no constraints left); broken pattern rebuilt;
  refusal of splines and of patterning a copy; save/reload keeps ids, names, record; the sketch stays
  fully constrained if it was (DOF before == DOF after).
- GUI (`tests/gui/test_sketch_patterns.py`, replacing the probe written today): the ribbon buttons; the dialog
  with picks made through the sketch selection; empty start with the hint; double-click on a copy opens Edit
  Pattern; Cancel leaves the sketch untouched; the 3D view is not hidden during the dialog.
- Real part (`tests/gui/test_pattern_real_part.py`, new tests): a hole sketched on the block's top patterned
  4× by the dialog, reopened and set to 5, cut by Extrude; five holes in the solid.

## 9. Out of scope

Mirror as an InCad dialog (later, on this model); patterns of dimensions; nested patterns (a pattern of a
pattern); associativity to geometry outside the sketch (external/projected edges are accepted as picks only
through their copies in the sketch).
