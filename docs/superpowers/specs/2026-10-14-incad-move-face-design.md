# InCad — Move Face (direct editing, first version) — design

Date: 2026-10-14. Status: approved in chat, spec for review.

## Goal
Inventor-style direct editing of a part's flat faces: pick one or more faces, move them by a distance or up to a face /
plane, and choose how their neighbours behave. It is the user's next step after 0.2.0 ("direct editing: Move Face by a
distance -> To a face/plane -> slanted neighbours -> curved faces"); this version covers the first three, curved
neighbours in the Inventor mode come later. Plus: the assembly DOF gizmo arrows a little smaller.

## Decisions (from the user, 2026-10-14)
- Three ways the neighbours behave, chosen in the dialog (pictures shown in chat):
  1. **Step** — only the face moves (a straight slab); a slanted neighbour stays, a straight wall appears at its edge.
  2. **Inventor** (preselected) — the neighbours keep their angle and extend / shrink (a chamfer grows, the face gets
     narrower).
  3. **Together** — the face and its slanted or round neighbours (chamfers, fillets) move as one piece; the walls next
     to them grow.
- Distance in the dialog **and** a drag arrow on the face (like the assembly gizmo, a wide grab zone); **while dragging
  the distance shows at the arrow** (like Fusion), live.
- **To a face or plane** is in this version.
- **Several faces at once**, all facing the same way, moved together by the same distance.
- The assembly gizmo arrows: **about 20 % smaller** (the grab zone stays as wide); the Move Face arrow uses the same
  look.
- Keep it small: the user wants InCad finished.

## The feature
- Command `feature.move_face`, label "Move Face", ribbon 3D Model ▸ Modify (next to Draft / Shell), the face marking
  menu's list, the right-click menu of a part. Select the faces first, or pick them in the open dialog (the usual
  picking field).
- A step at the end of the part's history: a `PartDesign::FeaturePython` (as `incad.features.hole_chamfer`), its row
  "Move Face" (Move Face001 …) in the browser, editable (double-click), Suppress / Delete as any feature, one undo step
  per OK. It sits at the body's tip when made (End of Part rules as for every feature).
- **Faces are kept by geometry, not by name**: for each picked face its plane (normal, a point), its outline points and
  area. On every recompute the feature finds, in the shape before it, the face in that plane whose outline matches best
  (overlap of the outlines); a picked face that is gone gives the feature's error "A face to move is no longer there"
  (the feature turns Invalid like any failed feature, its dialog says the same).
- Fields (feature dialog, the usual preview, OK / Apply + / Cancel):
  - **Faces** — picks (faces), one or more; all must be flat and face the same way (normals within 1e-6 rad), else
    "The faces must be flat and face the same way".
  - **Extent** — Distance / To.
  - **Distance** — value_length (units, formulas, parameters; a named parameter like every value: d…), positive =
    outward (along the first face's outward normal), negative = inward. 0 = no change.
  - **To** — pick a flat face or a work / origin plane parallel to the faces; the faces move into its plane (the
    distance is the signed gap, recomputed every time, so it follows the target). Not parallel: "Pick a face or plane
    parallel to the faces".
  - **Neighbours** — Inventor (default) / Step / Together.
- **The arrow**: while the dialog is open, an arrow on the (first) face's centre along its normal, drawn like the
  assembly gizmo's slide arrow (`incad.ui.dof_glyphs` look, the new smaller size, theme colours), hit-tested in screen
  space with `HANDLE_PX` (`incad.ui.dof_handles` way, through `Navigator.handle_hook`, never FreeCAD's picking). Drag
  it: the face moves along its normal by the pointer's projection (screen to the arrow's line); the Distance field
  follows (rounded to 0.1 mm), the preview updates as the pointer moves (throttled like the other previews); **a label
  at the arrow tip shows the value** ("12.5 mm", "−3 mm") during the drag and stays while the dialog is open. Typing a
  distance moves the arrow and the label. With Extent = To the arrow shows but is not draggable.

## How the shape is made
On the shape before the feature (its BaseFeature) S and the picked faces F (one plane P, outward normal n), moved by d
(signed) to the plane P' = P + d·n. A closed slab X between the faces' old and new place is built and then
`S ∪ X` (d > 0) or `S − X` (d < 0), refined (no seams on flat faces). The three modes differ only in X:
- **Step**: X = each face extruded by d along n (`face.extrude(n * d)`).
- **Inventor**: for each face, the outline F' in P' is found from the neighbours: every edge of F lies on a neighbour
  face N; flat N: its plane; a cylinder whose axis is along n (a hole's or a boss's wall): the edge slides along n.
  Each vertex of F moves along the line where the planes of its two neighbours meet (the side edge's direction) until
  it reaches P'; arcs move with their cylinder. X is bounded by F, F' and side faces lying in the neighbour planes /
  cylinders. A neighbour that is round across the move (a fillet, a cone, a cylinder not along n) cannot follow yet:
  "A neighbouring face is round: Inventor mode can't follow it yet — try Step or Together".
- **Together**: the moved set M = F plus every neighbour of F that is not along n (chamfers, fillets, cones: faces whose
  surface is not parallel to n). The walls W around M (the faces next to M outside it) must be along n (flat faces
  parallel to n, cylinders with the axis along n), else "The walls around the chamfer / fillet must run along the
  move — try Inventor or Step". X is bounded by M, M moved by d, and the strip of W between M's outer edges and the
  same edges moved by d (those strips lie on W).
- Checks (the feature fails with the message, nothing changes): the result must be one valid solid with the same
  number of solids as S; a move so large that a neighbour vanishes (an edge of F' collapses, F' self-intersects, or the
  slab cuts through the part) → "The move is too large: a neighbouring face would vanish"; d = 0 → the shape before,
  unchanged (no error).
- Units: shapes are in the body's frame (as `hole_chamfer`); the picked faces come from the selection in global
  coordinates and are stored in the body's frame.

## Smaller assembly gizmo arrows
`incad.ui.shell` sizes each part's DOF glyph `max(diagonal × 0.35, 5 mm)`; make it `max(diagonal × 0.28, 4 mm)` (20 %
smaller), the cone and the arcs scale with it; `HANDLE_PX` unchanged. The DOF handles' tests that measure on screen
keep working (they read the size from `dof_handles.drawn`). Release notes: "Assembly: the gizmo arrows are a little
smaller".

## Out of scope (later phases)
Curved faces themselves (moving a cylinder = changing its radius), Inventor mode with round neighbours, moving along
another direction than the face's normal, rotating faces, faces of different directions at once, snapping while
dragging.

## Testing
- Headless (`tests/headless/test_move_face.py`), each on a part made in the test:
  - block 40×30×10: top face +5 / −3 in each mode → the box's height 15 / 7, volume exact, one solid;
  - block with a 3 mm 45° chamfer on one top edge, top +4: Inventor → the chamfer face's plane unchanged, the top face
    4 mm narrower in that direction (volume formula); Step → a 4 mm straight wall above the chamfer; Together → the
    chamfer moved up 4 (its size unchanged), the side wall 4 mm taller;
  - block with a 2 mm fillet on the top edges, top +3: Inventor → the round-neighbour error; Together → fillets moved
    up, height 13; Step → works;
  - a slot (pocket) floor −2 (deeper) and +2; a hole through the top face, top +5 → the hole still goes through (the
    cylinder neighbour slides);
  - two boss tops at one height moved together +3; two faces of different direction → the error;
  - To: top face to a work plane 6 mm above → +6; then the plane moved to 8 → the face follows; a non-parallel plane →
    the error;
  - a move too large (inward past the chamfer's width in Inventor mode) → the error, shape unchanged;
  - robustness: an earlier feature edited (the block made taller) → Move Face finds its face again and still moves it;
    an earlier feature that removes the face → the error message;
  - Suppress / Delete of the Move Face give the shape before; Undo of the OK is one step.
- GUI (`tests/gui/test_move_face.py`): select the top face → Move Face → dialog with the preview; type 5 mm → the part
  grows; drag the arrow (screen-space press on its head, move, release) → Distance changes by the pointer's amount, the
  label at the arrow shows the value during the drag; OK → one "Move Face" undo step; double-click the row → the
  dialog with the values; the three modes switch in the preview; the gizmo-size change keeps
  `tests/gui/test_dof_handles.py` green.
- Then a copy of one of the user's real parts.
