# InCad — sketch Offset (Inventor style) — design

Date: 2026-10-15. Status: approved in chat, spec for review.

## Goal
InCad's own Offset in the sketch, replacing FreeCAD's `Sketcher_Offset` behind the ribbon's Offset button. FreeCAD's
tool fails the user three ways (its source, FreeCAD 1.1 `DrawSketchHandlerOffset.h`): it starts in its Arc mode
(rounded outer corners — fixed for now by starting it in Intersection), it never allows an open result (a single line
becomes a slot round it), and it drops the B-spline OCC returns for an ellipse ("Offset could not be created").

## Decisions (from the user, 2026-10-15)
- **One click takes the whole shape** (Inventor's loop select) — in Offset and similar tools only; ordinary clicks in
  the sketch still select one edge (to dimension or constrain it).
- **Drag, click, then the box**: the copy follows the pointer, a click places it, InCad's value box opens on the new
  offset dimension to type the exact distance.
- **Tied to the original**: lines, arcs and circles follow the original when it changes; an ellipse / spline copy
  cannot be tied in FreeCAD and stays as drawn (its dimension shows the distance).
- Sharp corners; an open line or chain gets one copy on the pointer's side (no slot); ellipses and splines get their
  exact offset as a B-spline.

## What the user sees
1. Offset (ribbon Sketch ▸ Modify, the sketch marking menu where Offset is today) with nothing selected: the prompt
   "Click a shape to offset (Esc cancels)". A click on an edge picks the whole outline it belongs to — the edges
   joined end to end with it (coincident end points), open or closed: a rectangle, triangle, polygon, a chain drawn
   line by line, a circle, an ellipse, a spline. Cmd/Ctrl-click adds another outline. Edges selected before the
   command: their outlines are taken and the tool goes straight to step 2.
2. The copy is drawn live (a preview, no geometry yet) at the pointer: a closed outline outward or inward by the
   pointer's side, an open one to its left or right; the distance is the pointer's distance from the outline.
3. A click places it: the geometry and its constraints are added in one undo step ("Offset"), the offset dimension is
   named like every InCad dimension (dN) and InCad's value box opens on it — typing a value (or a formula) and Enter
   sets the distance; Esc in the box keeps the placed distance. Esc before the click cancels the tool.
4. The tool ends after one offset (Inventor); the button starts it again.

## Geometry (`incad.core.sketch_offset`, sketch coordinates)
- **Outline**: from a picked geometry index, the connected chain of the sketch's normal (non-construction) geometry
  by coincident end points (the sketch's Coincident constraints and points within 1e-7), ordered end to end; closed
  when its ends meet. A circle, a full ellipse or a closed spline is a closed outline of one curve.
- **Offset**: `Part.Wire(edges).makeOffset2D(d, join=2 (intersection), openResult=True)` for an open chain on the
  chosen side (the sign from the pointer's side), `Part.Face(wire).makeOffset2D(±d, 2)` for a closed one (outward /
  inward). The side: the sign that puts the offset nearer the pointer.
- **Into sketch geometry**: each result edge → `Part.LineSegment` / `Part.ArcOfCircle` / `Part.Circle`; any other curve
  (an ellipse's or a spline's offset) → its B-spline (`Edge.Curve.toBSpline(...)` trimmed to the edge), added as
  `Part.BSplineCurve` geometry.
- **Refused**: an inward offset that folds the outline (an old outline point not exactly d from the new one, as Move
  Face round walls check) → "The offset is too large for this shape"; a pick on construction geometry, a point or an
  external (projected) edge → "Click a line, arc, circle, ellipse or spline of the sketch".

## The tie (`incad.core.sketch_offset`)
- Consecutive copies joined by Coincident at their shared end points (sharp corners).
- Each line copy: Parallel to its original; the first line copy also gets a Distance (point-to-line) to its original
  — the **offset dimension**, driving; every other line copy gets a Distance with the expression of the first
  (`Constraints.dN`), so one value drives them all.
- Each arc / circle copy: Coincident centre with its original (concentric) and its radius by an expression
  (original's radius ± dN, the sign by the side).
- An ellipse / spline copy: no tie; when the outline has no line, arc or circle, the offset dimension is a
  reference (non-driving) distance between the original and the copy, so the value shows.
- The solve after adding must leave the copy where it was placed (the constraints agree with the geometry); a failed
  solve undoes the step and reports it.

## UI (`incad.ui.offset_tool`, like `incad.ui.slot_tool`)
- Started by the `sketch.offset` command (replacing the `Sketcher_Offset` entry and its Intersection mode pin);
  picking goes through the view's clicks (as the slot tool), the preview is a coin line set on the sketch plane
  (no document objects), redrawn on every mouse move.
- Esc / another command / leaving the sketch stops it and removes the preview.

## Tests
- Headless (`tests/headless/test_sketch_offset.py`): the outline of a picked edge (rectangle, triangle, a 3-line
  chain, a circle, an ellipse); the offset geometry exact on both sides — line (one parallel copy, no slot), rectangle
  out / in (sharp corners: 4 lines, corners at exactly ±d diagonally), triangle, circle (r ± d), ellipse (a B-spline
  every point of which is d from the ellipse), open chain; the tie — after placing, change the original rectangle's
  width and the copy follows at d; set dN and the copy moves; the fold refusal (a 10 x 4 rectangle inward by 3).
- GUI (`tests/gui/test_sketch_offset.py`): a click on one edge of a rectangle picks all four, a pointer move outside
  draws the preview, a click places it (4 new lines), the value box opens on the new dimension, typing "3" and Enter
  sets the distance to 3; a single line offsets as one line.

## Out of scope (later)
Offsetting several outlines with one distance each, "delete original", offset of a projected (external) edge, tying
ellipse / spline copies, Move / Copy with loop select.
