# InCad — Move Face on round walls (radial offset) — design

Date: 2026-10-15. Status: approved in chat (three sections), spec for review.

## Goal
Move Face for curved faces: push a straight round wall (a hole, a boss, the elliptic band of the user's part) outward
or inward along its own surface — a cylinder's radius changes, an ellipse or spline outline is offset exactly. It is
the "curved faces" phase the Move Face spec left for later ("Curved faces themselves (moving a cylinder = changing
its radius)"). Approach chosen by the user (variant 1 of four discussed): a ring slab fused on or cut away, the
history kept as it is (a Move Face step at the end of the tree, the sketch and the fillets untouched).

## Decisions (from the user, 2026-10-15)
- **Neighbours as for flat faces**: Inventor / Step / Together, the same choice in the dialog.
- **Distance only** (+ outward, − inward); no To for round walls.
- **Straight-walled faces**: cylinders and curves extruded straight along one direction (an ellipse, a spline: the
  user's band). Cones, spheres, tori and free-form faces are not offset.
- **One click takes the whole wall**: every piece of the same surface joined to the picked one (across seams).
- **Closed walls first** (full rings: holes, bosses, the user's band); an open wall (a round end between flat faces)
  comes in a later phase.
- **Tests on the user's own body** (a copy of the file they send), every mode outward and inward.

## What the user sees
- Move Face's Faces field also takes a straight round wall, clicked in the view or selected before the command; one
  click picks the whole wall. Several walls may be picked: each is offset by the same distance.
- Flat faces and round walls in one move: refused, "Pick flat faces or round walls, not both".
- Extent: Distance only — "To" is greyed out (the kind's `unavailable(values)`) while a round wall is picked.
- Distance: + outward (more material on a boss, a smaller hole), − inward; it starts at 0 mm as today; it has its
  parameter (dN) as today.
- The arrow sits on the wall at its middle height and points straight out of it (the outward normal there); dragging
  it changes the distance, the value shown at its tip, as for flat faces.
- Neighbours:
  - **Step** — only the wall moves; where it meets a fillet or chamfer a flat ledge remains; a flat face square to the
    wall's direction merges with the slab (a boss's top grows, no ledge).
  - **Inventor** — the flat faces across the wall's top and bottom edges stay attached (extend / trim); a fillet or
    chamfer there: refused with ROUND_MSG ("A neighbouring face is round: Inventor mode can't follow it yet — try
    Step or Together").
  - **Together** — the wall carries the fillets / chamfers on its top and bottom edges with it; the faces beyond them
    extend or trim.
- The result is an ordinary Move Face step: editable, suppressible, one undo step, kept across save and reopen.

## Geometry (`incad.core.move_face`)
Terms: W the picked wall (all its pieces); a its direction (a cylinder's axis, an extrusion's Direction); P its
section (W cut square to a at its middle height), a closed wire; h0..h1 its extent along a.
1. **Which faces**: a face is a straight round wall when its surface is a Cylinder or a SurfaceOfExtrusion (or a
   B-spline square to a direction everywhere, as `_along` already tests). The pieces of W: the faces of the same
   surface (same axis and radius; same extrusion direction and section curve) joined to the picked one by a shared
   edge, collected transitively. P not closed → refused, "Pick a whole round wall (a ring); a part of one comes later".
2. **Offset**: P' = P offset by d in its plane (a circle: radius r ± d; else OCC's exact 2D offset,
   `Wire.makeOffset2D`, arcs at corners). Outward = away from the material (the faces' normals). An inward offset
   that collapses or folds the outline: TOO_LARGE_MSG.
3. **Ring**: R = the region between P and P' (outward: Face(P') minus Face(P); inward: the other way round).
4. **Slab per mode**, R extruded along a:
   - Step: over h0..h1 exactly.
   - Inventor: over h0..h1, then trimmed / extended to the planes of the flat faces across W's top and bottom edges
     (slanted ends); a non-flat face there → ROUND_MSG.
   - Together: M = W + the faces chained to W's top / bottom edges that do not run along a (fillets, chamfers);
     m0..m1 its extent along a. Q = the part between m0 and m1 (common with a thick slab); Q' = Q offset by d in 3D
     (OCC, `makeOffsetShape`); Z = the ring prism, m0..m1, between P' and P moved inward by the blends' depth — the largest distance,
     seen along a, from P to a point of the blends, plus 0.1 mm.
     Plus: fuse Q' ∩ Z; minus: cut (Q ∩ Z) − Q'. Other walls in m0..m1 (an inner hole) lie outside Z and stay. The
     faces beyond M must be flat or run along a, else WALLS_MSG.
5. **Fuse or cut** as flat Move Face does: plus fuses, minus cuts (the slab must lie inside the material, else
   TOO_LARGE_MSG), then `removeSplitter`, a valid solid with the same number of solids, else TOO_LARGE_MSG; an
   OCCError from any step → TOO_LARGE_MSG (never a raw OCC error).

## Storage and recompute (`incad.features.move_face`)
- The wall is stored by geometry in the feature's Signatures (no face names, as flat faces): its kind, direction a, a
  point on its axis / its section outline sampled in 3D, h0..h1. On every recompute the wall is found again (same
  kind, direction parallel, the stored outline lying on the face), and all its pieces are collected; not found →
  GONE_MSG.
- Mode, Extent (always distance for round walls), Distance and its parameter as today; save / reopen, Suppress, undo
  unchanged.

## Refusals (messages in the dialog)
- Flat faces and round walls together — "Pick flat faces or round walls, not both".
- A cone, sphere, torus or free-form face — "Pick a flat face or a straight round wall".
- An open wall — "Pick a whole round wall (a ring); a part of one comes later".
- An inward move the outline cannot take, any OCC failure — TOO_LARGE_MSG.
- Inventor next to a fillet / chamfer — ROUND_MSG.
- Together with faces beyond the blends that neither are flat nor run along a — WALLS_MSG.

## Tests
- Headless geometry (`tests/headless/test_move_face_geom.py`), exact values:
  - a cylinder boss (r 5, h 10) on a block: ±1 in Step / Inventor / Together — volume π((r±1)² − r²)·h added /
    removed, the boss's radius r ± 1, valid;
  - a hole (r 5) through a block: +1 = a smaller hole (r 4), −1 = a bigger one (r 6);
  - an ellipse pad (20 × 10, h 10): Step and Inventor ±1 — volume change = (area of Face(P') − area of Face(P))·h;
  - an ellipse pad with a fillet on top and a chamfer at the bottom (the user's kind of part): Together +1 / −1 —
    valid, every sampled point of the new wall at distance 1 from the old outline; Inventor → ROUND_MSG; Step →
    ledges (valid);
  - the refusals above; the wall found again after an earlier feature made the part taller.
- Headless feature (`tests/headless/test_move_face.py`): create / read / update on a round wall, To unavailable,
  save and reopen, Suppress.
- The user's body (a copy of the file they send): its band ± a distance in all three modes — valid, the band at
  exactly d.
- GUI (`tests/gui/test_move_face.py`): a click on the band picks the whole ring, the preview shows, the arrow points
  out of the wall and its drag changes the distance, "To" is greyed out.

## Out of scope (later phases)
Open walls (a round end between flat faces, tangent neighbours moving with it), cones / spheres / tori / free-form
faces, To for round walls, Inventor with round neighbours (for flat and round faces alike), moving a round wall
sideways (a hole to a new place).
