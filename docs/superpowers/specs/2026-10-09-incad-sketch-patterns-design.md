# InCad — Sketch Patterns (design)

Status: implemented (phase 1: rectangular + circular, branch `sketch-patterns`); phase 2 (along path) open.

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

- FreeCAD gives every sketch geometry a permanent id itself (`sk.getGeometryId(i)`: 1, 2, 3…), keeps it across
  `delGeometry` of other geometry and a save/reload, never reuses it, and derives the element names of the
  features built on the sketch (a pad's faces) from it. The pattern reads those ids and **never overwrites
  them** (overwriting renamed the pad's faces and detached the sketches on them, review probe 2026-10-09).
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

Probed on 2026-10-09: a sketch expression may use model parameters (`InCadModel.dN`) and driving constraints,
but **never a reference (non-driving) constraint of the same sketch** ("Reference constraint from this sketch
cannot be used in this expression"), and construction geometry cannot be hidden. So:

- **Rectangular**: the copies are ordinary geometry tied to the original by hidden driving constraints: for
  every point of the original (line ends, arc ends, circle centres, points) and every copy k, a `DistanceX`
  and a `DistanceY` from the original's point to the copy's point with the expressions
  `k * InCadModel.dS * cos(D)` and `k * InCadModel.dS * sin(D)`, where `dS` is the spacing parameter and `D`
  is the direction angle **as a literal in degrees** (0 or 90 for the axes; the picked line's angle at
  creation, read again at every Edit Pattern: a rotated direction line moves the pattern on the next edit, not
  live). Two directions add `j * InCadModel.dS2 * cos(D2)` terms. Flip negates k. Equal spacing computes the
  spacing from the limits, stores it in `dS` and recomputes it on edit. A circle gets `Equal` to the original
  (radius); an arc ties its two ends plus ONE equation on its centre (DistanceX or DistanceY, whichever has a
  component along the chord's bisector: a semicircle's chord already fixes the radius, so an `Equal` would be
  redundant there); a line ties both ends (4), a circle its centre and radius (3), a point its position (2):
  every copy is exactly constrained and the sketch reports no redundant constraints. These constraints live in
  virtual space (hidden) and are never shown or listed.
- **Circular**: live association needs construction "spokes" (agreed with the user): for each reference point
  of the original (a point, a line's start, a circle's centre, an arc's start and end) one construction line
  from the axis point to it (`spoke0`), and for every copy k one construction line from the axis point to the
  copy's point, with `Equal(spoke0, spoke_k)` and `Angle(spoke0, spoke_k)` whose expression is
  `k * InCadModel.dA / divisor` (`dA` is the Angle the dialog shows; the divisor is Count-1 for Fitted, Count for
  a closed 360° ring, 1 for Between copies). Every point of a copy (line ends, arc ends, a circle's centre, a
  point) sits on such a spoke; a circle adds `Equal` (radius); an arc adds a spoke to its centre with ONE
  constraint, `Equal` when the centre moves radially with the bulge or `Angle` when sideways. Spokes are construction
  geometry (visible, blue), are part of the pattern and go with it; their constraints are hidden. Moving the
  original, the axis point or the angle parameter moves every copy at once.
- Construction geometry in the selection is copied as construction. Dimensions on the original are not copied.
- Every constraint the pattern adds is named `pat<n>_<i>` (`pat1_17`); `incad.core.sketch` treats names with
  this prefix as the pattern's own: they are not dimensions (not listed in Parameters, not snapshot, not
  auto-named) and not symbols (the Constraints toggle leaves them hidden).
- Spacing and Angle are model parameters (`dN`, made with `model.new_feature_parameter`), shown in
  Parameters and labelled in the dialog like the 3D patterns' spacing. Count lives only in the record: it
  changes through Edit Pattern.

## 5. The pattern record, editing, deleting

- The sketch gets `InCadPatterns` (`App::PropertyString`, JSON list). One entry per pattern: `name`, `kind`
  (`rect` | `circ` | `path`), the dialog `values`, `originals` (geometry ids), `copies` (list per copy of
  geometry ids, spokes included), `constraints` (names), `params` (model parameter names: spacing, angle).
- Geometry ids are FreeCAD's own; copies get theirs at creation. Every pick (geometry, direction, limits, axis)
  is stored as an id reference and the dialog's texts are regenerated when the pattern is read, so deleting
  other geometry does not break the record.
- **Edit Pattern**: a double-click on a copy in the view (via `_dblclick_hook`, which already catches
  double-clicks in sketch mode for dimensions) or the marking menu / right-click "Edit Pattern" on a selected
  copy opens the same dialog with `read()` values. `update()` deletes the pattern's copies and constraints,
  then creates them afresh from the new values. The whole edit is one undo step.
- **Delete Pattern** (marking menu / right-click on a selected copy): removes copies, spokes, constraints and
  parameters; the original stays. The Delete key on a selected copy deletes just that geometry, as for any
  sketch geometry: the pattern is then *broken* (below).
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
