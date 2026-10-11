# InCad — Move Solid, Boolean "Keep tool", clearance labels (design)

Agreed with the user on 2026-10-11. Context: inside a part (not an assembly), a new Extrude that touches the part
joins it; one that does not touch becomes its own Solid (Solid2…), and Extrude's New Solid makes one on purpose.
Boolean combines solids, but there was no way to put a solid into position, and the tool was always kept hidden.

## 1. Move Solid

**Goal:** put a solid where a Boolean needs it — precisely, and changeable later.

- **Command:** 3D Model ▸ Modify ▸ **Move Solid** (`feature.move_solid`), also in the face right-click list. Pick a face
  of the solid to move, or its row (a used-up Boolean tool's row under its Boolean too). Preselected: that solid.
- **One dialog, live preview; the sections apply in this order:**
  1. **Snap** (optional, one of): **None**, **Point to point** (a point on the solid → a target point: vertex,
     edge midpoint, circle/arc centre), **Align faces** (a flat face of the solid → a flat target face, faces end up
     coplanar and facing each other; **Flip**; **Gap** distance).
  2. **Offset X / Y / Z** (lengths), added after the snap.
  3. **Rotate X / Y / Z** (angles), about **Solid centre** / **Origin** / **Picked point**.
- **Result:** a **Move** step at the end of that solid's history (a `PartDesign::FeaturePython` with the
  `InCadMove` store): the solid's own sketches and features stay where they are; only its result is moved (probed
  2026-10-11: exact rigid copy `transformShape(m, True)` — true cylinders/planes, exact volumes, rollback by End of
  Part, saved and reopened). Double-click edits it; delete puts the solid back; several Moves may follow each other.
- **Values are model parameters** (offsets, angles, gap), so formulas work as for any feature value.
- **Snaps are applied once:** the snapped placement is stored as numbers. If the target later moves, the solid does
  not follow (as Inventor's Move Bodies). The picks are stored only so the dialog can show them on edit.
- **Any solid can be moved**, the main one too (then the whole part moves). A pick that is not on a solid is refused
  with "Pick a face of the solid to move".
- **Phase 2 (separate plan, right after):** drag arrows and rotation rings in the 3D view that fill the Offset and
  Rotate fields.
- **Note for users:** a Move needs InCad to recompute (like InCad's other custom pieces); without InCad the file
  opens with the last result.

## 2. Boolean "Keep tool"

- **Checkbox "Keep tool"**, **off** when the dialog opens.
- **Off — used up:** the tool solid is hidden, leaves the Solid Bodies list and appears in the model tree **under the
  Boolean row**; expanding it shows the tool's features and Moves, double-click edits them and the Boolean follows. It
  is not a separate solid for selection, export or printing.
- **On — kept:** the tool stays a visible, separate solid in the list (print the pin and the box), still live.
- **Clearance on Tool / Split** (Cut): the "<Tool> fit" copy is always kept visible (it is what is printed); Keep tool
  decides only about the original tool.
- **Edit:** the checkbox can be changed later. **Delete the Boolean:** the tool comes back as a normal visible solid.
- **Old files:** Booleans without the setting behave as Keep tool off (they already hid their tools).
- **Join with Keep tool on** is allowed (the part plus a separate copy of the tool).

## 3. Clearance labels

Meaning unchanged, labels say how it is measured:
- Boolean: **"Clearance (per side)"** — each face of the cavity moves by it (Ø6 pin, 0.2 → Ø6.4 hole).
- Thread and Hole ▸ Tapped: **"Print clearance (on diameter)"** — total over the diameter (0.2 → 0.1 per side).

## 4. Code

- `incad/features/move.py`: the Move kind (fields, `create/read/update`, the FeaturePython proxy `MoveFeature` with
  `execute`: base shape → `transformShape(placement, True)`), snap maths in pure helpers (point→point, face→face).
- `incad/features/combine.py`: `keep_tool` field and store key; visibility and the Solid Bodies listing follow it.
- `incad/core/tree.py`: a used-up tool's Body appears as children of its Boolean row; Solid Bodies lists only kept
  solids.
- `incad/actions.py`, `ribbon_layout.py`, `marking_layout.py`, `tools/make_icons.py`: `feature.move_solid` + icon.
- Field labels in `thread.py` / `hole.py` / `combine.py`.

## 5. Testing

- Headless: Move offsets/rotations (exact volumes after a Cut), point-to-point and align-faces maths (pure),
  rollback by End of Part, delete restores, save/reopen, parameters drive it, several Moves; Keep tool on/off/edit,
  delete restores the tool, old-file default, fit copy always visible, tree children under the Boolean.
- GUI: Move Solid from the ribbon on a face, point-to-point pick in the view, OK = one undo step; Boolean with Keep
  tool off then on (visibility and the tree); the labels.

## 6. Out of scope

3D drag handles (phase 2), associative snaps (following a moved target), moving several solids at once, Split /
Imprint operations.
